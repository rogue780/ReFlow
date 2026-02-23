/*
 * C-level tests for the Random module (stdlib/random).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: int_range bounds — all results in [10, 20]
 * ======================================================================== */

static void test_int_range_bounds(void) {
    TEST(int_range_bounds);

    for (int i = 0; i < 1000; i++) {
        rf_int val = rf_random_int_range(10, 20);
        assert(val >= 10 && val <= 20);
    }

    PASS();
}

/* ========================================================================
 * Test 2: int_range single — min == max always returns that value
 * ======================================================================== */

static void test_int_range_single(void) {
    TEST(int_range_single);

    for (int i = 0; i < 100; i++) {
        rf_int val = rf_random_int_range(42, 42);
        assert(val == 42);
    }

    PASS();
}

/* ========================================================================
 * Test 3: int64_range bounds — all results in [100, 200]
 * ======================================================================== */

static void test_int64_range_bounds(void) {
    TEST(int64_range_bounds);

    for (int i = 0; i < 100; i++) {
        rf_int64 val = rf_random_int64_range(100, 200);
        assert(val >= 100 && val <= 200);
    }

    PASS();
}

/* ========================================================================
 * Test 4: float_unit bounds — all results in [0.0, 1.0)
 * ======================================================================== */

static void test_float_unit_bounds(void) {
    TEST(float_unit_bounds);

    for (int i = 0; i < 1000; i++) {
        rf_float val = rf_random_float_unit();
        assert(val >= 0.0 && val < 1.0);
    }

    PASS();
}

/* ========================================================================
 * Test 5: random_bool — both true and false appear in 1000 calls
 * ======================================================================== */

static void test_random_bool_both_values(void) {
    TEST(random_bool_both_values);

    int true_count = 0;
    int false_count = 0;
    for (int i = 0; i < 1000; i++) {
        rf_bool val = rf_random_bool();
        if (val == rf_true) true_count++;
        else false_count++;
    }

    assert(true_count > 0);
    assert(false_count > 0);

    PASS();
}

/* ========================================================================
 * Test 6: random_bytes — requested length matches array length
 * ======================================================================== */

static void test_random_bytes_length(void) {
    TEST(random_bytes_length);

    RF_Array* arr = rf_random_bytes(32);
    assert(rf_array_len(arr) == 32);
    rf_array_release(arr);

    PASS();
}

/* ========================================================================
 * Test 7: random_bytes zero — request 0 bytes returns empty array
 * ======================================================================== */

static void test_random_bytes_zero(void) {
    TEST(random_bytes_zero);

    RF_Array* arr = rf_random_bytes(0);
    assert(rf_array_len(arr) == 0);
    rf_array_release(arr);

    PASS();
}

/* ========================================================================
 * Test 8: shuffle preserves elements — same sum and same length
 * ======================================================================== */

static void test_shuffle_preserves_elements(void) {
    TEST(shuffle_preserves_elements);

    rf_int data[] = {1, 2, 3, 4, 5};
    RF_Array* arr = rf_array_new(5, sizeof(rf_int), data);
    RF_Array* shuffled = rf_random_shuffle(arr);

    assert(rf_array_len(shuffled) == 5);

    /* Check same sum (15) */
    rf_int sum = 0;
    for (rf_int64 i = 0; i < 5; i++) {
        rf_int* ptr = (rf_int*)rf_array_get_ptr(shuffled, i);
        sum += *ptr;
    }
    assert(sum == 15);

    rf_array_release(arr);
    rf_array_release(shuffled);

    PASS();
}

/* ========================================================================
 * Test 9: shuffle single element — returns same element
 * ======================================================================== */

static void test_shuffle_single(void) {
    TEST(shuffle_single);

    rf_int data[] = {99};
    RF_Array* arr = rf_array_new(1, sizeof(rf_int), data);
    RF_Array* shuffled = rf_random_shuffle(arr);

    assert(rf_array_len(shuffled) == 1);
    rf_int* ptr = (rf_int*)rf_array_get_ptr(shuffled, 0);
    assert(*ptr == 99);

    rf_array_release(arr);
    rf_array_release(shuffled);

    PASS();
}

/* ========================================================================
 * Test 10: choice on nonempty array — all results in expected set
 * ======================================================================== */

static void test_choice_nonempty(void) {
    TEST(choice_nonempty);

    rf_int data[] = {10, 20, 30};
    RF_Array* arr = rf_array_new(3, sizeof(rf_int), data);

    for (int i = 0; i < 100; i++) {
        RF_Option_ptr opt = rf_random_choice(arr);
        assert(opt.tag == 1);
        /* For value types smaller than pointer, opt.value is a pointer into array data */
        rf_int val = *(rf_int*)opt.value;
        assert(val == 10 || val == 20 || val == 30);
    }

    rf_array_release(arr);

    PASS();
}

/* ========================================================================
 * Test 11: choice on empty array — returns NONE
 * ======================================================================== */

static void test_choice_empty(void) {
    TEST(choice_empty);

    RF_Array* arr = rf_array_new(0, sizeof(rf_int), NULL);
    RF_Option_ptr opt = rf_random_choice(arr);
    assert(opt.tag == 0);
    rf_array_release(arr);

    PASS();
}

/* ========================================================================
 * Test 12: int_range distribution — reasonable coverage of range
 * ======================================================================== */

static void test_int_range_distribution(void) {
    TEST(int_range_distribution);

    /* Call 10000 times with range [0, 9], verify all 10 values appear */
    int seen[10] = {0};
    for (int i = 0; i < 10000; i++) {
        rf_int val = rf_random_int_range(0, 9);
        assert(val >= 0 && val <= 9);
        seen[val] = 1;
    }
    for (int i = 0; i < 10; i++) {
        assert(seen[i] == 1);
    }

    PASS();
}

/* ========================================================================
 * Test 13: random_bytes not all zeros — at least one nonzero byte in 32
 * ======================================================================== */

static void test_random_bytes_nonzero(void) {
    TEST(random_bytes_nonzero);

    RF_Array* arr = rf_random_bytes(32);
    int has_nonzero = 0;
    for (rf_int64 i = 0; i < 32; i++) {
        rf_byte* ptr = (rf_byte*)rf_array_get_ptr(arr, i);
        if (*ptr != 0) { has_nonzero = 1; break; }
    }
    assert(has_nonzero);
    rf_array_release(arr);

    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Random module tests\n");
    printf("========================================\n");

    test_int_range_bounds();
    test_int_range_single();
    test_int64_range_bounds();
    test_float_unit_bounds();
    test_random_bool_both_values();
    test_random_bytes_length();
    test_random_bytes_zero();
    test_shuffle_preserves_elements();
    test_shuffle_single();
    test_choice_nonempty();
    test_choice_empty();
    test_int_range_distribution();
    test_random_bytes_nonzero();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
