/*
 * ReFlow Runtime Library
 * runtime/reflow_runtime.c — Runtime implementations.
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "reflow_runtime.h"
#include <limits.h>
#include <math.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <fcntl.h>

/* ========================================================================
 * Panic Functions (RT-1-1-3)
 * ======================================================================== */

void rf_panic(const char* msg) {
    fprintf(stderr, "ReFlow runtime error: %s\n", msg);
    exit(1);
}

void rf_panic_overflow(void) {
    rf_panic("OverflowError");
}

void rf_panic_divzero(void) {
    rf_panic("DivisionByZeroError");
}

void rf_panic_oob(void) {
    rf_panic("IndexOutOfBoundsError");
}

/* ========================================================================
 * String (RT-1-2-1, RT-1-2-2, RT-1-2-3)
 * ======================================================================== */

RF_String* rf_string_new(const char* data, rf_int64 len) {
    if (len < 0) rf_panic("rf_string_new: negative length");
    RF_String* s = (RF_String*)malloc(sizeof(RF_String) + (size_t)len + 1);
    if (!s) rf_panic("rf_string_new: out of memory");
    s->refcount = 1;
    s->len = len;
    if (len > 0 && data) {
        memcpy(s->data, data, (size_t)len);
    }
    s->data[len] = '\0';
    return s;
}

RF_String* rf_string_from_cstr(const char* cstr) {
    if (!cstr) rf_panic("rf_string_from_cstr: NULL pointer");
    rf_int64 len = (rf_int64)strlen(cstr);
    return rf_string_new(cstr, len);
}

void rf_string_retain(RF_String* s) {
    if (!s) return;
    atomic_fetch_add(&s->refcount, 1);
}

void rf_string_release(RF_String* s) {
    if (!s) return;
    if (atomic_fetch_sub(&s->refcount, 1) == 1) {
        free(s);
    }
}

RF_String* rf_string_concat(RF_String* a, RF_String* b) {
    if (!a || !b) rf_panic("rf_string_concat: NULL argument");
    rf_int64 total = a->len + b->len;
    RF_String* s = (RF_String*)malloc(sizeof(RF_String) + (size_t)total + 1);
    if (!s) rf_panic("rf_string_concat: out of memory");
    s->refcount = 1;
    s->len = total;
    memcpy(s->data, a->data, (size_t)a->len);
    memcpy(s->data + a->len, b->data, (size_t)b->len);
    s->data[total] = '\0';
    return s;
}

rf_bool rf_string_eq(RF_String* a, RF_String* b) {
    if (a == b) return rf_true;
    if (!a || !b) return rf_false;
    if (a->len != b->len) return rf_false;
    return memcmp(a->data, b->data, (size_t)a->len) == 0;
}

rf_int64 rf_string_len(RF_String* s) {
    if (!s) rf_panic("rf_string_len: NULL pointer");
    return s->len;
}

rf_int rf_string_cmp(RF_String* a, RF_String* b) {
    if (!a || !b) rf_panic("rf_string_cmp: NULL pointer");
    rf_int64 min_len = a->len < b->len ? a->len : b->len;
    int result = memcmp(a->data, b->data, (size_t)min_len);
    if (result < 0) return -1;
    if (result > 0) return 1;
    if (a->len < b->len) return -1;
    if (a->len > b->len) return 1;
    return 0;
}

/* Numeric conversions (RT-1-2-3) */

rf_bool rf_string_to_int(RF_String* s, rf_int* out) {
    if (!s || s->len == 0) return rf_false;
    char* endptr;
    long val = strtol(s->data, &endptr, 10);
    if (endptr != s->data + s->len) return rf_false;
    if (val < INT32_MIN || val > INT32_MAX) return rf_false;
    *out = (rf_int)val;
    return rf_true;
}

rf_bool rf_string_to_int64(RF_String* s, rf_int64* out) {
    if (!s || s->len == 0) return rf_false;
    char* endptr;
    long long val = strtoll(s->data, &endptr, 10);
    if (endptr != s->data + s->len) return rf_false;
    *out = (rf_int64)val;
    return rf_true;
}

rf_bool rf_string_to_float(RF_String* s, rf_float* out) {
    if (!s || s->len == 0) return rf_false;
    char* endptr;
    double val = strtod(s->data, &endptr);
    if (endptr != s->data + s->len) return rf_false;
    *out = (rf_float)val;
    return rf_true;
}

RF_String* rf_int_to_string(rf_int v) {
    char buf[16];
    int n = snprintf(buf, sizeof(buf), "%d", (int)v);
    return rf_string_new(buf, (rf_int64)n);
}

RF_String* rf_int64_to_string(rf_int64 v) {
    char buf[24];
    int n = snprintf(buf, sizeof(buf), "%lld", (long long)v);
    return rf_string_new(buf, (rf_int64)n);
}

RF_String* rf_float_to_string(rf_float v) {
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%.17g", (double)v);
    return rf_string_new(buf, (rf_int64)n);
}

RF_String* rf_bool_to_string(rf_bool v) {
    return v ? rf_string_new("true", 4) : rf_string_new("false", 5);
}

RF_String* rf_byte_to_string(rf_byte v) {
    char buf[8];
    int len = snprintf(buf, sizeof(buf), "%u", (unsigned)v);
    return rf_string_new(buf, len);
}

/* ========================================================================
 * Array (RT-1-4-1, RT-1-4-2)
 * ======================================================================== */

RF_Array* rf_array_new(rf_int64 len, rf_int64 element_size, void* initial_data) {
    RF_Array* arr = (RF_Array*)malloc(sizeof(RF_Array));
    if (!arr) rf_panic("rf_array_new: out of memory");
    arr->refcount = 1;
    arr->len = len;
    arr->element_size = element_size;
    if (len > 0) {
        arr->data = malloc((size_t)len * (size_t)element_size);
        if (!arr->data) rf_panic("rf_array_new: out of memory");
        if (initial_data) {
            memcpy(arr->data, initial_data, (size_t)len * (size_t)element_size);
        } else {
            memset(arr->data, 0, (size_t)len * (size_t)element_size);
        }
    } else {
        arr->data = NULL;
    }
    return arr;
}

void rf_array_retain(RF_Array* arr) {
    if (!arr) return;
    atomic_fetch_add(&arr->refcount, 1);
}

void rf_array_release(RF_Array* arr) {
    if (!arr) return;
    if (atomic_fetch_sub(&arr->refcount, 1) == 1) {
        free(arr->data);
        free(arr);
    }
}

void* rf_array_get_ptr(RF_Array* arr, rf_int64 idx) {
    if (!arr) rf_panic("rf_array_get_ptr: null array");
    if (idx < 0 || idx >= arr->len) rf_panic_oob();
    return (char*)arr->data + (size_t)idx * (size_t)arr->element_size;
}

RF_Option_ptr rf_array_get_safe(RF_Array* arr, rf_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len) return RF_NONE_PTR;
    void* ptr = (char*)arr->data + (size_t)idx * (size_t)arr->element_size;
    /* For pointer-sized elements (strings, opaque types), dereference the
       slot to return the stored pointer, not a pointer to the slot. */
    if (arr->element_size == sizeof(void*)) {
        return RF_SOME_PTR(*(void**)ptr);
    }
    return RF_SOME_PTR(ptr);
}

rf_int64 rf_array_len(RF_Array* arr) {
    if (!arr) return 0;
    return arr->len;
}

RF_Array* rf_array_push(RF_Array* arr, void* element) {
    if (!arr) rf_panic("rf_array_push: null array");
    if (!element) rf_panic("rf_array_push: null element");
    rf_int64 new_len = arr->len + 1;
    RF_Array* out = (RF_Array*)malloc(sizeof(RF_Array));
    if (!out) rf_panic("rf_array_push: out of memory");
    out->refcount = 1;
    out->len = new_len;
    out->element_size = arr->element_size;
    out->data = malloc((size_t)new_len * (size_t)arr->element_size);
    if (!out->data) rf_panic("rf_array_push: out of memory");
    if (arr->len > 0) {
        memcpy(out->data, arr->data, (size_t)arr->len * (size_t)arr->element_size);
    }
    memcpy((char*)out->data + (size_t)arr->len * (size_t)arr->element_size,
           element, (size_t)arr->element_size);
    return out;
}

/* ========================================================================
 * Stream (RT-1-5-1, RT-1-5-2)
 * ======================================================================== */

RF_Stream* rf_stream_new(RF_StreamNext next_fn, RF_StreamFree free_fn, void* state) {
    RF_Stream* s = (RF_Stream*)malloc(sizeof(RF_Stream));
    if (!s) rf_panic("rf_stream_new: out of memory");
    s->next_fn = next_fn;
    s->free_fn = free_fn;
    s->state = state;
    s->refcount = 1;
    return s;
}

void rf_stream_retain(RF_Stream* s) {
    if (!s) return;
    atomic_fetch_add(&s->refcount, 1);
}

void rf_stream_release(RF_Stream* s) {
    if (!s) return;
    if (atomic_fetch_sub(&s->refcount, 1) == 1) {
        if (s->free_fn) {
            s->free_fn(s);
        }
        free(s);
    }
}

RF_Option_ptr rf_stream_next(RF_Stream* s) {
    return s->next_fn(s);
}

/* ========================================================================
 * Channel — bounded, thread-safe FIFO queue
 * ======================================================================== */

struct RF_Channel {
    pthread_mutex_t  mutex;
    pthread_cond_t   not_full;
    pthread_cond_t   not_empty;
    void**           buffer;
    rf_int           capacity;
    rf_int           head;
    rf_int           tail;
    rf_int           count;
    rf_bool          closed;
    _Atomic rf_int64 refcount;
    void*            exception;
    rf_int           exception_tag;
    rf_bool          has_exception;
};

RF_Channel* rf_channel_new(rf_int capacity) {
    if (capacity < 1) capacity = 1;
    RF_Channel* ch = (RF_Channel*)malloc(sizeof(RF_Channel));
    if (!ch) rf_panic("rf_channel_new: out of memory");
    pthread_mutex_init(&ch->mutex, NULL);
    pthread_cond_init(&ch->not_full, NULL);
    pthread_cond_init(&ch->not_empty, NULL);
    ch->buffer = (void**)malloc(sizeof(void*) * (size_t)capacity);
    if (!ch->buffer) rf_panic("rf_channel_new: out of memory");
    ch->capacity = capacity;
    ch->head = 0;
    ch->tail = 0;
    ch->count = 0;
    ch->closed = rf_false;
    ch->refcount = 1;
    ch->exception = NULL;
    ch->exception_tag = 0;
    ch->has_exception = rf_false;
    return ch;
}

rf_bool rf_channel_send(RF_Channel* ch, void* val) {
    pthread_mutex_lock(&ch->mutex);
    while (ch->count == ch->capacity && !ch->closed) {
        pthread_cond_wait(&ch->not_full, &ch->mutex);
    }
    if (ch->closed) {
        pthread_mutex_unlock(&ch->mutex);
        return rf_false;
    }
    ch->buffer[ch->tail] = val;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
    return rf_true;
}

RF_Option_ptr rf_channel_recv(RF_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    while (ch->count == 0 && !ch->closed) {
        pthread_cond_wait(&ch->not_empty, &ch->mutex);
    }
    if (ch->count > 0) {
        void* val = ch->buffer[ch->head];
        ch->head = (ch->head + 1) % ch->capacity;
        ch->count--;
        pthread_cond_signal(&ch->not_full);
        pthread_mutex_unlock(&ch->mutex);
        return RF_SOME_PTR(val);
    }
    /* count == 0 && closed */
    if (ch->has_exception) {
        void* exc = ch->exception;
        rf_int tag = ch->exception_tag;
        pthread_mutex_unlock(&ch->mutex);
        _rf_throw(exc, tag);
    }
    pthread_mutex_unlock(&ch->mutex);
    return RF_NONE_PTR;
}

void rf_channel_close(RF_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    ch->closed = rf_true;
    pthread_cond_broadcast(&ch->not_full);
    pthread_cond_broadcast(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
}

rf_int rf_channel_len(RF_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    rf_int n = ch->count;
    pthread_mutex_unlock(&ch->mutex);
    return n;
}

rf_bool rf_channel_is_closed(RF_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    rf_bool c = ch->closed;
    pthread_mutex_unlock(&ch->mutex);
    return c;
}

void rf_channel_set_exception(RF_Channel* ch, void* exception, rf_int tag) {
    pthread_mutex_lock(&ch->mutex);
    ch->exception = exception;
    ch->exception_tag = tag;
    ch->has_exception = rf_true;
    pthread_mutex_unlock(&ch->mutex);
}

void rf_channel_retain(RF_Channel* ch) {
    if (!ch) return;
    atomic_fetch_add(&ch->refcount, 1);
}

void rf_channel_release(RF_Channel* ch) {
    if (!ch) return;
    if (atomic_fetch_sub(&ch->refcount, 1) == 1) {
        pthread_mutex_destroy(&ch->mutex);
        pthread_cond_destroy(&ch->not_full);
        pthread_cond_destroy(&ch->not_empty);
        free(ch->buffer);
        free(ch);
    }
}

/* Non-blocking channel operations (SL-5-5) */

rf_bool rf_channel_try_send(RF_Channel* ch, void* val) {
    pthread_mutex_lock(&ch->mutex);
    if (ch->closed || ch->count == ch->capacity) {
        pthread_mutex_unlock(&ch->mutex);
        return rf_false;
    }
    ch->buffer[ch->tail] = val;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
    return rf_true;
}

RF_Option_ptr rf_channel_try_recv(RF_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    if (ch->count == 0) {
        pthread_mutex_unlock(&ch->mutex);
        return RF_NONE_PTR;
    }
    void* val = ch->buffer[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    pthread_cond_signal(&ch->not_full);
    pthread_mutex_unlock(&ch->mutex);
    return RF_SOME_PTR(val);
}

/* ========================================================================
 * Coroutines
 * ======================================================================== */

/* --- Threaded coroutine producer --- */

typedef struct {
    RF_Stream*  stream;
    RF_Channel* channel;
} _RF_CoroutineProducerArg;

static void* _rf_coroutine_producer(void* raw) {
    _RF_CoroutineProducerArg* arg = (_RF_CoroutineProducerArg*)raw;
    RF_Stream* stream = arg->stream;
    RF_Channel* channel = arg->channel;
    free(arg);

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        RF_Option_ptr item;
        while ((item = rf_stream_next(stream)).tag == 1) {
            if (!rf_channel_send(channel, item.value))
                break;  /* channel closed by consumer */
        }
    } else {
        rf_channel_set_exception(channel, ef.exception, ef.exception_tag);
    }
    _rf_exception_pop();
    rf_channel_close(channel);
    rf_stream_release(stream);
    rf_channel_release(channel);  /* drop producer's ref */
    return NULL;
}

/* --- Constructors --- */

RF_Coroutine* rf_coroutine_new(RF_Stream* stream) {
    RF_Coroutine* c = (RF_Coroutine*)malloc(sizeof(RF_Coroutine));
    if (!c) rf_panic("rf_coroutine_new: out of memory");
    c->stream = stream;
    c->channel = NULL;
    c->input_channel = NULL;
    c->done = rf_false;
    return c;
}

RF_Coroutine* rf_coroutine_new_threaded(RF_Stream* stream, rf_int capacity) {
    RF_Coroutine* c = (RF_Coroutine*)malloc(sizeof(RF_Coroutine));
    if (!c) rf_panic("rf_coroutine_new_threaded: out of memory");
    c->stream = NULL;
    c->channel = rf_channel_new(capacity);
    c->input_channel = NULL;
    c->done = rf_false;

    /* Producer holds refs to both stream and channel */
    rf_stream_retain(stream);
    rf_channel_retain(c->channel);  /* producer's ref (consumer holds the other) */

    _RF_CoroutineProducerArg* arg = (_RF_CoroutineProducerArg*)malloc(sizeof(_RF_CoroutineProducerArg));
    if (!arg) rf_panic("rf_coroutine_new_threaded: out of memory");
    arg->stream = stream;
    arg->channel = c->channel;

    pthread_create(&c->thread, NULL, _rf_coroutine_producer, arg);
    return c;
}

/* --- Operations --- */

RF_Option_ptr rf_coroutine_next(RF_Coroutine* c) {
    RF_Option_ptr result;
    if (c->channel) {
        result = rf_channel_recv(c->channel);
    } else {
        result = rf_stream_next(c->stream);
    }
    if (result.tag == 0) c->done = rf_true;
    return result;
}

rf_bool rf_coroutine_done(RF_Coroutine* c) {
    return c->done;
}

void rf_coroutine_release(RF_Coroutine* c) {
    if (!c) return;
    if (c->input_channel) {
        rf_channel_close(c->input_channel);    /* unblock producer if waiting on inbox */
        rf_channel_release(c->input_channel);  /* drop consumer-side ref */
    }
    if (c->channel) {
        rf_channel_close(c->channel);    /* unblock producer if blocked */
        pthread_join(c->thread, NULL);   /* wait for producer to exit */
        rf_channel_release(c->channel);  /* drop consumer's ref */
    } else {
        rf_stream_release(c->stream);
    }
    free(c);
}

void rf_coroutine_send(RF_Coroutine* c, void* val) {
    if (!c->input_channel) rf_panic("rf_coroutine_send: coroutine has no input channel");
    rf_channel_send(c->input_channel, val);
}

rf_bool rf_coroutine_try_send(RF_Coroutine* c, void* val) {
    if (!c->input_channel) return rf_false;
    return rf_channel_try_send(c->input_channel, val);
}

void rf_coroutine_set_input(RF_Coroutine* c, RF_Channel* input) {
    c->input_channel = input;
    rf_channel_retain(input);  /* consumer-side ref */
}

/* --- Stream backed by a channel (for receivable coroutine inbox) --- */

static RF_Option_ptr _rf_stream_from_channel_next(RF_Stream* self) {
    RF_Channel* ch = (RF_Channel*)self->state;
    return rf_channel_recv(ch);
}

static void _rf_stream_from_channel_free(RF_Stream* self) {
    RF_Channel* ch = (RF_Channel*)self->state;
    rf_channel_release(ch);  /* drop the stream's ref */
}

RF_Stream* rf_stream_from_channel(RF_Channel* ch) {
    rf_channel_retain(ch);  /* stream holds a ref */
    return rf_stream_new(_rf_stream_from_channel_next,
                         _rf_stream_from_channel_free,
                         (void*)ch);
}

/* Non-blocking variant: try_recv returns none immediately if empty */
static RF_Option_ptr _rf_stream_from_channel_try_next(RF_Stream* self) {
    RF_Channel* ch = (RF_Channel*)self->state;
    return rf_channel_try_recv(ch);
}

RF_Stream* rf_stream_from_channel_nonblocking(RF_Channel* ch) {
    rf_channel_retain(ch);  /* stream holds a ref */
    return rf_stream_new(_rf_stream_from_channel_try_next,
                         _rf_stream_from_channel_free,
                         (void*)ch);
}

/* ========================================================================
 * Stream Helpers
 * ======================================================================== */

/* --- take --- */

typedef struct {
    RF_Stream* src;
    rf_int     remaining;
} RF_StreamTakeState;

static RF_Option_ptr rf__stream_take_next(RF_Stream* self) {
    RF_StreamTakeState* st = (RF_StreamTakeState*)self->state;
    if (st->remaining <= 0) return RF_NONE_PTR;
    st->remaining--;
    return rf_stream_next(st->src);
}

static void rf__stream_take_free(RF_Stream* self) {
    RF_StreamTakeState* st = (RF_StreamTakeState*)self->state;
    rf_stream_release(st->src);
    free(st);
}

RF_Stream* rf_stream_take(RF_Stream* src, rf_int n) {
    rf_stream_retain(src);
    RF_StreamTakeState* st = (RF_StreamTakeState*)malloc(sizeof(RF_StreamTakeState));
    if (!st) rf_panic("rf_stream_take: out of memory");
    st->src = src;
    st->remaining = n;
    return rf_stream_new(rf__stream_take_next, rf__stream_take_free, st);
}

/* --- skip --- */

typedef struct {
    RF_Stream* src;
    rf_int     to_skip;
    rf_bool    skipped;
} RF_StreamSkipState;

static RF_Option_ptr rf__stream_skip_next(RF_Stream* self) {
    RF_StreamSkipState* st = (RF_StreamSkipState*)self->state;
    if (!st->skipped) {
        st->skipped = rf_true;
        for (rf_int i = 0; i < st->to_skip; i++) {
            RF_Option_ptr item = rf_stream_next(st->src);
            if (item.tag == 0) return RF_NONE_PTR;
        }
    }
    return rf_stream_next(st->src);
}

static void rf__stream_skip_free(RF_Stream* self) {
    RF_StreamSkipState* st = (RF_StreamSkipState*)self->state;
    rf_stream_release(st->src);
    free(st);
}

RF_Stream* rf_stream_skip(RF_Stream* src, rf_int n) {
    rf_stream_retain(src);
    RF_StreamSkipState* st = (RF_StreamSkipState*)malloc(sizeof(RF_StreamSkipState));
    if (!st) rf_panic("rf_stream_skip: out of memory");
    st->src = src;
    st->to_skip = n;
    st->skipped = rf_false;
    return rf_stream_new(rf__stream_skip_next, rf__stream_skip_free, st);
}

/* --- map --- */

typedef struct {
    RF_Stream*  src;
    RF_Closure* fn;
} RF_StreamMapState;

static RF_Option_ptr rf__stream_map_next(RF_Stream* self) {
    RF_StreamMapState* st = (RF_StreamMapState*)self->state;
    RF_Option_ptr item = rf_stream_next(st->src);
    if (item.tag == 0) return RF_NONE_PTR;
    void* result = ((void*(*)(void*, void*))st->fn->fn)(st->fn->env, item.value);
    return RF_SOME_PTR(result);
}

static void rf__stream_map_free(RF_Stream* self) {
    RF_StreamMapState* st = (RF_StreamMapState*)self->state;
    rf_stream_release(st->src);
    free(st);
}

RF_Stream* rf_stream_map(RF_Stream* src, RF_Closure* fn) {
    rf_stream_retain(src);
    RF_StreamMapState* st = (RF_StreamMapState*)malloc(sizeof(RF_StreamMapState));
    if (!st) rf_panic("rf_stream_map: out of memory");
    st->src = src;
    st->fn = fn;
    return rf_stream_new(rf__stream_map_next, rf__stream_map_free, st);
}

/* --- filter --- */

typedef struct {
    RF_Stream*  src;
    RF_Closure* fn;
} RF_StreamFilterState;

static RF_Option_ptr rf__stream_filter_next(RF_Stream* self) {
    RF_StreamFilterState* st = (RF_StreamFilterState*)self->state;
    while (1) {
        RF_Option_ptr item = rf_stream_next(st->src);
        if (item.tag == 0) return RF_NONE_PTR;
        rf_bool keep = (rf_bool)(intptr_t)((void*(*)(void*, void*))st->fn->fn)(st->fn->env, item.value);
        if (keep) return item;
    }
}

static void rf__stream_filter_free(RF_Stream* self) {
    RF_StreamFilterState* st = (RF_StreamFilterState*)self->state;
    rf_stream_release(st->src);
    free(st);
}

RF_Stream* rf_stream_filter(RF_Stream* src, RF_Closure* fn) {
    rf_stream_retain(src);
    RF_StreamFilterState* st = (RF_StreamFilterState*)malloc(sizeof(RF_StreamFilterState));
    if (!st) rf_panic("rf_stream_filter: out of memory");
    st->src = src;
    st->fn = fn;
    return rf_stream_new(rf__stream_filter_next, rf__stream_filter_free, st);
}

/* --- reduce --- */

void* rf_stream_reduce(RF_Stream* src, void* init, RF_Closure* fn) {
    void* acc = init;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        acc = ((void*(*)(void*, void*, void*))fn->fn)(fn->env, acc, item.value);
    }
    return acc;
}

