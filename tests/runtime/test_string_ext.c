/*
 * C-level tests for rf_string_to_bytes and rf_string_from_bytes.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: rf_string_to_bytes on "hello"
 * ======================================================================== */

static void test_to_bytes_hello(void) {
    TEST(to_bytes_hello);

    RF_String* s = rf_string_from_cstr("hello");
    RF_Array* arr = rf_string_to_bytes(s);

    assert(rf_array_len(arr) == 5);

    rf_byte expected[] = {'h', 'e', 'l', 'l', 'o'};
    for (rf_int64 i = 0; i < 5; i++) {
        rf_byte* bp = (rf_byte*)rf_array_get_ptr(arr, i);
        assert(*bp == expected[i]);
    }

    rf_array_release(arr);
    rf_string_release(s);
    PASS();
}

/* ========================================================================
 * Test 2: rf_string_to_bytes on empty string
 * ======================================================================== */

static void test_to_bytes_empty(void) {
    TEST(to_bytes_empty);

    RF_String* s = rf_string_from_cstr("");
    RF_Array* arr = rf_string_to_bytes(s);

    assert(rf_array_len(arr) == 0);

    rf_array_release(arr);
    rf_string_release(s);
    PASS();
}

/* ========================================================================
 * Test 3: Round-trip: string -> bytes -> string
 * ======================================================================== */

static void test_round_trip(void) {
    TEST(round_trip_to_bytes_from_bytes);

    RF_String* original = rf_string_from_cstr("Hello, ReFlow!");
    RF_Array* bytes = rf_string_to_bytes(original);
    RF_String* restored = rf_string_from_bytes(bytes);

    assert(rf_string_eq(original, restored));

    rf_string_release(restored);
    rf_array_release(bytes);
    rf_string_release(original);
    PASS();
}

/* ========================================================================
 * Test 4: rf_string_from_bytes on known byte values
 * ======================================================================== */

static void test_from_bytes_known(void) {
    TEST(from_bytes_known_values);

    rf_byte data[] = {'R', 'e', 'F', 'l', 'o', 'w'};
    RF_Array* arr = rf_array_new(6, sizeof(rf_byte), data);
    RF_String* s = rf_string_from_bytes(arr);

    RF_String* expected = rf_string_from_cstr("ReFlow");
    assert(rf_string_eq(s, expected));

    rf_string_release(expected);
    rf_string_release(s);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 5: to_bytes produces an independent copy
 * ======================================================================== */

static void test_to_bytes_independent_copy(void) {
    TEST(to_bytes_independent_copy);

    RF_String* s = rf_string_from_cstr("test");
    RF_Array* arr = rf_string_to_bytes(s);

    /* Verify the data pointer is different (independent copy) */
    assert(arr->data != (void*)s->data);

    /* Verify the content is the same */
    assert(memcmp(arr->data, s->data, 4) == 0);

    rf_array_release(arr);
    rf_string_release(s);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("rf_string_to_bytes / rf_string_from_bytes tests\n");
    printf("================================================\n");

    test_to_bytes_hello();
    test_to_bytes_empty();
    test_round_trip();
    test_from_bytes_known();
    test_to_bytes_independent_copy();

    printf("================================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
