/*
 * C-level tests for sort functions (SG-4-2 / SG-5-2-1).
 *
 * Tests cover: fl_sort_array_by (with env-first closure convention),
 * fl_array_reverse.  The type-specific fl_sort_ints/strings/floats were
 * removed in SG-4-2-2; tests now use fl_sort_array_by with typed comparators.
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
 * Comparator functions — env-first convention: (void* env, const void* a, const void* b)
 * ======================================================================== */

static fl_int _cmp_int_asc(void* env, const void* a, const void* b) {
    (void)env;
    fl_int va = *(const fl_int*)a;
    fl_int vb = *(const fl_int*)b;
    return (va > vb) - (va < vb);
}

static fl_int _cmp_int_desc(void* env, const void* a, const void* b) {
    (void)env;
    fl_int va = *(const fl_int*)a;
    fl_int vb = *(const fl_int*)b;
    return (vb > va) - (vb < va);
}

static fl_int _cmp_string_asc(void* env, const void* a, const void* b) {
    (void)env;
    FL_String* sa = *(FL_String* const*)a;
    FL_String* sb = *(FL_String* const*)b;
    return fl_string_cmp(sa, sb);
}

static fl_int _cmp_float_asc(void* env, const void* a, const void* b) {
    (void)env;
    fl_float va = *(const fl_float*)a;
    fl_float vb = *(const fl_float*)b;
    return (va > vb) - (va < vb);
}

/* ========================================================================
 * Test 1: sort_ints_ascending — sort unsorted array
 * ======================================================================== */

static void test_sort_ints_ascending(void) {
    TEST(sort_ints_ascending);

    fl_int data[] = {3, 1, 4, 1, 5, 9, 2, 6};
    FL_Array* arr = fl_array_new(8, sizeof(fl_int), data);

    FL_Closure cmp = { .fn = (void*)_cmp_int_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 8);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 0) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 1) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 2) == 2);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 3) == 3);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 4) == 4);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 5) == 5);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 6) == 6);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 7) == 9);

    /* Original array should be unchanged */
    assert(*(fl_int*)fl_array_get_ptr(arr, 0) == 3);

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 2: sort_ints_already_sorted — no-op sort
 * ======================================================================== */