/* ========================================================================
 * Stream Construction (SL-5-2)
 * ======================================================================== */

/* --- range --- */

typedef struct {
    rf_int current;
    rf_int end;
} _RF_RangeState;

static RF_Option_ptr _rf_range_next(RF_Stream* self) {
    _RF_RangeState* st = (_RF_RangeState*)self->state;
    if (st->current >= st->end) return RF_NONE_PTR;
    rf_int val = st->current;
    st->current++;
    return RF_SOME_PTR((void*)(intptr_t)val);
}

static void _rf_range_free(RF_Stream* self) {
    free(self->state);
}

RF_Stream* rf_stream_range(rf_int start, rf_int end) {
    _RF_RangeState* st = (_RF_RangeState*)malloc(sizeof(_RF_RangeState));
    if (!st) rf_panic("rf_stream_range: out of memory");
    st->current = start;
    st->end = end;
    return rf_stream_new(_rf_range_next, _rf_range_free, st);
}

/* --- range_step --- */

typedef struct {
    rf_int current;
    rf_int end;
    rf_int step;
} _RF_RangeStepState;

static RF_Option_ptr _rf_range_step_next(RF_Stream* self) {
    _RF_RangeStepState* st = (_RF_RangeStepState*)self->state;
    if (st->step > 0 && st->current >= st->end) return RF_NONE_PTR;
    if (st->step < 0 && st->current <= st->end) return RF_NONE_PTR;
    rf_int val = st->current;
    st->current += st->step;
    return RF_SOME_PTR((void*)(intptr_t)val);
}

static void _rf_range_step_free(RF_Stream* self) {
    free(self->state);
}

RF_Stream* rf_stream_range_step(rf_int start, rf_int end, rf_int step) {
    if (step == 0) rf_panic("range_step: step cannot be zero");
    _RF_RangeStepState* st = (_RF_RangeStepState*)malloc(sizeof(_RF_RangeStepState));
    if (!st) rf_panic("rf_stream_range_step: out of memory");
    st->current = start;
    st->end = end;
    st->step = step;
    return rf_stream_new(_rf_range_step_next, _rf_range_step_free, st);
}

/* --- from_array --- */

typedef struct {
    RF_Array* arr;
    rf_int64 index;
} _RF_FromArrayState;

static RF_Option_ptr _rf_from_array_next(RF_Stream* self) {
    _RF_FromArrayState* st = (_RF_FromArrayState*)self->state;
    if (st->index >= st->arr->len) return RF_NONE_PTR;
    void* ptr = (char*)st->arr->data + st->index * st->arr->element_size;
    st->index++;
    /* For pointer-sized elements, dereference; for value types, copy */
    if (st->arr->element_size == sizeof(void*)) {
        void* val = *(void**)ptr;
        return RF_SOME_PTR(val);
    }
    /* For value types, cast through intptr_t (works for int-sized values) */
    if (st->arr->element_size <= (rf_int64)sizeof(intptr_t)) {
        intptr_t val = 0;
        memcpy(&val, ptr, (size_t)st->arr->element_size);
        return RF_SOME_PTR((void*)val);
    }
    /* For larger types, return pointer to data */
    return RF_SOME_PTR(ptr);
}

static void _rf_from_array_free(RF_Stream* self) {
    _RF_FromArrayState* st = (_RF_FromArrayState*)self->state;
    rf_array_release(st->arr);
    free(st);
}

RF_Stream* rf_stream_from_array(RF_Array* arr) {
    _RF_FromArrayState* st = (_RF_FromArrayState*)malloc(sizeof(_RF_FromArrayState));
    if (!st) rf_panic("rf_stream_from_array: out of memory");
    rf_array_retain(arr);
    st->arr = arr;
    st->index = 0;
    return rf_stream_new(_rf_from_array_next, _rf_from_array_free, st);
}

/* --- repeat --- */

typedef struct {
    void* val;
    rf_int remaining;
} _RF_RepeatState;

static RF_Option_ptr _rf_repeat_next(RF_Stream* self) {
    _RF_RepeatState* st = (_RF_RepeatState*)self->state;
    if (st->remaining <= 0) return RF_NONE_PTR;
    st->remaining--;
    return RF_SOME_PTR(st->val);
}

static void _rf_repeat_free(RF_Stream* self) {
    free(self->state);
}

RF_Stream* rf_stream_repeat(void* val, rf_int n) {
    _RF_RepeatState* st = (_RF_RepeatState*)malloc(sizeof(_RF_RepeatState));
    if (!st) rf_panic("rf_stream_repeat: out of memory");
    st->val = val;
    st->remaining = n;
    return rf_stream_new(_rf_repeat_next, _rf_repeat_free, st);
}

/* --- empty --- */

static RF_Option_ptr _rf_empty_next(RF_Stream* self) {
    (void)self;
    return RF_NONE_PTR;
}

static void _rf_empty_free(RF_Stream* self) {
    (void)self;
}

RF_Stream* rf_stream_empty(void) {
    return rf_stream_new(_rf_empty_next, _rf_empty_free, NULL);
}

/* ========================================================================
 * Stream Transformation (SL-5-3)
 * ======================================================================== */

/* --- enumerate --- */

typedef struct {
    RF_Stream* source;
    rf_int64   index;
} _RF_EnumerateState;

static RF_Option_ptr _rf_enumerate_next(RF_Stream* self) {
    _RF_EnumerateState* st = (_RF_EnumerateState*)self->state;
    RF_Option_ptr item = rf_stream_next(st->source);
    if (item.tag == 0) return RF_NONE_PTR;
    RF_Pair* pair = (RF_Pair*)malloc(sizeof(RF_Pair));
    if (!pair) rf_panic("rf_stream_enumerate: out of memory");
    pair->first = (void*)(intptr_t)(st->index++);
    pair->second = item.value;
    return RF_SOME_PTR(pair);
}

static void _rf_enumerate_free(RF_Stream* self) {
    _RF_EnumerateState* st = (_RF_EnumerateState*)self->state;
    rf_stream_release(st->source);
    free(st);
}

RF_Stream* rf_stream_enumerate(RF_Stream* source) {
    rf_stream_retain(source);
    _RF_EnumerateState* st = (_RF_EnumerateState*)malloc(sizeof(_RF_EnumerateState));
    if (!st) rf_panic("rf_stream_enumerate: out of memory");
    st->source = source;
    st->index = 0;
    return rf_stream_new(_rf_enumerate_next, _rf_enumerate_free, st);
}

/* --- zip --- */

typedef struct {
    RF_Stream* a;
    RF_Stream* b;
} _RF_ZipState;

static RF_Option_ptr _rf_zip_next(RF_Stream* self) {
    _RF_ZipState* st = (_RF_ZipState*)self->state;
    RF_Option_ptr item_a = rf_stream_next(st->a);
    if (item_a.tag == 0) return RF_NONE_PTR;
    RF_Option_ptr item_b = rf_stream_next(st->b);
    if (item_b.tag == 0) return RF_NONE_PTR;
    RF_Pair* pair = (RF_Pair*)malloc(sizeof(RF_Pair));
    if (!pair) rf_panic("rf_stream_zip: out of memory");
    pair->first = item_a.value;
    pair->second = item_b.value;
    return RF_SOME_PTR(pair);
}

static void _rf_zip_free(RF_Stream* self) {
    _RF_ZipState* st = (_RF_ZipState*)self->state;
    rf_stream_release(st->a);
    rf_stream_release(st->b);
    free(st);
}

RF_Stream* rf_stream_zip(RF_Stream* a, RF_Stream* b) {
    rf_stream_retain(a);
    rf_stream_retain(b);
    _RF_ZipState* st = (_RF_ZipState*)malloc(sizeof(_RF_ZipState));
    if (!st) rf_panic("rf_stream_zip: out of memory");
    st->a = a;
    st->b = b;
    return rf_stream_new(_rf_zip_next, _rf_zip_free, st);
}

/* --- chain --- */

typedef struct {
    RF_Stream* a;
    RF_Stream* b;
    rf_bool    a_done;
} _RF_ChainState;

static RF_Option_ptr _rf_chain_next(RF_Stream* self) {
    _RF_ChainState* st = (_RF_ChainState*)self->state;
    if (!st->a_done) {
        RF_Option_ptr item = rf_stream_next(st->a);
        if (item.tag == 1) return item;
        st->a_done = rf_true;
    }
    return rf_stream_next(st->b);
}

static void _rf_chain_free(RF_Stream* self) {
    _RF_ChainState* st = (_RF_ChainState*)self->state;
    rf_stream_release(st->a);
    rf_stream_release(st->b);
    free(st);
}

RF_Stream* rf_stream_chain(RF_Stream* a, RF_Stream* b) {
    rf_stream_retain(a);
    rf_stream_retain(b);
    _RF_ChainState* st = (_RF_ChainState*)malloc(sizeof(_RF_ChainState));
    if (!st) rf_panic("rf_stream_chain: out of memory");
    st->a = a;
    st->b = b;
    st->a_done = rf_false;
    return rf_stream_new(_rf_chain_next, _rf_chain_free, st);
}

/* --- flat_map --- */

typedef struct {
    RF_Stream*  source;
    RF_Closure* f;
    RF_Stream*  current_sub;
} _RF_FlatMapState;

static RF_Option_ptr _rf_flat_map_next(RF_Stream* self) {
    _RF_FlatMapState* st = (_RF_FlatMapState*)self->state;
    for (;;) {
        /* Try to pull from the current sub-stream */
        if (st->current_sub) {
            RF_Option_ptr item = rf_stream_next(st->current_sub);
            if (item.tag == 1) return item;
            /* Sub-stream exhausted */
            rf_stream_release(st->current_sub);
            st->current_sub = NULL;
        }
        /* Pull next element from source */
        RF_Option_ptr src_item = rf_stream_next(st->source);
        if (src_item.tag == 0) return RF_NONE_PTR;
        /* Call closure: RF_Stream* (*)(void* item, void* env) */
        typedef RF_Stream* (*FlatMapFn)(void*, void*);
        FlatMapFn fn = (FlatMapFn)st->f->fn;
        st->current_sub = fn(src_item.value, st->f->env);
    }
}

static void _rf_flat_map_free(RF_Stream* self) {
    _RF_FlatMapState* st = (_RF_FlatMapState*)self->state;
    rf_stream_release(st->source);
    if (st->current_sub) {
        rf_stream_release(st->current_sub);
    }
    free(st);
}

RF_Stream* rf_stream_flat_map(RF_Stream* source, RF_Closure* f) {
    rf_stream_retain(source);
    _RF_FlatMapState* st = (_RF_FlatMapState*)malloc(sizeof(_RF_FlatMapState));
    if (!st) rf_panic("rf_stream_flat_map: out of memory");
    st->source = source;
    st->f = f;
    st->current_sub = NULL;
    return rf_stream_new(_rf_flat_map_next, _rf_flat_map_free, st);
}

/* ========================================================================
 * Stream Consumption (SL-5-4)
 * ======================================================================== */

RF_Array* rf_stream_to_array(RF_Stream* src, rf_int64 element_size) {
    RF_Buffer* buf = rf_buffer_collect(src, element_size);
    RF_Array* arr = rf_array_new(buf->len, buf->element_size, buf->data);
    rf_buffer_release(buf);
    return arr;
}

void rf_stream_foreach(RF_Stream* src, RF_Closure* fn) {
    typedef void (*ForeachFn)(void*, void*);
    ForeachFn f = (ForeachFn)fn->fn;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        f(fn->env, item.value);
    }
}

rf_int rf_stream_count(RF_Stream* src) {
    rf_int count = 0;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        count++;
    }
    return count;
}

rf_bool rf_stream_any(RF_Stream* src, RF_Closure* fn) {
    typedef rf_bool (*PredFn)(void*, void*);
    PredFn pred = (PredFn)fn->fn;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        if (pred(fn->env, item.value)) return rf_true;
    }
    return rf_false;
}

rf_bool rf_stream_all(RF_Stream* src, RF_Closure* fn) {
    typedef rf_bool (*PredFn)(void*, void*);
    PredFn pred = (PredFn)fn->fn;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        if (!pred(fn->env, item.value)) return rf_false;
    }
    return rf_true;
}

RF_Option_ptr rf_stream_find(RF_Stream* src, RF_Closure* fn) {
    typedef rf_bool (*PredFn)(void*, void*);
    PredFn pred = (PredFn)fn->fn;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        if (pred(fn->env, item.value)) return item;
    }
    return RF_NONE_PTR;
}

rf_int rf_stream_sum_int(RF_Stream* src) {
    rf_int sum = 0;
    RF_Option_ptr item;
    while ((item = rf_stream_next(src)).tag == 1) {
        rf_int val = (rf_int)(intptr_t)item.value;
        RF_CHECKED_ADD(sum, val, &sum);
    }
    return sum;
}

/* ========================================================================
 * Map — open-addressing hash table (RT-1-6-1)
 * BOOTSTRAP: replace with production hash map
 * ======================================================================== */

#define RF_MAP_INITIAL_CAPACITY 16

typedef struct {
    void*    key;
    rf_int64 key_len;
    void*    val;
    rf_bool  occupied;
} RF_MapEntry;

struct RF_Map {
    _Atomic rf_int64 refcount;
    rf_int64     count;
    rf_int64     capacity;
    RF_MapEntry* entries;
};

static rf_uint64 rf__fnv1a(const void* key, rf_int64 len) {
    const rf_byte* p = (const rf_byte*)key;
    rf_uint64 h = UINT64_C(14695981039346656037);
    for (rf_int64 i = 0; i < len; i++) {
        h ^= (rf_uint64)p[i];
        h *= UINT64_C(1099511628211);
    }
    return h;
}

static RF_Map* rf__map_alloc(rf_int64 capacity) {
    RF_Map* m = (RF_Map*)malloc(sizeof(RF_Map));
    if (!m) rf_panic("rf_map: out of memory");
    m->refcount = 1;
    m->count = 0;
    m->capacity = capacity;
    m->entries = (RF_MapEntry*)calloc((size_t)capacity, sizeof(RF_MapEntry));
    if (!m->entries) rf_panic("rf_map: out of memory");
    return m;
}

static rf_int64 rf__map_probe(RF_Map* m, const void* key, rf_int64 key_len) {
    rf_uint64 h = rf__fnv1a(key, key_len);
    rf_int64 idx = (rf_int64)(h % (rf_uint64)m->capacity);
    for (;;) {
        RF_MapEntry* e = &m->entries[idx];
        if (!e->occupied) return idx;
        if (e->key_len == key_len && memcmp(e->key, key, (size_t)key_len) == 0)
            return idx;
        idx = (idx + 1) % m->capacity;
    }
}

RF_Map* rf_map_new(void) {
    return rf__map_alloc(RF_MAP_INITIAL_CAPACITY);
}

