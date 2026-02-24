/*
 * C-level tests for Time (stdlib/time) runtime functions.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
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
 * Test 1: fl_time_now returns non-NULL
 * ======================================================================== */

static void test_now_returns_instant(void) {
    TEST(now_returns_instant);

    FL_Instant* inst = fl_time_now();
    assert(inst != NULL);
    fl_instant_release(inst);
    PASS();
}

/* ========================================================================
 * Test 2: elapsed_ms is positive after sleep
 * ======================================================================== */

static void test_elapsed_ms_positive(void) {
    TEST(elapsed_ms_positive);

    FL_Instant* start = fl_time_now();
    usleep(10000); /* 10ms */
    fl_int64 ms = fl_time_elapsed_ms(start);
    assert(ms > 0);
    fl_instant_release(start);
    PASS();
}

/* ========================================================================
 * Test 3: elapsed_us is positive after sleep
 * ======================================================================== */

static void test_elapsed_us_positive(void) {
    TEST(elapsed_us_positive);

    FL_Instant* start = fl_time_now();
    usleep(1000); /* 1ms */
    fl_int64 us = fl_time_elapsed_us(start);
    assert(us > 0);
    fl_instant_release(start);
    PASS();
}

/* ========================================================================
 * Test 4: diff_ms basic
 * ======================================================================== */

static void test_diff_ms_basic(void) {
    TEST(diff_ms_basic);

    FL_Instant* start = fl_time_now();
    usleep(20000); /* 20ms */
    FL_Instant* end = fl_time_now();
    fl_int64 diff = fl_time_diff_ms(start, end);
    assert(diff > 0);
    fl_instant_release(start);
    fl_instant_release(end);
    PASS();
}

/* ========================================================================
 * Test 5: datetime_now returns valid components
 * ======================================================================== */

static void test_datetime_now_valid(void) {
    TEST(datetime_now_valid);

    FL_DateTime* dt = fl_time_datetime_now();
    assert(dt != NULL);
    fl_int year = fl_time_year(dt);
    fl_int month = fl_time_month(dt);
    fl_int day = fl_time_day(dt);

    assert(year >= 2026);
    assert(month >= 1 && month <= 12);
    assert(day >= 1 && day <= 31);

    fl_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 6: datetime_utc returns valid components
 * ======================================================================== */

static void test_datetime_utc_valid(void) {
    TEST(datetime_utc_valid);

    FL_DateTime* dt = fl_time_datetime_utc();
    assert(dt != NULL);
    fl_int year = fl_time_year(dt);
    fl_int month = fl_time_month(dt);
    fl_int day = fl_time_day(dt);

    assert(year >= 2026);
    assert(month >= 1 && month <= 12);
    assert(day >= 1 && day <= 31);

    fl_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 7: unix_timestamp is positive and reasonable
 * ======================================================================== */

static void test_unix_timestamp_positive(void) {
    TEST(unix_timestamp_positive);

    fl_int64 ts = fl_time_unix_timestamp();
    /* Must be after Nov 2023 */
    assert(ts > 1700000000);
    PASS();
}

/* ========================================================================
 * Test 8: unix_timestamp_ms is positive and reasonable
 * ======================================================================== */

static void test_unix_timestamp_ms_positive(void) {
    TEST(unix_timestamp_ms_positive);

    fl_int64 ts_ms = fl_time_unix_timestamp_ms();
    /* Must be after Nov 2023 in milliseconds */
    assert(ts_ms > 1700000000000LL);
    PASS();
}

/* ========================================================================
 * Test 9: format_iso8601 contains 'T' and timezone offset
 * ======================================================================== */

static void test_format_iso8601(void) {
    TEST(format_iso8601);

    FL_DateTime* dt = fl_time_datetime_utc();
    FL_String* s = fl_time_format_iso8601(dt);
    assert(s != NULL);
    assert(s->len >= 25); /* e.g. 2026-02-22T14:30:45+00:00 */

    /* Must contain 'T' separator */
    fl_bool has_t = fl_false;
    for (fl_int64 i = 0; i < s->len; i++) {
        if (s->data[i] == 'T') { has_t = fl_true; break; }
    }
    assert(has_t == fl_true);

    /* Must contain '+' or '-' for timezone */
    fl_bool has_tz = fl_false;
    for (fl_int64 i = 10; i < s->len; i++) {
        if (s->data[i] == '+' || s->data[i] == '-') { has_tz = fl_true; break; }
    }
    assert(has_tz == fl_true);

    fl_string_release(s);
    fl_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 10: format_rfc2822 contains day abbreviation and offset
 * ======================================================================== */

static void test_format_rfc2822(void) {
    TEST(format_rfc2822);

    FL_DateTime* dt = fl_time_datetime_utc();
    FL_String* s = fl_time_format_rfc2822(dt);
    assert(s != NULL);

    /* Should contain a comma (day abbreviation) */
    fl_bool has_comma = fl_false;
    for (fl_int64 i = 0; i < s->len; i++) {
        if (s->data[i] == ',') { has_comma = fl_true; break; }
    }
    assert(has_comma == fl_true);

    /* Should contain '+' or '-' for timezone offset */
    fl_bool has_tz = fl_false;
    for (fl_int64 i = 10; i < s->len; i++) {
        if (s->data[i] == '+' || s->data[i] == '-') { has_tz = fl_true; break; }
    }
    assert(has_tz == fl_true);

    fl_string_release(s);
    fl_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 11: format_http ends with "GMT"
 * ======================================================================== */

static void test_format_http_gmt(void) {
    TEST(format_http_gmt);

    FL_DateTime* dt = fl_time_datetime_now();
    FL_String* s = fl_time_format_http(dt);
    assert(s != NULL);
    assert(s->len >= 3);

    /* Must end with "GMT" */
    assert(s->data[s->len - 3] == 'G');
    assert(s->data[s->len - 2] == 'M');
    assert(s->data[s->len - 1] == 'T');

    fl_string_release(s);
    fl_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 12: component accessors in valid ranges
 * ======================================================================== */

static void test_component_consistency(void) {
    TEST(component_consistency);

    FL_DateTime* dt = fl_time_datetime_now();
    fl_int year = fl_time_year(dt);
    fl_int month = fl_time_month(dt);
    fl_int day = fl_time_day(dt);
    fl_int hour = fl_time_hour(dt);
    fl_int minute = fl_time_minute(dt);
    fl_int second = fl_time_second(dt);

    assert(year >= 2024 && year <= 2100);
    assert(month >= 1 && month <= 12);
    assert(day >= 1 && day <= 31);
    assert(hour >= 0 && hour <= 23);
    assert(minute >= 0 && minute <= 59);
    assert(second >= 0 && second <= 60); /* 60 for leap second */

    fl_datetime_release(dt);
    PASS();
}

/* ========================================================================
 * Test 13: instant_release does not crash
 * ======================================================================== */

static void test_instant_release_no_crash(void) {
    TEST(instant_release_no_crash);

    FL_Instant* inst = fl_time_now();
    fl_instant_release(inst);
    /* If we got here, no crash */
    PASS();
}

/* ========================================================================
 * Test 14: datetime_release does not crash
 * ======================================================================== */

static void test_datetime_release_no_crash(void) {
    TEST(datetime_release_no_crash);

    FL_DateTime* dt = fl_time_datetime_now();
    fl_datetime_release(dt);
    /* If we got here, no crash */

    dt = fl_time_datetime_utc();
    fl_datetime_release(dt);
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
