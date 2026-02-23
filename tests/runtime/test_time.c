/*
 * C-level tests for Time (stdlib/time) runtime functions.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: rf_time_now returns non-NULL
 * ======================================================================== */

static void test_now_returns_instant(void) {
    TEST(now_returns_instant);

    RF_Instant* inst = rf_time_now();
    assert(inst != NULL);
    rf_instant_release(inst);
    PASS();
}

/* ========================================================================
 * Test 2: elapsed_ms is positive after sleep
 * ======================================================================== */

static void test_elapsed_ms_positive(void) {
    TEST(elapsed_ms_positive);

    RF_Instant* start = rf_time_now();
    usleep(10000); /* 10ms */
    rf_int64 ms = rf_time_elapsed_ms(start);
    assert(ms > 0);
    rf_instant_release(start);
    PASS();
}

/* ========================================================================
 * Test 3: elapsed_us is positive after sleep
 * ======================================================================== */

static void test_elapsed_us_positive(void) {
    TEST(elapsed_us_positive);

    RF_Instant* start = rf_time_now();
    usleep(1000); /* 1ms */
    rf_int64 us = rf_time_elapsed_us(start);
    assert(us > 0);
    rf_instant_release(start);
    PASS();
}

/* ========================================================================
 * Test 4: diff_ms basic
 * ======================================================================== */

static void test_diff_ms_basic(void) {
    TEST(diff_ms_basic);

    RF_Instant* start = rf_time_now();
    usleep(20000); /* 20ms */
    RF_Instant* end = rf_time_now();
    rf_int64 diff = rf_time_diff_ms(start, end);
    assert(diff > 0);
    rf_instant_release(start);
    rf_instant_release(end);
    PASS();
}

/* ========================================================================
 * Test 5: datetime_now returns valid components
 * ======================================================================== */

