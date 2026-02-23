/*
 * C-level tests for stream transformation functions (SL-5-3).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: enumerate(range(10,13)) -> pairs (0,10), (1,11), (2,12)
 * ======================================================================== */

static void test_enumerate_indices(void) {
    TEST(enumerate_indices);

    RF_Stream* src = rf_stream_range(10, 13);
    RF_Stream* s = rf_stream_enumerate(src);

    for (rf_int i = 0; i < 3; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        RF_Pair* pair = (RF_Pair*)opt.value;
        rf_int64 idx = (rf_int64)(intptr_t)pair->first;
        rf_int val = (rf_int)(intptr_t)pair->second;
        assert(idx == i);
        assert(val == 10 + i);
        free(pair);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(src);
    PASS();
}

/* ========================================================================
 * Test 2: enumerate(empty) -> empty
 * ======================================================================== */

static void test_enumerate_empty(void) {
    TEST(enumerate_empty);

    RF_Stream* src = rf_stream_empty();
    RF_Stream* s = rf_stream_enumerate(src);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    rf_stream_release(src);
    PASS();
}

/* ========================================================================
 * Test 3: zip(range(0,3), range(10,13)) -> (0,10), (1,11), (2,12)
 * ======================================================================== */

static void test_zip_same_length(void) {
    TEST(zip_same_length);

    RF_Stream* a = rf_stream_range(0, 3);
    RF_Stream* b = rf_stream_range(10, 13);
    RF_Stream* s = rf_stream_zip(a, b);

    for (rf_int i = 0; i < 3; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        RF_Pair* pair = (RF_Pair*)opt.value;
        rf_int first = (rf_int)(intptr_t)pair->first;
        rf_int second = (rf_int)(intptr_t)pair->second;
        assert(first == i);
        assert(second == 10 + i);
        free(pair);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(a);
    rf_stream_release(b);
    PASS();
}

/* ========================================================================
 * Test 4: zip(range(0,5), range(0,2)) -> only 2 pairs
 * ======================================================================== */

static void test_zip_different_length(void) {
    TEST(zip_different_length);

    RF_Stream* a = rf_stream_range(0, 5);
    RF_Stream* b = rf_stream_range(0, 2);
    RF_Stream* s = rf_stream_zip(a, b);

    for (rf_int i = 0; i < 2; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        RF_Pair* pair = (RF_Pair*)opt.value;
        rf_int first = (rf_int)(intptr_t)pair->first;
        rf_int second = (rf_int)(intptr_t)pair->second;
        assert(first == i);
        assert(second == i);
        free(pair);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(a);
    rf_stream_release(b);
    PASS();
}

/* ========================================================================
 * Test 5: zip(empty, range(0,3)) -> empty
 * ======================================================================== */

static void test_zip_one_empty(void) {
    TEST(zip_one_empty);

    RF_Stream* a = rf_stream_empty();
    RF_Stream* b = rf_stream_range(0, 3);
    RF_Stream* s = rf_stream_zip(a, b);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    rf_stream_release(a);
    rf_stream_release(b);
    PASS();
}

/* ========================================================================
 * Test 6: chain(range(0,3), range(10,12)) -> 0,1,2,10,11
 * ======================================================================== */

static void test_chain_basic(void) {
    TEST(chain_basic);

    RF_Stream* a = rf_stream_range(0, 3);
    RF_Stream* b = rf_stream_range(10, 12);
    RF_Stream* s = rf_stream_chain(a, b);

    rf_int expected[] = {0, 1, 2, 10, 11};
    for (int i = 0; i < 5; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(a);
    rf_stream_release(b);
    PASS();
}

/* ========================================================================
 * Test 7: chain(empty, range(0,3)) -> 0,1,2
 * ======================================================================== */

static void test_chain_first_empty(void) {
    TEST(chain_first_empty);

    RF_Stream* a = rf_stream_empty();
    RF_Stream* b = rf_stream_range(0, 3);
    RF_Stream* s = rf_stream_chain(a, b);

    for (rf_int i = 0; i < 3; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == i);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(a);
    rf_stream_release(b);
    PASS();
}

/* ========================================================================
 * Test 8: chain(range(0,3), empty) -> 0,1,2
 * ======================================================================== */

static void test_chain_second_empty(void) {
    TEST(chain_second_empty);

    RF_Stream* a = rf_stream_range(0, 3);
    RF_Stream* b = rf_stream_empty();
    RF_Stream* s = rf_stream_chain(a, b);

    for (rf_int i = 0; i < 3; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == i);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(a);
    rf_stream_release(b);
    PASS();
}

/* ========================================================================
 * flat_map helper: fn that returns range(0, n)
 * ======================================================================== */

static RF_Stream* _test_flatmap_fn(void* item, void* env) {
    (void)env;
    rf_int n = (rf_int)(intptr_t)item;
    return rf_stream_range(0, n);
}

/* ========================================================================
 * Test 9: flat_map(range(1,4), fn -> range(0,n)) -> 0, 0,1, 0,1,2
 * ======================================================================== */

static void test_flat_map_basic(void) {
    TEST(flat_map_basic);

    RF_Stream* src = rf_stream_range(1, 4);
    RF_Closure cls = { .fn = (void*)_test_flatmap_fn, .env = NULL };
    RF_Stream* s = rf_stream_flat_map(src, &cls);

    /* n=1 -> [0], n=2 -> [0,1], n=3 -> [0,1,2] */
    rf_int expected[] = {0, 0, 1, 0, 1, 2};
    for (int i = 0; i < 6; i++) {
        RF_Option_ptr opt = rf_stream_next(s);
        assert(opt.tag == 1);
        rf_int val = (rf_int)(intptr_t)opt.value;
        assert(val == expected[i]);
    }

    RF_Option_ptr end = rf_stream_next(s);
    assert(end.tag == 0);

    rf_stream_release(s);
    rf_stream_release(src);
    PASS();
}

/* ========================================================================
 * Test 10: flat_map(empty, ...) -> empty
 * ======================================================================== */

static void test_flat_map_empty_source(void) {
    TEST(flat_map_empty_source);

    RF_Stream* src = rf_stream_empty();
    RF_Closure cls = { .fn = (void*)_test_flatmap_fn, .env = NULL };
    RF_Stream* s = rf_stream_flat_map(src, &cls);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    rf_stream_release(src);
    PASS();
}

/* ========================================================================
 * flat_map helper: fn that returns empty stream
 * ======================================================================== */

static RF_Stream* _test_flatmap_empty_fn(void* item, void* env) {
    (void)item; (void)env;
    return rf_stream_empty();
}

/* ========================================================================
 * Test 11: flat_map(range(0,3), fn -> empty) -> empty
 * ======================================================================== */

static void test_flat_map_empty_sub(void) {
    TEST(flat_map_empty_sub);

    RF_Stream* src = rf_stream_range(0, 3);
    RF_Closure cls = { .fn = (void*)_test_flatmap_empty_fn, .env = NULL };
    RF_Stream* s = rf_stream_flat_map(src, &cls);

    RF_Option_ptr opt = rf_stream_next(s);
    assert(opt.tag == 0);

    rf_stream_release(s);
    rf_stream_release(src);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Stream Transformation tests (SL-5-3)\n");
    printf("=====================================\n");

    test_enumerate_indices();
    test_enumerate_empty();
    test_zip_same_length();
    test_zip_different_length();
    test_zip_one_empty();
    test_chain_basic();
    test_chain_first_empty();
    test_chain_second_empty();
    test_flat_map_basic();
    test_flat_map_empty_source();
    test_flat_map_empty_sub();

    printf("=====================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
