PYTHON ?= python3

.PHONY: test test-unit test-golden test-e2e test-negative check clean

test:
	$(PYTHON) -m pytest tests/ -v

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v

test-golden:
	$(PYTHON) tests/run_tests.py --golden

test-e2e:
	$(PYTHON) tests/run_tests.py --e2e

test-negative:
	$(PYTHON) tests/run_tests.py --negative

check:
	$(PYTHON) -m mypy compiler/

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
	find . -name '*.generated.c' -delete