RF_Map* rf_map_set(RF_Map* m, void* key, rf_int64 key_len, void* val) {
    /* Determine if key already exists */
    rf_int64 existing_idx = rf__map_probe(m, key, key_len);
    rf_int64 new_count = m->count;
    if (!m->entries[existing_idx].occupied) new_count++;

    /* Resize if load factor >= 75% */
    rf_int64 new_cap = m->capacity;
    while (4 * new_count >= 3 * new_cap) new_cap *= 2;

    RF_Map* n = rf__map_alloc(new_cap);

    /* Copy existing entries (except the one being overwritten) */
    for (rf_int64 i = 0; i < m->capacity; i++) {
        RF_MapEntry* e = &m->entries[i];
        if (!e->occupied) continue;
        if (e->key_len == key_len && memcmp(e->key, key, (size_t)key_len) == 0)
            continue;
        void* key_copy = malloc((size_t)e->key_len);
        if (!key_copy) rf_panic("rf_map: out of memory");
        memcpy(key_copy, e->key, (size_t)e->key_len);
        rf_int64 idx = rf__map_probe(n, key_copy, e->key_len);
        n->entries[idx].key = key_copy;
        n->entries[idx].key_len = e->key_len;
        n->entries[idx].val = e->val;
        n->entries[idx].occupied = rf_true;
        n->count++;
    }

    /* Insert the new/updated key */
    void* new_key_copy = malloc((size_t)key_len);
    if (!new_key_copy) rf_panic("rf_map: out of memory");
    memcpy(new_key_copy, key, (size_t)key_len);
    rf_int64 idx = rf__map_probe(n, new_key_copy, key_len);
    n->entries[idx].key = new_key_copy;
    n->entries[idx].key_len = key_len;
    n->entries[idx].val = val;
    n->entries[idx].occupied = rf_true;
    n->count++;

    return n;
}

RF_Option_ptr rf_map_get(RF_Map* m, void* key, rf_int64 key_len) {
    if (m->count == 0) return RF_NONE_PTR;
    rf_int64 idx = rf__map_probe(m, key, key_len);
    if (!m->entries[idx].occupied) return RF_NONE_PTR;
    return RF_SOME_PTR(m->entries[idx].val);
}

rf_bool rf_map_has(RF_Map* m, void* key, rf_int64 key_len) {
    if (m->count == 0) return rf_false;
    rf_int64 idx = rf__map_probe(m, key, key_len);
    return m->entries[idx].occupied;
}

rf_int64 rf_map_len(RF_Map* m) {
    return m->count;
}

void rf_map_retain(RF_Map* m) {
    if (!m) return;
    atomic_fetch_add(&m->refcount, 1);
}

void rf_map_release(RF_Map* m) {
    if (!m) return;
    if (atomic_fetch_sub(&m->refcount, 1) != 1) return;
    for (rf_int64 i = 0; i < m->capacity; i++) {
        if (m->entries[i].occupied) {
            free(m->entries[i].key);
        }
    }
    free(m->entries);
    free(m);
}

/* ========================================================================
 * Set (RT-1-6-2)
 * ======================================================================== */

struct RF_Set {
    RF_Map*  map;
    _Atomic rf_int64 refcount;
};

RF_Set* rf_set_new(void) {
    RF_Set* s = (RF_Set*)malloc(sizeof(RF_Set));
    if (!s) rf_panic("rf_set: out of memory");
    s->refcount = 1;
    s->map = rf_map_new();
    return s;
}

rf_bool rf_set_add(RF_Set* s, void* key, rf_int64 key_len) {
    rf_bool already = rf_map_has(s->map, key, key_len);
    RF_Map* new_map = rf_map_set(s->map, key, key_len, NULL);
    rf_map_release(s->map);
    s->map = new_map;
    return !already;
}

rf_bool rf_set_has(RF_Set* s, void* key, rf_int64 key_len) {
    return rf_map_has(s->map, key, key_len);
}

rf_bool rf_set_remove(RF_Set* s, void* key, rf_int64 key_len) {
    if (!rf_map_has(s->map, key, key_len)) return rf_false;
    RF_Map* old = s->map;
    RF_Map* n = rf__map_alloc(old->capacity > RF_MAP_INITIAL_CAPACITY
                               ? old->capacity : RF_MAP_INITIAL_CAPACITY);
    for (rf_int64 i = 0; i < old->capacity; i++) {
        RF_MapEntry* e = &old->entries[i];
        if (!e->occupied) continue;
        if (e->key_len == key_len && memcmp(e->key, key, (size_t)key_len) == 0)
            continue;
        void* kc = malloc((size_t)e->key_len);
        if (!kc) rf_panic("rf_set: out of memory");
        memcpy(kc, e->key, (size_t)e->key_len);
        rf_int64 idx = rf__map_probe(n, kc, e->key_len);
        n->entries[idx].key = kc;
        n->entries[idx].key_len = e->key_len;
        n->entries[idx].val = NULL;
        n->entries[idx].occupied = rf_true;
        n->count++;
    }
    rf_map_release(old);
    s->map = n;
    return rf_true;
}

rf_int64 rf_set_len(RF_Set* s) {
    return rf_map_len(s->map);
}

void rf_set_retain(RF_Set* s) {
    if (!s) return;
    atomic_fetch_add(&s->refcount, 1);
}

void rf_set_release(RF_Set* s) {
    if (!s) return;
    if (atomic_fetch_sub(&s->refcount, 1) != 1) return;
    rf_map_release(s->map);
    free(s);
}

/* ========================================================================
 * Buffer (RT-1-7-1, RT-1-7-2)
 * ======================================================================== */

#define RF_BUFFER_INITIAL_CAPACITY 8

RF_Buffer* rf_buffer_new(rf_int64 element_size) {
    return rf_buffer_with_capacity(RF_BUFFER_INITIAL_CAPACITY, element_size);
}

RF_Buffer* rf_buffer_with_capacity(rf_int64 cap, rf_int64 element_size) {
    if (cap < 1) cap = 1;
    RF_Buffer* buf = (RF_Buffer*)malloc(sizeof(RF_Buffer));
    if (!buf) rf_panic("BufferOverflowError");
    buf->refcount = 1;
    buf->len = 0;
    buf->capacity = cap;
    buf->element_size = element_size;
    buf->data = malloc((size_t)(cap * element_size));
    if (!buf->data) rf_panic("BufferOverflowError");
    return buf;
}

void rf_buffer_push(RF_Buffer* buf, void* element) {
    if (buf->len == buf->capacity) {
        rf_int64 new_cap = buf->capacity * 2;
        void* new_data = realloc(buf->data, (size_t)(new_cap * buf->element_size));
        if (!new_data) rf_panic("BufferOverflowError");
        buf->data = new_data;
        buf->capacity = new_cap;
    }
    char* dest = (char*)buf->data + buf->len * buf->element_size;
    memcpy(dest, element, (size_t)buf->element_size);
    buf->len++;
}

RF_Option_ptr rf_buffer_get(RF_Buffer* buf, rf_int64 idx) {
    if (idx < 0 || idx >= buf->len) return RF_NONE_PTR;
    void* ptr = (char*)buf->data + idx * buf->element_size;
    return RF_SOME_PTR(ptr);
}

rf_int64 rf_buffer_len(RF_Buffer* buf) {
    return buf->len;
}

void rf_buffer_sort_by(RF_Buffer* buf, int (*cmp)(const void*, const void*)) {
    if (buf->len < 2) return;
    qsort(buf->data, (size_t)buf->len, (size_t)buf->element_size, cmp);
}

void rf_buffer_reverse(RF_Buffer* buf) {
    if (buf->len < 2) return;
    rf_int64 lo = 0, hi = buf->len - 1;
    rf_int64 esz = buf->element_size;
    void* tmp = malloc((size_t)esz);
    if (!tmp) rf_panic("BufferOverflowError");
    while (lo < hi) {
        char* a = (char*)buf->data + lo * esz;
        char* b = (char*)buf->data + hi * esz;
        memcpy(tmp, a, (size_t)esz);
        memcpy(a, b, (size_t)esz);
        memcpy(b, tmp, (size_t)esz);
        lo++;
        hi--;
    }
    free(tmp);
}

void rf_buffer_retain(RF_Buffer* buf) {
    if (!buf) return;
    atomic_fetch_add(&buf->refcount, 1);
}

void rf_buffer_release(RF_Buffer* buf) {
    if (!buf) return;
    if (atomic_fetch_sub(&buf->refcount, 1) == 1) {
        free(buf->data);
        free(buf);
    }
}

RF_Buffer* rf_buffer_collect(RF_Stream* s, rf_int64 element_size) {
    RF_Buffer* buf = rf_buffer_new(element_size);
    RF_Option_ptr item;
    while ((item = rf_stream_next(s)).tag == 1) {
        rf_buffer_push(buf, &item.value);
    }
    return buf;
}

/* Buffer drain stream */
typedef struct {
    RF_Buffer* buf;
    rf_int64   idx;
} RF_BufferDrainState;

static RF_Option_ptr rf__buffer_drain_next(RF_Stream* self) {
    RF_BufferDrainState* st = (RF_BufferDrainState*)self->state;
    if (st->idx >= st->buf->len) return RF_NONE_PTR;
    void* ptr = (char*)st->buf->data + st->idx * st->buf->element_size;
    st->idx++;
    return RF_SOME_PTR(ptr);
}

static void rf__buffer_drain_free(RF_Stream* self) {
    RF_BufferDrainState* st = (RF_BufferDrainState*)self->state;
    rf_buffer_release(st->buf);
    free(st);
}

RF_Stream* rf_buffer_drain(RF_Buffer* buf) {
    rf_buffer_retain(buf);
    RF_BufferDrainState* st = (RF_BufferDrainState*)malloc(sizeof(RF_BufferDrainState));
    if (!st) rf_panic("BufferOverflowError");
    st->buf = buf;
    st->idx = 0;
    return rf_stream_new(rf__buffer_drain_next, rf__buffer_drain_free, st);
}

/* --- Buffer extensions (SL-4-3) --- */

RF_Array* rf_buffer_to_array(RF_Buffer* buf) {
    return rf_array_new(buf->len, buf->element_size, buf->data);
}

void rf_buffer_clear(RF_Buffer* buf) {
    buf->len = 0;
}

RF_Option_ptr rf_buffer_pop(RF_Buffer* buf) {
    if (buf->len == 0) return RF_NONE_PTR;
    buf->len--;
    void* ptr = (char*)buf->data + buf->len * buf->element_size;
    void* copy = malloc((size_t)buf->element_size);
    if (!copy) rf_panic("rf_buffer_pop: out of memory");
    memcpy(copy, ptr, (size_t)buf->element_size);
    return RF_SOME_PTR(copy);
}

RF_Option_ptr rf_buffer_last(RF_Buffer* buf) {
    if (buf->len == 0) return RF_NONE_PTR;
    void* ptr = (char*)buf->data + (buf->len - 1) * buf->element_size;
    void* copy = malloc((size_t)buf->element_size);
    if (!copy) rf_panic("rf_buffer_last: out of memory");
    memcpy(copy, ptr, (size_t)buf->element_size);
    return RF_SOME_PTR(copy);
}

void rf_buffer_set(RF_Buffer* buf, rf_int64 idx, void* element) {
    if (idx < 0 || idx >= buf->len) rf_panic_oob();
    void* ptr = (char*)buf->data + idx * buf->element_size;
    memcpy(ptr, element, (size_t)buf->element_size);
}

void rf_buffer_insert(RF_Buffer* buf, rf_int64 idx, void* element) {
    if (idx < 0 || idx > buf->len) rf_panic_oob();
    /* Ensure capacity */
    if (buf->len >= buf->capacity) {
        rf_int64 new_cap = buf->capacity < 8 ? 8 : buf->capacity * 2;
        buf->data = realloc(buf->data, (size_t)(new_cap * buf->element_size));
        if (!buf->data) rf_panic("rf_buffer_insert: out of memory");
        buf->capacity = new_cap;
    }
    /* Shift elements right */
    if (idx < buf->len) {
        memmove((char*)buf->data + (idx + 1) * buf->element_size,
                (char*)buf->data + idx * buf->element_size,
                (size_t)((buf->len - idx) * buf->element_size));
    }
    memcpy((char*)buf->data + idx * buf->element_size, element, (size_t)buf->element_size);
    buf->len++;
}

RF_Option_ptr rf_buffer_remove(RF_Buffer* buf, rf_int64 idx) {
    if (idx < 0 || idx >= buf->len) return RF_NONE_PTR;
    void* ptr = (char*)buf->data + idx * buf->element_size;
    void* copy = malloc((size_t)buf->element_size);
    if (!copy) rf_panic("rf_buffer_remove: out of memory");
    memcpy(copy, ptr, (size_t)buf->element_size);
    /* Shift elements left */
    if (idx < buf->len - 1) {
        memmove(ptr,
                (char*)buf->data + (idx + 1) * buf->element_size,
                (size_t)((buf->len - idx - 1) * buf->element_size));
    }
    buf->len--;
    return RF_SOME_PTR(copy);
}

rf_bool rf_buffer_contains(RF_Buffer* buf, void* element, rf_int64 element_size) {
    for (rf_int64 i = 0; i < buf->len; i++) {
        void* ptr = (char*)buf->data + i * buf->element_size;
        if (memcmp(ptr, element, (size_t)element_size) == 0) return rf_true;
    }
    return rf_false;
}

RF_Buffer* rf_buffer_slice(RF_Buffer* buf, rf_int64 start, rf_int64 end) {
    if (start < 0) start = 0;
    if (end > buf->len) end = buf->len;
    if (start >= end) return rf_buffer_new(buf->element_size);
    rf_int64 count = end - start;
    RF_Buffer* result = rf_buffer_with_capacity(count, buf->element_size);
    memcpy(result->data, (char*)buf->data + start * buf->element_size,
           (size_t)(count * buf->element_size));
    result->len = count;
    return result;
}

/* ========================================================================
 * Sort (stdlib/sort)
 * ======================================================================== */

/* --- closure-based sort (rf_sort_array_by) --- */
/*
 * The comparator closure must have fn signature:
 *   rf_int (*)(void* env, const void* a_ptr, const void* b_ptr)
 * where a_ptr and b_ptr are pointers into the array's element buffer.
 *
 * The compiler generates a sort comparator wrapper (via _lower_sort_closure_wrapper
 * in lowering.py) that dereferences a_ptr and b_ptr to typed element values
 * before calling the user's typed comparator closure. This bridging is needed
 * because qsort passes element addresses, not element values.
 */

static _Thread_local RF_Closure* _rf_sort_closure;

static int _rf_sort_closure_cmp(const void* a, const void* b) {
    typedef rf_int (*CmpFn)(void*, const void*, const void*);
    CmpFn fn = (CmpFn)_rf_sort_closure->fn;
    return (int)fn(_rf_sort_closure->env, a, b);
}

RF_Array* rf_sort_array_by(RF_Array* arr, RF_Closure* cmp) {
    if (!arr) rf_panic("rf_sort_array_by: NULL array");
    if (!cmp) rf_panic("rf_sort_array_by: NULL closure");
    if (arr->len == 0) return rf_array_new(0, arr->element_size, NULL);

    /* Copy data into temp buffer */
    size_t total = (size_t)arr->len * (size_t)arr->element_size;
    void* tmp = malloc(total);
    if (!tmp) rf_panic("rf_sort_array_by: out of memory");
    memcpy(tmp, arr->data, total);

    /* Set thread-local closure and sort */
    _rf_sort_closure = cmp;
    qsort(tmp, (size_t)arr->len, (size_t)arr->element_size, _rf_sort_closure_cmp);

    RF_Array* result = rf_array_new(arr->len, arr->element_size, tmp);
    free(tmp);
    return result;
}

/* --- reverse --- */

RF_Array* rf_array_reverse(RF_Array* arr) {
    if (!arr) rf_panic("rf_array_reverse: NULL array");
    if (arr->len == 0) return rf_array_new(0, arr->element_size, NULL);

    rf_int64 esz = arr->element_size;
    size_t total = (size_t)arr->len * (size_t)esz;
    void* tmp = malloc(total);
    if (!tmp) rf_panic("rf_array_reverse: out of memory");

    for (rf_int64 i = 0; i < arr->len; i++) {
        char* src = (char*)arr->data + i * esz;
        char* dst = (char*)tmp + (arr->len - 1 - i) * esz;
        memcpy(dst, src, (size_t)esz);
    }

    RF_Array* result = rf_array_new(arr->len, arr->element_size, tmp);
    free(tmp);
    return result;
}

/* ========================================================================
 * Bytes (stdlib/bytes)
 * ======================================================================== */

RF_Array* rf_bytes_slice(RF_Array* arr, rf_int64 start, rf_int64 end) {
    if (!arr) rf_panic("rf_bytes_slice: NULL array");
    rf_int64 len = rf_array_len(arr);
    if (start < 0) start = 0;
    if (start > len) start = len;
    if (end < start) end = start;
    if (end > len) end = len;
    rf_int64 slice_len = end - start;
    if (slice_len == 0) return rf_array_new(0, 1, NULL);
    rf_byte* src = (rf_byte*)arr->data + start;
    return rf_array_new(slice_len, 1, src);
}

RF_Array* rf_bytes_concat(RF_Array* a, RF_Array* b) {
    if (!a) rf_panic("rf_bytes_concat: NULL first argument");
    if (!b) rf_panic("rf_bytes_concat: NULL second argument");
    rf_int64 a_len = rf_array_len(a);
    rf_int64 b_len = rf_array_len(b);
    rf_int64 total = a_len + b_len;
    if (total == 0) return rf_array_new(0, 1, NULL);
    rf_byte* buf = (rf_byte*)malloc((size_t)total);
    if (!buf) rf_panic("rf_bytes_concat: out of memory");
    if (a_len > 0) memcpy(buf, a->data, (size_t)a_len);
    if (b_len > 0) memcpy(buf + a_len, b->data, (size_t)b_len);
    RF_Array* result = rf_array_new(total, 1, buf);
    free(buf);
    return result;
}

RF_Option_ptr rf_bytes_index_of(RF_Array* haystack, rf_byte needle) {
    if (!haystack) rf_panic("rf_bytes_index_of: NULL array");
    rf_int64 len = rf_array_len(haystack);
    rf_byte* data = (rf_byte*)haystack->data;
    for (rf_int64 i = 0; i < len; i++) {
        if (data[i] == needle) {
            return RF_SOME_PTR((void*)(intptr_t)i);
        }
    }
    return RF_NONE_PTR;
}

rf_int64 rf_bytes_len(RF_Array* arr) {
    if (!arr) rf_panic("rf_bytes_len: NULL array");
    return rf_array_len(arr);
}

/* ========================================================================
 * I/O Primitives (RT-1-8-1, RT-1-8-2)
 * ======================================================================== */

void rf_print(RF_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stdout);
}

void rf_println(RF_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stdout);
    fputc('\n', stdout);
}

void rf_eprint(RF_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stderr);
}

void rf_eprintln(RF_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stderr);
    fputc('\n', stderr);
}

/* Stdin byte stream */
typedef struct {
    int dummy;
} RF_StdinState;

static RF_Option_ptr rf__stdin_next(RF_Stream* self) {
    (void)self;
    int c = fgetc(stdin);
    if (c == EOF) return RF_NONE_PTR;
    rf_byte* bp = (rf_byte*)malloc(sizeof(rf_byte));
    if (!bp) rf_panic("rf_stdin_stream: out of memory");
    *bp = (rf_byte)c;
    return RF_SOME_PTR(bp);
}

static void rf__stdin_free(RF_Stream* self) {
    free(self->state);
}

