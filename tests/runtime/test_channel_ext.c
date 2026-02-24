/*
 * C-level tests for non-blocking channel operations (SL-5-5):
 * fl_channel_try_send and fl_channel_try_recv.
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
 * Test 1: try_send to channel with available capacity succeeds
 * ======================================================================== */

static void test_try_send_to_empty_channel(void) {
    TEST(try_send_to_empty_channel);

    FL_Channel* ch = fl_channel_new(4);

    fl_bool result = fl_channel_try_send(ch, (void*)(intptr_t)42);
    assert(result == fl_true);

    /* Verify the value is actually in the channel */
    FL_Option_ptr r = fl_channel_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 42);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 2: try_send to full channel returns false (non-blocking)
 * ======================================================================== */

static void test_try_send_to_full_channel(void) {
    TEST(try_send_to_full_channel);

    FL_Channel* ch = fl_channel_new(2);

    /* Fill to capacity */
    assert(fl_channel_try_send(ch, (void*)(intptr_t)1) == fl_true);
    assert(fl_channel_try_send(ch, (void*)(intptr_t)2) == fl_true);

    /* Channel is full — should return false immediately */
    fl_bool result = fl_channel_try_send(ch, (void*)(intptr_t)3);
    assert(result == fl_false);

    /* Verify original values are intact */
    FL_Option_ptr r1 = fl_channel_recv(ch);
    FL_Option_ptr r2 = fl_channel_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 1);
    assert(r2.tag == 1 && (intptr_t)r2.value == 2);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 3: try_send to closed channel returns false
 * ======================================================================== */

static void test_try_send_to_closed_channel(void) {
    TEST(try_send_to_closed_channel);

    FL_Channel* ch = fl_channel_new(4);
    fl_channel_close(ch);

    fl_bool result = fl_channel_try_send(ch, (void*)(intptr_t)99);
    assert(result == fl_false);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 4: try_recv from non-empty channel returns SOME with correct value
 * ======================================================================== */

static void test_try_recv_from_nonempty(void) {
    TEST(try_recv_from_nonempty);

    FL_Channel* ch = fl_channel_new(4);

    fl_channel_send(ch, (void*)(intptr_t)100);
    fl_channel_send(ch, (void*)(intptr_t)200);

    FL_Option_ptr r1 = fl_channel_try_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 100);

    FL_Option_ptr r2 = fl_channel_try_recv(ch);
    assert(r2.tag == 1 && (intptr_t)r2.value == 200);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 5: try_recv from empty channel returns NONE (non-blocking)
 * ======================================================================== */

static void test_try_recv_from_empty(void) {
    TEST(try_recv_from_empty);

    FL_Channel* ch = fl_channel_new(4);

    /* Channel is empty — should return NONE immediately */
    FL_Option_ptr r = fl_channel_try_recv(ch);
    assert(r.tag == 0);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 6: try_recv from closed empty channel returns NONE
 * ======================================================================== */

static void test_try_recv_from_closed_empty(void) {
    TEST(try_recv_from_closed_empty);

    FL_Channel* ch = fl_channel_new(4);
    fl_channel_close(ch);

    FL_Option_ptr r = fl_channel_try_recv(ch);
    assert(r.tag == 0);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 7: try_recv from closed channel with buffered data returns SOME
 * ======================================================================== */

static void test_try_recv_from_closed_nonempty(void) {
    TEST(try_recv_from_closed_nonempty);

    FL_Channel* ch = fl_channel_new(4);

    fl_channel_send(ch, (void*)(intptr_t)77);
    fl_channel_send(ch, (void*)(intptr_t)88);
    fl_channel_close(ch);

    /* Should still get buffered values even though channel is closed */
    FL_Option_ptr r1 = fl_channel_try_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 77);

    FL_Option_ptr r2 = fl_channel_try_recv(ch);
    assert(r2.tag == 1 && (intptr_t)r2.value == 88);

    /* Now empty and closed — should get NONE */
    FL_Option_ptr r3 = fl_channel_try_recv(ch);
    assert(r3.tag == 0);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 8: Interleaved try_send/try_recv in a loop
 * ======================================================================== */

static void test_try_send_recv_interleaved(void) {
    TEST(try_send_recv_interleaved);

    FL_Channel* ch = fl_channel_new(2);

    int total_sent = 0;
    int total_received = 0;
    int sum = 0;

    for (int i = 1; i <= 50; i++) {
        /* Try to send; if full, drain one first */
        while (fl_channel_try_send(ch, (void*)(intptr_t)i) == fl_false) {
            FL_Option_ptr r = fl_channel_try_recv(ch);
            assert(r.tag == 1);
            sum += (int)(intptr_t)r.value;
            total_received++;
        }
        total_sent++;
    }

    /* Drain remaining */
    FL_Option_ptr r;
    while ((r = fl_channel_try_recv(ch)).tag == 1) {
        sum += (int)(intptr_t)r.value;
        total_received++;
    }

    assert(total_sent == 50);
    assert(total_received == 50);
    /* sum of 1..50 = 1275 */
    assert(sum == 1275);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 9: try_send after drain allows re-sending
 * ======================================================================== */

static void test_try_send_after_drain(void) {
    TEST(try_send_after_drain);

    FL_Channel* ch = fl_channel_new(1);

    /* Fill */
    assert(fl_channel_try_send(ch, (void*)(intptr_t)10) == fl_true);
    /* Full */
    assert(fl_channel_try_send(ch, (void*)(intptr_t)20) == fl_false);

    /* Drain */
    FL_Option_ptr r = fl_channel_try_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 10);

    /* Should be able to send again */
    assert(fl_channel_try_send(ch, (void*)(intptr_t)30) == fl_true);
    r = fl_channel_try_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 30);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 10: try_recv does NOT throw exceptions (unlike regular recv)
 * ======================================================================== */

static void test_try_recv_no_exception(void) {
    TEST(try_recv_no_exception);

    FL_Channel* ch = fl_channel_new(4);

    /* Set exception and close — regular recv would throw */
    FL_String* exc_msg = fl_string_from_cstr("test error");
    fl_channel_set_exception(ch, exc_msg, 42);
    fl_channel_close(ch);

    /* try_recv should just return NONE, not throw */
    FL_Option_ptr r = fl_channel_try_recv(ch);
    assert(r.tag == 0);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("FL_Channel non-blocking extension tests (SL-5-5)\n");
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
