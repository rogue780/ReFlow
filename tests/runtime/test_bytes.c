/*
 * C-level tests for rf_bytes_* functions (stdlib/bytes).
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
 * Helper: create a byte array from a C array
 * ======================================================================== */

static RF_Array* make_bytes(rf_byte* data, rf_int64 len) {
    return rf_array_new(len, 1, data);
}

/* ========================================================================
 * Test 1: slice_middle — slice bytes [0,1,2,3,4] from 1 to 4 -> [1,2,3]
 * ======================================================================== */

static void test_slice_middle(void) {
    TEST(slice_middle);

    rf_byte data[] = {0, 1, 2, 3, 4};
    RF_Array* arr = make_bytes(data, 5);
    RF_Array* result = rf_bytes_slice(arr, 1, 4);

    assert(rf_array_len(result) == 3);
    rf_byte* out = (rf_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);
    assert(out[2] == 3);

    rf_array_release(result);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 2: slice_full — slice from 0 to len -> same as original
 * ======================================================================== */

static void test_slice_full(void) {
    TEST(slice_full);

    rf_byte data[] = {10, 20, 30};
    RF_Array* arr = make_bytes(data, 3);
    RF_Array* result = rf_bytes_slice(arr, 0, 3);

    assert(rf_array_len(result) == 3);
    rf_byte* out = (rf_byte*)result->data;
    assert(out[0] == 10);
    assert(out[1] == 20);
    assert(out[2] == 30);

    rf_array_release(result);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 3: slice_empty — slice from 2 to 2 -> empty
 * ======================================================================== */

static void test_slice_empty(void) {
    TEST(slice_empty);

    rf_byte data[] = {1, 2, 3};
    RF_Array* arr = make_bytes(data, 3);
    RF_Array* result = rf_bytes_slice(arr, 2, 2);

    assert(rf_array_len(result) == 0);

    rf_array_release(result);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 4: slice_clamped — out-of-bounds indices are clamped
 * ======================================================================== */

static void test_slice_clamped(void) {
    TEST(slice_clamped);

    rf_byte data[] = {1, 2, 3, 4, 5};
    RF_Array* arr = make_bytes(data, 5);

    /* start before 0, end beyond len */
    RF_Array* r1 = rf_bytes_slice(arr, -10, 100);
    assert(rf_array_len(r1) == 5);
    rf_byte* out1 = (rf_byte*)r1->data;
    assert(out1[0] == 1 && out1[4] == 5);

    /* start > end -> clamped to empty */
    RF_Array* r2 = rf_bytes_slice(arr, 3, 1);
    assert(rf_array_len(r2) == 0);

    rf_array_release(r1);
    rf_array_release(r2);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 5: concat_basic — concat [1,2] + [3,4] -> [1,2,3,4]
 * ======================================================================== */

static void test_concat_basic(void) {
    TEST(concat_basic);

    rf_byte a_data[] = {1, 2};
    rf_byte b_data[] = {3, 4};
    RF_Array* a = make_bytes(a_data, 2);
    RF_Array* b = make_bytes(b_data, 2);
    RF_Array* result = rf_bytes_concat(a, b);

    assert(rf_array_len(result) == 4);
    rf_byte* out = (rf_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);
    assert(out[2] == 3);
    assert(out[3] == 4);

    rf_array_release(result);
    rf_array_release(a);
    rf_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 6: concat_empty_left — concat [] + [1,2] -> [1,2]
 * ======================================================================== */

static void test_concat_empty_left(void) {
    TEST(concat_empty_left);

    RF_Array* a = rf_array_new(0, 1, NULL);
    rf_byte b_data[] = {1, 2};
    RF_Array* b = make_bytes(b_data, 2);
    RF_Array* result = rf_bytes_concat(a, b);

    assert(rf_array_len(result) == 2);
    rf_byte* out = (rf_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);

    rf_array_release(result);
    rf_array_release(a);
    rf_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 7: concat_empty_right — concat [1,2] + [] -> [1,2]
 * ======================================================================== */

static void test_concat_empty_right(void) {
    TEST(concat_empty_right);

    rf_byte a_data[] = {1, 2};
    RF_Array* a = make_bytes(a_data, 2);
    RF_Array* b = rf_array_new(0, 1, NULL);
    RF_Array* result = rf_bytes_concat(a, b);

    assert(rf_array_len(result) == 2);
    rf_byte* out = (rf_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);

    rf_array_release(result);
    rf_array_release(a);
    rf_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 8: index_of_found — find byte 3 in [1,2,3,4,5] -> SOME(2)
 * ======================================================================== */

static void test_index_of_found(void) {
    TEST(index_of_found);

    rf_byte data[] = {1, 2, 3, 4, 5};
    RF_Array* arr = make_bytes(data, 5);
    RF_Option_ptr result = rf_bytes_index_of(arr, 3);

    assert(result.tag == 1);
    assert((intptr_t)result.value == 2);

    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 9: index_of_not_found — find byte 9 in [1,2,3] -> NONE
 * ======================================================================== */

static void test_index_of_not_found(void) {
    TEST(index_of_not_found);

    rf_byte data[] = {1, 2, 3};
    RF_Array* arr = make_bytes(data, 3);
    RF_Option_ptr result = rf_bytes_index_of(arr, 9);

    assert(result.tag == 0);

    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 10: index_of_first_occurrence — find byte 2 in [2,1,2,3] -> SOME(0)
 * ======================================================================== */

static void test_index_of_first_occurrence(void) {
    TEST(index_of_first_occurrence);

    rf_byte data[] = {2, 1, 2, 3};
    RF_Array* arr = make_bytes(data, 4);
    RF_Option_ptr result = rf_bytes_index_of(arr, 2);

    assert(result.tag == 1);
    assert((intptr_t)result.value == 0);

    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 11: len_basic — len of 5-element array -> 5
 * ======================================================================== */

static void test_len_basic(void) {
    TEST(len_basic);

    rf_byte data[] = {10, 20, 30, 40, 50};
    RF_Array* arr = make_bytes(data, 5);

    assert(rf_bytes_len(arr) == 5);

    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 12: len_empty — len of empty -> 0
 * ======================================================================== */

static void test_len_empty(void) {
    TEST(len_empty);

    RF_Array* arr = rf_array_new(0, 1, NULL);

    assert(rf_bytes_len(arr) == 0);

    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 13: string_roundtrip — from_string("hello") -> to_string -> "hello"
 * ======================================================================== */

static void test_string_roundtrip(void) {
    TEST(string_roundtrip);

    RF_String* original = rf_string_from_cstr("hello");
    RF_Array* bytes = rf_string_to_bytes(original);

    assert(rf_array_len(bytes) == 5);
    rf_byte* data = (rf_byte*)bytes->data;
    assert(data[0] == 'h');
    assert(data[1] == 'e');
    assert(data[2] == 'l');
    assert(data[3] == 'l');
    assert(data[4] == 'o');

    RF_String* recovered = rf_string_from_bytes(bytes);
    assert(rf_string_eq(original, recovered));

    rf_string_release(recovered);
    rf_array_release(bytes);
    rf_string_release(original);
    PASS();
}

/* ========================================================================
 * Test 14: concat_both_empty — concat [] + [] -> []
 * ======================================================================== */

static void test_concat_both_empty(void) {
    TEST(concat_both_empty);

    RF_Array* a = rf_array_new(0, 1, NULL);
    RF_Array* b = rf_array_new(0, 1, NULL);
    RF_Array* result = rf_bytes_concat(a, b);

    assert(rf_array_len(result) == 0);

    rf_array_release(result);
    rf_array_release(a);
    rf_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 15: slice_then_concat — slice and concat round-trip
 * ======================================================================== */

static void test_slice_then_concat(void) {
    TEST(slice_then_concat);

    rf_byte data[] = {1, 2, 3, 4, 5};
    RF_Array* arr = make_bytes(data, 5);

    RF_Array* left = rf_bytes_slice(arr, 0, 2);   /* [1, 2] */
    RF_Array* right = rf_bytes_slice(arr, 2, 5);   /* [3, 4, 5] */
    RF_Array* joined = rf_bytes_concat(left, right);

    assert(rf_array_len(joined) == 5);
    rf_byte* out = (rf_byte*)joined->data;
    for (int i = 0; i < 5; i++) {
        assert(out[i] == data[i]);
    }

    rf_array_release(joined);
    rf_array_release(right);
    rf_array_release(left);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("rf_bytes_* tests\n");
    printf("========================================\n");

    test_slice_middle();
    test_slice_full();
    test_slice_empty();
    test_slice_clamped();
    test_concat_basic();
    test_concat_empty_left();
    test_concat_empty_right();
    test_index_of_found();
    test_index_of_not_found();
    test_index_of_first_occurrence();
    test_len_basic();
    test_len_empty();
    test_string_roundtrip();
    test_concat_both_empty();
    test_slice_then_concat();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