RF_Stream* rf_stdin_stream(void) {
    RF_StdinState* st = (RF_StdinState*)malloc(sizeof(RF_StdinState));
    if (!st) rf_panic("rf_stdin_stream: out of memory");
    st->dummy = 0;
    return rf_stream_new(rf__stdin_next, rf__stdin_free, st);
}

RF_Option_ptr rf_read_line(void) {
    rf_int64 cap = 128;
    rf_int64 len = 0;
    char* buf = (char*)malloc((size_t)cap);
    if (!buf) rf_panic("rf_read_line: out of memory");

    int c;
    while ((c = fgetc(stdin)) != EOF) {
        if (len + 1 >= cap) {
            cap *= 2;
            char* nb = (char*)realloc(buf, (size_t)cap);
            if (!nb) { free(buf); rf_panic("rf_read_line: out of memory"); }
            buf = nb;
        }
        if (c == '\n') break;
        buf[len++] = (char)c;
    }

    if (len == 0 && c == EOF) {
        free(buf);
        return RF_NONE_PTR;
    }

    RF_String* s = rf_string_new(buf, len);
    free(buf);
    return RF_SOME_PTR(s);
}

RF_Option_ptr rf_read_byte(void) {
    int c = fgetc(stdin);
    if (c == EOF) return RF_NONE_PTR;
    return (RF_Option_ptr){.tag = 1, .value = (void*)(uintptr_t)(rf_byte)c};
}

/* ========================================================================
 * String Operations (stdlib/string — RB-1-1)
 * ======================================================================== */

RF_Option_char rf_string_char_at(RF_String* s, rf_int64 idx) {
    /* BOOTSTRAP SIMPLIFICATION: byte indexing, not codepoint indexing.
     * All bootstrap compiler source files are ASCII. */
    if (!s || idx < 0 || idx >= s->len) return (RF_Option_char){.tag = 0};
    rf_char c = (rf_char)(unsigned char)s->data[idx];
    return (RF_Option_char){.tag = 1, .value = c};
}

RF_String* rf_string_substring(RF_String* s, rf_int64 start, rf_int64 end) {
    if (!s) rf_panic("rf_string_substring: NULL pointer");
    if (start < 0) start = 0;
    if (end > s->len) end = s->len;
    if (start > end) rf_panic("rf_string_substring: start > end");
    return rf_string_new(s->data + start, end - start);
}

RF_Option_int rf_string_index_of(RF_String* haystack, RF_String* needle) {
    if (!haystack || !needle) return (RF_Option_int){.tag = 0};
    if (needle->len == 0) {
        return (RF_Option_int){.tag = 1, .value = 0};
    }
    if (needle->len > haystack->len) return (RF_Option_int){.tag = 0};
    for (rf_int64 i = 0; i <= haystack->len - needle->len; i++) {
        if (memcmp(haystack->data + i, needle->data, (size_t)needle->len) == 0) {
            return (RF_Option_int){.tag = 1, .value = (rf_int)i};
        }
    }
    return (RF_Option_int){.tag = 0};
}

rf_bool rf_string_contains(RF_String* s, RF_String* needle) {
    RF_Option_int result = rf_string_index_of(s, needle);
    return result.tag == 1;
}

rf_bool rf_string_starts_with(RF_String* s, RF_String* prefix) {
    if (!s || !prefix) return rf_false;
    if (prefix->len > s->len) return rf_false;
    return memcmp(s->data, prefix->data, (size_t)prefix->len) == 0;
}

rf_bool rf_string_ends_with(RF_String* s, RF_String* suffix) {
    if (!s || !suffix) return rf_false;
    if (suffix->len > s->len) return rf_false;
    return memcmp(s->data + s->len - suffix->len, suffix->data,
                  (size_t)suffix->len) == 0;
}

RF_Array* rf_string_split(RF_String* s, RF_String* sep) {
    if (!s || !sep) rf_panic("rf_string_split: NULL argument");

    /* Collect parts into a buffer, then convert to array. */
    RF_Buffer* buf = rf_buffer_new(sizeof(RF_String*));

    if (sep->len == 0) {
        /* Split into individual characters (bytes for bootstrap). */
        for (rf_int64 i = 0; i < s->len; i++) {
            RF_String* ch = rf_string_new(s->data + i, 1);
            rf_buffer_push(buf, &ch);
        }
    } else {
        rf_int64 start = 0;
        for (rf_int64 i = 0; i <= s->len - sep->len; i++) {
            if (memcmp(s->data + i, sep->data, (size_t)sep->len) == 0) {
                RF_String* part = rf_string_new(s->data + start, i - start);
                rf_buffer_push(buf, &part);
                i += sep->len - 1;
                start = i + 1;
            }
        }
        /* Last segment */
        RF_String* last = rf_string_new(s->data + start, s->len - start);
        rf_buffer_push(buf, &last);
    }

    /* Convert buffer to array. */
    RF_Array* arr = rf_array_new(buf->len, sizeof(RF_String*), buf->data);
    rf_buffer_release(buf);
    return arr;
}

static rf_bool rf__is_ascii_ws(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

RF_String* rf_string_trim(RF_String* s) {
    if (!s) rf_panic("rf_string_trim: NULL pointer");
    rf_int64 start = 0;
    rf_int64 end = s->len;
    while (start < end && rf__is_ascii_ws(s->data[start])) start++;
    while (end > start && rf__is_ascii_ws(s->data[end - 1])) end--;
    return rf_string_new(s->data + start, end - start);
}

RF_String* rf_string_trim_left(RF_String* s) {
    if (!s) rf_panic("rf_string_trim_left: NULL pointer");
    rf_int64 start = 0;
    while (start < s->len && rf__is_ascii_ws(s->data[start])) start++;
    return rf_string_new(s->data + start, s->len - start);
}

RF_String* rf_string_trim_right(RF_String* s) {
    if (!s) rf_panic("rf_string_trim_right: NULL pointer");
    rf_int64 end = s->len;
    while (end > 0 && rf__is_ascii_ws(s->data[end - 1])) end--;
    return rf_string_new(s->data, end);
}

RF_String* rf_string_replace(RF_String* s, RF_String* old_s, RF_String* new_s) {
    if (!s || !old_s || !new_s) rf_panic("rf_string_replace: NULL argument");
    if (old_s->len == 0) return rf_string_new(s->data, s->len);

    /* Count occurrences to pre-calculate size. */
    rf_int64 count = 0;
    for (rf_int64 i = 0; i <= s->len - old_s->len; i++) {
        if (memcmp(s->data + i, old_s->data, (size_t)old_s->len) == 0) {
            count++;
            i += old_s->len - 1;
        }
    }
    if (count == 0) return rf_string_new(s->data, s->len);

    rf_int64 new_len = s->len + count * (new_s->len - old_s->len);
    RF_String* result = (RF_String*)malloc(sizeof(RF_String) + (size_t)new_len + 1);
    if (!result) rf_panic("rf_string_replace: out of memory");
    result->refcount = 1;
    result->len = new_len;

    rf_int64 src = 0, dst = 0;
    while (src <= s->len - old_s->len) {
        if (memcmp(s->data + src, old_s->data, (size_t)old_s->len) == 0) {
            memcpy(result->data + dst, new_s->data, (size_t)new_s->len);
            dst += new_s->len;
            src += old_s->len;
        } else {
            result->data[dst++] = s->data[src++];
        }
    }
    /* Copy remaining bytes after last possible match position. */
    while (src < s->len) {
        result->data[dst++] = s->data[src++];
    }
    result->data[new_len] = '\0';
    return result;
}

RF_String* rf_string_join(RF_Array* parts, RF_String* sep) {
    if (!parts || !sep) rf_panic("rf_string_join: NULL argument");
    if (parts->len == 0) return rf_string_new("", 0);

    /* Calculate total length. */
    rf_int64 total = 0;
    for (rf_int64 i = 0; i < parts->len; i++) {
        RF_String** sp = (RF_String**)((char*)parts->data +
                         (size_t)i * (size_t)parts->element_size);
        total += (*sp)->len;
    }
    total += sep->len * (parts->len - 1);

    RF_String* result = (RF_String*)malloc(sizeof(RF_String) + (size_t)total + 1);
    if (!result) rf_panic("rf_string_join: out of memory");
    result->refcount = 1;
    result->len = total;

    rf_int64 pos = 0;
    for (rf_int64 i = 0; i < parts->len; i++) {
        if (i > 0) {
            memcpy(result->data + pos, sep->data, (size_t)sep->len);
            pos += sep->len;
        }
        RF_String** sp = (RF_String**)((char*)parts->data +
                         (size_t)i * (size_t)parts->element_size);
        memcpy(result->data + pos, (*sp)->data, (size_t)(*sp)->len);
        pos += (*sp)->len;
    }
    result->data[total] = '\0';
    return result;
}

RF_String* rf_string_to_lower(RF_String* s) {
    if (!s) rf_panic("rf_string_to_lower: NULL pointer");
    RF_String* r = rf_string_new(s->data, s->len);
    for (rf_int64 i = 0; i < r->len; i++) {
        if (r->data[i] >= 'A' && r->data[i] <= 'Z') {
            r->data[i] = r->data[i] + ('a' - 'A');
        }
    }
    return r;
}

RF_String* rf_string_to_upper(RF_String* s) {
    if (!s) rf_panic("rf_string_to_upper: NULL pointer");
    RF_String* r = rf_string_new(s->data, s->len);
    for (rf_int64 i = 0; i < r->len; i++) {
        if (r->data[i] >= 'a' && r->data[i] <= 'z') {
            r->data[i] = r->data[i] - ('a' - 'A');
        }
    }
    return r;
}

RF_Array* rf_string_to_bytes(RF_String* s) {
    if (!s) rf_panic("rf_string_to_bytes: NULL pointer");
    return rf_array_new(s->len, sizeof(rf_byte), s->data);
}

RF_String* rf_string_from_bytes(RF_Array* data) {
    if (!data) rf_panic("rf_string_from_bytes: NULL pointer");
    return rf_string_new((const char*)data->data, data->len);
}

/* ========================================================================
 * Character Utilities (stdlib/char — RB-1-2)
 * ======================================================================== */

rf_bool rf_char_is_digit(rf_char c) {
    return c >= '0' && c <= '9';
}

rf_bool rf_char_is_alpha(rf_char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}

rf_bool rf_char_is_alphanumeric(rf_char c) {
    return rf_char_is_alpha(c) || rf_char_is_digit(c);
}

rf_bool rf_char_is_whitespace(rf_char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

rf_int rf_char_to_int(rf_char c) {
    return (rf_int)c;
}

rf_char rf_int_to_char(rf_int n) {
    return (rf_char)n;
}

RF_String* rf_char_to_string(rf_char c) {
    /* ASCII fast path (bootstrap simplification). */
    char buf[1];
    buf[0] = (char)c;
    return rf_string_new(buf, 1);
}

/* ========================================================================
 * File I/O (stdlib/io — RB-1-3)
 * ======================================================================== */

RF_Option_ptr rf_read_file(RF_String* path) {
    if (!path) return RF_NONE_PTR;
    FILE* f = fopen(path->data, "rb");
    if (!f) return RF_NONE_PTR;

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (sz < 0) { fclose(f); return RF_NONE_PTR; }

    char* buf = (char*)malloc((size_t)sz);
    if (!buf) { fclose(f); rf_panic("rf_read_file: out of memory"); }

    size_t read = fread(buf, 1, (size_t)sz, f);
    fclose(f);

    RF_String* s = rf_string_new(buf, (rf_int64)read);
    free(buf);
    return RF_SOME_PTR(s);
}

rf_bool rf_write_file(RF_String* path, RF_String* contents) {
    if (!path || !contents) return rf_false;
    FILE* f = fopen(path->data, "wb");
    if (!f) return rf_false;
    size_t written = fwrite(contents->data, 1, (size_t)contents->len, f);
    fclose(f);
    return written == (size_t)contents->len;
}

RF_Option_ptr rf_read_file_bytes(RF_String* path) {
    if (!path) return RF_NONE_PTR;
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)path->len, path->data);
    FILE* f = fopen(buf, "rb");
    if (!f) return RF_NONE_PTR;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    rf_byte* data = (rf_byte*)malloc(size > 0 ? (size_t)size : 1);
    if (!data) { fclose(f); rf_panic("rf_read_file_bytes: out of memory"); }
    rf_int64 n = (rf_int64)fread(data, 1, (size_t)size, f);
    fclose(f);
    RF_Array* arr = rf_array_new(n, sizeof(rf_byte), data);
    free(data);
    return RF_SOME_PTR(arr);
}

rf_bool rf_write_file_bytes(RF_String* path, RF_Array* data) {
    if (!path || !data) return rf_false;
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)path->len, path->data);
    FILE* f = fopen(buf, "wb");
    if (!f) return rf_false;
    size_t written = fwrite(data->data, 1, (size_t)(data->len * data->element_size), f);
    fclose(f);
    return written == (size_t)(data->len * data->element_size) ? rf_true : rf_false;
}

rf_bool rf_append_file(RF_String* path, RF_String* contents) {
    if (!path || !contents) return rf_false;
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)path->len, path->data);
    FILE* f = fopen(buf, "a");
    if (!f) return rf_false;
    size_t written = fwrite(contents->data, 1, (size_t)contents->len, f);
    fclose(f);
    return written == (size_t)contents->len ? rf_true : rf_false;
}

/* ========================================================================
 * Process Execution (stdlib/sys — RB-1-4)
 * ======================================================================== */

rf_int rf_run_process(RF_String* command, RF_Array* args) {
    if (!command) rf_panic("rf_run_process: NULL command");

    /* Build argv: [command, args..., NULL] */
    rf_int64 argc = args ? args->len : 0;
    char** argv = (char**)malloc(sizeof(char*) * (size_t)(argc + 2));
    if (!argv) rf_panic("rf_run_process: out of memory");

    argv[0] = command->data;
    for (rf_int64 i = 0; i < argc; i++) {
        RF_String** sp = (RF_String**)((char*)args->data +
                         (size_t)i * (size_t)args->element_size);
        argv[i + 1] = (*sp)->data;
    }
    argv[argc + 1] = NULL;

    pid_t pid = fork();
    if (pid < 0) {
        free(argv);
        return -1;
    }
    if (pid == 0) {
        /* Child process. */
        execvp(argv[0], argv);
        _exit(127);
    }

    /* Parent: wait for child. */
    free(argv);
    int status = 0;
    waitpid(pid, &status, 0);
    if (WIFEXITED(status)) return (rf_int)WEXITSTATUS(status);
    return -1;
}

RF_Option_ptr rf_run_process_capture(RF_String* command, RF_Array* args) {
    if (!command) rf_panic("rf_run_process_capture: NULL command");

    /* Build argv. */
    rf_int64 argc = args ? args->len : 0;
    char** argv = (char**)malloc(sizeof(char*) * (size_t)(argc + 2));
    if (!argv) rf_panic("rf_run_process_capture: out of memory");

    argv[0] = command->data;
    for (rf_int64 i = 0; i < argc; i++) {
        RF_String** sp = (RF_String**)((char*)args->data +
                         (size_t)i * (size_t)args->element_size);
        argv[i + 1] = (*sp)->data;
    }
    argv[argc + 1] = NULL;

    /* Create pipe for stderr. */
    int pipefd[2];
    if (pipe(pipefd) < 0) { free(argv); return RF_NONE_PTR; }

    pid_t pid = fork();
    if (pid < 0) {
        free(argv);
        close(pipefd[0]);
        close(pipefd[1]);
        return RF_NONE_PTR;
    }
    if (pid == 0) {
        /* Child: redirect stderr to pipe. */
        close(pipefd[0]);
        dup2(pipefd[1], STDERR_FILENO);
        close(pipefd[1]);
        execvp(argv[0], argv);
        _exit(127);
    }

    /* Parent: read stderr from pipe. */
    free(argv);
    close(pipefd[1]);

    RF_Buffer* buf = rf_buffer_new(1);
    char c;
    while (read(pipefd[0], &c, 1) == 1) {
        rf_buffer_push(buf, &c);
    }
    close(pipefd[0]);

    int status = 0;
    waitpid(pid, &status, 0);
    int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;

    if (exit_code != 0) {
        /* Return captured stderr as some(string). */
        RF_String* stderr_str = rf_string_new((const char*)buf->data, buf->len);
        rf_buffer_release(buf);
        return RF_SOME_PTR(stderr_str);
    }

    rf_buffer_release(buf);
    return RF_NONE_PTR;  /* Success: none. */
}

/* ========================================================================
 * Temporary File Support (stdlib/io — RB-1-5)
 * ======================================================================== */

RF_String* rf_tmpfile_create(RF_String* suffix, RF_String* contents) {
    if (!suffix || !contents) rf_panic("rf_tmpfile_create: NULL argument");

    /* Build template: /tmp/reflow_XXXXXX<suffix> */
    const char* prefix = "/tmp/reflow_XXXXXX";
    rf_int64 prefix_len = (rf_int64)strlen(prefix);
    rf_int64 total_len = prefix_len + suffix->len;
    char* tmpl = (char*)malloc((size_t)total_len + 1);
    if (!tmpl) rf_panic("rf_tmpfile_create: out of memory");
    memcpy(tmpl, prefix, (size_t)prefix_len);
    memcpy(tmpl + prefix_len, suffix->data, (size_t)suffix->len);
    tmpl[total_len] = '\0';

    int fd = mkstemps(tmpl, (int)suffix->len);
    if (fd < 0) {
        free(tmpl);
        rf_panic("rf_tmpfile_create: mkstemps failed");
    }

    /* Write contents. */
    ssize_t written = write(fd, contents->data, (size_t)contents->len);
    close(fd);
    (void)written;

    RF_String* path = rf_string_from_cstr(tmpl);
    free(tmpl);
    return path;
}

void rf_tmpfile_remove(RF_String* path) {
    if (!path) return;
    unlink(path->data);
}

/* ========================================================================
 * Path Utilities (stdlib/path — RB-1-6)
 * ======================================================================== */

RF_String* rf_path_join(RF_String* a, RF_String* b) {
    if (!a || !b) rf_panic("rf_path_join: NULL argument");
    if (a->len == 0) return rf_string_new(b->data, b->len);
    if (b->len == 0) return rf_string_new(a->data, a->len);
    /* Check if a already ends with '/' */
    if (a->data[a->len - 1] == '/') {
        return rf_string_concat(a, b);
    }
    RF_String* slash = rf_string_from_cstr("/");
    RF_String* tmp = rf_string_concat(a, slash);
    RF_String* result = rf_string_concat(tmp, b);
    rf_string_release(slash);
    rf_string_release(tmp);
    return result;
}

RF_String* rf_path_stem(RF_String* path) {
    if (!path) rf_panic("rf_path_stem: NULL pointer");
    /* Find last '/' */
    rf_int64 start = 0;
    for (rf_int64 i = path->len - 1; i >= 0; i--) {
        if (path->data[i] == '/') { start = i + 1; break; }
    }
    /* Find last '.' after start */
    rf_int64 end = path->len;
    for (rf_int64 i = path->len - 1; i >= start; i--) {
        if (path->data[i] == '.') { end = i; break; }
    }
    return rf_string_new(path->data + start, end - start);
}

RF_String* rf_path_parent(RF_String* path) {
    if (!path) rf_panic("rf_path_parent: NULL pointer");
    rf_int64 len = path->len;
    /* Skip trailing slash so parent("/a/b/") == "/a", not "/a/b" */
    if (len > 1 && path->data[len - 1] == '/') len--;
    rf_int64 last_slash = -1;
    for (rf_int64 i = len - 1; i >= 0; i--) {
        if (path->data[i] == '/') { last_slash = i; break; }
    }
    if (last_slash < 0) return rf_string_from_cstr(".");
    if (last_slash == 0) return rf_string_from_cstr("/");
    return rf_string_new(path->data, last_slash);
}

