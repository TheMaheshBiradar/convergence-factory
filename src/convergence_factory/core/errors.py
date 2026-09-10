"""Framework error tracking, logging, and feedback capture.

Captures internal faults, probe warnings, parsing exceptions, and LLM timeouts
into a structured error log (`error.txt`) so errors can be inspected and fed back
into the system for self-healing and diagnostics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from typing import List, Optional

from convergence_factory.logger import LOGGER


@dataclass
class FrameworkError:
    timestamp: str
    phase: str            # e.g., "census", "probe:integration", "probe:semantic:judge", "remediation"
    source: str           # repository path, file path, module ID, or endpoint URL
    error_type: str       # e.g., "ParseError", "TimeoutError", "ValidationError", "PluginException"
    message: str          # human-readable explanation
    details: str = ""     # traceback or raw server response snippet
    remediation: str = "" # actionable hint to fix or self-heal
    severity: str = "ERROR" # "ERROR" or "WARNING"


class ErrorTracker:
    """Centralized collector for all runtime warnings and errors across the factory."""

    def __init__(self):
        self._errors: List[FrameworkError] = []

    def record(
        self,
        phase: str,
        source: str,
        error_type: str,
        message: str,
        details: str = "",
        remediation: str = "",
        severity: str = "ERROR"
    ) -> FrameworkError:
        err = FrameworkError(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            phase=phase,
            source=source,
            error_type=error_type,
            message=message,
            details=details,
            remediation=remediation,
            severity=severity.upper()
        )
        self._errors.append(err)
        if err.severity == "WARNING":
            LOGGER.warning("[%s] %s (%s): %s", phase, error_type, source, message)
        else:
            LOGGER.error("[%s] %s (%s): %s", phase, error_type, source, message)
        return err

    def record_warning(
        self,
        phase: str,
        source: str,
        warning_type: str,
        message: str,
        details: str = "",
        remediation: str = ""
    ) -> FrameworkError:
        return self.record(
            phase=phase,
            source=source,
            error_type=warning_type,
            message=message,
            details=details,
            remediation=remediation,
            severity="WARNING"
        )

    def get_errors(self) -> List[FrameworkError]:
        return list(self._errors)

    def clear(self) -> None:
        self._errors.clear()

    def has_errors(self) -> bool:
        return any(e.severity == "ERROR" for e in self._errors)

    def count(self) -> int:
        return len(self._errors)

    def format_log(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            "=" * 80,
            "CONVERGENCE FACTORY - FRAMEWORK ERROR & FEEDBACK LOG",
            f"Generated: {now}",
        ]

        if not self._errors:
            lines.extend([
                "Status: HEALTHY (0 framework errors or warnings recorded)",
                "=" * 80,
                "All ingestion connectors, AST probes, semantic recall pipelines,",
                "pairwise judges, and remediation generators executed cleanly.",
                "",
                "No faults recorded for feedback loop."
            ])
            return "\n".join(lines) + "\n"

        err_count = sum(1 for e in self._errors if e.severity == "ERROR")
        warn_count = sum(1 for e in self._errors if e.severity == "WARNING")
        lines.extend([
            f"Total Issues Recorded: {len(self._errors)} ({err_count} Errors, {warn_count} Warnings)",
            "=" * 80,
            ""
        ])

        for idx, err in enumerate(self._errors, 1):
            lines.append(f"[{err.severity} #{idx}] {err.timestamp}")
            lines.append(f"Phase       : {err.phase}")
            lines.append(f"Source      : {err.source}")
            lines.append(f"Type        : {err.error_type}")
            lines.append(f"Message     : {err.message}")
            if err.remediation:
                lines.append(f"Remediation : {err.remediation}")
            if err.details:
                lines.append("Details     :")
                for d_line in err.details.strip().splitlines():
                    lines.append(f"  {d_line}")
            lines.append("-" * 80)

        lines.append("\n[END OF ERROR LOG - Use above feedback to adjust probes, models, or configurations]\n")
        return "\n".join(lines)

    def write_to_file(self, target_path: str) -> str:
        """Writes error.txt to target path (or directory/error.txt)."""
        if os.path.isdir(target_path) or target_path.endswith(os.sep) or not os.path.splitext(target_path)[1]:
            os.makedirs(target_path, exist_ok=True)
            target_file = os.path.join(target_path, "error.txt")
        else:
            target_file = target_path
            parent = os.path.dirname(os.path.abspath(target_file))
            if parent:
                os.makedirs(parent, exist_ok=True)

        content = self.format_log()
        with open(target_file, "w", encoding="utf-8") as fh:
            fh.write(content)

        # Also sync to site/ subdirectory if present
        parent_dir = os.path.dirname(os.path.abspath(target_file))
        site_dir = os.path.join(parent_dir, "site")
        if os.path.isdir(site_dir) and site_dir != parent_dir:
            try:
                with open(os.path.join(site_dir, "error.txt"), "w", encoding="utf-8") as fh:
                    fh.write(content)
            except Exception:
                pass

        return target_file


# Global singleton instance for framework-wide tracking
ERROR_TRACKER = ErrorTracker()
