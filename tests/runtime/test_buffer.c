/*
 * C-level tests for FL_Buffer extension functions (SL-4-3).
 *
 * These tests cover: fl_buffer_to_array, fl_buffer_clear, fl_buffer_pop,
 * fl_buffer_last, fl_buffer_set, fl_buffer_insert, fl_buffer_remove,
 * fl_buffer_contains, fl_buffer_slice.
 *
 * Usage example (Flow equivalent, once generic native decl is supported):
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

/* Helper: push an fl_int into a buffer */
static void push_int(FL_Buffer* buf, fl_int val) {
    fl_buffer_push(buf, &val);
}

/* Helper: read an fl_int from a buffer at index */
static fl_int get_int(FL_Buffer* buf, fl_int64 idx) {
    FL_Option_ptr opt = fl_buffer_get(buf, idx);
    assert(opt.tag == 1);
    return *(fl_int*)opt.value;
}

/* ========================================================================
 * Test 1: fl_buffer_to_array — push 3 ints, convert, verify
 * ======================================================================== */

static void test_to_array(void) {
    TEST(buffer_to_array);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    FL_Array* arr = fl_buffer_to_array(buf);
    assert(fl_array_len(arr) == 3);
    assert(*(fl_int*)fl_array_get_ptr(arr, 0) == 10);
    assert(*(fl_int*)fl_array_get_ptr(arr, 1) == 20);
    assert(*(fl_int*)fl_array_get_ptr(arr, 2) == 30);

    fl_array_release(arr);
    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 2: fl_buffer_clear — push 5, clear, verify empty, push again
 * ======================================================================== */

static void test_clear(void) {
    TEST(buffer_clear);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    for (fl_int i = 0; i < 5; i++) push_int(buf, i);
    assert(fl_buffer_len(buf) == 5);

    fl_buffer_clear(buf);
    assert(fl_buffer_len(buf) == 0);

    /* Can push again after clear */
    push_int(buf, 42);
    assert(fl_buffer_len(buf) == 1);
    assert(get_int(buf, 0) == 42);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 3: fl_buffer_pop — push 3, pop returns last, len decremented
 * ======================================================================== */

static void test_pop(void) {
    TEST(buffer_pop);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    FL_Option_ptr opt = fl_buffer_pop(buf);
    assert(opt.tag == 1);
    assert(*(fl_int*)opt.value == 30);
    assert(fl_buffer_len(buf) == 2);
    free(opt.value);

    opt = fl_buffer_pop(buf);
    assert(opt.tag == 1);
    assert(*(fl_int*)opt.value == 20);
    assert(fl_buffer_len(buf) == 1);
    free(opt.value);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 4: fl_buffer_pop on empty buffer returns none
 * ======================================================================== */

static void test_pop_empty(void) {
    TEST(buffer_pop_empty);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    FL_Option_ptr opt = fl_buffer_pop(buf);
    assert(opt.tag == 0);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 5: fl_buffer_last — returns last without changing len
 * ======================================================================== */

static void test_last(void) {
    TEST(buffer_last);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    FL_Option_ptr opt = fl_buffer_last(buf);
    assert(opt.tag == 1);
    assert(*(fl_int*)opt.value == 30);
    assert(fl_buffer_len(buf) == 3);  /* unchanged */
    free(opt.value);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 6: fl_buffer_last on empty buffer returns none
 * ======================================================================== */

static void test_last_empty(void) {
    TEST(buffer_last_empty);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    FL_Option_ptr opt = fl_buffer_last(buf);
    assert(opt.tag == 0);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 7: fl_buffer_set — replace element at index
 * ======================================================================== */

static void test_set(void) {
    TEST(buffer_set);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    fl_int val = 99;
    fl_buffer_set(buf, 1, &val);

    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 99);
    assert(get_int(buf, 2) == 30);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 8: fl_buffer_insert — insert at middle
 * ======================================================================== */

static void test_insert_middle(void) {
    TEST(buffer_insert_middle);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 30);

    fl_int val = 20;
    fl_buffer_insert(buf, 1, &val);

    assert(fl_buffer_len(buf) == 3);
    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 20);
    assert(get_int(buf, 2) == 30);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 9: fl_buffer_insert — prepend and append
 * ======================================================================== */

static void test_insert_prepend_append(void) {
    TEST(buffer_insert_prepend_append);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 20);

    /* Prepend at index 0 */
    fl_int val10 = 10;
    fl_buffer_insert(buf, 0, &val10);

    /* Append at index == len */
    fl_int val30 = 30;
    fl_buffer_insert(buf, 2, &val30);

    assert(fl_buffer_len(buf) == 3);
    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 20);
    assert(get_int(buf, 2) == 30);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 10: fl_buffer_remove — remove middle element
 * ======================================================================== */

static void test_remove(void) {
    TEST(buffer_remove);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    FL_Option_ptr opt = fl_buffer_remove(buf, 1);
    assert(opt.tag == 1);
    assert(*(fl_int*)opt.value == 20);
    free(opt.value);

    assert(fl_buffer_len(buf) == 2);
    assert(get_int(buf, 0) == 10);
    assert(get_int(buf, 1) == 30);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 11: fl_buffer_contains — linear scan
 * ======================================================================== */

static void test_contains(void) {
    TEST(buffer_contains);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    fl_int search20 = 20;
    fl_int search99 = 99;
    assert(fl_buffer_contains(buf, &search20, sizeof(fl_int)) == fl_true);
    assert(fl_buffer_contains(buf, &search99, sizeof(fl_int)) == fl_false);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 12: fl_buffer_slice — sub-range
 * ======================================================================== */

static void test_slice(void) {
    TEST(buffer_slice);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);
    push_int(buf, 40);
    push_int(buf, 50);

    FL_Buffer* sliced = fl_buffer_slice(buf, 1, 4);
    assert(fl_buffer_len(sliced) == 3);
    assert(get_int(sliced, 0) == 20);
    assert(get_int(sliced, 1) == 30);
    assert(get_int(sliced, 2) == 40);

    fl_buffer_release(sliced);
    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 13: fl_buffer_slice — edge cases (clamping, empty)
 * ======================================================================== */

static void test_slice_edge_cases(void) {
    TEST(buffer_slice_edge_cases);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);
    push_int(buf, 20);
    push_int(buf, 30);

    /* start < 0 clamps to 0 */
    FL_Buffer* s1 = fl_buffer_slice(buf, -5, 2);
    assert(fl_buffer_len(s1) == 2);
    assert(get_int(s1, 0) == 10);
    assert(get_int(s1, 1) == 20);
    fl_buffer_release(s1);

    /* end > len clamps to len */
    FL_Buffer* s2 = fl_buffer_slice(buf, 1, 100);
    assert(fl_buffer_len(s2) == 2);
    assert(get_int(s2, 0) == 20);
    assert(get_int(s2, 1) == 30);
    fl_buffer_release(s2);

    /* start >= end returns empty */
    FL_Buffer* s3 = fl_buffer_slice(buf, 2, 2);
    assert(fl_buffer_len(s3) == 0);
    fl_buffer_release(s3);

    FL_Buffer* s4 = fl_buffer_slice(buf, 3, 1);
    assert(fl_buffer_len(s4) == 0);
    fl_buffer_release(s4);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 14: fl_buffer_remove on out-of-bounds returns none
 * ======================================================================== */

static void test_remove_oob(void) {
    TEST(buffer_remove_oob);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    push_int(buf, 10);

    FL_Option_ptr opt = fl_buffer_remove(buf, 5);
    assert(opt.tag == 0);

    opt = fl_buffer_remove(buf, -1);
    assert(opt.tag == 0);

    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Test 15: fl_buffer_to_array on empty buffer
 * ======================================================================== */

static void test_to_array_empty(void) {
    TEST(buffer_to_array_empty);

    FL_Buffer* buf = fl_buffer_new(sizeof(fl_int));
    FL_Array* arr = fl_buffer_to_array(buf);
    assert(fl_array_len(arr) == 0);

    fl_array_release(arr);
    fl_buffer_release(buf);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("FL_Buffer extension tests (SL-4-3)\n");
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