RF_String* rf_path_with_suffix(RF_String* path, RF_String* suffix) {
    if (!path || !suffix) rf_panic("rf_path_with_suffix: NULL argument");
    /* Find last '.' */
    rf_int64 dot = -1;
    rf_int64 last_slash = -1;
    for (rf_int64 i = path->len - 1; i >= 0; i--) {
        if (path->data[i] == '/' && last_slash < 0) { last_slash = i; break; }
        if (path->data[i] == '.' && dot < 0) { dot = i; }
    }
    rf_int64 base_end = (dot >= 0 && dot > last_slash) ? dot : path->len;
    RF_String* base = rf_string_new(path->data, base_end);
    RF_String* result = rf_string_concat(base, suffix);
    rf_string_release(base);
    return result;
}

RF_String* rf_path_cwd(void) {
    char buf[PATH_MAX];
    if (getcwd(buf, sizeof(buf)) == NULL) {
        rf_panic("rf_path_cwd: getcwd failed");
    }
    return rf_string_from_cstr(buf);
}

RF_String* rf_path_resolve(RF_String* path) {
    if (!path) rf_panic("rf_path_resolve: NULL pointer");
    char resolved[PATH_MAX];
    if (realpath(path->data, resolved) == NULL) {
        /* If file doesn't exist, return the path as-is. */
        return rf_string_new(path->data, path->len);
    }
    return rf_string_from_cstr(resolved);
}

rf_bool rf_path_exists(RF_String* path) {
    if (!path) return rf_false;
    return access(path->data, F_OK) == 0;
}

rf_bool rf_path_is_dir(RF_String* path) {
    if (!path) return rf_false;
    struct stat st;
    if (stat(path->data, &st) != 0) return rf_false;
    return S_ISDIR(st.st_mode) ? rf_true : rf_false;
}

rf_bool rf_path_is_file(RF_String* path) {
    if (!path) return rf_false;
    struct stat st;
    if (stat(path->data, &st) != 0) return rf_false;
    return S_ISREG(st.st_mode) ? rf_true : rf_false;
}

RF_Option_ptr rf_path_extension(RF_String* path) {
    if (!path) return RF_NONE_PTR;
    /* Find the last '/' to determine basename start */
    rf_int64 base_start = 0;
    for (rf_int64 i = path->len - 1; i >= 0; i--) {
        if (path->data[i] == '/') { base_start = i + 1; break; }
    }
    /* Find the last '.' after base_start */
    rf_int64 dot = -1;
    for (rf_int64 i = path->len - 1; i >= base_start; i--) {
        if (path->data[i] == '.') { dot = i; break; }
    }
    if (dot < 0 || dot == base_start) return RF_NONE_PTR;
    /* Return extension including the dot */
    RF_String* ext = rf_string_new(path->data + dot, path->len - dot);
    return RF_SOME_PTR(ext);
}

RF_Option_ptr rf_path_list_dir(RF_String* path) {
    if (!path) return RF_NONE_PTR;
    DIR* dir = opendir(path->data);
    if (!dir) return RF_NONE_PTR;

    RF_Buffer* buf = rf_buffer_new(sizeof(RF_String*));
    struct dirent* entry;
    while ((entry = readdir(dir)) != NULL) {
        /* Skip "." and ".." */
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;
        RF_String* name = rf_string_from_cstr(entry->d_name);
        rf_buffer_push(buf, &name);
    }
    closedir(dir);

    RF_Array* arr = rf_array_new(buf->len, sizeof(RF_String*), buf->data);
    rf_buffer_release(buf);
    return RF_SOME_PTR(arr);
}

/* ========================================================================
 * File Handle I/O (stdlib/file)
 * ======================================================================== */

struct RF_File {
    FILE*   fp;
    rf_bool is_binary;
};

/* --- Opening --- */

static RF_Option_ptr rf__file_open(RF_String* path, const char* mode, rf_bool is_binary) {
    if (!path) return RF_NONE_PTR;
    FILE* fp = fopen(path->data, mode);
    if (!fp) return RF_NONE_PTR;
    RF_File* f = (RF_File*)malloc(sizeof(RF_File));
    if (!f) { fclose(fp); rf_panic("rf_file_open: out of memory"); }
    f->fp = fp;
    f->is_binary = is_binary;
    return RF_SOME_PTR(f);
}

RF_Option_ptr rf_file_open_read(RF_String* path) {
    return rf__file_open(path, "r", rf_false);
}

RF_Option_ptr rf_file_open_write(RF_String* path) {
    return rf__file_open(path, "w", rf_false);
}

RF_Option_ptr rf_file_open_append(RF_String* path) {
    return rf__file_open(path, "a", rf_false);
}

RF_Option_ptr rf_file_open_read_bytes(RF_String* path) {
    return rf__file_open(path, "rb", rf_true);
}

RF_Option_ptr rf_file_open_write_bytes(RF_String* path) {
    return rf__file_open(path, "wb", rf_true);
}

/* --- Closing --- */

void rf_file_close(RF_File* f) {
    if (!f) return;
    if (f->fp) {
        fclose(f->fp);
        f->fp = NULL;
    }
    free(f);
}

/* --- Reading --- */

RF_Option_ptr rf_file_read_bytes(RF_File* f, rf_int n) {
    if (!f || !f->fp || n <= 0) return RF_NONE_PTR;
    rf_byte* buf = (rf_byte*)malloc((size_t)n);
    if (!buf) rf_panic("rf_file_read_bytes: out of memory");
    size_t read_count = fread(buf, 1, (size_t)n, f->fp);
    if (read_count == 0) {
        free(buf);
        return RF_NONE_PTR;
    }
    RF_Array* arr = rf_array_new((rf_int64)read_count, sizeof(rf_byte), buf);
    free(buf);
    return RF_SOME_PTR(arr);
}

RF_Option_ptr rf_file_read_line(RF_File* f) {
    if (!f || !f->fp) return RF_NONE_PTR;
    rf_int64 cap = 128;
    rf_int64 len = 0;
    char* buf = (char*)malloc((size_t)cap);
    if (!buf) rf_panic("rf_file_read_line: out of memory");

    int c;
    while ((c = fgetc(f->fp)) != EOF) {
        if (len + 1 >= cap) {
            cap *= 2;
            char* nb = (char*)realloc(buf, (size_t)cap);
            if (!nb) { free(buf); rf_panic("rf_file_read_line: out of memory"); }
            buf = nb;
        }
        if (c == '\n') break;
        buf[len++] = (char)c;
    }

    if (len == 0 && c == EOF) {
        free(buf);
        return RF_NONE_PTR;
    }

    /* Strip trailing \r for CRLF line endings */
    if (len > 0 && buf[len - 1] == '\r') len--;

    RF_String* s = rf_string_new(buf, len);
    free(buf);
    return RF_SOME_PTR(s);
}

RF_Option_ptr rf_file_read_all(RF_File* f) {
    if (!f || !f->fp) return RF_NONE_PTR;

    /* Save current position, seek to end to get remaining size */
    long cur = ftell(f->fp);
    if (cur < 0) return RF_NONE_PTR;
    fseek(f->fp, 0, SEEK_END);
    long end = ftell(f->fp);
    if (end < 0) { fseek(f->fp, cur, SEEK_SET); return RF_NONE_PTR; }
    fseek(f->fp, cur, SEEK_SET);

    long remaining = end - cur;
    if (remaining <= 0) {
        /* Try reading in a loop in case ftell doesn't work (e.g. pipes) */
        RF_Buffer* buf = rf_buffer_new(1);
        int c;
        while ((c = fgetc(f->fp)) != EOF) {
            char ch = (char)c;
            rf_buffer_push(buf, &ch);
        }
        if (buf->len == 0) {
            rf_buffer_release(buf);
            return RF_NONE_PTR;
        }
        RF_String* s = rf_string_new((const char*)buf->data, buf->len);
        rf_buffer_release(buf);
        return RF_SOME_PTR(s);
    }

    char* data = (char*)malloc((size_t)remaining);
    if (!data) rf_panic("rf_file_read_all: out of memory");
    size_t read_count = fread(data, 1, (size_t)remaining, f->fp);
    RF_String* s = rf_string_new(data, (rf_int64)read_count);
    free(data);
    return RF_SOME_PTR(s);
}

RF_Option_ptr rf_file_read_all_bytes(RF_File* f) {
    if (!f || !f->fp) return RF_NONE_PTR;

    long cur = ftell(f->fp);
    if (cur < 0) return RF_NONE_PTR;
    fseek(f->fp, 0, SEEK_END);
    long end = ftell(f->fp);
    if (end < 0) { fseek(f->fp, cur, SEEK_SET); return RF_NONE_PTR; }
    fseek(f->fp, cur, SEEK_SET);

    long remaining = end - cur;
    if (remaining <= 0) {
        /* Fallback: read in a loop */
        RF_Buffer* buf = rf_buffer_new(1);
        int c;
        while ((c = fgetc(f->fp)) != EOF) {
            rf_byte b = (rf_byte)c;
            rf_buffer_push(buf, &b);
        }
        if (buf->len == 0) {
            rf_buffer_release(buf);
            return RF_NONE_PTR;
        }
        RF_Array* arr = rf_array_new(buf->len, sizeof(rf_byte), buf->data);
        rf_buffer_release(buf);
        return RF_SOME_PTR(arr);
    }

    rf_byte* data = (rf_byte*)malloc((size_t)remaining);
    if (!data) rf_panic("rf_file_read_all_bytes: out of memory");
    size_t read_count = fread(data, 1, (size_t)remaining, f->fp);
    RF_Array* arr = rf_array_new((rf_int64)read_count, sizeof(rf_byte), data);
    free(data);
    return RF_SOME_PTR(arr);
}

/* --- Streams --- */

typedef struct {
    RF_File* file;
} _RF_FileLinesState;

static RF_Option_ptr _rf_file_lines_next(RF_Stream* self) {
    _RF_FileLinesState* st = (_RF_FileLinesState*)self->state;
    return rf_file_read_line(st->file);
}

static void _rf_file_lines_free(RF_Stream* self) {
    /* Does NOT close the file -- caller manages file lifetime */
    free(self->state);
}

RF_Stream* rf_file_lines(RF_File* f) {
    _RF_FileLinesState* st = (_RF_FileLinesState*)malloc(sizeof(_RF_FileLinesState));
    if (!st) rf_panic("rf_file_lines: out of memory");
    st->file = f;
    return rf_stream_new(_rf_file_lines_next, _rf_file_lines_free, st);
}

typedef struct {
    RF_File* file;
} _RF_FileByteStreamState;

static RF_Option_ptr _rf_file_byte_stream_next(RF_Stream* self) {
    _RF_FileByteStreamState* st = (_RF_FileByteStreamState*)self->state;
    if (!st->file || !st->file->fp) return RF_NONE_PTR;
    int c = fgetc(st->file->fp);
    if (c == EOF) return RF_NONE_PTR;
    return (RF_Option_ptr){.tag = 1, .value = (void*)(uintptr_t)(rf_byte)c};
}

static void _rf_file_byte_stream_free(RF_Stream* self) {
    /* Does NOT close the file -- caller manages file lifetime */
    free(self->state);
}

RF_Stream* rf_file_byte_stream(RF_File* f) {
    _RF_FileByteStreamState* st = (_RF_FileByteStreamState*)malloc(sizeof(_RF_FileByteStreamState));
    if (!st) rf_panic("rf_file_byte_stream: out of memory");
    st->file = f;
    return rf_stream_new(_rf_file_byte_stream_next, _rf_file_byte_stream_free, st);
}

/* --- Writing --- */

rf_bool rf_file_write_bytes(RF_File* f, RF_Array* data) {
    if (!f || !f->fp || !data) return rf_false;
    size_t total = (size_t)data->len * (size_t)data->element_size;
    size_t written = fwrite(data->data, 1, total, f->fp);
    return written == total ? rf_true : rf_false;
}

rf_bool rf_file_write_string(RF_File* f, RF_String* s) {
    if (!f || !f->fp || !s) return rf_false;
    size_t written = fwrite(s->data, 1, (size_t)s->len, f->fp);
    return written == (size_t)s->len ? rf_true : rf_false;
}

rf_bool rf_file_flush(RF_File* f) {
    if (!f || !f->fp) return rf_false;
    return fflush(f->fp) == 0 ? rf_true : rf_false;
}

/* --- Seeking --- */

rf_bool rf_file_seek(RF_File* f, rf_int64 offset) {
    if (!f || !f->fp) return rf_false;
    return fseek(f->fp, (long)offset, SEEK_SET) == 0 ? rf_true : rf_false;
}

rf_bool rf_file_seek_end(RF_File* f, rf_int64 offset) {
    if (!f || !f->fp) return rf_false;
    return fseek(f->fp, (long)offset, SEEK_END) == 0 ? rf_true : rf_false;
}

rf_int64 rf_file_position(RF_File* f) {
    if (!f || !f->fp) return -1;
    return (rf_int64)ftell(f->fp);
}

rf_int64 rf_file_size(RF_File* f) {
    if (!f || !f->fp) return -1;
    long cur = ftell(f->fp);
    if (cur < 0) return -1;
    fseek(f->fp, 0, SEEK_END);
    long sz = ftell(f->fp);
    fseek(f->fp, cur, SEEK_SET);
    return (rf_int64)sz;
}

/* ========================================================================
 * Math Functions (stdlib/math)
 * ======================================================================== */

rf_float rf_math_floor(rf_float f) {
    return floor(f);
}

rf_float rf_math_ceil(rf_float f) {
    return ceil(f);
}

rf_float rf_math_round(rf_float f) {
    return round(f);
}

rf_float rf_math_pow(rf_float base, rf_float exp) {
    return pow(base, exp);
}

rf_float rf_math_sqrt(rf_float f) {
    return sqrt(f);
}

rf_float rf_math_log(rf_float f) {
    return log(f);
}

/* ========================================================================
 * Exception Handling (setjmp/longjmp)
 * ======================================================================== */

_Thread_local RF_ExceptionFrame* _rf_exception_current = NULL;

void _rf_exception_push(RF_ExceptionFrame* frame) {
    frame->parent = _rf_exception_current;
    frame->exception = NULL;
    frame->exception_tag = -1;
    _rf_exception_current = frame;
}

void _rf_exception_pop(void) {
    if (_rf_exception_current) {
        _rf_exception_current = _rf_exception_current->parent;
    }
}

void _rf_throw(void* exception, rf_int tag) {
    if (_rf_exception_current == NULL) {
        fprintf(stderr, "ReFlow runtime error: unhandled exception (tag %d)\n", tag);
        exit(1);
    }
    _rf_exception_current->exception = exception;
    _rf_exception_current->exception_tag = tag;
    longjmp(_rf_exception_current->jmp, 1);
}

void _rf_rethrow(void) {
    /* Re-throw the current exception up to the parent frame.
     * The exception pointer and tag are preserved from the catch dispatch. */
    if (_rf_exception_current == NULL) {
        fprintf(stderr, "ReFlow runtime error: unhandled exception (rethrow)\n");
        exit(1);
    }
    longjmp(_rf_exception_current->jmp, 1);
}

/* ========================================================================
 * Parallel Fan-out
 * ======================================================================== */

static void* _rf_fanout_worker(void* raw) {
    RF_FanoutBranch* task = (RF_FanoutBranch*)raw;
    task->has_exception = rf_false;
    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        task->result = task->fn(task->arg);
    } else {
        task->has_exception = rf_true;
        task->exception = ef.exception;
        task->exception_tag = ef.exception_tag;
    }
    _rf_exception_pop();
    return NULL;
}

void rf_fanout_run(RF_FanoutBranch* branches, rf_int count) {
    if (count <= 0) return;
    if (count == 1) {
        _rf_fanout_worker(&branches[0]);
        return;
    }
    pthread_t* threads = malloc(sizeof(pthread_t) * (size_t)count);
    /* Run branches 1..N-1 on new threads, branch 0 on current thread */
    for (rf_int i = 1; i < count; i++)
        pthread_create(&threads[i], NULL, _rf_fanout_worker, &branches[i]);
    /* Branch 0 on main thread (preserves exception frame stack) */
    _rf_fanout_worker(&branches[0]);
    for (rf_int i = 1; i < count; i++)
        pthread_join(threads[i], NULL);
    free(threads);
    /* Re-throw leftmost exception (sequential semantics) */
    for (rf_int i = 0; i < count; i++)
        if (branches[i].has_exception)
            _rf_throw(branches[i].exception, branches[i].exception_tag);
}

/* ========================================================================
 * Runtime Initialization
 * ======================================================================== */

static int    _rf_argc = 0;
static char** _rf_argv = NULL;

void _rf_runtime_init(int argc, char** argv) {
    _rf_argc = argc;
    _rf_argv = argv;
}

/* ========================================================================
 * System Functions (stdlib/sys)
 * ======================================================================== */

void rf_sys_exit(rf_int code) {
    exit((int)code);
}

RF_Array* rf_sys_args(void) {
    RF_Array* arr = rf_array_new(_rf_argc, sizeof(RF_String*), NULL);
    for (int i = 0; i < _rf_argc; i++) {
        RF_String* s = rf_string_from_cstr(_rf_argv[i]);
        memcpy((char*)arr->data + (size_t)i * sizeof(RF_String*), &s, sizeof(RF_String*));
    }
    return arr;
}

RF_Option_ptr rf_env_get(RF_String* name) {
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)name->len, name->data);
    const char* val = getenv(buf);
    if (!val) return RF_NONE_PTR;
    return RF_SOME_PTR(rf_string_from_cstr(val));
}

rf_int64 rf_clock_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (rf_int64)ts.tv_sec * 1000 + (rf_int64)ts.tv_nsec / 1000000;
}

/* ========================================================================
 * Conversion Wrappers (stdlib/conv)
 * ======================================================================== */

RF_Option_int rf_string_to_int_opt(RF_String* s) {
    rf_int val;
    if (rf_string_to_int(s, &val)) {
        return (RF_Option_int){.tag = 1, .value = val};
    }
    return (RF_Option_int){.tag = 0, .value = 0};
}

RF_Option_int64 rf_string_to_int64_opt(RF_String* s) {
    rf_int64 val;
    if (rf_string_to_int64(s, &val)) {
        return (RF_Option_int64){.tag = 1, .value = val};
    }
    return (RF_Option_int64){.tag = 0, .value = 0};
}

RF_Option_float rf_string_to_float_opt(RF_String* s) {
    rf_float val;
    if (rf_string_to_float(s, &val)) {
        return (RF_Option_float){.tag = 1, .value = val};
    }
    return (RF_Option_float){.tag = 0, .value = 0.0};
}

/* ========================================================================
 * Random (stdlib/random) — xoshiro256** PRNG
 * ======================================================================== */

/* Thread-local xoshiro256** state */
static _Thread_local uint64_t _rf_rng_state[4];
static _Thread_local rf_bool _rf_rng_seeded = rf_false;