static void test_datetime_now_valid(void) {
    TEST(datetime_now_valid);

    RF_DateTime* dt = rf_time_datetime_now();
    assert(dt != NULL);
    rf_int year = rf_time_year(dt);
    rf_int month = rf_time_month(dt);
    rf_int day = rf_time_day(dt);

    assert(year >= 2026);
    assert(month >= 1 && month <= 12);
    assert(day >= 1 && day <= 31);

    rf_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 6: datetime_utc returns valid components
 * ======================================================================== */

static void test_datetime_utc_valid(void) {
    TEST(datetime_utc_valid);

    RF_DateTime* dt = rf_time_datetime_utc();
    assert(dt != NULL);
    rf_int year = rf_time_year(dt);
    rf_int month = rf_time_month(dt);
    rf_int day = rf_time_day(dt);

    assert(year >= 2026);
    assert(month >= 1 && month <= 12);
    assert(day >= 1 && day <= 31);

    rf_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 7: unix_timestamp is positive and reasonable
 * ======================================================================== */

static void test_unix_timestamp_positive(void) {
    TEST(unix_timestamp_positive);

    rf_int64 ts = rf_time_unix_timestamp();
    /* Must be after Nov 2023 */
    assert(ts > 1700000000);
    PASS();
}

/* ========================================================================
 * Test 8: unix_timestamp_ms is positive and reasonable
 * ======================================================================== */

static void test_unix_timestamp_ms_positive(void) {
    TEST(unix_timestamp_ms_positive);

    rf_int64 ts_ms = rf_time_unix_timestamp_ms();
    /* Must be after Nov 2023 in milliseconds */
    assert(ts_ms > 1700000000000LL);
    PASS();
}

/* ========================================================================
 * Test 9: format_iso8601 contains 'T' and timezone offset
 * ======================================================================== */

static void test_format_iso8601(void) {
    TEST(format_iso8601);

    RF_DateTime* dt = rf_time_datetime_utc();
    RF_String* s = rf_time_format_iso8601(dt);
    assert(s != NULL);
    assert(s->len >= 25); /* e.g. 2026-02-22T14:30:45+00:00 */

    /* Must contain 'T' separator */
    rf_bool has_t = rf_false;
    for (rf_int64 i = 0; i < s->len; i++) {
        if (s->data[i] == 'T') { has_t = rf_true; break; }
    }
    assert(has_t == rf_true);

    /* Must contain '+' or '-' for timezone */
    rf_bool has_tz = rf_false;
    for (rf_int64 i = 10; i < s->len; i++) {
        if (s->data[i] == '+' || s->data[i] == '-') { has_tz = rf_true; break; }
    }
    assert(has_tz == rf_true);

    rf_string_release(s);
    rf_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 10: format_rfc2822 contains day abbreviation and offset
 * ======================================================================== */

static void test_format_rfc2822(void) {
    TEST(format_rfc2822);

    RF_DateTime* dt = rf_time_datetime_utc();
    RF_String* s = rf_time_format_rfc2822(dt);
    assert(s != NULL);

    /* Should contain a comma (day abbreviation) */
    rf_bool has_comma = rf_false;
    for (rf_int64 i = 0; i < s->len; i++) {
        if (s->data[i] == ',') { has_comma = rf_true; break; }
    }
    assert(has_comma == rf_true);

    /* Should contain '+' or '-' for timezone offset */
    rf_bool has_tz = rf_false;
    for (rf_int64 i = 10; i < s->len; i++) {
        if (s->data[i] == '+' || s->data[i] == '-') { has_tz = rf_true; break; }
    }
    assert(has_tz == rf_true);

    rf_string_release(s);
    rf_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 11: format_http ends with "GMT"
 * ======================================================================== */

static void test_format_http_gmt(void) {
    TEST(format_http_gmt);

    RF_DateTime* dt = rf_time_datetime_now();
    RF_String* s = rf_time_format_http(dt);
    assert(s != NULL);
    assert(s->len >= 3);

    /* Must end with "GMT" */
    assert(s->data[s->len - 3] == 'G');
    assert(s->data[s->len - 2] == 'M');
    assert(s->data[s->len - 1] == 'T');

    rf_string_release(s);
    rf_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 12: component accessors in valid ranges
 * ======================================================================== */

static void test_component_consistency(void) {
    TEST(component_consistency);

    RF_DateTime* dt = rf_time_datetime_now();
    rf_int year = rf_time_year(dt);
    rf_int month = rf_time_month(dt);
    rf_int day = rf_time_day(dt);
    rf_int hour = rf_time_hour(dt);
    rf_int minute = rf_time_minute(dt);
    rf_int second = rf_time_second(dt);

    assert(year >= 2024 && year <= 2100);
    assert(month >= 1 && month <= 12);
    assert(day >= 1 && day <= 31);
    assert(hour >= 0 && hour <= 23);
    assert(minute >= 0 && minute <= 59);
    assert(second >= 0 && second <= 60); /* 60 for leap second */

    rf_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 13: instant_release does not crash
 * ======================================================================== */

static void test_instant_release_no_crash(void) {
    TEST(instant_release_no_crash);

    RF_Instant* inst = rf_time_now();
    rf_instant_release(inst);
    /* If we got here, no crash */
    PASS();
}

/* ========================================================================
 * Test 14: datetime_release does not crash
 * ======================================================================== */

static void test_datetime_release_no_crash(void) {
    TEST(datetime_release_no_crash);

    RF_DateTime* dt = rf_time_datetime_now();
    rf_datetime_release(dt);
    /* If we got here, no crash */

    dt = rf_time_datetime_utc();
    rf_datetime_release(dt);
    /* If we got here, no crash */
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Time (stdlib/time) tests\n");
    printf("========================\n");

    test_now_returns_instant();
    test_elapsed_ms_positive();
    test_elapsed_us_positive();
    test_diff_ms_basic();
    test_datetime_now_valid();
    test_datetime_utc_valid();
    test_unix_timestamp_positive();
    test_unix_timestamp_ms_positive();
    test_format_iso8601();
    test_format_rfc2822();
    test_format_http_gmt();
    test_component_consistency();
    test_instant_release_no_crash();
    test_datetime_release_no_crash();

    printf("========================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
