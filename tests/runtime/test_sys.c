/*
 * C-level tests for fl_env_get and fl_clock_ms (stdlib/sys extensions).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: fl_env_get for PATH (always set)
 * ======================================================================== */

static void test_env_get_path(void) {
    TEST(env_get_PATH_returns_some);

    FL_String* name = fl_string_from_cstr("PATH");
    FL_Option_ptr result = fl_env_get(name);

    assert(result.tag == 1);  /* some */
    FL_String* val = (FL_String*)result.value;
    assert(val->len > 0);

    fl_string_release(val);
    fl_string_release(name);
    PASS();
}

/* ========================================================================
 * Test 2: fl_env_get for nonexistent variable
 * ======================================================================== */

static void test_env_get_nonexistent(void) {
    TEST(env_get_nonexistent_returns_none);

    FL_String* name = fl_string_from_cstr("FL_TEST_NONEXISTENT_VAR_12345");
    FL_Option_ptr result = fl_env_get(name);

    assert(result.tag == 0);  /* none */

    fl_string_release(name);
    PASS();
}

/* ========================================================================
 * Test 3: fl_env_get after setenv
 * ======================================================================== */

static void test_env_get_after_setenv(void) {
    TEST(env_get_after_setenv);

    setenv("FL_TEST_VAR", "hello", 1);

    FL_String* name = fl_string_from_cstr("FL_TEST_VAR");
    FL_Option_ptr result = fl_env_get(name);

    assert(result.tag == 1);  /* some */
    FL_String* val = (FL_String*)result.value;
    FL_String* expected = fl_string_from_cstr("hello");
    assert(fl_string_eq(val, expected));

    fl_string_release(val);
    fl_string_release(expected);
    fl_string_release(name);

    unsetenv("FL_TEST_VAR");
    PASS();
}

/* ========================================================================
 * Test 4: fl_clock_ms returns a positive value
 * ======================================================================== */

static void test_clock_ms_positive(void) {
    TEST(clock_ms_returns_positive);

    fl_int64 ms = fl_clock_ms();
    assert(ms > 0);

    PASS();
}

/* ========================================================================
 * Test 5: fl_clock_ms is monotonically increasing
 * ======================================================================== */

static void test_clock_ms_monotonic(void) {
    TEST(clock_ms_monotonically_increasing);

    fl_int64 t1 = fl_clock_ms();
    usleep(10000);  /* 10ms */
    fl_int64 t2 = fl_clock_ms();

    assert(t2 >= t1 + 5);  /* at least 5ms elapsed (generous margin) */

    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("fl_env_get and fl_clock_ms tests\n");
    printf("================================\n");

    test_env_get_path();
    test_env_get_nonexistent();
    test_env_get_after_setenv();
    test_clock_ms_positive();
    test_clock_ms_monotonic();

    printf("================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