static uint64_t _rf_rotl(uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

static void _rf_rng_ensure_seeded(void) {
    if (_rf_rng_seeded) return;
    FILE* f = fopen("/dev/urandom", "rb");
    if (f) {
        size_t n = fread(_rf_rng_state, sizeof(uint64_t), 4, f);
        fclose(f);
        if (n == 4) { _rf_rng_seeded = rf_true; return; }
    }
    /* Fallback: seed from time + thread ID */
    uint64_t seed = (uint64_t)time(NULL) ^ ((uint64_t)(uintptr_t)&_rf_rng_state);
    _rf_rng_state[0] = seed;
    _rf_rng_state[1] = seed ^ 0x123456789ABCDEF0ULL;
    _rf_rng_state[2] = seed ^ 0xFEDCBA9876543210ULL;
    _rf_rng_state[3] = seed ^ 0xACEACEACEACEACEAULL;
    _rf_rng_seeded = rf_true;
}

static uint64_t _rf_rng_next_u64(void) {
    _rf_rng_ensure_seeded();
    uint64_t result = _rf_rotl(_rf_rng_state[1] * 5, 7) * 9;
    uint64_t t = _rf_rng_state[1] << 17;
    _rf_rng_state[2] ^= _rf_rng_state[0];
    _rf_rng_state[3] ^= _rf_rng_state[1];
    _rf_rng_state[1] ^= _rf_rng_state[2];
    _rf_rng_state[0] ^= _rf_rng_state[3];
    _rf_rng_state[2] ^= t;
    _rf_rng_state[3] = _rf_rotl(_rf_rng_state[3], 45);
    return result;
}

rf_int rf_random_int_range(rf_int min, rf_int max) {
    if (min > max) rf_panic("random.int_range: min > max");
    if (min == max) return min;
    uint64_t range = (uint64_t)(max - min) + 1;
    uint64_t limit = UINT64_MAX - (UINT64_MAX % range);
    uint64_t r;
    do { r = _rf_rng_next_u64(); } while (r >= limit);
    return min + (rf_int)(r % range);
}

rf_int64 rf_random_int64_range(rf_int64 min, rf_int64 max) {
    if (min > max) rf_panic("random.int64_range: min > max");
    if (min == max) return min;
    uint64_t range = (uint64_t)(max - min) + 1;
    uint64_t limit = UINT64_MAX - (UINT64_MAX % range);
    uint64_t r;
    do { r = _rf_rng_next_u64(); } while (r >= limit);
    return min + (rf_int64)(r % range);
}

rf_float rf_random_float_unit(void) {
    uint64_t r = _rf_rng_next_u64() >> 11;  /* 53 bits */
    return (rf_float)r * (1.0 / ((uint64_t)1 << 53));
}

rf_bool rf_random_bool(void) {
    return (_rf_rng_next_u64() & 1) ? rf_true : rf_false;
}

RF_Array* rf_random_bytes(rf_int n) {
    if (n <= 0) return rf_array_new(0, 1, NULL);
    rf_byte* buf = (rf_byte*)malloc((size_t)n);
    if (!buf) rf_panic("rf_random_bytes: out of memory");
    FILE* f = fopen("/dev/urandom", "rb");
    if (f) {
        size_t read = fread(buf, 1, (size_t)n, f);
        fclose(f);
        if (read < (size_t)n) {
            /* Fill remainder from PRNG */
            _rf_rng_ensure_seeded();
            for (rf_int i = (rf_int)read; i < n; i++) {
                buf[i] = (rf_byte)(_rf_rng_next_u64() & 0xFF);
            }
        }
    } else {
        _rf_rng_ensure_seeded();
        for (rf_int i = 0; i < n; i++) {
            buf[i] = (rf_byte)(_rf_rng_next_u64() & 0xFF);
        }
    }
    RF_Array* arr = rf_array_new(n, 1, buf);
    free(buf);
    return arr;
}

RF_Array* rf_random_shuffle(RF_Array* arr) {
    rf_int64 len = rf_array_len(arr);
    if (len <= 1) {
        rf_array_retain(arr);
        return arr;
    }
    rf_int64 elem_size = arr->element_size;
    rf_byte* buf = (rf_byte*)malloc((size_t)(len * elem_size));
    if (!buf) rf_panic("rf_random_shuffle: out of memory");
    memcpy(buf, arr->data, (size_t)(len * elem_size));
    _rf_rng_ensure_seeded();
    for (rf_int64 i = len - 1; i > 0; i--) {
        rf_int64 j = (rf_int64)(_rf_rng_next_u64() % (uint64_t)(i + 1));
        /* swap buf[i] and buf[j] */
        if (elem_size <= 16) {
            rf_byte tmp[16];
            memcpy(tmp, buf + i * elem_size, (size_t)elem_size);
            memcpy(buf + i * elem_size, buf + j * elem_size, (size_t)elem_size);
            memcpy(buf + j * elem_size, tmp, (size_t)elem_size);
        } else {
            rf_byte* t = (rf_byte*)malloc((size_t)elem_size);
            if (!t) rf_panic("rf_random_shuffle: out of memory");
            memcpy(t, buf + i * elem_size, (size_t)elem_size);
            memcpy(buf + i * elem_size, buf + j * elem_size, (size_t)elem_size);
            memcpy(buf + j * elem_size, t, (size_t)elem_size);
            free(t);
        }
    }
    RF_Array* result = rf_array_new(len, elem_size, buf);
    free(buf);
    return result;
}

RF_Option_ptr rf_random_choice(RF_Array* arr) {
    rf_int64 len = rf_array_len(arr);
    if (len == 0) return RF_NONE_PTR;
    rf_int64 idx = (rf_int64)(_rf_rng_next_u64() % (uint64_t)len);
    void* ptr = rf_array_get_ptr(arr, idx);
    /* For pointer-sized elements, dereference; for smaller, return pointer to data */
    if (arr->element_size == sizeof(void*)) {
        return RF_SOME_PTR(*(void**)ptr);
    }
    return RF_SOME_PTR(ptr);
}

/* ========================================================================
 * Time (stdlib/time)
 * ======================================================================== */

struct RF_Instant {
    struct timespec ts;
};

struct RF_DateTime {
    time_t     epoch;
    rf_int     utc_offset;
    struct tm  components;
};

/* --- Monotonic time --- */

RF_Instant* rf_time_now(void) {
    RF_Instant* inst = (RF_Instant*)malloc(sizeof(RF_Instant));
    if (!inst) rf_panic("rf_time_now: out of memory");
    clock_gettime(CLOCK_MONOTONIC, &inst->ts);
    return inst;
}

rf_int64 rf_time_elapsed_ms(RF_Instant* since) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    rf_int64 sec_diff = (rf_int64)(now.tv_sec - since->ts.tv_sec);
    rf_int64 nsec_diff = (rf_int64)(now.tv_nsec - since->ts.tv_nsec);
    return sec_diff * 1000 + nsec_diff / 1000000;
}

rf_int64 rf_time_elapsed_us(RF_Instant* since) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    rf_int64 sec_diff = (rf_int64)(now.tv_sec - since->ts.tv_sec);
    rf_int64 nsec_diff = (rf_int64)(now.tv_nsec - since->ts.tv_nsec);
    return sec_diff * 1000000 + nsec_diff / 1000;
}

rf_int64 rf_time_diff_ms(RF_Instant* start, RF_Instant* end) {
    rf_int64 sec_diff = (rf_int64)(end->ts.tv_sec - start->ts.tv_sec);
    rf_int64 nsec_diff = (rf_int64)(end->ts.tv_nsec - start->ts.tv_nsec);
    return sec_diff * 1000 + nsec_diff / 1000000;
}

void rf_instant_release(RF_Instant* inst) {
    free(inst);
}

/* --- Wall clock --- */

RF_DateTime* rf_time_datetime_now(void) {
    RF_DateTime* dt = (RF_DateTime*)malloc(sizeof(RF_DateTime));
    if (!dt) rf_panic("rf_time_datetime_now: out of memory");
    dt->epoch = time(NULL);
    localtime_r(&dt->epoch, &dt->components);
    dt->utc_offset = (rf_int)dt->components.tm_gmtoff;
    return dt;
}

RF_DateTime* rf_time_datetime_utc(void) {
    RF_DateTime* dt = (RF_DateTime*)malloc(sizeof(RF_DateTime));
    if (!dt) rf_panic("rf_time_datetime_utc: out of memory");
    dt->epoch = time(NULL);
    gmtime_r(&dt->epoch, &dt->components);
    dt->utc_offset = 0;
    return dt;
}

rf_int64 rf_time_unix_timestamp(void) {
    return (rf_int64)time(NULL);
}

rf_int64 rf_time_unix_timestamp_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (rf_int64)ts.tv_sec * 1000 + (rf_int64)ts.tv_nsec / 1000000;
}

void rf_datetime_release(RF_DateTime* dt) {
    free(dt);
}

/* --- Formatting --- */

RF_String* rf_time_format_iso8601(RF_DateTime* dt) {
    char buf[64];
    /* Format: 2026-02-22T14:30:45+00:00 */
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &dt->components);
    /* Append timezone offset */
    int off = dt->utc_offset;
    char sign = off >= 0 ? '+' : '-';
    if (off < 0) off = -off;
    int h = off / 3600;
    int m = (off % 3600) / 60;
    char full[80];
    snprintf(full, sizeof(full), "%s%c%02d:%02d", buf, sign, h, m);
    return rf_string_from_cstr(full);
}

RF_String* rf_time_format_rfc2822(RF_DateTime* dt) {
    char buf[64];
    /* Format: Sat, 22 Feb 2026 14:30:45 +0000 */
    strftime(buf, sizeof(buf), "%a, %d %b %Y %H:%M:%S", &dt->components);
    int off = dt->utc_offset;
    char sign = off >= 0 ? '+' : '-';
    if (off < 0) off = -off;
    int h = off / 3600;
    int m = (off % 3600) / 60;
    char full[80];
    snprintf(full, sizeof(full), "%s %c%02d%02d", buf, sign, h, m);
    return rf_string_from_cstr(full);
}

RF_String* rf_time_format_http(RF_DateTime* dt) {
    /* HTTP date is always GMT. Convert to UTC if needed. */
    struct tm utc;
    gmtime_r(&dt->epoch, &utc);
    char buf[64];
    strftime(buf, sizeof(buf), "%a, %d %b %Y %H:%M:%S GMT", &utc);
    return rf_string_from_cstr(buf);
}

/* --- Component accessors --- */

rf_int rf_time_year(RF_DateTime* dt) { return (rf_int)(dt->components.tm_year + 1900); }
rf_int rf_time_month(RF_DateTime* dt) { return (rf_int)(dt->components.tm_mon + 1); }
rf_int rf_time_day(RF_DateTime* dt) { return (rf_int)dt->components.tm_mday; }
rf_int rf_time_hour(RF_DateTime* dt) { return (rf_int)dt->components.tm_hour; }
rf_int rf_time_minute(RF_DateTime* dt) { return (rf_int)dt->components.tm_min; }
rf_int rf_time_second(RF_DateTime* dt) { return (rf_int)dt->components.tm_sec; }

/* ========================================================================
 * Testing (stdlib/testing)
 * ======================================================================== */

static void _rf_test_throw(RF_String* msg) {
    _rf_throw(msg, RF_TEST_FAILURE_TAG);
}

void rf_test_assert_true(rf_bool val, RF_String* msg) {
    if (val != rf_true) {
        RF_String* prefix = rf_string_from_cstr("assertion failed (expected true): ");
        RF_String* full = rf_string_concat(prefix, msg);
        rf_string_release(prefix);
        _rf_test_throw(full);
    }
}

void rf_test_assert_false(rf_bool val, RF_String* msg) {
    if (val != rf_false) {
        RF_String* prefix = rf_string_from_cstr("assertion failed (expected false): ");
        RF_String* full = rf_string_concat(prefix, msg);
        rf_string_release(prefix);
        _rf_test_throw(full);
    }
}

void rf_test_assert_eq_float(rf_float expected, rf_float actual,
                              rf_float epsilon, RF_String* msg) {
    rf_float diff = expected - actual;
    if (diff < 0) diff = -diff;
    if (diff > epsilon) {
        char buf[128];
        snprintf(buf, sizeof(buf), "expected %f, got %f (epsilon %f): ",
                 expected, actual, epsilon);
        RF_String* prefix = rf_string_from_cstr(buf);
        RF_String* full = rf_string_concat(prefix, msg);
        rf_string_release(prefix);
        _rf_test_throw(full);
    }
}

void* rf_test_assert_some(RF_Option_ptr opt, RF_String* msg) {
    if (opt.tag == 0) {
        RF_String* prefix = rf_string_from_cstr("expected Some, got None: ");
        RF_String* full = rf_string_concat(prefix, msg);
        rf_string_release(prefix);
        _rf_test_throw(full);
    }
    return opt.value;
}

void rf_test_assert_none(RF_Option_ptr opt, RF_String* msg) {
    if (opt.tag != 0) {
        RF_String* prefix = rf_string_from_cstr("expected None, got Some: ");
        RF_String* full = rf_string_concat(prefix, msg);
        rf_string_release(prefix);
        _rf_test_throw(full);
    }
}

void rf_test_fail(RF_String* msg) {
    _rf_test_throw(msg);
}

RF_TestResult rf_test_run(RF_String* name, RF_Closure* test_fn) {
    RF_TestResult result;
    result.name = name;
    result.failure_msg = NULL;

    RF_ExceptionFrame ef;
    _rf_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        /* Call the test closure: void (*)(void* env) */
        typedef void (*TestFn)(void*);
        TestFn fn = (TestFn)test_fn->fn;
        fn(test_fn->env);
        result.passed = 1;
    } else {
        result.passed = 0;
        if (ef.exception_tag == RF_TEST_FAILURE_TAG) {
            result.failure_msg = (RF_String*)ef.exception;
        } else {
            result.failure_msg = rf_string_from_cstr("unexpected exception");
        }
    }
    _rf_exception_pop();
    return result;
}

void rf_test_report(RF_TestResult* result) {
    if (result->passed) {
        fprintf(stdout, "  PASS  %.*s\n",
                (int)rf_string_len(result->name), result->name->data);
    } else {
        fprintf(stdout, "  FAIL  %.*s: %.*s\n",
                (int)rf_string_len(result->name), result->name->data,
                (int)rf_string_len(result->failure_msg), result->failure_msg->data);
    }
}

rf_int rf_test_run_all(RF_Array* tests) {
    rf_int64 len = rf_array_len(tests);
    rf_int failures = 0;
    rf_int total = 0;

    for (rf_int64 i = 0; i < len; i++) {
        /* Each element is a pointer to a struct { RF_String* name; RF_Closure* fn; } */
        typedef struct { RF_String* name; RF_Closure* fn; } TestEntry;
        TestEntry* entry = *(TestEntry**)rf_array_get_ptr(tests, i);
        RF_TestResult result = rf_test_run(entry->name, entry->fn);
        rf_test_report(&result);
        total++;
        if (!result.passed) failures++;
    }

    fprintf(stdout, "\n%d/%d tests passed\n", total - failures, total);
    if (failures > 0) {
        fprintf(stdout, "%d FAILED\n", failures);
    }
    return failures;
}

/* ========================================================================
 * Net (stdlib/net)
 * ======================================================================== */

struct RF_Socket {
    int fd;
};

RF_Option_ptr rf_net_listen(RF_String* addr, rf_int port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return RF_NONE_PTR;

    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons((uint16_t)port);

    if (addr && rf_string_len(addr) > 0) {
        char buf[256];
        rf_int64 len = rf_string_len(addr);
        if (len >= (rf_int64)sizeof(buf)) len = (rf_int64)(sizeof(buf) - 1);
        memcpy(buf, addr->data, (size_t)len);
        buf[len] = '\0';
        inet_pton(AF_INET, buf, &sa.sin_addr);
    } else {
        sa.sin_addr.s_addr = INADDR_ANY;
    }

    if (bind(fd, (struct sockaddr*)&sa, sizeof(sa)) < 0) {
        close(fd);
        return RF_NONE_PTR;
    }

    if (listen(fd, 128) < 0) {
        close(fd);
        return RF_NONE_PTR;
    }

    RF_Socket* listener = (RF_Socket*)malloc(sizeof(RF_Socket));
    if (!listener) { close(fd); return RF_NONE_PTR; }
    listener->fd = fd;
    return RF_SOME_PTR(listener);
}

RF_Option_ptr rf_net_accept(RF_Socket* listener) {
    if (!listener || listener->fd < 0) return RF_NONE_PTR;

    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    int client_fd = accept(listener->fd, (struct sockaddr*)&client_addr, &client_len);
    if (client_fd < 0) return RF_NONE_PTR;

    RF_Socket* conn = (RF_Socket*)malloc(sizeof(RF_Socket));
    if (!conn) { close(client_fd); return RF_NONE_PTR; }
    conn->fd = client_fd;
    return RF_SOME_PTR(conn);
}

RF_Option_ptr rf_net_connect(RF_String* host, rf_int port) {
    if (!host) return RF_NONE_PTR;

    char host_buf[256];
    rf_int64 hlen = rf_string_len(host);
    if (hlen >= (rf_int64)sizeof(host_buf)) return RF_NONE_PTR;
    memcpy(host_buf, host->data, (size_t)hlen);
    host_buf[hlen] = '\0';

    char port_buf[16];
    snprintf(port_buf, sizeof(port_buf), "%d", port);

    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(host_buf, port_buf, &hints, &res) != 0) {
        return RF_NONE_PTR;
    }

    int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (fd < 0) {
        freeaddrinfo(res);
        return RF_NONE_PTR;
    }

    if (connect(fd, res->ai_addr, res->ai_addrlen) < 0) {
        close(fd);
        freeaddrinfo(res);
        return RF_NONE_PTR;
    }

    freeaddrinfo(res);
    RF_Socket* conn = (RF_Socket*)malloc(sizeof(RF_Socket));
    if (!conn) { close(fd); return RF_NONE_PTR; }
    conn->fd = fd;
    return RF_SOME_PTR(conn);
}

RF_Option_ptr rf_net_read(RF_Socket* conn, rf_int max_bytes) {
    if (!conn || conn->fd < 0 || max_bytes <= 0) return RF_NONE_PTR;

    rf_byte* buf = (rf_byte*)malloc((size_t)max_bytes);
    if (!buf) return RF_NONE_PTR;

    ssize_t n = recv(conn->fd, buf, (size_t)max_bytes, 0);
    if (n <= 0) {
        /* n < 0: error; n == 0: peer closed connection (EOF) */
        free(buf);
        return RF_NONE_PTR;
    }

    RF_Array* arr = rf_array_new((rf_int64)n, sizeof(rf_byte), NULL);
    memcpy(arr->data, buf, (size_t)n);
    free(buf);
    return RF_SOME_PTR(arr);
}

rf_bool rf_net_write(RF_Socket* conn, RF_Array* data) {
    if (!conn || conn->fd < 0 || !data) return rf_false;

    rf_int64 total = rf_array_len(data);
    rf_int64 sent = 0;
    while (sent < total) {
        ssize_t n = send(conn->fd, (char*)data->data + sent,
                         (size_t)(total - sent), MSG_NOSIGNAL);
        if (n <= 0) return rf_false;
        sent += n;
    }
    return rf_true;
}

rf_bool rf_net_write_string(RF_Socket* conn, RF_String* s) {
    if (!conn || conn->fd < 0 || !s) return rf_false;

    rf_int64 total = rf_string_len(s);
    rf_int64 sent = 0;
    while (sent < total) {
        ssize_t n = send(conn->fd, s->data + sent,
                         (size_t)(total - sent), MSG_NOSIGNAL);
        if (n <= 0) return rf_false;
        sent += n;
    }
    return rf_true;
}

