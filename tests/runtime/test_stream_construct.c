/*
 * C-level tests for stream construction functions (SL-5-2).
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
 * Test 1: rf_stream_range(0, 5) yields 0, 1, 2, 3, 4 then none
 * ======================================================================== */

static void test_range_basic(void) {
    TEST(range_0_to_5);

    RF_Stream* s = rf_stream_range(0, 5);

    for (rf_int i = 0; i < 5; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == i);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 2: rf_stream_range(3, 3) yields nothing (empty range)
 * ======================================================================== */

static void test_range_empty_equal(void) {
    TEST(range_3_to_3_empty);

    RF_Stream* s = rf_stream_range(3, 3);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 3: rf_stream_range(5, 3) yields nothing (start > end)
 * ======================================================================== */

static void test_range_empty_reversed(void) {
    TEST(range_5_to_3_empty);

    RF_Stream* s = rf_stream_range(5, 3);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 4: rf_stream_range_step(0, 10, 2) yields 0, 2, 4, 6, 8
 * ======================================================================== */

static void test_range_step_positive(void) {
    TEST(range_step_0_10_2);

    RF_Stream* s = rf_stream_range_step(0, 10, 2);

    rf_int expected[] = {0, 2, 4, 6, 8};
    for (int i = 0; i < 5; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 5: rf_stream_range_step(10, 0, -2) yields 10, 8, 6, 4, 2
 * ======================================================================== */

static void test_range_step_negative(void) {
    TEST(range_step_10_0_neg2);

    RF_Stream* s = rf_stream_range_step(10, 0, -2);

    rf_int expected[] = {10, 8, 6, 4, 2};
    for (int i = 0; i < 5; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 6: rf_stream_from_array on array of ints [10, 20, 30]
 * ======================================================================== */

static void test_from_array(void) {
    TEST(from_array_ints);

    rf_int data[] = {10, 20, 30};
    RF_Array* arr = rf_array_new(3, sizeof(rf_int), data);

    RF_Stream* s = rf_stream_from_array(arr);

    rf_int expected[] = {10, 20, 30};
    for (int i = 0; i < 3; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 7: rf_stream_repeat(42, 3) yields 42, 42, 42 then none
 * ======================================================================== */

static void test_repeat(void) {
    TEST(repeat_42_three_times);

    RF_Stream* s = rf_stream_repeat((void*)(intptr_t)42, 3);

    for (int i = 0; i < 3; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == 42);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 8: rf_stream_repeat(x, 0) yields nothing
 * ======================================================================== */

static void test_repeat_zero(void) {
    TEST(repeat_zero_times);

    RF_Stream* s = rf_stream_repeat((void*)(intptr_t)99, 0);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 9: rf_stream_empty() yields none immediately
 * ======================================================================== */

static void test_empty(void) {
    TEST(empty_stream);

    RF_Stream* s = rf_stream_empty();

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    /* Calling next again should still return none */
    RF_Option_ptr opt2 = rf_stream_next(s);
    assert(opt2.tag == 0);

    rf_stream_release(s);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Stream construction tests (SL-5-2)\n");
    printf("====================================\n");

    test_range_basic();
    test_range_empty_equal();
    test_range_empty_reversed();
    test_range_step_positive();
    test_range_step_negative();
    test_from_array();
    test_repeat();
    test_repeat_zero();
    test_empty();

    printf("====================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
