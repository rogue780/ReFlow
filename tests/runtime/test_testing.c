/*
 * C-level tests for stdlib/testing assertions and runner.
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
 * Test 1: assert_true passes on true
 * ======================================================================== */

static void test_assert_true_passes(void) {
    TEST(assert_true_passes);

    RF_String* msg = rf_string_from_cstr("should not fail");
    rf_test_assert_true(rf_true, msg);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 2: assert_true fails on false
 * ======================================================================== */

static void test_assert_true_fails(void) {
    TEST(assert_true_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_String* msg = rf_string_from_cstr("test msg");
        rf_test_assert_true(rf_false, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(err != NULL);
        /* Verify message contains expected prefix */
        assert(strstr(err->data, "expected true") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 3: assert_false passes on false
 * ======================================================================== */

static void test_assert_false_passes(void) {
    TEST(assert_false_passes);

    RF_String* msg = rf_string_from_cstr("should not fail");
    rf_test_assert_false(rf_false, msg);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 4: assert_false fails on true
 * ======================================================================== */

static void test_assert_false_fails(void) {
    TEST(assert_false_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_String* msg = rf_string_from_cstr("test msg");
        rf_test_assert_false(rf_true, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(strstr(err->data, "expected false") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 5: assert_eq_int passes on equal values
 * ======================================================================== */

static void test_assert_eq_int_passes(void) {
    TEST(assert_eq_int_passes);

    RF_String* msg = rf_string_from_cstr("should pass");
    rf_test_assert_eq_int(42, 42, msg);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 6: assert_eq_int fails on different values
 * ======================================================================== */

static void test_assert_eq_int_fails(void) {
    TEST(assert_eq_int_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_String* msg = rf_string_from_cstr("int check");
        rf_test_assert_eq_int(42, 43, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(strstr(err->data, "expected 42, got 43") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 7: assert_eq_string passes on equal strings
 * ======================================================================== */

static void test_assert_eq_string_passes(void) {
    TEST(assert_eq_string_passes);

    RF_String* a = rf_string_from_cstr("hello");
    RF_String* b = rf_string_from_cstr("hello");
    RF_String* msg = rf_string_from_cstr("strings match");
    rf_test_assert_eq_string(a, b, msg);
    rf_string_release(a);
    rf_string_release(b);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 8: assert_eq_string fails on different strings
 * ======================================================================== */

static void test_assert_eq_string_fails(void) {
    TEST(assert_eq_string_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_String* a = rf_string_from_cstr("hello");
        RF_String* b = rf_string_from_cstr("world");
        RF_String* msg = rf_string_from_cstr("string check");
        rf_test_assert_eq_string(a, b, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(strstr(err->data, "expected") != NULL);
        assert(strstr(err->data, "hello") != NULL);
        assert(strstr(err->data, "world") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 9: assert_eq_bool passes on matching booleans
 * ======================================================================== */

static void test_assert_eq_bool_passes(void) {
    TEST(assert_eq_bool_passes);

    RF_String* msg = rf_string_from_cstr("bools match");
    rf_test_assert_eq_bool(rf_true, rf_true, msg);
    rf_test_assert_eq_bool(rf_false, rf_false, msg);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 10: assert_eq_float passes within epsilon
 * ======================================================================== */

static void test_assert_eq_float_passes(void) {
    TEST(assert_eq_float_passes);

    RF_String* msg = rf_string_from_cstr("float check");
    rf_test_assert_eq_float(3.14, 3.14, 0.001, msg);
    rf_test_assert_eq_float(1.0, 1.0001, 0.001, msg);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 11: assert_eq_float fails outside epsilon
 * ======================================================================== */

static void test_assert_eq_float_fails(void) {
    TEST(assert_eq_float_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_String* msg = rf_string_from_cstr("float check");
        rf_test_assert_eq_float(1.0, 2.0, 0.001, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(strstr(err->data, "expected") != NULL);
        assert(strstr(err->data, "epsilon") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 12: assert_some passes on Some value and returns it
 * ======================================================================== */

static void test_assert_some_passes(void) {
    TEST(assert_some_passes);

    int val = 42;
    RF_Option_ptr opt = RF_SOME_PTR((void*)(intptr_t)val);
    RF_String* msg = rf_string_from_cstr("should be some");
    void* result = rf_test_assert_some(opt, msg);
    assert((intptr_t)result == 42);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 13: assert_some fails on None
 * ======================================================================== */

static void test_assert_some_fails(void) {
    TEST(assert_some_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_Option_ptr opt = RF_NONE_PTR;
        RF_String* msg = rf_string_from_cstr("some check");
        rf_test_assert_some(opt, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(strstr(err->data, "expected Some, got None") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 14: assert_none passes on None
 * ======================================================================== */

static void test_assert_none_passes(void) {
    TEST(assert_none_passes);

    RF_Option_ptr opt = RF_NONE_PTR;
    RF_String* msg = rf_string_from_cstr("should be none");
    rf_test_assert_none(opt, msg);
    rf_string_release(msg);

    PASS();
}

/* ========================================================================
 * Test 15: assert_none fails on Some
 * ======================================================================== */

static void test_assert_none_fails(void) {
    TEST(assert_none_fails);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_Option_ptr opt = RF_SOME_PTR((void*)(intptr_t)1);
        RF_String* msg = rf_string_from_cstr("none check");
        rf_test_assert_none(opt, msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(strstr(err->data, "expected None, got Some") != NULL);
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 16: fail always throws
 * ======================================================================== */

static void test_fail(void) {
    TEST(test_fail);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    rf_bool caught = rf_false;
    if (setjmp(ef.jmp) == 0) {
        RF_String* msg = rf_string_from_cstr("intentional failure");
        rf_test_fail(msg);
        assert(0 && "should have thrown");
    } else {
        caught = rf_true;
        assert(ef.exception_tag == RF_TEST_FAILURE_TAG);
        RF_String* err = (RF_String*)ef.exception;
        assert(rf_string_eq(err, rf_string_from_cstr("intentional failure")));
    }
    _rf_exception_pop();
    assert(caught == rf_true);

    PASS();
}

/* ========================================================================
 * Test 17: rf_test_run with passing closure
 * ======================================================================== */

static void _passing_test(void* env) {
    (void)env;
    /* does nothing = passes */
}

static void test_run_passing(void) {
    TEST(test_run_passing);

    RF_Closure closure;
    closure.fn = (void*)_passing_test;
    closure.env = NULL;

    RF_String* name = rf_string_from_cstr("my passing test");
    RF_TestResult result = rf_test_run(name, &closure);

    assert(result.passed == 1);
    assert(result.failure_msg == NULL);
    assert(rf_string_eq(result.name, name));

    rf_string_release(name);
    PASS();
}

/* ========================================================================
 * Test 18: rf_test_run with failing closure
 * ======================================================================== */

static void _failing_test(void* env) {
    (void)env;
    rf_test_fail(rf_string_from_cstr("intentional failure"));
}

static void test_run_failing(void) {
    TEST(test_run_failing);

    RF_Closure closure;
    closure.fn = (void*)_failing_test;
    closure.env = NULL;

    RF_String* name = rf_string_from_cstr("my failing test");
    RF_TestResult result = rf_test_run(name, &closure);

    assert(result.passed == 0);
    assert(result.failure_msg != NULL);
    assert(rf_string_eq(result.failure_msg, rf_string_from_cstr("intentional failure")));

    rf_string_release(name);
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
    test_assert_eq_int_passes();
    test_assert_eq_int_fails();
    test_assert_eq_string_passes();
    test_assert_eq_string_fails();
    test_assert_eq_bool_passes();
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
