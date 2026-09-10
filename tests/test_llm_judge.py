import http.server
import json
import socketserver
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

from convergence_factory.core.errors import ERROR_TRACKER
from convergence_factory.core.store import Store
from convergence_factory.probes.semantic.judge import (
    HeuristicJudge,
    JudgeResult,
    RestJudge,
    _build_auth_headers,
    _extract_retry_after,
    _parse_json_object,
    judge_candidates,
    test_llm_connection as run_test_llm_connection,
)
from convergence_factory.schema import CapabilitySummary, Module, Project


class TestLLMJudge(unittest.TestCase):
    def test_parse_json_object_raw_and_fenced(self):
        # 1. Plain raw JSON
        raw = '{"confirmed": true, "confidence": 0.95, "reason": "Exact match", "play": "STANDARDIZE"}'
        parsed = _parse_json_object(raw)
        self.assertTrue(parsed.get("confirmed"))
        self.assertEqual(parsed.get("confidence"), 0.95)
        self.assertEqual(parsed.get("play"), "STANDARDIZE")

        # 2. Markdown code fences
        fenced = '```json\n{"confirmed": false, "confidence": 0.3, "reason": "Different", "play": "LEAVE"}\n```'
        parsed = _parse_json_object(fenced)
        self.assertFalse(parsed.get("confirmed"))
        self.assertEqual(parsed.get("play"), "LEAVE")

        # 3. Preamble and postscript
        messy = 'Here is the decision:\n{"confirmed": true, "confidence": 0.88, "reason": "Both do JWT", "play": "RETIRE"}\nThanks!'
        parsed = _parse_json_object(messy)
        self.assertTrue(parsed.get("confirmed"))
        self.assertEqual(parsed.get("play"), "RETIRE")

        # 4. Empty or invalid text
        self.assertEqual(_parse_json_object(""), {})
        self.assertEqual(_parse_json_object("random text without braces"), {})

    def test_rest_judge_with_mock_server_ollama_format(self):
        """Verify RestJudge handles Ollama format responses correctly."""
        class MockOllamaHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                content_len = int(self.headers.get("Content-Length", 0))
                _ = self.rfile.read(content_len)
                response_body = json.dumps({
                    "response": json.dumps({
                        "confirmed": True,
                        "confidence": 0.92,
                        "reason": "Both modules handle JWT tokens",
                        "play": "STANDARDIZE"
                    })
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, format, *args):
                pass

        with socketserver.TCPServer(("127.0.0.1", 0), MockOllamaHandler) as server:
            port = server.server_address[1]
            t = threading.Thread(target=server.serve_forever)
            t.daemon = True
            t.start()
            try:
                judge = RestJudge(
                    endpoint=f"http://127.0.0.1:{port}/api/generate",
                    model="test-model",
                    timeout=5.0
                )
                cand = {"a": "auth-jwt", "b": "pyjwt", "similarity": 0.88}
                res = judge.evaluate(cand, "JWT validation", "JWT signing", "team-a", "team-b")
                self.assertTrue(res.confirmed)
                self.assertEqual(res.confidence, 0.92)
                self.assertEqual(res.play, "STANDARDIZE")
                self.assertIn("Both modules handle JWT", res.reason)
            finally:
                server.shutdown()

    def test_rest_judge_with_mock_server_chat_completions_format(self):
        """Verify RestJudge handles OpenAI / Azure / Groq /chat/completions format."""
        class MockChatHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                content_len = int(self.headers.get("Content-Length", 0))
                _ = self.rfile.read(content_len)
                response_body = json.dumps({
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "confirmed": False,
                                "confidence": 0.25,
                                "reason": "Distinct business services",
                                "play": "LEAVE"
                            })
                        }
                    }]
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, format, *args):
                pass

        with socketserver.TCPServer(("127.0.0.1", 0), MockChatHandler) as server:
            port = server.server_address[1]
            t = threading.Thread(target=server.serve_forever)
            t.daemon = True
            t.start()
            try:
                judge = RestJudge(
                    endpoint=f"http://127.0.0.1:{port}/chat/completions",
                    model="gpt-4o-mini",
                    api_key="test-key",
                    timeout=5.0
                )
                cand = {"a": "orders", "b": "analytics", "similarity": 0.40}
                res = judge.evaluate(cand, "Order processing", "Data aggregations", "team-a", "team-b")
                self.assertFalse(res.confirmed)
                self.assertEqual(res.confidence, 0.25)
                self.assertEqual(res.play, "LEAVE")
            finally:
                server.shutdown()

    def test_rest_judge_fallback_on_unreachable_endpoint(self):
        """Verify that when endpoint is unreachable, it logs error and cleanly falls back to HeuristicJudge with reason annotated."""
        judge = RestJudge(
            endpoint="http://127.0.0.1:59999/api/generate",
            model="missing-model",
            timeout=1.0,
            fallback=HeuristicJudge()
        )
        cand = {"a": "orders-svc", "b": "checkout-svc", "similarity": 0.85}
        sum_a = "Processes customer orders and transactions"
        sum_b = "Handles customer order checkout"
        res = judge.evaluate(cand, sum_a, sum_b, "team-a", "team-b")

        # Heuristic judge confirms because of shared terms (order, customer)
        self.assertTrue(res.confirmed)
        self.assertIn("[Fallback:", res.reason)
        self.assertIsNotNone(judge.last_error)

    def test_test_llm_connection_diagnostic(self):
        """Verify test_llm_connection reports errors clearly for unreachable endpoints."""
        res = run_test_llm_connection(endpoint="http://127.0.0.1:59999/api/generate", model="any-model", timeout=1.0)
        self.assertFalse(res["ok"])
        self.assertIn("Connection failed", res["error"])
        self.assertIn("suggestion", res)

    def test_judge_candidates_interactive_progress(self):
        """Verify judge_candidates outputs live progress indicators."""
        import io

        store = Store()
        p1 = Project(id="p1", repo_url="/p1", owner_team="team-alpha")
        p2 = Project(id="p2", repo_url="/p2", owner_team="team-beta")
        store.add_project(p1)
        store.add_project(p2)
        m1 = Module(id="p1:srv", project_id="p1", path="/p1", name="srv-a", kind="service", lang="python")
        m2 = Module(id="p2:srv", project_id="p2", path="/p2", name="srv-b", kind="service", lang="python")
        store.add_module(m1)
        store.add_module(m2)
        store.add_summaries([
            CapabilitySummary(module_id="p1:srv", summary="Order payment checkout", tier="MED"),
            CapabilitySummary(module_id="p2:srv", summary="Customer payment checkout", tier="MED"),
        ])

        candidates = [{"a": "p1:srv", "b": "p2:srv", "similarity": 0.88, "tier": "MED"}]
        captured = io.StringIO()

        with patch("sys.stdout", captured):
            results = judge_candidates(store, candidates, judge=HeuristicJudge(), interactive=True)

        output = captured.getvalue()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["confirmed"])
        self.assertIn("Calling judge for 'p1:srv' <-> 'p2:srv'", output)
        self.assertIn("[CONFIRMED]", output)
        store.close()

    def test_auth_headers_normalization_and_bearer_handling(self):
        """Verify tokens with or without Bearer prefix are normalized correctly."""
        # 1. Raw token: adds Bearer to Authorization, sets api-key and x-api-key
        h1 = _build_auth_headers("my-internal-token-123")
        self.assertEqual(h1["Authorization"], "Bearer my-internal-token-123")
        self.assertEqual(h1["api-key"], "my-internal-token-123")
        self.assertEqual(h1["x-api-key"], "my-internal-token-123")

        # 2. Token with 'Bearer ' already present: does NOT produce 'Bearer Bearer'
        h2 = _build_auth_headers("Bearer my-internal-token-123")
        self.assertEqual(h2["Authorization"], "Bearer my-internal-token-123")
        self.assertEqual(h2["api-key"], "my-internal-token-123")
        self.assertEqual(h2["x-api-key"], "my-internal-token-123")

        # 3. Lowercase 'bearer '
        h3 = _build_auth_headers("bearer my-internal-token-123")
        self.assertEqual(h3["Authorization"], "bearer my-internal-token-123")
        self.assertEqual(h3["api-key"], "my-internal-token-123")
        self.assertEqual(h3["x-api-key"], "my-internal-token-123")

        # 4. None or empty
        self.assertEqual(_build_auth_headers(None), {})
        self.assertEqual(_build_auth_headers("   "), {})

    def test_extract_retry_after_headers(self):
        """Verify _extract_retry_after parses various header formats."""
        # 1. retry-after-ms (Azure / LiteLLM)
        self.assertAlmostEqual(_extract_retry_after({"retry-after-ms": "1500"}, 1.0), 1.5)

        # 2. Retry-After (seconds)
        self.assertAlmostEqual(_extract_retry_after({"Retry-After": "4.5"}, 1.0), 4.5)

        # 3. x-ratelimit-reset (seconds)
        self.assertAlmostEqual(_extract_retry_after({"x-ratelimit-reset": "8"}, 1.0), 8.0)

        # 4. Fallback to default
        self.assertAlmostEqual(_extract_retry_after({}, 2.5), 2.5)
        self.assertAlmostEqual(_extract_retry_after({"Retry-After": "invalid"}, 2.5), 2.5)

    def test_rest_judge_retries_on_http_429(self):
        """Verify RestJudge retries on HTTP 429 and succeeds when subsequent attempt returns 200."""
        call_count = 0

        class MockThrottledHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                nonlocal call_count
                call_count += 1
                content_len = int(self.headers.get("Content-Length", 0))
                _ = self.rfile.read(content_len)

                if call_count == 1:
                    # Return 429 on first call with Retry-After header
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Retry-After", "0.05")
                    self.end_headers()
                    self.wfile.write(b'{"error": "Too Many Requests"}')
                else:
                    # Return 200 on second call
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    resp_data = {
                        "response": json.dumps({
                            "confirmed": True,
                            "confidence": 0.94,
                            "reason": "Recovered after 429 backoff",
                            "play": "STANDARDIZE"
                        })
                    }
                    self.wfile.write(json.dumps(resp_data).encode("utf-8"))

            def log_message(self, format, *args):
                pass

        with socketserver.TCPServer(("127.0.0.1", 0), MockThrottledHandler) as server:
            port = server.server_address[1]
            t = threading.Thread(target=server.serve_forever)
            t.daemon = True
            t.start()
            try:
                judge = RestJudge(
                    endpoint=f"http://127.0.0.1:{port}/api/generate",
                    model="test-model",
                    max_retries=2,
                    timeout=5.0
                )
                cand = {"a": "auth-svc", "b": "security-svc", "similarity": 0.89}
                res = judge.evaluate(cand, "Auth service", "Security service", "team-a", "team-b")
                self.assertEqual(call_count, 2)
                self.assertTrue(res.confirmed)
                self.assertEqual(res.confidence, 0.94)
                self.assertNotIn("Fallback", res.reason)
                self.assertIn("Recovered after 429", res.reason)
            finally:
                server.shutdown()

    def test_rest_judge_exhausts_retries_on_persistent_429(self):
        """Verify RestJudge falls back to HeuristicJudge and records RateLimitExhausted warning when retries run out."""
        call_count = 0

        class Persistent429Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                nonlocal call_count
                call_count += 1
                content_len = int(self.headers.get("Content-Length", 0))
                _ = self.rfile.read(content_len)
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "0.01")
                self.end_headers()
                self.wfile.write(b'{"error": "Quota Exceeded"}')

            def log_message(self, format, *args):
                pass

        with socketserver.TCPServer(("127.0.0.1", 0), Persistent429Handler) as server:
            port = server.server_address[1]
            t = threading.Thread(target=server.serve_forever)
            t.daemon = True
            t.start()
            try:
                judge = RestJudge(
                    endpoint=f"http://127.0.0.1:{port}/api/generate",
                    model="test-model",
                    max_retries=2,
                    timeout=5.0
                )
                cand = {"a": "orders-svc", "b": "checkout-svc", "similarity": 0.85}
                res = judge.evaluate(cand, "Order processing", "Order checkout", "team-a", "team-b")
                # Initial attempt + 2 retries = 3 calls
                self.assertEqual(call_count, 3)
                # Fallback to heuristic judge succeeds because of shared tokens
                self.assertTrue(res.confirmed)
                self.assertIn("[Fallback: HTTP Error 429", res.reason)
                self.assertIn("429", judge.last_error or res.reason)
                rate_limit_warnings = [
                    e for e in ERROR_TRACKER.get_errors() if getattr(e, "error_type", None) == "RateLimitExhausted"
                ]
                self.assertGreaterEqual(len(rate_limit_warnings), 1)
            finally:
                server.shutdown()

    def test_judge_candidates_proactive_delay(self):
        """Verify judge_candidates respects proactive delay pacing."""
        store = Store()
        p1 = Project(id="p1", repo_url="/p1", owner_team="team-alpha")
        p2 = Project(id="p2", repo_url="/p2", owner_team="team-beta")
        store.add_project(p1)
        store.add_project(p2)
        m1 = Module(id="p1:srv", project_id="p1", path="/p1", name="srv-a", kind="service", lang="python")
        m2 = Module(id="p2:srv", project_id="p2", path="/p2", name="srv-b", kind="service", lang="python")
        store.add_module(m1)
        store.add_module(m2)
        store.add_summaries([
            CapabilitySummary(module_id="p1:srv", summary="Order payment checkout", tier="MED"),
            CapabilitySummary(module_id="p2:srv", summary="Customer payment checkout", tier="MED"),
        ])

        candidates = [
            {"a": "p1:srv", "b": "p2:srv", "similarity": 0.88, "tier": "MED"},
            {"a": "p1:srv", "b": "p2:srv", "similarity": 0.85, "tier": "MED"}
        ]
        t0 = time.time()
        results = judge_candidates(store, candidates, judge=HeuristicJudge(), interactive=False, delay=0.05)
        elapsed = time.time() - t0
        self.assertEqual(len(results), 2)
        # Should have delayed at least once between pair 1 and pair 2
        self.assertGreaterEqual(elapsed, 0.04)
        store.close()


if __name__ == "__main__":
    unittest.main()
