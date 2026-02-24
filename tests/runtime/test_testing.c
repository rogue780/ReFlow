/*
 * C-level tests for stdlib/testing assertions and runner.
 *
 * Note: fl_test_assert_eq_int, fl_test_assert_eq_string, fl_test_assert_eq_bool
 * were removed in SG-4-3-2 (those behaviors are now in monomorphized Flow code).
 * This file tests the remaining runtime testing functions.
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
 * Test 1: assert_true passes on true
 * ======================================================================== */

static void test_assert_true_passes(void) {
    TEST(assert_true_passes);

    FL_String* msg = fl_string_from_cstr("should not fail");
    fl_test_assert_true(fl_true, msg);
    fl_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 2: assert_true fails on false
 * ======================================================================== */

static void test_assert_true_fails(void) {
    TEST(assert_true_fails);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        FL_String* msg = fl_string_from_cstr("test msg");
        fl_test_assert_true(fl_false, msg);
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == FL_TEST_FAILURE_TAG);
        FL_String* err = (FL_String*)ef.exception;
        assert(err != NULL);
        /* Verify message contains expected prefix */
        assert(strstr(err->data, "expected true") != NULL);
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    PASS();
}

/* ========================================================================
 * Test 3: assert_false passes on false
 * ======================================================================== */

static void test_assert_false_passes(void) {
    TEST(assert_false_passes);

    FL_String* msg = fl_string_from_cstr("should not fail");
    fl_test_assert_false(fl_false, msg);
    fl_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 4: assert_false fails on true
 * ======================================================================== */

static void test_assert_false_fails(void) {
    TEST(assert_false_fails);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        FL_String* msg = fl_string_from_cstr("test msg");
        fl_test_assert_false(fl_true, msg);
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == FL_TEST_FAILURE_TAG);
        FL_String* err = (FL_String*)ef.exception;
        assert(strstr(err->data, "expected false") != NULL);
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    PASS();
}

/* ========================================================================
 * Test 5: assert_eq_float passes within epsilon
 * ======================================================================== */

static void test_assert_eq_float_passes(void) {
    TEST(assert_eq_float_passes);

    FL_String* msg = fl_string_from_cstr("float check");
    fl_test_assert_eq_float(3.14, 3.14, 0.001, msg);
    fl_test_assert_eq_float(1.0, 1.0001, 0.001, msg);
    fl_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 6: assert_eq_float fails outside epsilon
 * ======================================================================== */

static void test_assert_eq_float_fails(void) {
    TEST(assert_eq_float_fails);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        FL_String* msg = fl_string_from_cstr("float check");
        fl_test_assert_eq_float(1.0, 2.0, 0.001, msg);
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == FL_TEST_FAILURE_TAG);
        FL_String* err = (FL_String*)ef.exception;
        assert(strstr(err->data, "expected") != NULL);
        assert(strstr(err->data, "epsilon") != NULL);
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    PASS();
}

/* ========================================================================
 * Test 7: assert_some passes on Some value and returns it
 * ======================================================================== */

static void test_assert_some_passes(void) {
    TEST(assert_some_passes);

    int val = 42;
    FL_Option_ptr opt = FL_SOME_PTR((void*)(intptr_t)val);
    FL_String* msg = fl_string_from_cstr("should be some");
    void* result = fl_test_assert_some(opt, msg);
    assert((intptr_t)result == 42);
    fl_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 8: assert_some fails on None
 * ======================================================================== */

static void test_assert_some_fails(void) {
    TEST(assert_some_fails);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        FL_Option_ptr opt = FL_NONE_PTR;
        FL_String* msg = fl_string_from_cstr("some check");
        fl_test_assert_some(opt, msg);
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == FL_TEST_FAILURE_TAG);
        FL_String* err = (FL_String*)ef.exception;
        assert(strstr(err->data, "expected Some, got None") != NULL);
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    PASS();
}

/* ========================================================================
 * Test 9: assert_none passes on None
 * ======================================================================== */

static void test_assert_none_passes(void) {
    TEST(assert_none_passes);

    FL_Option_ptr opt = FL_NONE_PTR;
    FL_String* msg = fl_string_from_cstr("should be none");
    fl_test_assert_none(opt, msg);
    fl_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 10: assert_none fails on Some
 * ======================================================================== */

static void test_assert_none_fails(void) {
    TEST(assert_none_fails);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        FL_Option_ptr opt = FL_SOME_PTR((void*)(intptr_t)1);
        FL_String* msg = fl_string_from_cstr("none check");
        fl_test_assert_none(opt, msg);
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == FL_TEST_FAILURE_TAG);
        FL_String* err = (FL_String*)ef.exception;
        assert(strstr(err->data, "expected None, got Some") != NULL);
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    PASS();
}

/* ========================================================================
 * Test 11: fail always throws
 * ======================================================================== */

static void test_fail(void) {
    TEST(test_fail);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        FL_String* msg = fl_string_from_cstr("intentional failure");
        fl_test_fail(msg);
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == FL_TEST_FAILURE_TAG);
        FL_String* err = (FL_String*)ef.exception;
        assert(fl_string_eq(err, fl_string_from_cstr("intentional failure")));
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    PASS();
}

/* ========================================================================
 * Test 12: fl_test_run with passing closure
 * ======================================================================== */

static void _passing_test(void* env) {
    (void)env;
    /* does nothing = passes */
}

static void test_run_passing(void) {
    TEST(test_run_passing);

    FL_Closure closure;
    closure.fn = (void*)_passing_test;
    closure.env = NULL;

    FL_String* name = fl_string_from_cstr("my passing test");
    FL_TestResult result = fl_test_run(name, &closure);

    assert(result.passed == 1);
    assert(result.failure_msg == NULL);
    assert(fl_string_eq(result.name, name));

    fl_string_release(name);
    PASS();
}

/* ========================================================================
 * Test 13: fl_test_run with failing closure
 * ======================================================================== */

static void _failing_test(void* env) {
    (void)env;
    fl_test_fail(fl_string_from_cstr("intentional failure"));
}

static void test_run_failing(void) {
    TEST(test_run_failing);

    FL_Closure closure;
    closure.fn = (void*)_failing_test;
    closure.env = NULL;

    FL_String* name = fl_string_from_cstr("my failing test");
    FL_TestResult result = fl_test_run(name, &closure);

    assert(result.passed == 0);
    assert(result.failure_msg != NULL);
    assert(fl_string_eq(result.failure_msg, fl_string_from_cstr("intentional failure")));

    fl_string_release(name);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Testing module (stdlib/testing) tests\n");
    printf("=====================================\n");

    test_assert_true_passes();
    test_assert_true_fails();
    test_assert_false_passes();
    test_assert_false_fails();
    test_assert_eq_float_passes();
    test_assert_eq_float_fails();
    test_assert_some_passes();
    test_assert_some_fails();
    test_assert_none_passes();
    test_assert_none_fails();
    test_fail();
    test_run_passing();
    test_run_failing();

    printf("=====================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