static void test_sort_ints_already_sorted(void) {
    TEST(sort_ints_already_sorted);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Array* arr = fl_array_new(5, sizeof(fl_int), data);

    FL_Closure cmp = { .fn = (void*)_cmp_int_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 5);
    for (fl_int64 i = 0; i < 5; i++) {
        assert(*(fl_int*)fl_array_get_ptr(sorted, i) == (fl_int)(i + 1));
    }

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 3: sort_ints_single — single element
 * ======================================================================== */

static void test_sort_ints_single(void) {
    TEST(sort_ints_single);

    fl_int data[] = {42};
    FL_Array* arr = fl_array_new(1, sizeof(fl_int), data);

    FL_Closure cmp = { .fn = (void*)_cmp_int_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 0) == 42);

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 4: sort_ints_empty — empty array
 * ======================================================================== */

static void test_sort_ints_empty(void) {
    TEST(sort_ints_empty);

    FL_Array* arr = fl_array_new(0, sizeof(fl_int), NULL);

    FL_Closure cmp = { .fn = (void*)_cmp_int_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 0);

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 5: sort_strings_lexicographic
 * ======================================================================== */

static void test_sort_strings_lexicographic(void) {
    TEST(sort_strings_lexicographic);

    FL_String* banana = fl_string_from_cstr("banana");
    FL_String* apple = fl_string_from_cstr("apple");
    FL_String* cherry = fl_string_from_cstr("cherry");

    FL_String* data[] = {banana, apple, cherry};
    FL_Array* arr = fl_array_new(3, sizeof(FL_String*), data);

    FL_Closure cmp = { .fn = (void*)_cmp_string_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 3);

    FL_String* s0 = *(FL_String**)fl_array_get_ptr(sorted, 0);
    FL_String* s1 = *(FL_String**)fl_array_get_ptr(sorted, 1);
    FL_String* s2 = *(FL_String**)fl_array_get_ptr(sorted, 2);

    assert(fl_string_eq(s0, apple));
    assert(fl_string_eq(s1, banana));
    assert(fl_string_eq(s2, cherry));

    fl_array_release(sorted);
    fl_array_release(arr);
    fl_string_release(banana);
    fl_string_release(apple);
    fl_string_release(cherry);
    PASS();
}

/* ========================================================================
 * Test 6: sort_floats
 * ======================================================================== */

static void test_sort_floats(void) {
    TEST(sort_floats);

    fl_float data[] = {3.14, 1.0, 2.71};
    FL_Array* arr = fl_array_new(3, sizeof(fl_float), data);

    FL_Closure cmp = { .fn = (void*)_cmp_float_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 3);
    assert(*(fl_float*)fl_array_get_ptr(sorted, 0) == 1.0);
    assert(*(fl_float*)fl_array_get_ptr(sorted, 1) == 2.71);
    assert(*(fl_float*)fl_array_get_ptr(sorted, 2) == 3.14);

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 7: reverse_basic — reverse [1,2,3,4,5]
 * ======================================================================== */

static void test_reverse_basic(void) {
    TEST(reverse_basic);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Array* arr = fl_array_new(5, sizeof(fl_int), data);

    FL_Array* rev = fl_array_reverse(arr);
    assert(fl_array_len(rev) == 5);
    assert(*(fl_int*)fl_array_get_ptr(rev, 0) == 5);
    assert(*(fl_int*)fl_array_get_ptr(rev, 1) == 4);
    assert(*(fl_int*)fl_array_get_ptr(rev, 2) == 3);
    assert(*(fl_int*)fl_array_get_ptr(rev, 3) == 2);
    assert(*(fl_int*)fl_array_get_ptr(rev, 4) == 1);

    /* Original unchanged */
    assert(*(fl_int*)fl_array_get_ptr(arr, 0) == 1);

    fl_array_release(rev);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 8: reverse_single — single element
 * ======================================================================== */

static void test_reverse_single(void) {
    TEST(reverse_single);

    fl_int data[] = {99};
    FL_Array* arr = fl_array_new(1, sizeof(fl_int), data);

    FL_Array* rev = fl_array_reverse(arr);
    assert(fl_array_len(rev) == 1);
    assert(*(fl_int*)fl_array_get_ptr(rev, 0) == 99);

    fl_array_release(rev);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 9: reverse_empty — empty array
 * ======================================================================== */

static void test_reverse_empty(void) {
    TEST(reverse_empty);

    FL_Array* arr = fl_array_new(0, sizeof(fl_int), NULL);

    FL_Array* rev = fl_array_reverse(arr);
    assert(fl_array_len(rev) == 0);

    fl_array_release(rev);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 10: sort_array_by_closure — descending sort via closure
 * ======================================================================== */

static void test_sort_array_by_closure(void) {
    TEST(sort_array_by_closure);

    fl_int data[] = {3, 1, 4, 1, 5};
    FL_Array* arr = fl_array_new(5, sizeof(fl_int), data);

    FL_Closure cmp = { .fn = (void*)_cmp_int_desc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);

    assert(fl_array_len(sorted) == 5);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 0) == 5);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 1) == 4);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 2) == 3);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 3) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 4) == 1);

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 11: sort_ints_duplicates — many duplicate values
 * ======================================================================== */

static void test_sort_ints_duplicates(void) {
    TEST(sort_ints_duplicates);

    fl_int data[] = {5, 3, 5, 3, 1, 1, 5, 3, 1};
    FL_Array* arr = fl_array_new(9, sizeof(fl_int), data);

    FL_Closure cmp = { .fn = (void*)_cmp_int_asc, .env = NULL };
    FL_Array* sorted = fl_sort_array_by(arr, &cmp);
    assert(fl_array_len(sorted) == 9);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 0) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 1) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 2) == 1);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 3) == 3);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 4) == 3);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 5) == 3);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 6) == 5);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 7) == 5);
    assert(*(fl_int*)fl_array_get_ptr(sorted, 8) == 5);

    fl_array_release(sorted);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Sort function tests (SG-4-2 / SG-5-2-1)\n");
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
