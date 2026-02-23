/*
 * C-level tests for non-blocking channel operations (SL-5-5):
 * rf_channel_try_send and rf_channel_try_recv.
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
 * Test 1: try_send to channel with available capacity succeeds
 * ======================================================================== */

static void test_try_send_to_empty_channel(void) {
    TEST(try_send_to_empty_channel);

    RF_Channel* ch = rf_channel_new(4);

    rf_bool result = rf_channel_try_send(ch, (void*)(intptr_t)42);
    assert(result == rf_true);

    /* Verify the value is actually in the channel */
    RF_Option_ptr r = rf_channel_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 42);

    rf_channel_close(ch);
    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 2: try_send to full channel returns false (non-blocking)
 * ======================================================================== */

static void test_try_send_to_full_channel(void) {
    TEST(try_send_to_full_channel);

    RF_Channel* ch = rf_channel_new(2);

    /* Fill to capacity */
    assert(rf_channel_try_send(ch, (void*)(intptr_t)1) == rf_true);
    assert(rf_channel_try_send(ch, (void*)(intptr_t)2) == rf_true);

    /* Channel is full — should return false immediately */
    rf_bool result = rf_channel_try_send(ch, (void*)(intptr_t)3);
    assert(result == rf_false);

    /* Verify original values are intact */
    RF_Option_ptr r1 = rf_channel_recv(ch);
    RF_Option_ptr r2 = rf_channel_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 1);
    assert(r2.tag == 1 && (intptr_t)r2.value == 2);

    rf_channel_close(ch);
    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 3: try_send to closed channel returns false
 * ======================================================================== */

static void test_try_send_to_closed_channel(void) {
    TEST(try_send_to_closed_channel);

    RF_Channel* ch = rf_channel_new(4);
    rf_channel_close(ch);

    rf_bool result = rf_channel_try_send(ch, (void*)(intptr_t)99);
    assert(result == rf_false);

    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 4: try_recv from non-empty channel returns SOME with correct value
 * ======================================================================== */

static void test_try_recv_from_nonempty(void) {
    TEST(try_recv_from_nonempty);

    RF_Channel* ch = rf_channel_new(4);

    rf_channel_send(ch, (void*)(intptr_t)100);
    rf_channel_send(ch, (void*)(intptr_t)200);

    RF_Option_ptr r1 = rf_channel_try_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 100);

    RF_Option_ptr r2 = rf_channel_try_recv(ch);
    assert(r2.tag == 1 && (intptr_t)r2.value == 200);

    rf_channel_close(ch);
    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 5: try_recv from empty channel returns NONE (non-blocking)
 * ======================================================================== */

static void test_try_recv_from_empty(void) {
    TEST(try_recv_from_empty);

    RF_Channel* ch = rf_channel_new(4);

    /* Channel is empty — should return NONE immediately */
    RF_Option_ptr r = rf_channel_try_recv(ch);
    assert(r.tag == 0);

    rf_channel_close(ch);
    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 6: try_recv from closed empty channel returns NONE
 * ======================================================================== */

static void test_try_recv_from_closed_empty(void) {
    TEST(try_recv_from_closed_empty);

    RF_Channel* ch = rf_channel_new(4);
    rf_channel_close(ch);

    RF_Option_ptr r = rf_channel_try_recv(ch);
    assert(r.tag == 0);

    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 7: try_recv from closed channel with buffered data returns SOME
 * ======================================================================== */

static void test_try_recv_from_closed_nonempty(void) {
    TEST(try_recv_from_closed_nonempty);

    RF_Channel* ch = rf_channel_new(4);

    rf_channel_send(ch, (void*)(intptr_t)77);
    rf_channel_send(ch, (void*)(intptr_t)88);
    rf_channel_close(ch);

    /* Should still get buffered values even though channel is closed */
    RF_Option_ptr r1 = rf_channel_try_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 77);

    RF_Option_ptr r2 = rf_channel_try_recv(ch);
    assert(r2.tag == 1 && (intptr_t)r2.value == 88);

    /* Now empty and closed — should get NONE */
    RF_Option_ptr r3 = rf_channel_try_recv(ch);
    assert(r3.tag == 0);

    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 8: Interleaved try_send/try_recv in a loop
 * ======================================================================== */

static void test_try_send_recv_interleaved(void) {
    TEST(try_send_recv_interleaved);

    RF_Channel* ch = rf_channel_new(2);

    int total_sent = 0;
    int total_received = 0;
    int sum = 0;

    for (int i = 1; i <= 50; i++) {
        /* Try to send; if full, drain one first */
        while (rf_channel_try_send(ch, (void*)(intptr_t)i) == rf_false) {
            RF_Option_ptr r = rf_channel_try_recv(ch);
            assert(r.tag == 1);
            sum += (int)(intptr_t)r.value;
            total_received++;
        }
        total_sent++;
    }

    /* Drain remaining */
    RF_Option_ptr r;
    while ((r = rf_channel_try_recv(ch)).tag == 1) {
        sum += (int)(intptr_t)r.value;
        total_received++;
    }

    assert(total_sent == 50);
    assert(total_received == 50);
    /* sum of 1..50 = 1275 */
    assert(sum == 1275);

    rf_channel_close(ch);
    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 9: try_send after drain allows re-sending
 * ======================================================================== */

static void test_try_send_after_drain(void) {
    TEST(try_send_after_drain);

    RF_Channel* ch = rf_channel_new(1);

    /* Fill */
    assert(rf_channel_try_send(ch, (void*)(intptr_t)10) == rf_true);
    /* Full */
    assert(rf_channel_try_send(ch, (void*)(intptr_t)20) == rf_false);

    /* Drain */
    RF_Option_ptr r = rf_channel_try_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 10);

    /* Should be able to send again */
    assert(rf_channel_try_send(ch, (void*)(intptr_t)30) == rf_true);
    r = rf_channel_try_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 30);

    rf_channel_close(ch);
    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 10: try_recv does NOT throw exceptions (unlike regular recv)
 * ======================================================================== */

static void test_try_recv_no_exception(void) {
    TEST(try_recv_no_exception);

    RF_Channel* ch = rf_channel_new(4);

    /* Set exception and close — regular recv would throw */
    RF_String* exc_msg = rf_string_from_cstr("test error");
    rf_channel_set_exception(ch, exc_msg, 42);
    rf_channel_close(ch);

    /* try_recv should just return NONE, not throw */
    RF_Option_ptr r = rf_channel_try_recv(ch);
    assert(r.tag == 0);

    rf_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("RF_Channel non-blocking extension tests (SL-5-5)\n");
    printf("=================================================\n");

    test_try_send_to_empty_channel();
    test_try_send_to_full_channel();
    test_try_send_to_closed_channel();
    test_try_recv_from_nonempty();
    test_try_recv_from_empty();
    test_try_recv_from_closed_empty();
    test_try_recv_from_closed_nonempty();
    test_try_send_recv_interleaved();
    test_try_send_after_drain();
    test_try_recv_no_exception();

    printf("=================================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
