PYTHON ?= python3

.PHONY: test test-unit test-golden test-e2e test-negative test-runtime check clean

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

test-runtime:
	$(CC) -o tests/runtime/test_channel tests/runtime/test_channel.c runtime/reflow_runtime.c -lpthread -I runtime -std=c11
	tests/runtime/test_channel
	@rm -f tests/runtime/test_channel

check:
	$(PYTHON) -m mypy compiler/

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
	find . -name '*.generated.c' -delete
