/*
 * C-level tests for fl_bytes_* functions (stdlib/bytes).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
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

static FL_Array* make_bytes(fl_byte* data, fl_int64 len) {
    return fl_array_new(len, 1, data);
}

/* ========================================================================
 * Test 1: slice_middle — slice bytes [0,1,2,3,4] from 1 to 4 -> [1,2,3]
 * ======================================================================== */

static void test_slice_middle(void) {
    TEST(slice_middle);

    fl_byte data[] = {0, 1, 2, 3, 4};
    FL_Array* arr = make_bytes(data, 5);
    FL_Array* result = fl_bytes_slice(arr, 1, 4);

    assert(fl_array_len(result) == 3);
    fl_byte* out = (fl_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);
    assert(out[2] == 3);

    fl_array_release(result);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 2: slice_full — slice from 0 to len -> same as original
 * ======================================================================== */

static void test_slice_full(void) {
    TEST(slice_full);

    fl_byte data[] = {10, 20, 30};
    FL_Array* arr = make_bytes(data, 3);
    FL_Array* result = fl_bytes_slice(arr, 0, 3);

    assert(fl_array_len(result) == 3);
    fl_byte* out = (fl_byte*)result->data;
    assert(out[0] == 10);
    assert(out[1] == 20);
    assert(out[2] == 30);

    fl_array_release(result);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 3: slice_empty — slice from 2 to 2 -> empty
 * ======================================================================== */

static void test_slice_empty(void) {
    TEST(slice_empty);

    fl_byte data[] = {1, 2, 3};
    FL_Array* arr = make_bytes(data, 3);
    FL_Array* result = fl_bytes_slice(arr, 2, 2);

    assert(fl_array_len(result) == 0);

    fl_array_release(result);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 4: slice_clamped — out-of-bounds indices are clamped
 * ======================================================================== */

static void test_slice_clamped(void) {
    TEST(slice_clamped);

    fl_byte data[] = {1, 2, 3, 4, 5};
    FL_Array* arr = make_bytes(data, 5);

    /* start before 0, end beyond len */
    FL_Array* r1 = fl_bytes_slice(arr, -10, 100);
    assert(fl_array_len(r1) == 5);
    fl_byte* out1 = (fl_byte*)r1->data;
    assert(out1[0] == 1 && out1[4] == 5);

    /* start > end -> clamped to empty */
    FL_Array* r2 = fl_bytes_slice(arr, 3, 1);
    assert(fl_array_len(r2) == 0);

    fl_array_release(r1);
    fl_array_release(r2);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 5: concat_basic — concat [1,2] + [3,4] -> [1,2,3,4]
 * ======================================================================== */

static void test_concat_basic(void) {
    TEST(concat_basic);

    fl_byte a_data[] = {1, 2};
    fl_byte b_data[] = {3, 4};
    FL_Array* a = make_bytes(a_data, 2);
    FL_Array* b = make_bytes(b_data, 2);
    FL_Array* result = fl_bytes_concat(a, b);

    assert(fl_array_len(result) == 4);
    fl_byte* out = (fl_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);
    assert(out[2] == 3);
    assert(out[3] == 4);

    fl_array_release(result);
    fl_array_release(a);
    fl_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 6: concat_empty_left — concat [] + [1,2] -> [1,2]
 * ======================================================================== */

static void test_concat_empty_left(void) {
    TEST(concat_empty_left);

    FL_Array* a = fl_array_new(0, 1, NULL);
    fl_byte b_data[] = {1, 2};
    FL_Array* b = make_bytes(b_data, 2);
    FL_Array* result = fl_bytes_concat(a, b);

    assert(fl_array_len(result) == 2);
    fl_byte* out = (fl_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);

    fl_array_release(result);
    fl_array_release(a);
    fl_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 7: concat_empty_right — concat [1,2] + [] -> [1,2]
 * ======================================================================== */

static void test_concat_empty_right(void) {
    TEST(concat_empty_right);

    fl_byte a_data[] = {1, 2};
    FL_Array* a = make_bytes(a_data, 2);
    FL_Array* b = fl_array_new(0, 1, NULL);
    FL_Array* result = fl_bytes_concat(a, b);

    assert(fl_array_len(result) == 2);
    fl_byte* out = (fl_byte*)result->data;
    assert(out[0] == 1);
    assert(out[1] == 2);

    fl_array_release(result);
    fl_array_release(a);
    fl_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 8: index_of_found — find byte 3 in [1,2,3,4,5] -> SOME(2)
 * ======================================================================== */

static void test_index_of_found(void) {
    TEST(index_of_found);

    fl_byte data[] = {1, 2, 3, 4, 5};
    FL_Array* arr = make_bytes(data, 5);
    FL_Option_ptr result = fl_bytes_index_of(arr, 3);

    assert(result.tag == 1);
    assert((intptr_t)result.value == 2);

    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 9: index_of_not_found — find byte 9 in [1,2,3] -> NONE
 * ======================================================================== */

static void test_index_of_not_found(void) {
    TEST(index_of_not_found);

    fl_byte data[] = {1, 2, 3};
    FL_Array* arr = make_bytes(data, 3);
    FL_Option_ptr result = fl_bytes_index_of(arr, 9);

    assert(result.tag == 0);

    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 10: index_of_first_occurrence — find byte 2 in [2,1,2,3] -> SOME(0)
 * ======================================================================== */

static void test_index_of_first_occurrence(void) {
    TEST(index_of_first_occurrence);

    fl_byte data[] = {2, 1, 2, 3};
    FL_Array* arr = make_bytes(data, 4);
    FL_Option_ptr result = fl_bytes_index_of(arr, 2);

    assert(result.tag == 1);
    assert((intptr_t)result.value == 0);

    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 11: len_basic — len of 5-element array -> 5
 * ======================================================================== */

static void test_len_basic(void) {
    TEST(len_basic);

    fl_byte data[] = {10, 20, 30, 40, 50};
    FL_Array* arr = make_bytes(data, 5);

    assert(fl_bytes_len(arr) == 5);

    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 12: len_empty — len of empty -> 0
 * ======================================================================== */

static void test_len_empty(void) {
    TEST(len_empty);

    FL_Array* arr = fl_array_new(0, 1, NULL);

    assert(fl_bytes_len(arr) == 0);

    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 13: string_roundtrip — from_string("hello") -> to_string -> "hello"
 * ======================================================================== */

static void test_string_roundtrip(void) {
    TEST(string_roundtrip);

    FL_String* original = fl_string_from_cstr("hello");
    FL_Array* bytes = fl_string_to_bytes(original);

    assert(fl_array_len(bytes) == 5);
    fl_byte* data = (fl_byte*)bytes->data;
    assert(data[0] == 'h');
    assert(data[1] == 'e');
    assert(data[2] == 'l');
    assert(data[3] == 'l');
    assert(data[4] == 'o');

    FL_String* recovered = fl_string_from_bytes(bytes);
    assert(fl_string_eq(original, recovered));

    fl_string_release(recovered);
    fl_array_release(bytes);
    fl_string_release(original);
    PASS();
}

/* ========================================================================
 * Test 14: concat_both_empty — concat [] + [] -> []
 * ======================================================================== */

static void test_concat_both_empty(void) {
    TEST(concat_both_empty);

    FL_Array* a = fl_array_new(0, 1, NULL);
    FL_Array* b = fl_array_new(0, 1, NULL);
    FL_Array* result = fl_bytes_concat(a, b);

    assert(fl_array_len(result) == 0);

    fl_array_release(result);
    fl_array_release(a);
    fl_array_release(b);
    PASS();
}

/* ========================================================================
 * Test 15: slice_then_concat — slice and concat round-trip
 * ======================================================================== */

static void test_slice_then_concat(void) {
    TEST(slice_then_concat);

    fl_byte data[] = {1, 2, 3, 4, 5};
    FL_Array* arr = make_bytes(data, 5);

    FL_Array* left = fl_bytes_slice(arr, 0, 2);   /* [1, 2] */
    FL_Array* right = fl_bytes_slice(arr, 2, 5);   /* [3, 4, 5] */
    FL_Array* joined = fl_bytes_concat(left, right);

    assert(fl_array_len(joined) == 5);
    fl_byte* out = (fl_byte*)joined->data;
    for (int i = 0; i < 5; i++) {
        assert(out[i] == data[i]);
    }

    fl_array_release(joined);
    fl_array_release(right);
    fl_array_release(left);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("fl_bytes_* tests\n");
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
