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
	$(CC) -o tests/runtime/test_stream_transform tests/runtime/test_stream_transform.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_stream_transform
	@rm -f tests/runtime/test_stream_transform
	$(CC) -o tests/runtime/test_sort tests/runtime/test_sort.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_sort
	@rm -f tests/runtime/test_sort
	$(CC) -o tests/runtime/test_channel_ext tests/runtime/test_channel_ext.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_channel_ext
	@rm -f tests/runtime/test_channel_ext
	$(CC) -o tests/runtime/test_file tests/runtime/test_file.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_file
	@rm -f tests/runtime/test_file
	$(CC) -o tests/runtime/test_bytes tests/runtime/test_bytes.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_bytes
	@rm -f tests/runtime/test_bytes
	$(CC) -o tests/runtime/test_random tests/runtime/test_random.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_random
	@rm -f tests/runtime/test_random
	$(CC) -o tests/runtime/test_time tests/runtime/test_time.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_time
	@rm -f tests/runtime/test_time
	$(CC) -o tests/runtime/test_testing tests/runtime/test_testing.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_testing
	@rm -f tests/runtime/test_testing
	$(CC) -o tests/runtime/test_net tests/runtime/test_net.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_net
	@rm -f tests/runtime/test_net
	$(CC) -o tests/runtime/test_json tests/runtime/test_json.c runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
	tests/runtime/test_json
	@rm -f tests/runtime/test_json

check:
	$(PYTHON) -m mypy compiler/

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
	find . -name '*.generated.c' -delete
