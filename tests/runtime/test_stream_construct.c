/*
 * C-level tests for stream construction functions (SL-5-2).
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
 * Test 1: fl_stream_range(0, 5) yields 0, 1, 2, 3, 4 then none
 * ======================================================================== */

static void test_range_basic(void) {
    TEST(range_0_to_5);

    FL_Stream* s = fl_stream_range(0, 5);

    for (fl_int i = 0; i < 5; i++) {
        FL_Option_ptr opt = fl_stream_next(s);
        assert(opt.tag == 1);
        fl_int val = (fl_int)(intptr_t)opt.value;
        assert(val == i);
    }

    FL_Option_ptr end = fl_stream_next(s);
    assert(end.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 2: fl_stream_range(3, 3) yields nothing (empty range)
 * ======================================================================== */

static void test_range_empty_equal(void) {
    TEST(range_3_to_3_empty);

    FL_Stream* s = fl_stream_range(3, 3);

    FL_Option_ptr opt = fl_stream_next(s);
    assert(opt.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 3: fl_stream_range(5, 3) yields nothing (start > end)
 * ======================================================================== */

static void test_range_empty_reversed(void) {
    TEST(range_5_to_3_empty);

    FL_Stream* s = fl_stream_range(5, 3);

    FL_Option_ptr opt = fl_stream_next(s);
    assert(opt.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 4: fl_stream_range_step(0, 10, 2) yields 0, 2, 4, 6, 8
 * ======================================================================== */

static void test_range_step_positive(void) {
    TEST(range_step_0_10_2);

    FL_Stream* s = fl_stream_range_step(0, 10, 2);

    fl_int expected[] = {0, 2, 4, 6, 8};
    for (int i = 0; i < 5; i++) {
        FL_Option_ptr opt = fl_stream_next(s);
        assert(opt.tag == 1);
        fl_int val = (fl_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    FL_Option_ptr end = fl_stream_next(s);
    assert(end.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 5: fl_stream_range_step(10, 0, -2) yields 10, 8, 6, 4, 2
 * ======================================================================== */

static void test_range_step_negative(void) {
    TEST(range_step_10_0_neg2);

    FL_Stream* s = fl_stream_range_step(10, 0, -2);

    fl_int expected[] = {10, 8, 6, 4, 2};
    for (int i = 0; i < 5; i++) {
        FL_Option_ptr opt = fl_stream_next(s);
        assert(opt.tag == 1);
        fl_int val = (fl_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    FL_Option_ptr end = fl_stream_next(s);
    assert(end.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 6: fl_stream_from_array on array of ints [10, 20, 30]
 * ======================================================================== */

static void test_from_array(void) {
    TEST(from_array_ints);

    fl_int data[] = {10, 20, 30};
    FL_Array* arr = fl_array_new(3, sizeof(fl_int), data);

    FL_Stream* s = fl_stream_from_array(arr);

    fl_int expected[] = {10, 20, 30};
    for (int i = 0; i < 3; i++) {
        FL_Option_ptr opt = fl_stream_next(s);
        assert(opt.tag == 1);
        fl_int val = (fl_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    FL_Option_ptr end = fl_stream_next(s);
    assert(end.tag == 0);

    fl_stream_release(s);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 7: fl_stream_repeat(42, 3) yields 42, 42, 42 then none
 * ======================================================================== */

static void test_repeat(void) {
    TEST(repeat_42_three_times);

    FL_Stream* s = fl_stream_repeat((void*)(intptr_t)42, 3);

    for (int i = 0; i < 3; i++) {
        FL_Option_ptr opt = fl_stream_next(s);
        assert(opt.tag == 1);
        fl_int val = (fl_int)(intptr_t)opt.value;
        assert(val == 42);
    }

    FL_Option_ptr end = fl_stream_next(s);
    assert(end.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 8: fl_stream_repeat(x, 0) yields nothing
 * ======================================================================== */

static void test_repeat_zero(void) {
    TEST(repeat_zero_times);

    FL_Stream* s = fl_stream_repeat((void*)(intptr_t)99, 0);

    FL_Option_ptr opt = fl_stream_next(s);
    assert(opt.tag == 0);

    fl_stream_release(s);
    PASS();
}

/* ========================================================================
 * Test 9: fl_stream_empty() yields none immediately
 * ======================================================================== */

static void test_empty(void) {
    TEST(empty_stream);

    FL_Stream* s = fl_stream_empty();

    FL_Option_ptr opt = fl_stream_next(s);
    assert(opt.tag == 0);

    /* Calling next again should still return none */
    FL_Option_ptr opt2 = fl_stream_next(s);
    assert(opt2.tag == 0);

    fl_stream_release(s);
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
