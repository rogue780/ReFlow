/*
 * C-level tests for IO module extensions: fl_read_file_bytes,
 * fl_write_file_bytes, fl_append_file.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: fl_read_file_bytes on a file that exists
 * ======================================================================== */

static void test_read_file_bytes_exists(void) {
    TEST(read_file_bytes_exists);

    /* Create a temp file with known bytes */
    FL_String* suffix = fl_string_from_cstr(".bin");
    FL_String* initial = fl_string_from_cstr("ABCDE");
    FL_String* path = fl_tmpfile_create(suffix, initial);

    FL_Option_ptr result = fl_read_file_bytes(path);
    assert(result.tag == 1);

    FL_Array* arr = (FL_Array*)result.value;
    assert(arr->len == 5);
    assert(arr->element_size == sizeof(fl_byte));

    fl_byte* data = (fl_byte*)arr->data;
    assert(data[0] == 'A');
    assert(data[1] == 'B');
    assert(data[2] == 'C');
    assert(data[3] == 'D');
    assert(data[4] == 'E');

    fl_tmpfile_remove(path);
    fl_array_release(arr);
    fl_string_release(path);
    fl_string_release(suffix);
    fl_string_release(initial);
    PASS();
}

/* ========================================================================
 * Test 2: fl_read_file_bytes on nonexistent file returns none
 * ======================================================================== */

static void test_read_file_bytes_nonexistent(void) {
    TEST(read_file_bytes_nonexistent);

    FL_String* path = fl_string_from_cstr("/tmp/flow_test_nonexistent_9999.bin");
    FL_Option_ptr result = fl_read_file_bytes(path);
    assert(result.tag == 0);

    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 3: fl_write_file_bytes + fl_read_file_bytes round-trip
 * ======================================================================== */

static void test_write_read_bytes_roundtrip(void) {
    TEST(write_read_bytes_roundtrip);

    FL_String* path = fl_string_from_cstr("/tmp/flow_test_io_roundtrip.bin");

    /* Create an array of bytes: [0x00, 0x01, 0xFF, 0x42, 0x80] */
    fl_byte bytes[] = {0x00, 0x01, 0xFF, 0x42, 0x80};
    FL_Array* arr = fl_array_new(5, sizeof(fl_byte), bytes);

    fl_bool ok = fl_write_file_bytes(path, arr);
    assert(ok == fl_true);

    FL_Option_ptr result = fl_read_file_bytes(path);
    assert(result.tag == 1);

    FL_Array* read_arr = (FL_Array*)result.value;
    assert(read_arr->len == 5);
    fl_byte* read_data = (fl_byte*)read_arr->data;
    assert(read_data[0] == 0x00);
    assert(read_data[1] == 0x01);
    assert(read_data[2] == 0xFF);
    assert(read_data[3] == 0x42);
    assert(read_data[4] == 0x80);

    /* Clean up */
    unlink(path->data);
    fl_array_release(arr);
    fl_array_release(read_arr);
    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 4: fl_append_file — write initial, append, read back combined
 * ======================================================================== */

static void test_append_file(void) {
    TEST(append_file);

    FL_String* suffix = fl_string_from_cstr(".txt");
    FL_String* initial = fl_string_from_cstr("Hello");
    FL_String* path = fl_tmpfile_create(suffix, initial);

    FL_String* appended = fl_string_from_cstr(" World");
    fl_bool ok = fl_append_file(path, appended);
    assert(ok == fl_true);

    FL_Option_ptr result = fl_read_file(path);
    assert(result.tag == 1);

    FL_String* contents = (FL_String*)result.value;
    FL_String* expected = fl_string_from_cstr("Hello World");
    assert(fl_string_eq(contents, expected) == fl_true);

    fl_tmpfile_remove(path);
    fl_string_release(path);
    fl_string_release(suffix);
    fl_string_release(initial);
    fl_string_release(appended);
    fl_string_release(contents);
    fl_string_release(expected);
    PASS();
}

/* ========================================================================
 * Test 5: fl_append_file on new file (creates it)
 * ======================================================================== */

static void test_append_file_creates_new(void) {
    TEST(append_file_creates_new);

    FL_String* path = fl_string_from_cstr("/tmp/flow_test_io_append_new.txt");

    /* Make sure file doesn't exist */
    unlink(path->data);

    FL_String* contents = fl_string_from_cstr("Created by append");
    fl_bool ok = fl_append_file(path, contents);
    assert(ok == fl_true);

    FL_Option_ptr result = fl_read_file(path);
    assert(result.tag == 1);

    FL_String* read_back = (FL_String*)result.value;
    assert(fl_string_eq(read_back, contents) == fl_true);

    /* Clean up */
    unlink(path->data);
    fl_string_release(path);
    fl_string_release(contents);
    fl_string_release(read_back);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("IO module extension tests\n");
    printf("========================================\n");

    test_read_file_bytes_exists();
    test_read_file_bytes_nonexistent();
    test_write_read_bytes_roundtrip();
    test_append_file();
    test_append_file_creates_new();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
