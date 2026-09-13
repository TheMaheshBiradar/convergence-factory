# Convergence Factory — common tasks. Run `make help`.
PY      ?= python3
ROOT    ?= fixtures/repos
OUT     ?= .factory
IMAGE   ?= convergence-factory:latest
export PYTHONPATH := src

.PHONY: help install install-dev test eval lint run matrix docker-build docker-run clean

help:
	@echo "install       install the package + pinned probe backends"
	@echo "install-dev   install + dev tools (pytest, ruff)"
	@echo "test          run the test suite"
	@echo "eval          run the calibration eval (precision/recall/resolution)"
	@echo "lint          run pyflakes over src"
	@echo "run           legacy redundancy-map pipeline (ROOT=, OUT=)"
	@echo "matrix        capability-matrix pipeline -> dashboard/matrix (ROOT=, OUT=)"
	@echo "docker-build  build the delivery image ($(IMAGE))"
	@echo "docker-run    run the image on ROOT -> OUT"

install:
	$(PY) -m pip install -r constraints.txt
	$(PY) -m pip install .

install-dev:
	$(PY) -m pip install -r constraints.txt -r requirements-dev.txt
	$(PY) -m pip install -e .

test:
	$(PY) -m pytest

eval:
	$(PY) -m convergence_factory eval

lint:
	$(PY) -m pyflakes src || true

run:
	$(PY) -m convergence_factory run $(ROOT) --out $(OUT)

matrix:
	$(PY) -m convergence_factory.pipeline $(ROOT) --out $(OUT)

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -v "$(abspath $(ROOT)):/repos" -v "$(abspath $(OUT)):/out" $(IMAGE) /repos --out /out

clean:
	rm -rf .factory* .pytest_cache **/__pycache__ *.egg-info
