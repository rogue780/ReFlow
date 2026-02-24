/*
 * C-level tests for stream consumption functions (SL-5-4).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
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
 * Helper: create a stream from a C int array
 * ======================================================================== */

typedef struct {
    fl_int* data;
    fl_int  len;
    fl_int  idx;
} _TestArrayState;

static FL_Option_ptr _test_array_next(FL_Stream* self) {
    _TestArrayState* st = (_TestArrayState*)self->state;
    if (st->idx >= st->len) return FL_NONE_PTR;
    fl_int val = st->data[st->idx++];
    return FL_SOME_PTR((void*)(intptr_t)val);
}

static void _test_array_free(FL_Stream* self) {
    free(self->state);
}

static FL_Stream* _make_int_stream(fl_int* data, fl_int len) {
    _TestArrayState* st = (_TestArrayState*)malloc(sizeof(_TestArrayState));
    st->data = data;
    st->len = len;
    st->idx = 0;
    return fl_stream_new(_test_array_next, _test_array_free, st);
}

/* ========================================================================
 * Predicate closures for tests
 * ======================================================================== */

static fl_bool _pred_gt3(void* env, void* val) {
    (void)env;
    return (fl_int)(intptr_t)val > 3;
}

static fl_bool _pred_gt10(void* env, void* val) {
    (void)env;
    return (fl_int)(intptr_t)val > 10;
}

static fl_bool _pred_gt0(void* env, void* val) {
    (void)env;
    return (fl_int)(intptr_t)val > 0;
}

static fl_bool _pred_eq3(void* env, void* val) {
    (void)env;
    return (fl_int)(intptr_t)val == 3;
}

static fl_bool _pred_eq99(void* env, void* val) {
    (void)env;
    return (fl_int)(intptr_t)val == 99;
}

/* ========================================================================
 * Foreach helper
 * ======================================================================== */

static fl_int _foreach_count;
static void _foreach_counter(void* env, void* val) {
    (void)env; (void)val;
    _foreach_count++;
}

/* ========================================================================
 * Test 1: fl_stream_count on [1,2,3,4,5] -> 5
 * ======================================================================== */

static void test_count_nonempty(void) {
    TEST(count_nonempty);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    fl_int result = fl_stream_count(s);
    assert(result == 5);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 2: fl_stream_count on empty stream -> 0
 * ======================================================================== */

static void test_count_empty(void) {
    TEST(count_empty);

    FL_Stream* s = _make_int_stream(NULL, 0);
    fl_int result = fl_stream_count(s);
    assert(result == 0);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 3: fl_stream_sum_int on [1,2,3,4,5] -> 15
 * ======================================================================== */

static void test_sum_int_nonempty(void) {
    TEST(sum_int_nonempty);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    fl_int result = fl_stream_sum_int(s);
    assert(result == 15);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 4: fl_stream_sum_int on empty stream -> 0
 * ======================================================================== */

static void test_sum_int_empty(void) {
    TEST(sum_int_empty);

    FL_Stream* s = _make_int_stream(NULL, 0);
    fl_int result = fl_stream_sum_int(s);
    assert(result == 0);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 5: fl_stream_any with "x > 3" on [1,2,3,4,5] -> true
 * ======================================================================== */

static void test_any_true(void) {
    TEST(any_true);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    FL_Closure pred = { .fn = (void*)_pred_gt3, .env = NULL };
    fl_bool result = fl_stream_any(s, &pred);
    assert(result == fl_true);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 6: fl_stream_any with "x > 10" on [1,2,3,4,5] -> false
 * ======================================================================== */

static void test_any_false(void) {
    TEST(any_false);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    FL_Closure pred = { .fn = (void*)_pred_gt10, .env = NULL };
    fl_bool result = fl_stream_any(s, &pred);
    assert(result == fl_false);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 7: fl_stream_all with "x > 0" on [1,2,3,4,5] -> true
 * ======================================================================== */

static void test_all_true(void) {
    TEST(all_true);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    FL_Closure pred = { .fn = (void*)_pred_gt0, .env = NULL };
    fl_bool result = fl_stream_all(s, &pred);
    assert(result == fl_true);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 8: fl_stream_all with "x > 3" on [1,2,3,4,5] -> false
 * ======================================================================== */

static void test_all_false(void) {
    TEST(all_false);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    FL_Closure pred = { .fn = (void*)_pred_gt3, .env = NULL };
    fl_bool result = fl_stream_all(s, &pred);
    assert(result == fl_false);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 9: fl_stream_find with "x == 3" on [1,2,3,4,5] -> some(3)
 * ======================================================================== */

static void test_find_found(void) {
    TEST(find_found);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    FL_Closure pred = { .fn = (void*)_pred_eq3, .env = NULL };
    FL_Option_ptr result = fl_stream_find(s, &pred);
    assert(result.tag == 1);
    assert((fl_int)(intptr_t)result.value == 3);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 10: fl_stream_find with "x == 99" on [1,2,3,4,5] -> none
 * ======================================================================== */

static void test_find_not_found(void) {
    TEST(find_not_found);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    FL_Closure pred = { .fn = (void*)_pred_eq99, .env = NULL };
    FL_Option_ptr result = fl_stream_find(s, &pred);
    assert(result.tag == 0);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 11: fl_stream_to_array on stream of [10,20,30]
 * ======================================================================== */

static void test_to_array(void) {
    TEST(to_array);

    fl_int data[] = {10, 20, 30};
    FL_Stream* s = _make_int_stream(data, 3);
    FL_Array* arr = fl_stream_to_array(s, sizeof(void*));
    assert(fl_array_len(arr) == 3);

    /* Values stored as void* in buffer_collect via &item.value */
    void* v0 = *(void**)fl_array_get_ptr(arr, 0);
    void* v1 = *(void**)fl_array_get_ptr(arr, 1);
    void* v2 = *(void**)fl_array_get_ptr(arr, 2);
    assert((fl_int)(intptr_t)v0 == 10);
    assert((fl_int)(intptr_t)v1 == 20);
    assert((fl_int)(intptr_t)v2 == 30);

    fl_array_release(arr);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Test 12: fl_stream_foreach — verify called for each element
 * ======================================================================== */

static void test_foreach(void) {
    TEST(foreach);

    fl_int data[] = {1, 2, 3, 4, 5};
    FL_Stream* s = _make_int_stream(data, 5);
    _foreach_count = 0;
    FL_Closure fn = { .fn = (void*)_foreach_counter, .env = NULL };
    fl_stream_foreach(s, &fn);
    assert(_foreach_count == 5);
    fl_stream_release(s);

    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Stream Consumption tests (SL-5-4)\n");
    printf("==================================\n");

    test_count_nonempty();
    test_count_empty();
    test_sum_int_nonempty();
    test_sum_int_empty();
    test_any_true();
    test_any_false();
    test_all_true();
    test_all_false();
    test_find_found();
    test_find_not_found();
    test_to_array();
    test_foreach();

    printf("==================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
