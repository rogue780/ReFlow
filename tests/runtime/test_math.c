/*
 * C-level tests for math runtime functions (stdlib/math).
 *
 * Compile and run via:
 *   cc -o tests/runtime/test_math tests/runtime/test_math.c \
 *      runtime/reflow_runtime.c -lpthread -lm -I runtime -std=c11
 *   ./tests/runtime/test_math
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
 * abs_int
 * ======================================================================== */

static void test_abs_int_positive(void) {
    TEST(abs_int_positive);
    assert(rf_math_abs_int(42) == 42);
    PASS();
}

static void test_abs_int_negative(void) {
    TEST(abs_int_negative);
    assert(rf_math_abs_int(-42) == 42);
    PASS();
}

static void test_abs_int_zero(void) {
    TEST(abs_int_zero);
    assert(rf_math_abs_int(0) == 0);
    PASS();
}

/* ========================================================================
 * abs_float
 * ======================================================================== */

static void test_abs_float_positive(void) {
    TEST(abs_float_positive);
    assert(FLOAT_EQ(rf_math_abs_float(3.14), 3.14));
    PASS();
}

static void test_abs_float_negative(void) {
    TEST(abs_float_negative);
    assert(FLOAT_EQ(rf_math_abs_float(-3.14), 3.14));
    PASS();
}

static void test_abs_float_zero(void) {
    TEST(abs_float_zero);
    assert(FLOAT_EQ(rf_math_abs_float(0.0), 0.0));
    PASS();
}

/* ========================================================================
 * min_int / max_int
 * ======================================================================== */

static void test_min_int(void) {
    TEST(min_int);
    assert(rf_math_min_int(3, 7) == 3);
    assert(rf_math_min_int(7, 3) == 3);
    assert(rf_math_min_int(5, 5) == 5);
    assert(rf_math_min_int(-10, 10) == -10);
    PASS();
}

static void test_max_int(void) {
    TEST(max_int);
    assert(rf_math_max_int(3, 7) == 7);
    assert(rf_math_max_int(7, 3) == 7);
    assert(rf_math_max_int(5, 5) == 5);
    assert(rf_math_max_int(-10, 10) == 10);
    PASS();
}

/* ========================================================================
 * min_float / max_float
 * ======================================================================== */

static void test_min_float(void) {
    TEST(min_float);
    assert(FLOAT_EQ(rf_math_min_float(1.5, 2.5), 1.5));
    assert(FLOAT_EQ(rf_math_min_float(2.5, 1.5), 1.5));
    assert(FLOAT_EQ(rf_math_min_float(-1.0, 1.0), -1.0));
    PASS();
}

static void test_max_float(void) {
    TEST(max_float);
    assert(FLOAT_EQ(rf_math_max_float(1.5, 2.5), 2.5));
    assert(FLOAT_EQ(rf_math_max_float(2.5, 1.5), 2.5));
    assert(FLOAT_EQ(rf_math_max_float(-1.0, 1.0), 1.0));
    PASS();
}

/* ========================================================================
 * clamp_int
 * ======================================================================== */

static void test_clamp_int_below(void) {
    TEST(clamp_int_below_range);
    assert(rf_math_clamp_int(-5, 0, 10) == 0);
    PASS();
}

static void test_clamp_int_within(void) {
    TEST(clamp_int_within_range);
    assert(rf_math_clamp_int(5, 0, 10) == 5);
    PASS();
}

static void test_clamp_int_above(void) {
    TEST(clamp_int_above_range);
    assert(rf_math_clamp_int(15, 0, 10) == 10);
    PASS();
}

static void test_clamp_int_at_boundaries(void) {
    TEST(clamp_int_at_boundaries);
    assert(rf_math_clamp_int(0, 0, 10) == 0);
    assert(rf_math_clamp_int(10, 0, 10) == 10);
    PASS();
}

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
    /* log(e^2) = 2 */
    assert(FLOAT_EQ(rf_math_log(M_E * M_E), 2.0));
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Math function tests\n");
    printf("========================================\n");

    test_abs_int_positive();
    test_abs_int_negative();
    test_abs_int_zero();
    test_abs_float_positive();
    test_abs_float_negative();
    test_abs_float_zero();
    test_min_int();
    test_max_int();
    test_min_float();
    test_max_float();
    test_clamp_int_below();
    test_clamp_int_within();
    test_clamp_int_above();
    test_clamp_int_at_boundaries();
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
