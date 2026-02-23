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
	$(CC) -o tests/runtime/test_channel tests/runtime/test_channel.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_channel
	@rm -f tests/runtime/test_channel
	$(CC) -o tests/runtime/test_math tests/runtime/test_math.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_math
	@rm -f tests/runtime/test_math
	$(CC) -o tests/runtime/test_path tests/runtime/test_path.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_path
	@rm -f tests/runtime/test_path
	$(CC) -o tests/runtime/test_io tests/runtime/test_io.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_io
	@rm -f tests/runtime/test_io
	$(CC) -o tests/runtime/test_sys tests/runtime/test_sys.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_sys
	@rm -f tests/runtime/test_sys
	$(CC) -o tests/runtime/test_string_ext tests/runtime/test_string_ext.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_string_ext
	@rm -f tests/runtime/test_string_ext
	$(CC) -o tests/runtime/test_buffer tests/runtime/test_buffer.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_buffer
	@rm -f tests/runtime/test_buffer
	$(CC) -o tests/runtime/test_stream_construct tests/runtime/test_stream_construct.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_stream_construct
	@rm -f tests/runtime/test_stream_construct
	$(CC) -o tests/runtime/test_stream_consume tests/runtime/test_stream_consume.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_stream_consume
	@rm -f tests/runtime/test_stream_consume

check:
	$(PYTHON) -m mypy compiler/

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
	find . -name '*.generated.c' -delete
