/*
 * C-level tests for math runtime functions (stdlib/math).
 *
 * Note: rf_math_abs_int, rf_math_abs_float, rf_math_min_int/float,
 * rf_math_max_int/float, rf_math_clamp_int were removed in SG-4-1-2
 * (those behaviors are now in monomorphized ReFlow code).
 * This file tests the remaining float-specific runtime functions.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

#define FLOAT_EQ(a, b) (fabs((a) - (b)) < 1e-9)

/* ========================================================================
 * floor / ceil / round
 * ======================================================================== */

static void test_floor(void) {
    TEST(floor);
    assert(FLOAT_EQ(rf_math_floor(3.7), 3.0));
    assert(FLOAT_EQ(rf_math_floor(3.0), 3.0));
    assert(FLOAT_EQ(rf_math_floor(-3.2), -4.0));
    assert(FLOAT_EQ(rf_math_floor(-3.7), -4.0));
    PASS();
}

static void test_ceil(void) {
    TEST(ceil);
    assert(FLOAT_EQ(rf_math_ceil(3.2), 4.0));
    assert(FLOAT_EQ(rf_math_ceil(3.0), 3.0));
    assert(FLOAT_EQ(rf_math_ceil(-3.2), -3.0));
    assert(FLOAT_EQ(rf_math_ceil(-3.7), -3.0));
    PASS();
}

static void test_round(void) {
    TEST(round);
    assert(FLOAT_EQ(rf_math_round(3.5), 4.0));
    assert(FLOAT_EQ(rf_math_round(3.4), 3.0));
    assert(FLOAT_EQ(rf_math_round(-3.5), -4.0));
    assert(FLOAT_EQ(rf_math_round(-3.4), -3.0));
    PASS();
}

/* ========================================================================
 * pow
 * ======================================================================== */

static void test_pow(void) {
    TEST(pow);
    assert(FLOAT_EQ(rf_math_pow(2.0, 10.0), 1024.0));
    assert(FLOAT_EQ(rf_math_pow(3.0, 0.0), 1.0));
    assert(FLOAT_EQ(rf_math_pow(5.0, 1.0), 5.0));
    assert(FLOAT_EQ(rf_math_pow(2.0, -1.0), 0.5));
    PASS();
}

/* ========================================================================
 * sqrt
 * ======================================================================== */

static void test_sqrt(void) {
    TEST(sqrt);
    assert(FLOAT_EQ(rf_math_sqrt(4.0), 2.0));
    assert(FLOAT_EQ(rf_math_sqrt(9.0), 3.0));
    assert(FLOAT_EQ(rf_math_sqrt(0.0), 0.0));
    assert(FLOAT_EQ(rf_math_sqrt(1.0), 1.0));
    assert(FLOAT_EQ(rf_math_sqrt(144.0), 12.0));
    PASS();
}

/* ========================================================================
 * log
 * ======================================================================== */

static void test_log(void) {
    TEST(log);
    assert(FLOAT_EQ(rf_math_log(1.0), 0.0));
    assert(FLOAT_EQ(rf_math_log(M_E), 1.0));
    assert(FLOAT_EQ(rf_math_log(M_E * M_E), 2.0));
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Math function tests (float-specific, SG-4-1 / SG-5-2-1)\n");
    printf("========================================\n");

    test_floor();
    test_ceil();
    test_round();
    test_pow();
    test_sqrt();
    test_log();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
