/*
 * C-level tests for RF_Buffer extension functions (SL-4-3).
 *
 * These tests cover: rf_buffer_to_array, rf_buffer_clear, rf_buffer_pop,
 * rf_buffer_last, rf_buffer_set, rf_buffer_insert, rf_buffer_remove,
 * rf_buffer_contains, rf_buffer_slice.
 *
 * Usage example (ReFlow equivalent, once generic native decl is supported):
 *
 *   let buf = Buffer.new<int>()
 *   buf.push(10)
 *   buf.push(20)
 *   buf.push(30)
 *   let arr = buf.to_array()     // array<int> [10, 20, 30]
 *   let last = buf.last()        // some(30)
 *   buf.set(1, 99)               // [10, 99, 30]
 *   buf.insert(0, 5)             // [5, 10, 99, 30]
 *   let removed = buf.remove(2)  // some(99), buf is [5, 10, 30]
 *   let has20 = buf.contains(20) // false
 *   let sub = buf.slice(0, 2)    // [5, 10]
 *   let popped = buf.pop()       // some(30), buf is [5, 10]
 *   buf.clear()                  // len == 0
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

/* Helper: push an rf_int into a buffer */
static void push_int(RF_Buffer* buf, rf_int val) {
    rf_buffer_push(buf, &val);
}

/* Helper: read an rf_int from a buffer at index */
static rf_int get_int(RF_Buffer* buf, rf_int64 idx) {
    RF_Option_ptr opt = rf_buffer_get(buf, idx);
    assert(opt.tag == 1);
    return *(rf_int*)opt.value;
}

/* ========================================================================
 * Test 1: rf_buffer_to_array — push 3 ints, convert, verify
 * ======================================================================== */