void rf_net_close(RF_Socket* conn) {
    if (conn) {
        if (conn->fd >= 0) {
            close(conn->fd);
            conn->fd = -1;
        }
        free(conn);
    }
}

rf_bool rf_net_set_timeout(RF_Socket* conn, rf_int ms) {
    if (!conn || conn->fd < 0) return rf_false;

    struct timeval tv;
    tv.tv_sec = ms / 1000;
    tv.tv_usec = (ms % 1000) * 1000;

    if (setsockopt(conn->fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0) {
        return rf_false;
    }
    if (setsockopt(conn->fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv)) < 0) {
        return rf_false;
    }
    return rf_true;
}

RF_Option_ptr rf_net_remote_addr(RF_Socket* conn) {
    if (!conn || conn->fd < 0) return RF_NONE_PTR;

    struct sockaddr_in sa;
    socklen_t sa_len = sizeof(sa);
    if (getpeername(conn->fd, (struct sockaddr*)&sa, &sa_len) < 0) {
        return RF_NONE_PTR;
    }

    char ip_buf[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &sa.sin_addr, ip_buf, sizeof(ip_buf));
    int port = ntohs(sa.sin_port);

    char result[280];
    snprintf(result, sizeof(result), "%s:%d", ip_buf, port);

    RF_String* addr_str = rf_string_from_cstr(result);
    return RF_SOME_PTR(addr_str);
}

rf_int rf_net_fd(RF_Socket* conn) {
    if (!conn || conn->fd < 0) return -1;
    return conn->fd;
}

rf_bool rf_net_write_string_fd(rf_int fd, RF_String* s) {
    if (fd < 0 || !s) return rf_false;

    rf_int64 total = rf_string_len(s);
    rf_int64 sent = 0;
    while (sent < total) {
        ssize_t n = send(fd, s->data + sent, (size_t)(total - sent), 0);
        if (n <= 0) return rf_false;
        sent += n;
    }
    return rf_true;
}

/* ========================================================================
 * JSON (stdlib/json)
 * ======================================================================== */

struct RF_JsonValue {
    rf_byte tag;  /* RF_JSON_NULL..RF_JSON_OBJECT */
    union {
        rf_bool     bool_val;
        rf_int64    int_val;
        rf_float    float_val;
        RF_String*  string_val;
        RF_Array*   array_val;   /* Array of RF_JsonValue* */
        RF_Map*     object_val;  /* Map of RF_String* -> RF_JsonValue* */
    } data;
};

/* --- Constructors --- */

RF_JsonValue* rf_json_null(void) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_null: out of memory");
    v->tag = RF_JSON_NULL;
    memset(&v->data, 0, sizeof(v->data));
    return v;
}

RF_JsonValue* rf_json_bool(rf_bool val) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_bool: out of memory");
    v->tag = RF_JSON_BOOL;
    v->data.bool_val = val;
    return v;
}

RF_JsonValue* rf_json_int(rf_int64 val) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_int: out of memory");
    v->tag = RF_JSON_INT;
    v->data.int_val = val;
    return v;
}

RF_JsonValue* rf_json_float(rf_float val) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_float: out of memory");
    v->tag = RF_JSON_FLOAT;
    v->data.float_val = val;
    return v;
}

RF_JsonValue* rf_json_string(RF_String* val) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_string: out of memory");
    v->tag = RF_JSON_STRING;
    v->data.string_val = val;
    if (val) rf_string_retain(val);
    return v;
}

RF_JsonValue* rf_json_array(RF_Array* items) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_array: out of memory");
    v->tag = RF_JSON_ARRAY;
    v->data.array_val = items;
    if (items) rf_array_retain(items);
    return v;
}

RF_JsonValue* rf_json_object(RF_Map* entries) {
    RF_JsonValue* v = (RF_JsonValue*)malloc(sizeof(RF_JsonValue));
    if (!v) rf_panic("rf_json_object: out of memory");
    v->tag = RF_JSON_OBJECT;
    v->data.object_val = entries;
    if (entries) rf_map_retain(entries);
    return v;
}

/* --- Release --- */

void rf_json_release(RF_JsonValue* val) {
    if (!val) return;
    switch (val->tag) {
        case RF_JSON_STRING:
            rf_string_release(val->data.string_val);
            break;
        case RF_JSON_ARRAY: {
            RF_Array* arr = val->data.array_val;
            if (arr) {
                rf_int64 len = rf_array_len(arr);
                for (rf_int64 i = 0; i < len; i++) {
                    RF_JsonValue** slot = (RF_JsonValue**)rf_array_get_ptr(arr, i);
                    if (slot && *slot) rf_json_release(*slot);
                }
                rf_array_release(arr);
            }
            break;
        }
        case RF_JSON_OBJECT: {
            RF_Map* m = val->data.object_val;
            if (m) rf_map_release(m);
            break;
        }
        default:
            break;
    }
    free(val);
}

/* --- Accessors --- */

RF_Option_ptr rf_json_get(RF_JsonValue* obj, RF_String* key) {
    if (!obj || obj->tag != RF_JSON_OBJECT || !key) return RF_NONE_PTR;
    RF_Map* m = obj->data.object_val;
    if (!m) return RF_NONE_PTR;
    return rf_map_get(m, key->data, key->len);
}

RF_Option_ptr rf_json_get_index(RF_JsonValue* arr, rf_int64 index) {
    if (!arr || arr->tag != RF_JSON_ARRAY) return RF_NONE_PTR;
    RF_Array* a = arr->data.array_val;
    if (!a || index < 0 || index >= rf_array_len(a)) return RF_NONE_PTR;
    RF_JsonValue** slot = (RF_JsonValue**)rf_array_get_ptr(a, index);
    if (!slot) return RF_NONE_PTR;
    return RF_SOME_PTR(*slot);
}

RF_Option_ptr rf_json_as_string(RF_JsonValue* val) {
    if (!val || val->tag != RF_JSON_STRING) return RF_NONE_PTR;
    return RF_SOME_PTR(val->data.string_val);
}

RF_Option_int64 rf_json_as_int(RF_JsonValue* val) {
    if (val && val->tag == RF_JSON_INT)
        return (RF_Option_int64){.tag = 1, .value = val->data.int_val};
    return (RF_Option_int64){.tag = 0};
}

RF_Option_float rf_json_as_float(RF_JsonValue* val) {
    if (val && val->tag == RF_JSON_FLOAT)
        return (RF_Option_float){.tag = 1, .value = val->data.float_val};
    return (RF_Option_float){.tag = 0};
}

RF_Option_bool rf_json_as_bool(RF_JsonValue* val) {
    if (val && val->tag == RF_JSON_BOOL)
        return (RF_Option_bool){.tag = 1, .value = val->data.bool_val};
    return (RF_Option_bool){.tag = 0};
}

RF_Option_ptr rf_json_as_array(RF_JsonValue* val) {
    if (!val || val->tag != RF_JSON_ARRAY) return RF_NONE_PTR;
    return RF_SOME_PTR(val->data.array_val);
}

rf_bool rf_json_is_null(RF_JsonValue* val) {
    if (!val) return rf_false;
    return val->tag == RF_JSON_NULL ? rf_true : rf_false;
}

rf_byte rf_json_type_tag(RF_JsonValue* val) {
    if (!val) return RF_JSON_NULL;
    return val->tag;
}

/* --- Parser --- */

typedef struct {
    const char* input;
    rf_int64    pos;
    rf_int64    len;
} _RF_JsonParser;

static RF_JsonValue* _rf_json_parse_value(_RF_JsonParser* p);

static void _rf_json_skip_ws(_RF_JsonParser* p) {
    while (p->pos < p->len) {
        char c = p->input[p->pos];
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r')
            p->pos++;
        else
            break;
    }
}

static RF_JsonValue* _rf_json_parse_string_value(_RF_JsonParser* p) {
    /* p->pos points to opening '"' */
    p->pos++; /* skip '"' */
    rf_int64 cap = 64;
    rf_int64 len = 0;
    char* buf = (char*)malloc((size_t)cap);
    if (!buf) return NULL;

    while (p->pos < p->len) {
        char c = p->input[p->pos];
        if (c == '"') {
            p->pos++; /* skip closing '"' */
            buf[len] = '\0';
            RF_String* s = rf_string_new(buf, len);
            free(buf);
            return rf_json_string(s);
        }
        if (c == '\\') {
            p->pos++;
            if (p->pos >= p->len) { free(buf); return NULL; }
            char esc = p->input[p->pos];
            switch (esc) {
                case '"': case '\\': case '/': buf[len++] = esc; break;
                case 'b': buf[len++] = '\b'; break;
                case 'f': buf[len++] = '\f'; break;
                case 'n': buf[len++] = '\n'; break;
                case 'r': buf[len++] = '\r'; break;
                case 't': buf[len++] = '\t'; break;
                case 'u': {
                    /* \uXXXX - parse 4 hex digits, emit as UTF-8 */
                    if (p->pos + 4 >= p->len) { free(buf); return NULL; }
                    char hex[5] = {0};
                    memcpy(hex, &p->input[p->pos + 1], 4);
                    unsigned int cp = (unsigned int)strtoul(hex, NULL, 16);
                    p->pos += 4;
                    if (cp < 0x80) {
                        buf[len++] = (char)cp;
                    } else if (cp < 0x800) {
                        buf[len++] = (char)(0xC0 | (cp >> 6));
                        buf[len++] = (char)(0x80 | (cp & 0x3F));
                    } else {
                        buf[len++] = (char)(0xE0 | (cp >> 12));
                        buf[len++] = (char)(0x80 | ((cp >> 6) & 0x3F));
                        buf[len++] = (char)(0x80 | (cp & 0x3F));
                    }
                    break;
                }
                default: free(buf); return NULL;
            }
        } else {
            buf[len++] = c;
        }
        p->pos++;
        if (len + 6 >= cap) { cap *= 2; buf = (char*)realloc(buf, (size_t)cap); }
    }
    free(buf);
    return NULL;
}

/* Parse a raw string (not wrapped in RF_JsonValue) — returns RF_String* or NULL */
static RF_String* _rf_json_parse_string_raw(_RF_JsonParser* p) {
    RF_JsonValue* jv = _rf_json_parse_string_value(p);
    if (!jv) return NULL;
    RF_String* s = jv->data.string_val;
    rf_string_retain(s);
    rf_json_release(jv);
    return s;
}

static RF_JsonValue* _rf_json_parse_number(_RF_JsonParser* p) {
    rf_int64 start = p->pos;
    rf_bool is_float = rf_false;
    if (p->input[p->pos] == '-') p->pos++;
    while (p->pos < p->len && p->input[p->pos] >= '0' && p->input[p->pos] <= '9') p->pos++;
    if (p->pos < p->len && p->input[p->pos] == '.') {
        is_float = rf_true;
        p->pos++;
        while (p->pos < p->len && p->input[p->pos] >= '0' && p->input[p->pos] <= '9') p->pos++;
    }
    if (p->pos < p->len && (p->input[p->pos] == 'e' || p->input[p->pos] == 'E')) {
        is_float = rf_true;
        p->pos++;
        if (p->pos < p->len && (p->input[p->pos] == '+' || p->input[p->pos] == '-')) p->pos++;
        while (p->pos < p->len && p->input[p->pos] >= '0' && p->input[p->pos] <= '9') p->pos++;
    }
    char nbuf[64];
    rf_int64 num_len = p->pos - start;
    if (num_len >= 63) num_len = 63;
    memcpy(nbuf, &p->input[start], (size_t)num_len);
    nbuf[num_len] = '\0';
    if (is_float) return rf_json_float(strtod(nbuf, NULL));
    return rf_json_int((rf_int64)strtoll(nbuf, NULL, 10));
}

static RF_JsonValue* _rf_json_parse_array(_RF_JsonParser* p) {
    p->pos++; /* skip '[' */
    _rf_json_skip_ws(p);

    /* Collect items into a buffer, then convert to RF_Array */
    rf_int64 cap = 8;
    rf_int64 count = 0;
    RF_JsonValue** items = (RF_JsonValue**)malloc((size_t)cap * sizeof(RF_JsonValue*));
    if (!items) return NULL;

    if (p->pos < p->len && p->input[p->pos] == ']') {
        p->pos++; /* empty array */
        RF_Array* arr = rf_array_new(0, sizeof(RF_JsonValue*), NULL);
        free(items);
        return rf_json_array(arr);
    }

    for (;;) {
        _rf_json_skip_ws(p);
        RF_JsonValue* elem = _rf_json_parse_value(p);
        if (!elem) {
            /* Cleanup on failure */
            for (rf_int64 i = 0; i < count; i++) rf_json_release(items[i]);
            free(items);
            return NULL;
        }
        if (count >= cap) {
            cap *= 2;
            items = (RF_JsonValue**)realloc(items, (size_t)cap * sizeof(RF_JsonValue*));
        }
        items[count++] = elem;

        _rf_json_skip_ws(p);
        if (p->pos >= p->len) {
            for (rf_int64 i = 0; i < count; i++) rf_json_release(items[i]);
            free(items);
            return NULL;
        }
        if (p->input[p->pos] == ']') {
            p->pos++;
            break;
        }
        if (p->input[p->pos] != ',') {
            for (rf_int64 i = 0; i < count; i++) rf_json_release(items[i]);
            free(items);
            return NULL;
        }
        p->pos++; /* skip ',' */
    }

    RF_Array* arr = rf_array_new(count, sizeof(RF_JsonValue*), items);
    free(items);
    /* Array now owns the pointers; don't release the elements */
    return rf_json_array(arr);
}

static RF_JsonValue* _rf_json_parse_object(_RF_JsonParser* p) {
    p->pos++; /* skip '{' */
    _rf_json_skip_ws(p);

    RF_Map* map = rf_map_new();

    if (p->pos < p->len && p->input[p->pos] == '}') {
        p->pos++; /* empty object */
        RF_JsonValue* result = rf_json_object(map);
        rf_map_release(map);
        return result;
    }

    for (;;) {
        _rf_json_skip_ws(p);
        if (p->pos >= p->len || p->input[p->pos] != '"') {
            rf_map_release(map);
            return NULL;
        }
        RF_String* key = _rf_json_parse_string_raw(p);
        if (!key) {
            rf_map_release(map);
            return NULL;
        }

        _rf_json_skip_ws(p);
        if (p->pos >= p->len || p->input[p->pos] != ':') {
            rf_string_release(key);
            rf_map_release(map);
            return NULL;
        }
        p->pos++; /* skip ':' */

        _rf_json_skip_ws(p);
        RF_JsonValue* val = _rf_json_parse_value(p);
        if (!val) {
            rf_string_release(key);
            rf_map_release(map);
            return NULL;
        }

        RF_Map* new_map = rf_map_set(map, key->data, key->len, val);
        rf_map_release(map);
        map = new_map;
        rf_string_release(key);

        _rf_json_skip_ws(p);
        if (p->pos >= p->len) {
            rf_map_release(map);
            return NULL;
        }
        if (p->input[p->pos] == '}') {
            p->pos++;
            break;
        }
        if (p->input[p->pos] != ',') {
            rf_map_release(map);
            return NULL;
        }
        p->pos++; /* skip ',' */
    }

    RF_JsonValue* result = rf_json_object(map);
    rf_map_release(map);
    return result;
}

static RF_JsonValue* _rf_json_parse_value(_RF_JsonParser* p) {
    _rf_json_skip_ws(p);
    if (p->pos >= p->len) return NULL;

    char c = p->input[p->pos];
    switch (c) {
        case '"': return _rf_json_parse_string_value(p);
        case '{': return _rf_json_parse_object(p);
        case '[': return _rf_json_parse_array(p);
        case 't':
            if (p->pos + 3 < p->len &&
                p->input[p->pos+1] == 'r' && p->input[p->pos+2] == 'u' &&
                p->input[p->pos+3] == 'e') {
                p->pos += 4;
                return rf_json_bool(rf_true);
            }
            return NULL;
        case 'f':
            if (p->pos + 4 < p->len &&
                p->input[p->pos+1] == 'a' && p->input[p->pos+2] == 'l' &&
                p->input[p->pos+3] == 's' && p->input[p->pos+4] == 'e') {
                p->pos += 5;
                return rf_json_bool(rf_false);
            }
            return NULL;
        case 'n':
            if (p->pos + 3 < p->len &&
                p->input[p->pos+1] == 'u' && p->input[p->pos+2] == 'l' &&
                p->input[p->pos+3] == 'l') {
                p->pos += 4;
                return rf_json_null();
            }
            return NULL;
        default:
            if (c == '-' || (c >= '0' && c <= '9'))
                return _rf_json_parse_number(p);
            return NULL;
    }
}

RF_Option_ptr rf_json_parse(RF_String* s) {
    if (!s) return RF_NONE_PTR;
    _RF_JsonParser parser = { .input = s->data, .pos = 0, .len = s->len };
    RF_JsonValue* val = _rf_json_parse_value(&parser);
    if (!val) return RF_NONE_PTR;
    /* Skip trailing whitespace and verify nothing extra */
    _rf_json_skip_ws(&parser);
    if (parser.pos != parser.len) {
        rf_json_release(val);
        return RF_NONE_PTR;
    }
    return RF_SOME_PTR(val);
}

/* --- Serializer (dynamic string buffer) --- */

typedef struct {
    char*    buf;
    rf_int64 len;
    rf_int64 cap;
} _RF_JsonBuf;

static void _rf_jbuf_init(_RF_JsonBuf* b) {
    b->cap = 128;
    b->len = 0;
    b->buf = (char*)malloc((size_t)b->cap);
    if (!b->buf) rf_panic("json serialize: out of memory");
}

static void _rf_jbuf_ensure(_RF_JsonBuf* b, rf_int64 extra) {
    while (b->len + extra >= b->cap) {
        b->cap *= 2;
        b->buf = (char*)realloc(b->buf, (size_t)b->cap);
        if (!b->buf) rf_panic("json serialize: out of memory");
    }
}

static void _rf_jbuf_append_cstr(_RF_JsonBuf* b, const char* s) {
    rf_int64 slen = (rf_int64)strlen(s);
    _rf_jbuf_ensure(b, slen);
    memcpy(b->buf + b->len, s, (size_t)slen);
    b->len += slen;
}

static void _rf_jbuf_append_char(_RF_JsonBuf* b, char c) {
    _rf_jbuf_ensure(b, 1);
    b->buf[b->len++] = c;
}

static void _rf_jbuf_append_chars(_RF_JsonBuf* b, char c, rf_int count) {
    _rf_jbuf_ensure(b, (rf_int64)count);
    for (rf_int i = 0; i < count; i++) {
        b->buf[b->len++] = c;
    }
}

static void _rf_jbuf_append_escaped_string(_RF_JsonBuf* b, RF_String* s) {
    _rf_jbuf_append_char(b, '"');
    for (rf_int64 i = 0; i < s->len; i++) {
        unsigned char c = (unsigned char)s->data[i];
        switch (c) {
            case '"':  _rf_jbuf_append_cstr(b, "\\\""); break;
            case '\\': _rf_jbuf_append_cstr(b, "\\\\"); break;
            case '\b': _rf_jbuf_append_cstr(b, "\\b"); break;
            case '\f': _rf_jbuf_append_cstr(b, "\\f"); break;
            case '\n': _rf_jbuf_append_cstr(b, "\\n"); break;
            case '\r': _rf_jbuf_append_cstr(b, "\\r"); break;
            case '\t': _rf_jbuf_append_cstr(b, "\\t"); break;
            default:
                if (c < 0x20) {
                    char esc[8];
                    snprintf(esc, sizeof(esc), "\\u%04x", c);
                    _rf_jbuf_append_cstr(b, esc);
                } else {
                    _rf_jbuf_append_char(b, (char)c);
                }
                break;
        }
    }
    _rf_jbuf_append_char(b, '"');
}

