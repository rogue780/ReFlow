/*
 * C-level tests for FL_Channel and threaded FL_Coroutine.
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
 * Test 1: Basic FIFO ordering
 * ======================================================================== */

static void test_basic_fifo(void) {
    TEST(basic_fifo);

    FL_Channel* ch = fl_channel_new(4);

    int a = 10, b = 20, c = 30;
    assert(fl_channel_send(ch, (void*)(intptr_t)a) == fl_true);
    assert(fl_channel_send(ch, (void*)(intptr_t)b) == fl_true);
    assert(fl_channel_send(ch, (void*)(intptr_t)c) == fl_true);

    FL_Option_ptr r1 = fl_channel_recv(ch);
    FL_Option_ptr r2 = fl_channel_recv(ch);
    FL_Option_ptr r3 = fl_channel_recv(ch);

    assert(r1.tag == 1 && (intptr_t)r1.value == 10);
    assert(r2.tag == 1 && (intptr_t)r2.value == 20);
    assert(r3.tag == 1 && (intptr_t)r3.value == 30);

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 2: Close + drain (recv buffered values after close, then none)
 * ======================================================================== */

static void test_close_drain(void) {
    TEST(close_drain);

    FL_Channel* ch = fl_channel_new(8);

    fl_channel_send(ch, (void*)(intptr_t)1);
    fl_channel_send(ch, (void*)(intptr_t)2);
    fl_channel_close(ch);

    /* Should still get buffered values */
    FL_Option_ptr r1 = fl_channel_recv(ch);
    FL_Option_ptr r2 = fl_channel_recv(ch);
    assert(r1.tag == 1 && (intptr_t)r1.value == 1);
    assert(r2.tag == 1 && (intptr_t)r2.value == 2);

    /* Now should get none */
    FL_Option_ptr r3 = fl_channel_recv(ch);
    assert(r3.tag == 0);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 3: Send after close returns false
 * ======================================================================== */

static void test_send_after_close(void) {
    TEST(send_after_close);

    FL_Channel* ch = fl_channel_new(4);
    fl_channel_close(ch);

    fl_bool sent = fl_channel_send(ch, (void*)(intptr_t)42);
    assert(sent == fl_false);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 4: fl_channel_len and fl_channel_is_closed
 * ======================================================================== */

static void test_len_and_is_closed(void) {
    TEST(len_and_is_closed);

    FL_Channel* ch = fl_channel_new(4);
    assert(fl_channel_len(ch) == 0);
    assert(fl_channel_is_closed(ch) == fl_false);

    fl_channel_send(ch, (void*)(intptr_t)1);
    fl_channel_send(ch, (void*)(intptr_t)2);
    assert(fl_channel_len(ch) == 2);

    fl_channel_recv(ch);
    assert(fl_channel_len(ch) == 1);

    fl_channel_close(ch);
    assert(fl_channel_is_closed(ch) == fl_true);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 5: Threaded producer/consumer
 * ======================================================================== */

typedef struct {
    FL_Channel* ch;
    int         count;
} _ProducerArg;

static void* _test_producer(void* raw) {
    _ProducerArg* arg = (_ProducerArg*)raw;
    for (int i = 0; i < arg->count; i++) {
        fl_channel_send(arg->ch, (void*)(intptr_t)(i + 1));
    }
    fl_channel_close(arg->ch);
    return NULL;
}

static void test_threaded_producer_consumer(void) {
    TEST(threaded_producer_consumer);

    FL_Channel* ch = fl_channel_new(4);
    _ProducerArg arg = { .ch = ch, .count = 100 };

    pthread_t producer;
    pthread_create(&producer, NULL, _test_producer, &arg);

    int sum = 0;
    FL_Option_ptr item;
    while ((item = fl_channel_recv(ch)).tag == 1) {
        sum += (int)(intptr_t)item.value;
    }
    pthread_join(producer, NULL);

    /* sum of 1..100 = 5050 */
    assert(sum == 5050);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 6: Backpressure (capacity 1)
 * ======================================================================== */

static void* _test_slow_consumer(void* raw) {
    FL_Channel* ch = (FL_Channel*)raw;
    int received = 0;
    FL_Option_ptr item;
    while ((item = fl_channel_recv(ch)).tag == 1) {
        received++;
        /* Small delay to create backpressure */
        usleep(1000);
    }
    return (void*)(intptr_t)received;
}

static void test_backpressure(void) {
    TEST(backpressure_capacity_1);

    FL_Channel* ch = fl_channel_new(1);

    pthread_t consumer;
    pthread_create(&consumer, NULL, _test_slow_consumer, ch);

    int count = 20;
    for (int i = 0; i < count; i++) {
        fl_channel_send(ch, (void*)(intptr_t)(i + 1));
    }
    fl_channel_close(ch);

    void* result;
    pthread_join(consumer, &result);
    assert((int)(intptr_t)result == count);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 7: Exception propagation through channel
 * ======================================================================== */

static void test_exception_propagation(void) {
    TEST(exception_propagation);

    FL_Channel* ch = fl_channel_new(4);

    /* Simulate producer storing an exception */
    FL_String* exc_msg = fl_string_from_cstr("test error");
    fl_channel_set_exception(ch, exc_msg, 42);
    fl_channel_close(ch);

    /* Consumer should get the exception via _fl_throw */
    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    fl_bool caught = fl_false;
    if (setjmp(ef.jmp) == 0) {
        fl_channel_recv(ch);
        /* Should not reach here */
        assert(0 && "should have thrown");
    } else {
        caught = fl_true;
        assert(ef.exception_tag == 42);
        FL_String* msg = (FL_String*)ef.exception;
        assert(fl_string_eq(msg, exc_msg));
    }
    _fl_exception_pop();
    assert(caught == fl_true);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 8: fl_coroutine_new_threaded end-to-end
 * ======================================================================== */

typedef struct {
    int current;
    int limit;
} _CounterState;

static FL_Option_ptr _counter_next(FL_Stream* self) {
    _CounterState* st = (_CounterState*)self->state;
    if (st->current >= st->limit) return FL_NONE_PTR;
    int val = ++(st->current);
    return FL_SOME_PTR((void*)(intptr_t)val);
}

static void _counter_free(FL_Stream* self) {
    free(self->state);
}

static FL_Stream* _make_counter_stream(int limit) {
    _CounterState* st = (_CounterState*)malloc(sizeof(_CounterState));
    st->current = 0;
    st->limit = limit;
    return fl_stream_new(_counter_next, _counter_free, st);
}

static void test_coroutine_threaded_e2e(void) {
    TEST(coroutine_threaded_e2e);

    FL_Stream* stream = _make_counter_stream(50);
    FL_Coroutine* co = fl_coroutine_new_threaded(stream, 8);

    int sum = 0;
    int count = 0;
    FL_Option_ptr item;
    while ((item = fl_coroutine_next(co)).tag == 1) {
        sum += (int)(intptr_t)item.value;
        count++;
    }

    assert(count == 50);
    assert(sum == 1275);  /* sum of 1..50 */
    assert(fl_coroutine_done(co) == fl_true);

    fl_coroutine_release(co);
    fl_stream_release(stream);
    PASS();
}

/* ========================================================================
 * Test 9: Non-threaded coroutine still works (backward compat)
 * ======================================================================== */

static void test_coroutine_non_threaded(void) {
    TEST(coroutine_non_threaded_compat);

    FL_Stream* stream = _make_counter_stream(5);
    FL_Coroutine* co = fl_coroutine_new(stream);

    int sum = 0;
    FL_Option_ptr item;
    while ((item = fl_coroutine_next(co)).tag == 1) {
        sum += (int)(intptr_t)item.value;
    }

    assert(sum == 15);  /* 1+2+3+4+5 */
    assert(fl_coroutine_done(co) == fl_true);

    fl_coroutine_release(co);
    PASS();
}

/* ========================================================================
 * Test 10: Refcount management
 * ======================================================================== */

static void test_channel_refcount(void) {
    TEST(channel_refcount);

    FL_Channel* ch = fl_channel_new(4);
    fl_channel_retain(ch);
    fl_channel_retain(ch);
    /* refcount is now 3 */
    fl_channel_release(ch);  /* 2 */
    fl_channel_release(ch);  /* 1 */

    /* Channel should still be usable */
    assert(fl_channel_send(ch, (void*)(intptr_t)99) == fl_true);
    FL_Option_ptr r = fl_channel_recv(ch);
    assert(r.tag == 1 && (intptr_t)r.value == 99);

    fl_channel_close(ch);
    fl_channel_release(ch);  /* 0 — freed */
    PASS();
}

/* ========================================================================
 * Test 11: Close is idempotent
 * ======================================================================== */

static void test_close_idempotent(void) {
    TEST(close_idempotent);

    FL_Channel* ch = fl_channel_new(4);
    fl_channel_close(ch);
    fl_channel_close(ch);  /* should not crash */
    fl_channel_close(ch);  /* should not crash */
    assert(fl_channel_is_closed(ch) == fl_true);

    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Test 12: Circular buffer wrap-around
 * ======================================================================== */

static void test_circular_wraparound(void) {
    TEST(circular_buffer_wraparound);

    FL_Channel* ch = fl_channel_new(3);

    /* Fill and drain multiple times to exercise wrap-around */
    for (int round = 0; round < 5; round++) {
        for (int i = 0; i < 3; i++) {
            fl_channel_send(ch, (void*)(intptr_t)(round * 10 + i));
        }
        for (int i = 0; i < 3; i++) {
            FL_Option_ptr r = fl_channel_recv(ch);
            assert(r.tag == 1);
            assert((int)(intptr_t)r.value == round * 10 + i);
        }
    }

    fl_channel_close(ch);
    fl_channel_release(ch);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("FL_Channel and threaded coroutine tests\n");
    printf("========================================\n");

    test_basic_fifo();
    test_close_drain();
    test_send_after_close();
    test_len_and_is_closed();
    test_threaded_producer_consumer();
    test_backpressure();
    test_exception_propagation();
    test_coroutine_threaded_e2e();
    test_coroutine_non_threaded();
    test_channel_refcount();
    test_close_idempotent();
    test_circular_wraparound();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
