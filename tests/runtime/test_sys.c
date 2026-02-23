/*
 * C-level tests for rf_env_get and rf_clock_ms (stdlib/sys extensions).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
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
 * Test 1: rf_env_get for PATH (always set)
 * ======================================================================== */

static void test_env_get_path(void) {
    TEST(env_get_PATH_returns_some);

    RF_String* name = rf_string_from_cstr("PATH");
    RF_Option_ptr result = rf_env_get(name);

    assert(result.tag == 1);  /* some */
    RF_String* val = (RF_String*)result.value;
    assert(val->len > 0);

    rf_string_release(val);
    rf_string_release(name);
    PASS();
}

/* ========================================================================
 * Test 2: rf_env_get for nonexistent variable
 * ======================================================================== */

static void test_env_get_nonexistent(void) {
    TEST(env_get_nonexistent_returns_none);

    RF_String* name = rf_string_from_cstr("RF_TEST_NONEXISTENT_VAR_12345");
    RF_Option_ptr result = rf_env_get(name);

    assert(result.tag == 0);  /* none */

    rf_string_release(name);
    PASS();
}

/* ========================================================================
 * Test 3: rf_env_get after setenv
 * ======================================================================== */

static void test_env_get_after_setenv(void) {
    TEST(env_get_after_setenv);

    setenv("RF_TEST_VAR", "hello", 1);

    RF_String* name = rf_string_from_cstr("RF_TEST_VAR");
    RF_Option_ptr result = rf_env_get(name);

    assert(result.tag == 1);  /* some */
    RF_String* val = (RF_String*)result.value;
    RF_String* expected = rf_string_from_cstr("hello");
    assert(rf_string_eq(val, expected));

    rf_string_release(val);
    rf_string_release(expected);
    rf_string_release(name);

    unsetenv("RF_TEST_VAR");
    PASS();
}

/* ========================================================================
 * Test 4: rf_clock_ms returns a positive value
 * ======================================================================== */

static void test_clock_ms_positive(void) {
    TEST(clock_ms_returns_positive);

    rf_int64 ms = rf_clock_ms();
    assert(ms > 0);

    PASS();
}

/* ========================================================================
 * Test 5: rf_clock_ms is monotonically increasing
 * ======================================================================== */

static void test_clock_ms_monotonic(void) {
    TEST(clock_ms_monotonically_increasing);

    rf_int64 t1 = rf_clock_ms();
    usleep(10000);  /* 10ms */
    rf_int64 t2 = rf_clock_ms();

    assert(t2 >= t1 + 5);  /* at least 5ms elapsed (generous margin) */

    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("rf_env_get and rf_clock_ms tests\n");
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
