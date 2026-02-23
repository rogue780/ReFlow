/*
 * C-level tests for IO module extensions: rf_read_file_bytes,
 * rf_write_file_bytes, rf_append_file.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
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
 * Test 1: rf_read_file_bytes on a file that exists
 * ======================================================================== */

static void test_read_file_bytes_exists(void) {
    TEST(read_file_bytes_exists);

    /* Create a temp file with known bytes */
    RF_String* suffix = rf_string_from_cstr(".bin");
    RF_String* initial = rf_string_from_cstr("ABCDE");
    RF_String* path = rf_tmpfile_create(suffix, initial);

    RF_Option_ptr result = rf_read_file_bytes(path);
    assert(result.tag == 1);

    RF_Array* arr = (RF_Array*)result.value;
    assert(arr->len == 5);
    assert(arr->element_size == sizeof(rf_byte));

    rf_byte* data = (rf_byte*)arr->data;
    assert(data[0] == 'A');
    assert(data[1] == 'B');
    assert(data[2] == 'C');
    assert(data[3] == 'D');
    assert(data[4] == 'E');

    rf_tmpfile_remove(path);
    rf_array_release(arr);
    rf_string_release(path);
    rf_string_release(suffix);
    rf_string_release(initial);
    PASS();
}

/* ========================================================================
 * Test 2: rf_read_file_bytes on nonexistent file returns none
 * ======================================================================== */

static void test_read_file_bytes_nonexistent(void) {
    TEST(read_file_bytes_nonexistent);

    RF_String* path = rf_string_from_cstr("/tmp/reflow_test_nonexistent_9999.bin");
    RF_Option_ptr result = rf_read_file_bytes(path);
    assert(result.tag == 0);

    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 3: rf_write_file_bytes + rf_read_file_bytes round-trip
 * ======================================================================== */

static void test_write_read_bytes_roundtrip(void) {
    TEST(write_read_bytes_roundtrip);

    RF_String* path = rf_string_from_cstr("/tmp/reflow_test_io_roundtrip.bin");

    /* Create an array of bytes: [0x00, 0x01, 0xFF, 0x42, 0x80] */
    rf_byte bytes[] = {0x00, 0x01, 0xFF, 0x42, 0x80};
    RF_Array* arr = rf_array_new(5, sizeof(rf_byte), bytes);

    rf_bool ok = rf_write_file_bytes(path, arr);
    assert(ok == rf_true);

    RF_Option_ptr result = rf_read_file_bytes(path);
    assert(result.tag == 1);

    RF_Array* read_arr = (RF_Array*)result.value;
    assert(read_arr->len == 5);
    rf_byte* read_data = (rf_byte*)read_arr->data;
    assert(read_data[0] == 0x00);
    assert(read_data[1] == 0x01);
    assert(read_data[2] == 0xFF);
    assert(read_data[3] == 0x42);
    assert(read_data[4] == 0x80);

    /* Clean up */
    unlink(path->data);
    rf_array_release(arr);
    rf_array_release(read_arr);
    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 4: rf_append_file — write initial, append, read back combined
 * ======================================================================== */

static void test_append_file(void) {
    TEST(append_file);

    RF_String* suffix = rf_string_from_cstr(".txt");
    RF_String* initial = rf_string_from_cstr("Hello");
    RF_String* path = rf_tmpfile_create(suffix, initial);

    RF_String* appended = rf_string_from_cstr(" World");
    rf_bool ok = rf_append_file(path, appended);
    assert(ok == rf_true);

    RF_Option_ptr result = rf_read_file(path);
    assert(result.tag == 1);

    RF_String* contents = (RF_String*)result.value;
    RF_String* expected = rf_string_from_cstr("Hello World");
    assert(rf_string_eq(contents, expected) == rf_true);

    rf_tmpfile_remove(path);
    rf_string_release(path);
    rf_string_release(suffix);
    rf_string_release(initial);
    rf_string_release(appended);
    rf_string_release(contents);
    rf_string_release(expected);
    PASS();
}

/* ========================================================================
 * Test 5: rf_append_file on new file (creates it)
 * ======================================================================== */

static void test_append_file_creates_new(void) {
    TEST(append_file_creates_new);

    RF_String* path = rf_string_from_cstr("/tmp/reflow_test_io_append_new.txt");

    /* Make sure file doesn't exist */
    unlink(path->data);

    RF_String* contents = rf_string_from_cstr("Created by append");
    rf_bool ok = rf_append_file(path, contents);
    assert(ok == rf_true);

    RF_Option_ptr result = rf_read_file(path);
    assert(result.tag == 1);

    RF_String* read_back = (RF_String*)result.value;
    assert(rf_string_eq(read_back, contents) == rf_true);

    /* Clean up */
    unlink(path->data);
    rf_string_release(path);
    rf_string_release(contents);
    rf_string_release(read_back);
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
