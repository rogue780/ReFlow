/*
 * C-level tests for sort functions (SL-4-4).
 *
 * These tests cover: rf_sort_ints, rf_sort_strings, rf_sort_floats,
 * rf_array_reverse, rf_sort_array_by.
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
 * Test 1: sort_ints_ascending — sort unsorted array
 * ======================================================================== */

static void test_sort_ints_ascending(void) {
    TEST(sort_ints_ascending);

    rf_int data[] = {3, 1, 4, 1, 5, 9, 2, 6};
    RF_Array* arr = rf_array_new(8, sizeof(rf_int), data);

    RF_Array* sorted = rf_sort_ints(arr);
    assert(rf_array_len(sorted) == 8);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 0) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 1) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 2) == 2);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 3) == 3);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 4) == 4);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 5) == 5);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 6) == 6);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 7) == 9);

    /* Original array should be unchanged */
    assert(*(rf_int*)rf_array_get_ptr(arr, 0) == 3);

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 2: sort_ints_already_sorted — no-op sort
 * ======================================================================== */

static void test_sort_ints_already_sorted(void) {
    TEST(sort_ints_already_sorted);

    rf_int data[] = {1, 2, 3, 4, 5};
    RF_Array* arr = rf_array_new(5, sizeof(rf_int), data);

    RF_Array* sorted = rf_sort_ints(arr);
    assert(rf_array_len(sorted) == 5);
    for (rf_int64 i = 0; i < 5; i++) {
        assert(*(rf_int*)rf_array_get_ptr(sorted, i) == (rf_int)(i + 1));
    }

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 3: sort_ints_single — single element
 * ======================================================================== */

static void test_sort_ints_single(void) {
    TEST(sort_ints_single);

    rf_int data[] = {42};
    RF_Array* arr = rf_array_new(1, sizeof(rf_int), data);

    RF_Array* sorted = rf_sort_ints(arr);
    assert(rf_array_len(sorted) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 0) == 42);

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 4: sort_ints_empty — empty array
 * ======================================================================== */

static void test_sort_ints_empty(void) {
    TEST(sort_ints_empty);

    RF_Array* arr = rf_array_new(0, sizeof(rf_int), NULL);

    RF_Array* sorted = rf_sort_ints(arr);
    assert(rf_array_len(sorted) == 0);

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 5: sort_strings_lexicographic
 * ======================================================================== */

static void test_sort_strings_lexicographic(void) {
    TEST(sort_strings_lexicographic);

    RF_String* banana = rf_string_from_cstr("banana");
    RF_String* apple = rf_string_from_cstr("apple");
    RF_String* cherry = rf_string_from_cstr("cherry");

    RF_String* data[] = {banana, apple, cherry};
    RF_Array* arr = rf_array_new(3, sizeof(RF_String*), data);

    RF_Array* sorted = rf_sort_strings(arr);
    assert(rf_array_len(sorted) == 3);

    RF_String* s0 = *(RF_String**)rf_array_get_ptr(sorted, 0);
    RF_String* s1 = *(RF_String**)rf_array_get_ptr(sorted, 1);
    RF_String* s2 = *(RF_String**)rf_array_get_ptr(sorted, 2);

    assert(rf_string_eq(s0, apple));
    assert(rf_string_eq(s1, banana));
    assert(rf_string_eq(s2, cherry));

    rf_array_release(sorted);
    rf_array_release(arr);
    rf_string_release(banana);
    rf_string_release(apple);
    rf_string_release(cherry);
    PASS();
}

/* ========================================================================
 * Test 6: sort_floats
 * ======================================================================== */

static void test_sort_floats(void) {
    TEST(sort_floats);

    rf_float data[] = {3.14, 1.0, 2.71};
    RF_Array* arr = rf_array_new(3, sizeof(rf_float), data);

    RF_Array* sorted = rf_sort_floats(arr);
    assert(rf_array_len(sorted) == 3);
    assert(*(rf_float*)rf_array_get_ptr(sorted, 0) == 1.0);
    assert(*(rf_float*)rf_array_get_ptr(sorted, 1) == 2.71);
    assert(*(rf_float*)rf_array_get_ptr(sorted, 2) == 3.14);

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 7: reverse_basic — reverse [1,2,3,4,5]
 * ======================================================================== */

static void test_reverse_basic(void) {
    TEST(reverse_basic);

    rf_int data[] = {1, 2, 3, 4, 5};
    RF_Array* arr = rf_array_new(5, sizeof(rf_int), data);

    RF_Array* rev = rf_array_reverse(arr);
    assert(rf_array_len(rev) == 5);
    assert(*(rf_int*)rf_array_get_ptr(rev, 0) == 5);
    assert(*(rf_int*)rf_array_get_ptr(rev, 1) == 4);
    assert(*(rf_int*)rf_array_get_ptr(rev, 2) == 3);
    assert(*(rf_int*)rf_array_get_ptr(rev, 3) == 2);
    assert(*(rf_int*)rf_array_get_ptr(rev, 4) == 1);

    /* Original unchanged */
    assert(*(rf_int*)rf_array_get_ptr(arr, 0) == 1);

    rf_array_release(rev);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 8: reverse_single — single element
 * ======================================================================== */

static void test_reverse_single(void) {
    TEST(reverse_single);

    rf_int data[] = {99};
    RF_Array* arr = rf_array_new(1, sizeof(rf_int), data);

    RF_Array* rev = rf_array_reverse(arr);
    assert(rf_array_len(rev) == 1);
    assert(*(rf_int*)rf_array_get_ptr(rev, 0) == 99);

    rf_array_release(rev);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 9: reverse_empty — empty array
 * ======================================================================== */

static void test_reverse_empty(void) {
    TEST(reverse_empty);

    RF_Array* arr = rf_array_new(0, sizeof(rf_int), NULL);

    RF_Array* rev = rf_array_reverse(arr);
    assert(rf_array_len(rev) == 0);

    rf_array_release(rev);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 10: sort_array_by_closure — descending sort via closure
 * ======================================================================== */

static rf_int _descending_cmp(void* a, void* b, void* env) {
    (void)env;
    rf_int va = *(rf_int*)a;
    rf_int vb = *(rf_int*)b;
    /* Reverse ordering */
    return (vb > va) - (vb < va);
}

static void test_sort_array_by_closure(void) {
    TEST(sort_array_by_closure);

    rf_int data[] = {3, 1, 4, 1, 5};
    RF_Array* arr = rf_array_new(5, sizeof(rf_int), data);

    RF_Closure cmp = { .fn = (void*)_descending_cmp, .env = NULL };
    RF_Array* sorted = rf_sort_array_by(arr, &cmp);

    assert(rf_array_len(sorted) == 5);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 0) == 5);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 1) == 4);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 2) == 3);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 3) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 4) == 1);

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 11: sort_ints_duplicates — many duplicate values
 * ======================================================================== */

static void test_sort_ints_duplicates(void) {
    TEST(sort_ints_duplicates);

    rf_int data[] = {5, 3, 5, 3, 1, 1, 5, 3, 1};
    RF_Array* arr = rf_array_new(9, sizeof(rf_int), data);

    RF_Array* sorted = rf_sort_ints(arr);
    assert(rf_array_len(sorted) == 9);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 0) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 1) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 2) == 1);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 3) == 3);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 4) == 3);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 5) == 3);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 6) == 5);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 7) == 5);
    assert(*(rf_int*)rf_array_get_ptr(sorted, 8) == 5);

    rf_array_release(sorted);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Sort function tests (SL-4-4)\n");
    printf("========================================\n");

    test_sort_ints_ascending();
    test_sort_ints_already_sorted();
    test_sort_ints_single();
    test_sort_ints_empty();
    test_sort_strings_lexicographic();
    test_sort_floats();
    test_reverse_basic();
    test_reverse_single();
    test_reverse_empty();
    test_sort_array_by_closure();
    test_sort_ints_duplicates();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