static RF_String* _rf_jbuf_to_string(_RF_JsonBuf* b) {
    RF_String* s = rf_string_new(b->buf, b->len);
    free(b->buf);
    return s;
}

/* Forward declaration for recursive serialization */
static void _rf_json_serialize(_RF_JsonBuf* b, RF_JsonValue* val);
static void _rf_json_serialize_pretty(_RF_JsonBuf* b, RF_JsonValue* val,
                                      rf_int indent, rf_int depth);

static void _rf_json_serialize(_RF_JsonBuf* b, RF_JsonValue* val) {
    if (!val) { _rf_jbuf_append_cstr(b, "null"); return; }
    switch (val->tag) {
        case RF_JSON_NULL:
            _rf_jbuf_append_cstr(b, "null");
            break;
        case RF_JSON_BOOL:
            _rf_jbuf_append_cstr(b, val->data.bool_val ? "true" : "false");
            break;
        case RF_JSON_INT: {
            char nbuf[32];
            snprintf(nbuf, sizeof(nbuf), "%lld", (long long)val->data.int_val);
            _rf_jbuf_append_cstr(b, nbuf);
            break;
        }
        case RF_JSON_FLOAT: {
            char nbuf[64];
            snprintf(nbuf, sizeof(nbuf), "%.17g", val->data.float_val);
            _rf_jbuf_append_cstr(b, nbuf);
            break;
        }
        case RF_JSON_STRING:
            _rf_jbuf_append_escaped_string(b, val->data.string_val);
            break;
        case RF_JSON_ARRAY: {
            _rf_jbuf_append_char(b, '[');
            RF_Array* arr = val->data.array_val;
            if (arr) {
                rf_int64 len = rf_array_len(arr);
                for (rf_int64 i = 0; i < len; i++) {
                    if (i > 0) _rf_jbuf_append_char(b, ',');
                    RF_JsonValue** slot = (RF_JsonValue**)rf_array_get_ptr(arr, i);
                    _rf_json_serialize(b, slot ? *slot : NULL);
                }
            }
            _rf_jbuf_append_char(b, ']');
            break;
        }
        case RF_JSON_OBJECT: {
            _rf_jbuf_append_char(b, '{');
            RF_Map* m = val->data.object_val;
            if (m) {
                /* Iterate over map entries directly using internal knowledge
                 * of RF_Map structure. We access the entries array and capacity
                 * to iterate over occupied slots. */
                rf_int64 first = 1;
                /* Access map internals: count, capacity, entries are at known offsets.
                 * Since RF_Map is defined in this file, we can cast. */
                rf_int64 map_cap = m->capacity;
                for (rf_int64 i = 0; i < map_cap; i++) {
                    RF_MapEntry* e = &m->entries[i];
                    if (!e->occupied) continue;
                    if (!first) _rf_jbuf_append_char(b, ',');
                    first = 0;
                    /* Key is raw bytes, create temp string for escaping */
                    RF_String* key_str = rf_string_new((const char*)e->key, e->key_len);
                    _rf_jbuf_append_escaped_string(b, key_str);
                    rf_string_release(key_str);
                    _rf_jbuf_append_char(b, ':');
                    _rf_json_serialize(b, (RF_JsonValue*)e->val);
                }
            }
            _rf_jbuf_append_char(b, '}');
            break;
        }
    }
}

RF_String* rf_json_to_string(RF_JsonValue* val) {
    _RF_JsonBuf buf;
    _rf_jbuf_init(&buf);
    _rf_json_serialize(&buf, val);
    return _rf_jbuf_to_string(&buf);
}

/* --- Pretty serializer --- */

static void _rf_json_serialize_pretty(_RF_JsonBuf* b, RF_JsonValue* val,
                                      rf_int indent, rf_int depth) {
    if (!val) { _rf_jbuf_append_cstr(b, "null"); return; }
    switch (val->tag) {
        case RF_JSON_NULL:
            _rf_jbuf_append_cstr(b, "null");
            break;
        case RF_JSON_BOOL:
            _rf_jbuf_append_cstr(b, val->data.bool_val ? "true" : "false");
            break;
        case RF_JSON_INT: {
            char nbuf[32];
            snprintf(nbuf, sizeof(nbuf), "%lld", (long long)val->data.int_val);
            _rf_jbuf_append_cstr(b, nbuf);
            break;
        }
        case RF_JSON_FLOAT: {
            char nbuf[64];
            snprintf(nbuf, sizeof(nbuf), "%.17g", val->data.float_val);
            _rf_jbuf_append_cstr(b, nbuf);
            break;
        }
        case RF_JSON_STRING:
            _rf_jbuf_append_escaped_string(b, val->data.string_val);
            break;
        case RF_JSON_ARRAY: {
            RF_Array* arr = val->data.array_val;
            rf_int64 len = arr ? rf_array_len(arr) : 0;
            if (len == 0) {
                _rf_jbuf_append_cstr(b, "[]");
            } else {
                _rf_jbuf_append_cstr(b, "[\n");
                for (rf_int64 i = 0; i < len; i++) {
                    _rf_jbuf_append_chars(b, ' ', indent * (depth + 1));
                    RF_JsonValue** slot = (RF_JsonValue**)rf_array_get_ptr(arr, i);
                    _rf_json_serialize_pretty(b, slot ? *slot : NULL, indent, depth + 1);
                    if (i + 1 < len) _rf_jbuf_append_char(b, ',');
                    _rf_jbuf_append_char(b, '\n');
                }
                _rf_jbuf_append_chars(b, ' ', indent * depth);
                _rf_jbuf_append_char(b, ']');
            }
            break;
        }
        case RF_JSON_OBJECT: {
            RF_Map* m = val->data.object_val;
            rf_int64 cnt = m ? rf_map_len(m) : 0;
            if (cnt == 0) {
                _rf_jbuf_append_cstr(b, "{}");
            } else {
                _rf_jbuf_append_cstr(b, "{\n");
                rf_int64 map_cap = m->capacity;
                rf_int64 first = 1;
                rf_int64 emitted = 0;
                for (rf_int64 i = 0; i < map_cap; i++) {
                    RF_MapEntry* e = &m->entries[i];
                    if (!e->occupied) continue;
                    if (!first) {
                        _rf_jbuf_append_cstr(b, ",\n");
                    }
                    first = 0;
                    _rf_jbuf_append_chars(b, ' ', indent * (depth + 1));
                    RF_String* key_str = rf_string_new((const char*)e->key, e->key_len);
                    _rf_jbuf_append_escaped_string(b, key_str);
                    rf_string_release(key_str);
                    _rf_jbuf_append_cstr(b, ": ");
                    _rf_json_serialize_pretty(b, (RF_JsonValue*)e->val, indent, depth + 1);
                    emitted++;
                }
                _rf_jbuf_append_char(b, '\n');
                _rf_jbuf_append_chars(b, ' ', indent * depth);
                _rf_jbuf_append_char(b, '}');
            }
            break;
        }
    }
}

RF_String* rf_json_to_string_pretty(RF_JsonValue* val, rf_int indent) {
    _RF_JsonBuf buf;
    _rf_jbuf_init(&buf);
    _rf_json_serialize_pretty(&buf, val, indent, 0);
    return _rf_jbuf_to_string(&buf);
}

/* ========================================================================
 * Array stdlib extensions
 * ======================================================================== */

RF_Option_int rf_array_get_int(RF_Array* arr, rf_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (RF_Option_int){.tag = 0, .value = 0};
    rf_int* ptr = (rf_int*)((char*)arr->data + idx * arr->element_size);
    return (RF_Option_int){.tag = 1, .value = *ptr};
}

RF_Option_int64 rf_array_get_int64(RF_Array* arr, rf_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (RF_Option_int64){.tag = 0, .value = 0};
    rf_int64* ptr = (rf_int64*)((char*)arr->data + idx * arr->element_size);
    return (RF_Option_int64){.tag = 1, .value = *ptr};
}

RF_Option_float rf_array_get_float(RF_Array* arr, rf_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (RF_Option_float){.tag = 0, .value = 0.0};
    rf_float* ptr = (rf_float*)((char*)arr->data + idx * arr->element_size);
    return (RF_Option_float){.tag = 1, .value = *ptr};
}

RF_Option_bool rf_array_get_bool(RF_Array* arr, rf_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (RF_Option_bool){.tag = 0, .value = rf_false};
    rf_bool* ptr = (rf_bool*)((char*)arr->data + idx * arr->element_size);
    return (RF_Option_bool){.tag = 1, .value = *ptr};
}

rf_int rf_array_len_int(RF_Array* arr) {
    if (!arr) return 0;
    return (rf_int)arr->len;
}

RF_Array* rf_array_concat(RF_Array* a, RF_Array* b) {
    if (!a && !b) return rf_array_new(0, sizeof(void*), NULL);
    if (!a) { rf_array_retain(b); return b; }
    if (!b) { rf_array_retain(a); return a; }
    if (a->element_size != b->element_size)
        rf_panic("rf_array_concat: element size mismatch");
    rf_int64 total = a->len + b->len;
    void* data = malloc((size_t)(total * a->element_size));
    if (!data) rf_panic("rf_array_concat: out of memory");
    memcpy(data, a->data, (size_t)(a->len * a->element_size));
    memcpy((char*)data + a->len * a->element_size,
           b->data, (size_t)(b->len * b->element_size));
    RF_Array* result = rf_array_new(total, a->element_size, data);
    free(data);
    return result;
}

/* ========================================================================
 * String extensions: repeat, URL encode/decode
 * ======================================================================== */

RF_String* rf_string_repeat(RF_String* s, rf_int n) {
    if (!s || n <= 0) return rf_string_from_cstr("");
    rf_int64 total = s->len * (rf_int64)n;
    RF_String* result = (RF_String*)malloc(sizeof(RF_String) + (size_t)total + 1);
    if (!result) rf_panic("rf_string_repeat: out of memory");
    result->refcount = 1;
    result->len = total;
    for (rf_int i = 0; i < n; i++) {
        memcpy(result->data + (rf_int64)i * s->len, s->data, (size_t)s->len);
    }
    result->data[total] = '\0';
    return result;
}

static int _rf_hex_digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    return -1;
}

RF_String* rf_string_url_decode(RF_String* s) {
    if (!s) return rf_string_from_cstr("");
    char* buf = (char*)malloc((size_t)s->len + 1);
    if (!buf) rf_panic("rf_string_url_decode: out of memory");
    rf_int64 j = 0;
    for (rf_int64 i = 0; i < s->len; i++) {
        if (s->data[i] == '%' && i + 2 < s->len) {
            int hi = _rf_hex_digit(s->data[i + 1]);
            int lo = _rf_hex_digit(s->data[i + 2]);
            if (hi >= 0 && lo >= 0) {
                buf[j++] = (char)(hi * 16 + lo);
                i += 2;
                continue;
            }
        }
        if (s->data[i] == '+') {
            buf[j++] = ' ';
        } else {
            buf[j++] = s->data[i];
        }
    }
    buf[j] = '\0';
    RF_String* result = rf_string_new(buf, j);
    free(buf);
    return result;
}

RF_String* rf_string_url_encode(RF_String* s) {
    if (!s) return rf_string_from_cstr("");
    /* Worst case: every byte becomes %XX = 3x expansion */
    char* buf = (char*)malloc((size_t)s->len * 3 + 1);
    if (!buf) rf_panic("rf_string_url_encode: out of memory");
    rf_int64 j = 0;
    for (rf_int64 i = 0; i < s->len; i++) {
        unsigned char c = (unsigned char)s->data[i];
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' ||
            c == '.' || c == '~') {
            buf[j++] = (char)c;
        } else {
            buf[j++] = '%';
            buf[j++] = "0123456789ABCDEF"[c >> 4];
            buf[j++] = "0123456789ABCDEF"[c & 0x0F];
        }
    }
    buf[j] = '\0';
    RF_String* result = rf_string_new(buf, j);
    free(buf);
    return result;
}

/* ========================================================================
 * String Builder
 * ======================================================================== */

static void _rf_sb_grow(RF_StringBuilder* sb, rf_int64 needed) {
    rf_int64 new_cap = sb->capacity;
    while (new_cap < sb->len + needed) {
        new_cap = new_cap < 64 ? 64 : new_cap * 2;
    }
    if (new_cap != sb->capacity) {
        sb->data = (char*)realloc(sb->data, (size_t)new_cap);
        if (!sb->data) rf_panic("rf_sb_grow: out of memory");
        sb->capacity = new_cap;
    }
}

RF_StringBuilder* rf_sb_new(void) {
    RF_StringBuilder* sb = (RF_StringBuilder*)malloc(sizeof(RF_StringBuilder));
    if (!sb) rf_panic("rf_sb_new: out of memory");
    sb->refcount = 1;
    sb->data = NULL;
    sb->len = 0;
    sb->capacity = 0;
    return sb;
}

RF_StringBuilder* rf_sb_with_capacity(rf_int64 cap) {
    RF_StringBuilder* sb = rf_sb_new();
    if (cap > 0) {
        sb->data = (char*)malloc((size_t)cap);
        if (!sb->data) rf_panic("rf_sb_with_capacity: out of memory");
        sb->capacity = cap;
    }
    return sb;
}

void rf_sb_append(RF_StringBuilder* sb, RF_String* s) {
    if (!sb || !s) return;
    _rf_sb_grow(sb, s->len);
    memcpy(sb->data + sb->len, s->data, (size_t)s->len);
    sb->len += s->len;
}

void rf_sb_append_cstr(RF_StringBuilder* sb, const char* s) {
    if (!sb || !s) return;
    rf_int64 slen = (rf_int64)strlen(s);
    _rf_sb_grow(sb, slen);
    memcpy(sb->data + sb->len, s, (size_t)slen);
    sb->len += slen;
}

void rf_sb_append_char(RF_StringBuilder* sb, rf_char c) {
    if (!sb) return;
    /* UTF-8 encode the char (up to 4 bytes) */
    char buf[4];
    int n = 0;
    if (c < 0x80) {
        buf[0] = (char)c; n = 1;
    } else if (c < 0x800) {
        buf[0] = (char)(0xC0 | (c >> 6));
        buf[1] = (char)(0x80 | (c & 0x3F)); n = 2;
    } else if (c < 0x10000) {
        buf[0] = (char)(0xE0 | (c >> 12));
        buf[1] = (char)(0x80 | ((c >> 6) & 0x3F));
        buf[2] = (char)(0x80 | (c & 0x3F)); n = 3;
    } else {
        buf[0] = (char)(0xF0 | (c >> 18));
        buf[1] = (char)(0x80 | ((c >> 12) & 0x3F));
        buf[2] = (char)(0x80 | ((c >> 6) & 0x3F));
        buf[3] = (char)(0x80 | (c & 0x3F)); n = 4;
    }
    _rf_sb_grow(sb, n);
    memcpy(sb->data + sb->len, buf, (size_t)n);
    sb->len += n;
}

void rf_sb_append_int(RF_StringBuilder* sb, rf_int v) {
    if (!sb) return;
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%d", (int)v);
    _rf_sb_grow(sb, n);
    memcpy(sb->data + sb->len, buf, (size_t)n);
    sb->len += n;
}

void rf_sb_append_int64(RF_StringBuilder* sb, rf_int64 v) {
    if (!sb) return;
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%lld", (long long)v);
    _rf_sb_grow(sb, n);
    memcpy(sb->data + sb->len, buf, (size_t)n);
    sb->len += n;
}

void rf_sb_append_float(RF_StringBuilder* sb, rf_float v) {
    if (!sb) return;
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "%g", v);
    _rf_sb_grow(sb, n);
    memcpy(sb->data + sb->len, buf, (size_t)n);
    sb->len += n;
}

RF_String* rf_sb_build(RF_StringBuilder* sb) {
    if (!sb || sb->len == 0) return rf_string_from_cstr("");
    return rf_string_new(sb->data, sb->len);
}

rf_int64 rf_sb_len(RF_StringBuilder* sb) {
    if (!sb) return 0;
    return sb->len;
}

void rf_sb_clear(RF_StringBuilder* sb) {
    if (!sb) return;
    sb->len = 0;
}

void rf_sb_retain(RF_StringBuilder* sb) {
    if (!sb) return;
    atomic_fetch_add(&sb->refcount, 1);
}

void rf_sb_release(RF_StringBuilder* sb) {
    if (!sb) return;
    if (atomic_fetch_sub(&sb->refcount, 1) == 1) {
        free(sb->data);
        free(sb);
    }
}

/* ========================================================================
 * Map string-key convenience wrappers
 * ======================================================================== */

RF_Map* rf_map_set_str(RF_Map* m, RF_String* key, void* val) {
    if (!key) rf_panic("rf_map_set_str: NULL key");
    return rf_map_set(m, key->data, key->len, val);
}

RF_Option_ptr rf_map_get_str(RF_Map* m, RF_String* key) {
    if (!key) return (RF_Option_ptr){.tag = 0, .value = NULL};
    return rf_map_get(m, key->data, key->len);
}

rf_bool rf_map_has_str(RF_Map* m, RF_String* key) {
    if (!key) return rf_false;
    return rf_map_has(m, key->data, key->len);
}

RF_Map* rf_map_remove_str(RF_Map* m, RF_String* key) {
    if (!m || !key) return m;
    /* Find and unoccupy the entry */
    uint64_t hash = 14695981039346656037ULL;
    for (rf_int64 i = 0; i < key->len; i++) {
        hash ^= (unsigned char)key->data[i];
        hash *= 1099511628211ULL;
    }
    rf_int64 idx = (rf_int64)(hash % (uint64_t)m->capacity);
    for (rf_int64 step = 0; step < m->capacity; step++) {
        RF_MapEntry* e = &m->entries[idx];
        if (!e->occupied) break;
        if (e->key_len == key->len && memcmp(e->key, key->data, (size_t)key->len) == 0) {
            e->occupied = 0;
            m->count--;
            break;
        }
        idx = (idx + 1) % m->capacity;
    }
    return m;
}

RF_Array* rf_map_keys(RF_Map* m) {
    if (!m) return rf_array_new(0, sizeof(RF_String*), NULL);
    RF_String** keys = (RF_String**)malloc((size_t)m->count * sizeof(RF_String*));
    if (!keys) rf_panic("rf_map_keys: out of memory");
    rf_int64 j = 0;
    for (rf_int64 i = 0; i < m->capacity; i++) {
        RF_MapEntry* e = &m->entries[i];
        if (e->occupied) {
            keys[j++] = rf_string_new((const char*)e->key, e->key_len);
        }
    }
    RF_Array* arr = rf_array_new(j, sizeof(RF_String*), keys);
    free(keys);
    return arr;
}

RF_Array* rf_map_values(RF_Map* m) {
    if (!m) return rf_array_new(0, sizeof(void*), NULL);
    void** vals = (void**)malloc((size_t)m->count * sizeof(void*));
    if (!vals) rf_panic("rf_map_values: out of memory");
    rf_int64 j = 0;
    for (rf_int64 i = 0; i < m->capacity; i++) {
        RF_MapEntry* e = &m->entries[i];
        if (e->occupied) {
            vals[j++] = e->val;
        }
    }
    RF_Array* arr = rf_array_new(j, sizeof(void*), vals);
    free(vals);
    return arr;
}