static void test_to_array(void) {
    TEST(buffer_to_array);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    RF_Array* arr = rf_buffer_to_array(buf);
    assert(rf_array_len(arr) == 3);
    assert(*(rf_int*)rf_array_get_ptr(arr, 0) == 10);
    assert(*(rf_int*)rf_array_get_ptr(arr, 1) == 20);
    assert(*(rf_int*)rf_array_get_ptr(arr, 2) == 30);

    rf_array_release(arr);
    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 2: rf_buffer_clear — push 5, clear, verify empty, push again
 * ======================================================================== */

static void test_clear(void) {
    TEST(buffer_clear);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    for (rf_int i = 0; i < 5; i++) push_int(buf, i);
    assert(rf_buffer_len(buf) == 5);

    rf_buffer_clear(buf);
    assert(rf_buffer_len(buf) == 0);

    /* Can push again after clear */
    push_int(buf, 42);
    assert(rf_buffer_len(buf) == 1);
    assert(get_int(buf, 0) == 42);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 3: rf_buffer_pop — push 3, pop returns last, len decremented
 * ======================================================================== */

static void test_pop(void) {
    TEST(buffer_pop);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    RF_Option_ptr opt = rf_buffer_pop(buf);
    assert(opt.tag == 1);
    assert(*(rf_int*)opt.value == 30);
    assert(rf_buffer_len(buf) == 2);
    free(opt.value);

    opt = rf_buffer_pop(buf);
    assert(opt.tag == 1);
    assert(*(rf_int*)opt.value == 20);
    assert(rf_buffer_len(buf) == 1);
    free(opt.value);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 4: rf_buffer_pop on empty buffer returns none
 * ======================================================================== */

static void test_pop_empty(void) {
    TEST(buffer_pop_empty);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    RF_Option_ptr opt = rf_buffer_pop(buf);
    assert(opt.tag == 0);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 5: rf_buffer_last — returns last without changing len
 * ======================================================================== */

static void test_last(void) {
    TEST(buffer_last);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    RF_Option_ptr opt = rf_buffer_last(buf);
    assert(opt.tag == 1);
    assert(*(rf_int*)opt.value == 30);
    assert(rf_buffer_len(buf) == 3);  /* unchanged */
    free(opt.value);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 6: rf_buffer_last on empty buffer returns none
 * ======================================================================== */

static void test_last_empty(void) {
    TEST(buffer_last_empty);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    RF_Option_ptr opt = rf_buffer_last(buf);
    assert(opt.tag == 0);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 7: rf_buffer_set — replace element at index
 * ======================================================================== */

static void test_set(void) {
    TEST(buffer_set);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    rf_int val = 99;
    rf_buffer_set(buf, 1, &val);

    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 99);
    assert(get_int(buf, 2) == 30);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 8: rf_buffer_insert — insert at middle
 * ======================================================================== */

static void test_insert_middle(void) {
    TEST(buffer_insert_middle);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 30);

    rf_int val = 20;
    rf_buffer_insert(buf, 1, &val);

    assert(rf_buffer_len(buf) == 3);
    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 20);
    assert(get_int(buf, 2) == 30);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 9: rf_buffer_insert — prepend and append
 * ======================================================================== */

static void test_insert_prepend_append(void) {
    TEST(buffer_insert_prepend_append);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 20);

    /* Prepend at index 0 */
    rf_int val10 = 10;
    rf_buffer_insert(buf, 0, &val10);

    /* Append at index == len */
    rf_int val30 = 30;
    rf_buffer_insert(buf, 2, &val30);

    assert(rf_buffer_len(buf) == 3);
    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 20);
    assert(get_int(buf, 2) == 30);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 10: rf_buffer_remove — remove middle element
 * ======================================================================== */

static void test_remove(void) {
    TEST(buffer_remove);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    RF_Option_ptr opt = rf_buffer_remove(buf, 1);
    assert(opt.tag == 1);
    assert(*(rf_int*)opt.value == 20);
    free(opt.value);

    assert(rf_buffer_len(buf) == 2);
    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 30);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 11: rf_buffer_contains — linear scan
 * ======================================================================== */

static void test_contains(void) {
    TEST(buffer_contains);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    rf_int search20 = 20;
    rf_int search99 = 99;
    assert(rf_buffer_contains(buf, &search20, sizeof(rf_int)) == rf_true);
    assert(rf_buffer_contains(buf, &search99, sizeof(rf_int)) == rf_false);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 12: rf_buffer_slice — sub-range
 * ======================================================================== */

static void test_slice(void) {
    TEST(buffer_slice);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);
    push_int(buf, 40);
    push_int(buf, 50);

    RF_Buffer* sliced = rf_buffer_slice(buf, 1, 4);
    assert(rf_buffer_len(sliced) == 3);
    assert(get_int(sliced, 0) == 20);
    assert(get_int(sliced, 1) == 30);
    assert(get_int(sliced, 2) == 40);

    rf_buffer_release(sliced);
    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 13: rf_buffer_slice — edge cases (clamping, empty)
 * ======================================================================== */

static void test_slice_edge_cases(void) {
    TEST(buffer_slice_edge_cases);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    /* start < 0 clamps to 0 */
    RF_Buffer* s1 = rf_buffer_slice(buf, -5, 2);
    assert(rf_buffer_len(s1) == 2);
    assert(get_int(s1, 0) == 10);
    assert(get_int(s1, 1) == 20);
    rf_buffer_release(s1);

    /* end > len clamps to len */
    RF_Buffer* s2 = rf_buffer_slice(buf, 1, 100);
    assert(rf_buffer_len(s2) == 2);
    assert(get_int(s2, 0) == 20);
    assert(get_int(s2, 1) == 30);
    rf_buffer_release(s2);

    /* start >= end returns empty */
    RF_Buffer* s3 = rf_buffer_slice(buf, 2, 2);
    assert(rf_buffer_len(s3) == 0);
    rf_buffer_release(s3);

    RF_Buffer* s4 = rf_buffer_slice(buf, 3, 1);
    assert(rf_buffer_len(s4) == 0);
    rf_buffer_release(s4);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 14: rf_buffer_remove on out-of-bounds returns none
 * ======================================================================== */

static void test_remove_oob(void) {
    TEST(buffer_remove_oob);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    push_int(buf, 10);

    RF_Option_ptr opt = rf_buffer_remove(buf, 5);
    assert(opt.tag == 0);

    opt = rf_buffer_remove(buf, -1);
    assert(opt.tag == 0);

    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 15: rf_buffer_to_array on empty buffer
 * ======================================================================== */

static void test_to_array_empty(void) {
    TEST(buffer_to_array_empty);

    RF_Buffer* buf = rf_buffer_new(sizeof(rf_int));
    RF_Array* arr = rf_buffer_to_array(buf);
    assert(rf_array_len(arr) == 0);

    rf_array_release(arr);
    rf_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("RF_Buffer extension tests (SL-4-3)\n");
    printf("====================================\n");

    test_to_array();
    test_clear();
    test_pop();
    test_pop_empty();
    test_last();
    test_last_empty();
    test_set();
    test_insert_middle();
    test_insert_prepend_append();
    test_remove();
    test_contains();
    test_slice();
    test_slice_edge_cases();
    test_remove_oob();
    test_to_array_empty();

    printf("====================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
