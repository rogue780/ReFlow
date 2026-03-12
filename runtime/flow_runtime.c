/*
 * Flow Runtime Library
 * runtime/flow_runtime.c — Runtime implementations.
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "flow_runtime.h"
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
#include <signal.h>

/* ========================================================================
 * Panic Functions (RT-1-1-3)
 * ======================================================================== */

void fl_panic(const char* msg) {
    fprintf(stderr, "Flow runtime error: %s\n", msg);
    exit(1);
}

void fl_panic_overflow(void) {
    fl_panic("OverflowError");
}

void fl_panic_divzero(void) {
    fl_panic("DivisionByZeroError");
}

void fl_panic_oob(void) {
    fl_panic("IndexOutOfBoundsError");
}

/* ========================================================================
 * String (RT-1-2-1, RT-1-2-2, RT-1-2-3)
 * ======================================================================== */

FL_String* fl_string_new(const char* data, fl_int64 len) {
    if (len < 0) fl_panic("fl_string_new: negative length");
    FL_String* s = (FL_String*)malloc(sizeof(FL_String) + (size_t)len + 1);
    if (!s) fl_panic("fl_string_new: out of memory");
    s->refcount = 1;
    s->len = len;
    if (len > 0 && data) {
        memcpy(s->data, data, (size_t)len);
    }
    s->data[len] = '\0';
    return s;
}

FL_String* fl_string_from_cstr(const char* cstr) {
    if (!cstr) fl_panic("fl_string_from_cstr: NULL pointer");
    fl_int64 len = (fl_int64)strlen(cstr);
    return fl_string_new(cstr, len);
}

void fl_string_retain(FL_String* s) {
    if (!s) return;
    atomic_fetch_add(&s->refcount, 1);
}

void fl_string_release(FL_String* s) {
    if (!s) return;
    if (atomic_fetch_sub(&s->refcount, 1) == 1) {
        free(s);
    }
}

FL_String* fl_string_copy(FL_String* s) {
    if (!s) return NULL;
    return fl_string_new(s->data, s->len);
}

FL_String* fl_string_concat(FL_String* a, FL_String* b) {
    if (!a || !b) fl_panic("fl_string_concat: NULL argument");
    fl_int64 total = a->len + b->len;
    FL_String* s = (FL_String*)malloc(sizeof(FL_String) + (size_t)total + 1);
    if (!s) fl_panic("fl_string_concat: out of memory");
    s->refcount = 1;
    s->len = total;
    memcpy(s->data, a->data, (size_t)a->len);
    memcpy(s->data + a->len, b->data, (size_t)b->len);
    s->data[total] = '\0';
    return s;
}

/* In-place append: *a = concat(*a, b), with realloc when refcount==1.
 * This replaces the release-on-reassignment pattern for string concat:
 *   _fl_old = result;
 *   result = fl_string_concat(result, x);
 *   if (_fl_old != result) fl_string_release(_fl_old);
 * Avoiding the old-pointer save eliminates the dangling-pointer issue
 * that prevents in-place realloc in fl_string_concat. */
void fl_string_append(FL_String** a, FL_String* b) {
    if (!a || !*a || !b) fl_panic("fl_string_append: NULL argument");
    FL_String* old = *a;
    fl_int64 total = old->len + b->len;
    if (atomic_load(&old->refcount) == 1) {
        /* Exclusive owner — realloc in place */
        FL_String* s = (FL_String*)realloc(old, sizeof(FL_String) + (size_t)total + 1);
        if (!s) fl_panic("fl_string_append: out of memory");
        memcpy(s->data + s->len, b->data, (size_t)b->len);
        s->len = total;
        s->data[total] = '\0';
        *a = s;
    } else {
        /* Shared — allocate new, release old reference */
        FL_String* s = (FL_String*)malloc(sizeof(FL_String) + (size_t)total + 1);
        if (!s) fl_panic("fl_string_append: out of memory");
        s->refcount = 1;
        s->len = total;
        memcpy(s->data, old->data, (size_t)old->len);
        memcpy(s->data + old->len, b->data, (size_t)b->len);
        s->data[total] = '\0';
        fl_string_release(old);
        *a = s;
    }
}

// RUNTIME-DEBT: would be eliminated by mutable byte buffer type in Flow
FL_String* fl_string_join_array(FL_Array* parts) {
    if (!parts) return fl_string_from_cstr("");
    void** elems = (void**)parts->data;
    fl_int64 total = 0;
    for (fl_int64 i = 0; i < parts->len; i++) {
        FL_String* s = (FL_String*)elems[i];
        if (s) total += s->len;
    }
    FL_String* result = (FL_String*)malloc(sizeof(FL_String) + (size_t)total + 1);
    if (!result) fl_panic("fl_string_join_array: out of memory");
    result->refcount = 1;
    result->len = total;
    fl_int64 offset = 0;
    for (fl_int64 i = 0; i < parts->len; i++) {
        FL_String* s = (FL_String*)elems[i];
        if (s && s->len > 0) {
            memcpy(result->data + offset, s->data, (size_t)s->len);
            offset += s->len;
        }
    }
    result->data[total] = '\0';
    return result;
}

fl_bool fl_string_eq(FL_String* a, FL_String* b) {
    if (a == b) return fl_true;
    if (!a || !b) return fl_false;
    if (a->len != b->len) return fl_false;
    return memcmp(a->data, b->data, (size_t)a->len) == 0;
}

fl_int64 fl_string_len(FL_String* s) {
    if (!s) fl_panic("fl_string_len: NULL pointer");
    return s->len;
}

fl_int fl_string_cmp(FL_String* a, FL_String* b) {
    if (!a || !b) fl_panic("fl_string_cmp: NULL pointer");
    fl_int64 min_len = a->len < b->len ? a->len : b->len;
    int result = memcmp(a->data, b->data, (size_t)min_len);
    if (result < 0) return -1;
    if (result > 0) return 1;
    if (a->len < b->len) return -1;
    if (a->len > b->len) return 1;
    return 0;
}

/* Numeric conversions (RT-1-2-3) */

fl_bool fl_string_to_int(FL_String* s, fl_int* out) {
    if (!s || s->len == 0) return fl_false;
    char* endptr;
    long val = strtol(s->data, &endptr, 10);
    if (endptr != s->data + s->len) return fl_false;
    if (val < INT32_MIN || val > INT32_MAX) return fl_false;
    *out = (fl_int)val;
    return fl_true;
}

fl_bool fl_string_to_int64(FL_String* s, fl_int64* out) {
    if (!s || s->len == 0) return fl_false;
    char* endptr;
    long long val = strtoll(s->data, &endptr, 10);
    if (endptr != s->data + s->len) return fl_false;
    *out = (fl_int64)val;
    return fl_true;
}

fl_bool fl_string_to_float(FL_String* s, fl_float* out) {
    if (!s || s->len == 0) return fl_false;
    char* endptr;
    double val = strtod(s->data, &endptr);
    if (endptr != s->data + s->len) return fl_false;
    *out = (fl_float)val;
    return fl_true;
}

FL_String* fl_int_to_string(fl_int v) {
    char buf[16];
    int n = snprintf(buf, sizeof(buf), "%d", (int)v);
    return fl_string_new(buf, (fl_int64)n);
}

FL_String* fl_int64_to_string(fl_int64 v) {
    char buf[24];
    int n = snprintf(buf, sizeof(buf), "%lld", (long long)v);
    return fl_string_new(buf, (fl_int64)n);
}

FL_String* fl_float_to_string(fl_float v) {
    char buf[32];
    int n = snprintf(buf, sizeof(buf), "%.17g", (double)v);
    return fl_string_new(buf, (fl_int64)n);
}

FL_String* fl_bool_to_string(fl_bool v) {
    return v ? fl_string_new("true", 4) : fl_string_new("false", 5);
}

FL_String* fl_byte_to_string(fl_byte v) {
    char buf[8];
    int len = snprintf(buf, sizeof(buf), "%u", (unsigned)v);
    return fl_string_new(buf, len);
}

/* ========================================================================
 * Array (RT-1-4-1, RT-1-4-2)
 * ======================================================================== */

/* Forward declarations for element-level refcounting dispatch */
static void _fl_elem_retain(FL_ElemType t, void* slot,
                             void (*retainer)(void*)) {
    if (t == FL_ELEM_NONE) return;
    if (t == FL_ELEM_STRUCT) {
        if (retainer) retainer(slot);
        return;
    }
    void* p = *(void**)slot;
    if (!p) return;
    switch (t) {
        case FL_ELEM_STRING:  fl_string_retain((FL_String*)p); break;
        case FL_ELEM_ARRAY:   fl_array_retain((FL_Array*)p); break;
        case FL_ELEM_MAP:     fl_map_retain((FL_Map*)p); break;
        case FL_ELEM_CLOSURE: fl_closure_retain((FL_Closure*)p); break;
        case FL_ELEM_STREAM:  fl_stream_retain((FL_Stream*)p); break;
        case FL_ELEM_BUFFER:  fl_buffer_retain((FL_Buffer*)p); break;
        default: break;
    }
}

static void _fl_elem_release(FL_ElemType t, void* slot,
                              void (*destructor)(void*)) {
    if (t == FL_ELEM_NONE) return;
    if (t == FL_ELEM_STRUCT) {
        if (destructor) destructor(slot);
        return;
    }
    void* p = *(void**)slot;
    if (!p) return;
    switch (t) {
        case FL_ELEM_STRING:  fl_string_release((FL_String*)p); break;
        case FL_ELEM_ARRAY:   fl_array_release((FL_Array*)p); break;
        case FL_ELEM_MAP:     fl_map_release((FL_Map*)p); break;
        case FL_ELEM_CLOSURE: fl_closure_release((FL_Closure*)p); break;
        case FL_ELEM_STREAM:  fl_stream_release((FL_Stream*)p); break;
        case FL_ELEM_BUFFER:  fl_buffer_release((FL_Buffer*)p); break;
        case FL_ELEM_HEAP_BOX: free(p); break;
        default: break;
    }
}

FL_Array* fl_array_new(fl_int64 len, fl_int64 element_size, void* initial_data) {
    FL_Array* arr = (FL_Array*)malloc(sizeof(FL_Array));
    if (!arr) fl_panic("fl_array_new: out of memory");
    arr->refcount = 1;
    arr->len = len;
    arr->capacity = len;
    arr->element_size = element_size;
    arr->elem_type = FL_ELEM_NONE;
    arr->elem_destructor = NULL;
    arr->elem_retainer = NULL;
    if (len > 0) {
        arr->data = malloc((size_t)len * (size_t)element_size);
        if (!arr->data) fl_panic("fl_array_new: out of memory");
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

void fl_array_retain(FL_Array* arr) {
    if (!arr) return;
    atomic_fetch_add(&arr->refcount, 1);
}

void fl_array_release(FL_Array* arr) {
    if (!arr) return;
    if (atomic_fetch_sub(&arr->refcount, 1) == 1) {
        if (arr->elem_type != FL_ELEM_NONE && arr->data) {
            for (fl_int64 i = 0; i < arr->len; i++) {
                void* slot = (char*)arr->data + (size_t)i * (size_t)arr->element_size;
                _fl_elem_release(arr->elem_type, slot,
                                 arr->elem_destructor);
            }
        }
        free(arr->data);
        free(arr);
    }
}

void fl_array_set_struct_handlers(FL_Array* a,
                                   void (*destructor)(void*),
                                   void (*retainer)(void*)) {
    if (!a) return;
    a->elem_type = FL_ELEM_STRUCT;
    a->elem_destructor = destructor;
    a->elem_retainer = retainer;
}

FL_Array* fl_array_copy(FL_Array* arr) {
    if (!arr) return NULL;
    FL_Array* copy = fl_array_new(arr->len, arr->element_size, arr->data);
    copy->elem_type = arr->elem_type;
    copy->elem_destructor = arr->elem_destructor;
    copy->elem_retainer = arr->elem_retainer;
    if (copy->elem_type != FL_ELEM_NONE && copy->data) {
        for (fl_int64 i = 0; i < copy->len; i++) {
            void* slot = (char*)copy->data + (size_t)i * (size_t)copy->element_size;
            _fl_elem_retain(copy->elem_type, slot,
                            copy->elem_retainer);
        }
    }
    return copy;
}

void* fl_array_get_ptr(FL_Array* arr, fl_int64 idx) {
    if (!arr) fl_panic("fl_array_get_ptr: null array");
    if (idx < 0 || idx >= arr->len) fl_panic_oob();
    return (char*)arr->data + (size_t)idx * (size_t)arr->element_size;
}

FL_Option_ptr fl_array_get_safe(FL_Array* arr, fl_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len) return FL_NONE_PTR;
    void* ptr = (char*)arr->data + (size_t)idx * (size_t)arr->element_size;
    /* For pointer-sized elements (strings, opaque types), dereference the
       slot to return the stored pointer, not a pointer to the slot. */
    if (arr->element_size == sizeof(void*)) {
        return FL_SOME_PTR(*(void**)ptr);
    }
    return FL_SOME_PTR(ptr);
}

fl_int64 fl_array_len(FL_Array* arr) {
    if (!arr) return 0;
    return arr->len;
}

/* Helper: effective capacity (0 means capacity == len for legacy arrays) */
static inline fl_int64 fl__array_cap(FL_Array* arr) {
    return arr->capacity > 0 ? arr->capacity : arr->len;
}

FL_Array* fl_array_push(FL_Array* arr, void* element) {
    if (!arr) fl_panic("fl_array_push: null array");
    if (!element) fl_panic("fl_array_push: null element");
    fl_int64 new_len = arr->len + 1;
    size_t elem_sz = (size_t)arr->element_size;
    fl_int64 cap = fl__array_cap(arr);

    /* Exclusive owner with spare capacity — reuse the data buffer.
     * We write the new element into the spare capacity, then create a new
     * FL_Array header taking ownership of the data buffer.
     * The old header is stripped of its data pointer so that when the
     * caller releases it (Flow linear usage always releases old after push),
     * the old header is freed cleanly without touching the now-transferred
     * data buffer. */
    if (atomic_load(&arr->refcount) == 1 && new_len <= cap) {
        /* Write new element into spare capacity slot */
        memcpy((char*)arr->data + (size_t)arr->len * elem_sz, element, elem_sz);
        FL_Array* out = (FL_Array*)malloc(sizeof(FL_Array));
        if (!out) fl_panic("fl_array_push: out of memory");
        out->refcount = 1;
        out->len = new_len;
        out->capacity = cap;
        out->element_size = arr->element_size;
        out->elem_type = arr->elem_type;
        out->elem_destructor = arr->elem_destructor;
        out->elem_retainer = arr->elem_retainer;
        out->data = arr->data;
        /* Transfer data ownership to new header: old header no longer owns
         * the buffer, so releasing old header won't free or process elements. */
        arr->data = NULL;
        arr->len = 0;
        arr->elem_type = FL_ELEM_NONE;
        /* Retain the newly pushed element */
        if (out->elem_type != FL_ELEM_NONE) {
            void* new_slot = (char*)out->data + (size_t)(new_len - 1) * elem_sz;
            _fl_elem_retain(out->elem_type, new_slot,
                            out->elem_retainer);
        }
        return out;
    }

    /* Need new data buffer — either shared or no capacity left.
     * Use geometric growth (2x) to amortize future pushes. */
    fl_int64 new_cap = cap > 0 ? cap : 8;
    while (new_cap < new_len) new_cap *= 2;

    FL_Array* out = (FL_Array*)malloc(sizeof(FL_Array));
    if (!out) fl_panic("fl_array_push: out of memory");
    out->refcount = 1;
    out->len = new_len;
    out->capacity = new_cap;
    out->element_size = arr->element_size;
    out->elem_type = arr->elem_type;
    out->elem_destructor = arr->elem_destructor;
    out->elem_retainer = arr->elem_retainer;
    out->data = malloc((size_t)new_cap * elem_sz);
    if (!out->data) fl_panic("fl_array_push: out of memory");
    if (arr->len > 0) {
        memcpy(out->data, arr->data, (size_t)arr->len * elem_sz);
        /* Retain all copied elements (they're shared with old array) */
        if (out->elem_type != FL_ELEM_NONE) {
            for (fl_int64 i = 0; i < arr->len; i++) {
                void* slot = (char*)out->data + (size_t)i * elem_sz;
                _fl_elem_retain(out->elem_type, slot,
                                out->elem_retainer);
            }
        }
    }
    memcpy((char*)out->data + (size_t)arr->len * elem_sz, element, elem_sz);
    /* Retain the newly pushed element */
    if (out->elem_type != FL_ELEM_NONE) {
        void* new_slot = (char*)out->data + (size_t)arr->len * elem_sz;
        _fl_elem_retain(out->elem_type, new_slot,
                        out->elem_retainer);
    }
    return out;
}

FL_Array* fl_array_push_sized(FL_Array* arr, void* element, fl_int64 elem_size) {
    if (arr->element_size == 0) arr->element_size = elem_size;
    return fl_array_push(arr, element);
}

FL_Array* fl_array_push_ptr(FL_Array* arr, void* element) {
    if (arr->element_size == 0) arr->element_size = sizeof(void*);
    return fl_array_push(arr, &element);
}

FL_Array* fl_array_push_int(FL_Array* arr, fl_int val) {
    if (arr->element_size == 0) arr->element_size = sizeof(fl_int);
    return fl_array_push(arr, &val);
}

FL_Array* fl_array_push_int64(FL_Array* arr, fl_int64 val) {
    if (arr->element_size == 0) arr->element_size = sizeof(fl_int64);
    return fl_array_push(arr, &val);
}

FL_Array* fl_array_push_float(FL_Array* arr, fl_float val) {
    if (arr->element_size == 0) arr->element_size = sizeof(fl_float);
    return fl_array_push(arr, &val);
}

FL_Array* fl_array_push_bool(FL_Array* arr, fl_bool val) {
    if (arr->element_size == 0) arr->element_size = sizeof(fl_bool);
    return fl_array_push(arr, &val);
}

FL_Array* fl_array_push_byte(FL_Array* arr, fl_byte val) {
    if (arr->element_size == 0) arr->element_size = sizeof(fl_byte);
    return fl_array_push(arr, &val);
}

/* ========================================================================
 * Stream (RT-1-5-1, RT-1-5-2)
 * ======================================================================== */

FL_Stream* fl_stream_new(FL_StreamNext next_fn, FL_StreamFree free_fn, void* state) {
    FL_Stream* s = (FL_Stream*)malloc(sizeof(FL_Stream));
    if (!s) fl_panic("fl_stream_new: out of memory");
    s->next_fn = next_fn;
    s->free_fn = free_fn;
    s->state = state;
    s->refcount = 1;
    return s;
}

void fl_stream_retain(FL_Stream* s) {
    if (!s) return;
    atomic_fetch_add(&s->refcount, 1);
}

void fl_stream_release(FL_Stream* s) {
    if (!s) return;
    if (atomic_fetch_sub(&s->refcount, 1) == 1) {
        if (s->free_fn) {
            s->free_fn(s);
        }
        free(s);
    }
}

FL_Option_ptr fl_stream_next(FL_Stream* s) {
    return s->next_fn(s);
}

/* ========================================================================
 * Channel — bounded, thread-safe FIFO queue
 * ======================================================================== */

struct FL_Channel {
    pthread_mutex_t  mutex;
    pthread_cond_t   not_full;
    pthread_cond_t   not_empty;
    void**           buffer;
    fl_int           capacity;
    fl_int           head;
    fl_int           tail;
    fl_int           count;
    fl_bool          closed;
    _Atomic fl_int64 refcount;
    void*            exception;
    fl_int           exception_tag;
    fl_bool          has_exception;
};

FL_Channel* fl_channel_new(fl_int capacity) {
    if (capacity < 1) capacity = 1;
    FL_Channel* ch = (FL_Channel*)malloc(sizeof(FL_Channel));
    if (!ch) fl_panic("fl_channel_new: out of memory");
    pthread_mutex_init(&ch->mutex, NULL);
    pthread_cond_init(&ch->not_full, NULL);
    pthread_cond_init(&ch->not_empty, NULL);
    ch->buffer = (void**)malloc(sizeof(void*) * (size_t)capacity);
    if (!ch->buffer) fl_panic("fl_channel_new: out of memory");
    ch->capacity = capacity;
    ch->head = 0;
    ch->tail = 0;
    ch->count = 0;
    ch->closed = fl_false;
    ch->refcount = 1;
    ch->exception = NULL;
    ch->exception_tag = 0;
    ch->has_exception = fl_false;
    return ch;
}

fl_bool fl_channel_send(FL_Channel* ch, void* val) {
    pthread_mutex_lock(&ch->mutex);
    while (ch->count == ch->capacity && !ch->closed) {
        pthread_cond_wait(&ch->not_full, &ch->mutex);
    }
    if (ch->closed) {
        pthread_mutex_unlock(&ch->mutex);
        return fl_false;
    }
    ch->buffer[ch->tail] = val;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
    return fl_true;
}

FL_Option_ptr fl_channel_recv(FL_Channel* ch) {
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
        return FL_SOME_PTR(val);
    }
    /* count == 0 && closed */
    if (ch->has_exception) {
        void* exc = ch->exception;
        fl_int tag = ch->exception_tag;
        pthread_mutex_unlock(&ch->mutex);
        _fl_throw(exc, tag);
    }
    pthread_mutex_unlock(&ch->mutex);
    return FL_NONE_PTR;
}

void fl_channel_close(FL_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    ch->closed = fl_true;
    pthread_cond_broadcast(&ch->not_full);
    pthread_cond_broadcast(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
}

fl_int fl_channel_len(FL_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    fl_int n = ch->count;
    pthread_mutex_unlock(&ch->mutex);
    return n;
}

fl_bool fl_channel_is_closed(FL_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    fl_bool c = ch->closed;
    pthread_mutex_unlock(&ch->mutex);
    return c;
}

void fl_channel_set_exception(FL_Channel* ch, void* exception, fl_int tag) {
    pthread_mutex_lock(&ch->mutex);
    ch->exception = exception;
    ch->exception_tag = tag;
    ch->has_exception = fl_true;
    pthread_mutex_unlock(&ch->mutex);
}

void fl_channel_retain(FL_Channel* ch) {
    if (!ch) return;
    atomic_fetch_add(&ch->refcount, 1);
}

void fl_channel_release(FL_Channel* ch) {
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

fl_bool fl_channel_try_send(FL_Channel* ch, void* val) {
    pthread_mutex_lock(&ch->mutex);
    if (ch->closed || ch->count == ch->capacity) {
        pthread_mutex_unlock(&ch->mutex);
        return fl_false;
    }
    ch->buffer[ch->tail] = val;
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal(&ch->not_empty);
    pthread_mutex_unlock(&ch->mutex);
    return fl_true;
}

FL_Option_ptr fl_channel_try_recv(FL_Channel* ch) {
    pthread_mutex_lock(&ch->mutex);
    if (ch->count == 0) {
        pthread_mutex_unlock(&ch->mutex);
        return FL_NONE_PTR;
    }
    void* val = ch->buffer[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    pthread_cond_signal(&ch->not_full);
    pthread_mutex_unlock(&ch->mutex);
    return FL_SOME_PTR(val);
}

/* ========================================================================
 * Coroutines
 * ======================================================================== */

/* --- Threaded coroutine producer --- */

typedef struct {
    FL_Stream*    stream;
    FL_Channel*   channel;
    FL_Coroutine* coroutine;
} _FL_CoroutineProducerArg;

static void* _fl_coroutine_producer(void* raw) {
    _FL_CoroutineProducerArg* arg = (_FL_CoroutineProducerArg*)raw;
    FL_Stream* stream = arg->stream;
    FL_Channel* channel = arg->channel;
    FL_Coroutine* coroutine = arg->coroutine;
    free(arg);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        FL_Option_ptr item;
        while ((item = fl_stream_next(stream)).tag == 1) {
            if (atomic_load(&coroutine->cancelled))
                break;  /* cancelled by stop/kill */
            if (!fl_channel_send(channel, item.value))
                break;  /* channel closed by consumer */
        }
    } else {
        fl_channel_set_exception(channel, ef.exception, ef.exception_tag);
    }
    _fl_exception_pop();
    fl_channel_close(channel);
    fl_stream_release(stream);
    fl_channel_release(channel);  /* drop producer's ref */
    return NULL;
}

/* --- Constructors --- */

FL_Coroutine* fl_coroutine_new(FL_Stream* stream) {
    FL_Coroutine* c = (FL_Coroutine*)malloc(sizeof(FL_Coroutine));
    if (!c) fl_panic("fl_coroutine_new: out of memory");
    c->stream = stream;
    c->channel = NULL;
    c->input_channel = NULL;
    c->done = fl_false;
    atomic_store(&c->cancelled, fl_false);
    return c;
}

FL_Coroutine* fl_coroutine_new_threaded(FL_Stream* stream, fl_int capacity) {
    FL_Coroutine* c = (FL_Coroutine*)malloc(sizeof(FL_Coroutine));
    if (!c) fl_panic("fl_coroutine_new_threaded: out of memory");
    c->stream = NULL;
    c->channel = fl_channel_new(capacity);
    c->input_channel = NULL;
    c->done = fl_false;
    atomic_store(&c->cancelled, fl_false);

    /* Producer holds refs to both stream and channel */
    fl_stream_retain(stream);
    fl_channel_retain(c->channel);  /* producer's ref (consumer holds the other) */

    _FL_CoroutineProducerArg* arg = (_FL_CoroutineProducerArg*)malloc(sizeof(_FL_CoroutineProducerArg));
    if (!arg) fl_panic("fl_coroutine_new_threaded: out of memory");
    arg->stream = stream;
    arg->channel = c->channel;
    arg->coroutine = c;

    pthread_create(&c->thread, NULL, _fl_coroutine_producer, arg);
    return c;
}

/* --- Operations --- */

FL_Option_ptr fl_coroutine_next(FL_Coroutine* c) {
    FL_Option_ptr result;
    if (c->channel) {
        result = fl_channel_recv(c->channel);
    } else {
        result = fl_stream_next(c->stream);
    }
    if (result.tag == 0) c->done = fl_true;
    return result;
}

FL_Option_ptr fl_coroutine_try_next(FL_Coroutine* c) {
    if (c->done) return FL_NONE_PTR;
    FL_Option_ptr result;
    if (c->channel) {
        result = fl_channel_try_recv(c->channel);
        if (result.tag == 0 && c->channel->closed) c->done = fl_true;
    } else {
        result = fl_stream_next(c->stream);
        if (result.tag == 0) c->done = fl_true;
    }
    return result;
}

fl_bool fl_coroutine_done(FL_Coroutine* c) {
    return c->done;
}

void fl_coroutine_stop(FL_Coroutine* c) {
    if (!c || c->done) return;
    atomic_store(&c->cancelled, fl_true);
    if (c->input_channel) {
        fl_channel_close(c->input_channel);
    }
    if (c->channel) {
        fl_channel_close(c->channel);
        pthread_join(c->thread, NULL);
    }
    c->done = fl_true;
}

void fl_coroutine_kill(FL_Coroutine* c) {
    if (!c || c->done) return;
    atomic_store(&c->cancelled, fl_true);
    if (c->input_channel) {
        fl_channel_close(c->input_channel);
    }
    if (c->channel) {
        fl_channel_close(c->channel);
        pthread_detach(c->thread);
    }
    c->done = fl_true;
}

void fl_coroutine_release(FL_Coroutine* c) {
    if (!c) return;
    if (c->input_channel) {
        if (!c->done) {
            fl_channel_close(c->input_channel);    /* unblock producer if waiting on inbox */
        }
        fl_channel_release(c->input_channel);  /* drop consumer-side ref */
    }
    if (c->channel) {
        if (!c->done) {
            fl_channel_close(c->channel);    /* unblock producer if blocked */
            pthread_join(c->thread, NULL);   /* wait for producer to exit */
        }
        fl_channel_release(c->channel);  /* drop consumer's ref */
    } else {
        fl_stream_release(c->stream);
    }
    free(c);
}

void fl_coroutine_send(FL_Coroutine* c, void* val) {
    if (!c->input_channel) fl_panic("fl_coroutine_send: coroutine has no input channel");
    fl_channel_send(c->input_channel, val);
}

fl_bool fl_coroutine_try_send(FL_Coroutine* c, void* val) {
    if (!c->input_channel) return fl_false;
    return fl_channel_try_send(c->input_channel, val);
}

void fl_coroutine_set_input(FL_Coroutine* c, FL_Channel* input) {
    c->input_channel = input;
    fl_channel_retain(input);  /* consumer-side ref */
}

FL_Channel* fl_coroutine_get_channel(FL_Coroutine* c) {
    return c->channel;
}

/* --- Stream backed by a channel (for receivable coroutine inbox) --- */

static FL_Option_ptr _fl_stream_from_channel_next(FL_Stream* self) {
    FL_Channel* ch = (FL_Channel*)self->state;
    return fl_channel_recv(ch);
}

static void _fl_stream_from_channel_free(FL_Stream* self) {
    FL_Channel* ch = (FL_Channel*)self->state;
    fl_channel_release(ch);  /* drop the stream's ref */
}

FL_Stream* fl_stream_from_channel(FL_Channel* ch) {
    fl_channel_retain(ch);  /* stream holds a ref */
    return fl_stream_new(_fl_stream_from_channel_next,
                         _fl_stream_from_channel_free,
                         (void*)ch);
}

/* Non-blocking variant: try_recv returns none immediately if empty */
static FL_Option_ptr _fl_stream_from_channel_try_next(FL_Stream* self) {
    FL_Channel* ch = (FL_Channel*)self->state;
    return fl_channel_try_recv(ch);
}

FL_Stream* fl_stream_from_channel_nonblocking(FL_Channel* ch) {
    fl_channel_retain(ch);  /* stream holds a ref */
    return fl_stream_new(_fl_stream_from_channel_try_next,
                         _fl_stream_from_channel_free,
                         (void*)ch);
}

/* ========================================================================
 * Worker Pools
 * ======================================================================== */

struct FL_Pool {
    FL_Channel*   input;           /* shared inbox for all workers */
    FL_Channel*   output;          /* shared outbox for all workers */
    fl_int        max_workers;
    fl_int        num_workers;
    pthread_t*    threads;
    pthread_t     monitor;         /* joins workers then closes output */
    void*       (*fn)(void*);      /* stream factory: fn(inbox_stream) -> FL_Stream* */
};

typedef struct {
    void*       (*fn)(void*);
    FL_Channel*   input;
    FL_Channel*   output;
} _FL_PoolWorkerArg;

/* Each worker: read from shared input channel, pump through fn, write to shared output channel */
static void* _fl_pool_worker(void* raw) {
    _FL_PoolWorkerArg* arg = (_FL_PoolWorkerArg*)raw;
    void* (*fn)(void*) = arg->fn;
    FL_Channel* input = arg->input;
    FL_Channel* output = arg->output;
    free(arg);

    /* Create a blocking stream from the shared input channel */
    FL_Stream* inbox = fl_stream_from_channel(input);

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        /* Call the stream function with the inbox stream */
        FL_Stream* result = (FL_Stream*)fn(inbox);

        /* Pump result stream into shared output channel */
        FL_Option_ptr item;
        while ((item = fl_stream_next(result)).tag == 1) {
            if (!fl_channel_send(output, item.value))
                break;  /* output channel closed */
        }
        fl_stream_release(result);
    } else {
        fl_channel_set_exception(output, ef.exception, ef.exception_tag);
    }
    _fl_exception_pop();

    fl_stream_release(inbox);
    fl_channel_release(input);   /* drop worker's input ref */
    fl_channel_release(output);  /* drop worker's output ref */
    return NULL;
}

/* Monitor thread: waits for all workers to complete, then closes the output channel */
static void* _fl_pool_monitor(void* raw) {
    FL_Pool* pool = (FL_Pool*)raw;
    for (fl_int i = 0; i < pool->num_workers; i++) {
        pthread_join(pool->threads[i], NULL);
    }
    fl_channel_close(pool->output);  /* signal no more data */
    return NULL;
}

FL_Pool* fl_pool_new(void* (*fn)(void*), fl_int max_workers,
                     FL_Channel* input, fl_int output_capacity) {
    if (max_workers < 1) max_workers = 1;

    FL_Pool* pool = (FL_Pool*)malloc(sizeof(FL_Pool));
    if (!pool) fl_panic("fl_pool_new: out of memory");

    pool->input = input;
    pool->output = fl_channel_new(output_capacity);
    pool->max_workers = max_workers;
    pool->fn = fn;
    pool->threads = (pthread_t*)malloc(sizeof(pthread_t) * (size_t)max_workers);
    if (!pool->threads) fl_panic("fl_pool_new: out of memory");

    /* Spawn all workers immediately (elastic scaling deferred) */
    pool->num_workers = max_workers;
    for (fl_int i = 0; i < max_workers; i++) {
        fl_channel_retain(input);   /* each worker holds a ref */
        fl_channel_retain(pool->output);

        _FL_PoolWorkerArg* arg = (_FL_PoolWorkerArg*)malloc(sizeof(_FL_PoolWorkerArg));
        if (!arg) fl_panic("fl_pool_new: out of memory");
        arg->fn = fn;
        arg->input = input;
        arg->output = pool->output;

        pthread_create(&pool->threads[i], NULL, _fl_pool_worker, arg);
    }

    /* Spawn monitor thread to close output channel when all workers finish */
    pthread_create(&pool->monitor, NULL, _fl_pool_monitor, pool);

    return pool;
}

/* Wrap a pool as a coroutine for uniform .next()/.done() access */
FL_Coroutine* fl_pool_as_coroutine(FL_Pool* pool) {
    FL_Coroutine* c = (FL_Coroutine*)malloc(sizeof(FL_Coroutine));
    if (!c) fl_panic("fl_pool_as_coroutine: out of memory");
    c->stream = NULL;
    c->channel = pool->output;
    fl_channel_retain(pool->output);  /* coroutine consumer ref */
    c->input_channel = pool->input;
    fl_channel_retain(pool->input);   /* coroutine input ref */
    c->done = fl_false;

    /* Store thread info so release can join workers.
     * We'll use the pool's first thread for the pthread_join in release.
     * Actually, for proper cleanup we need to track all threads.
     * For now, the pool must outlive the coroutine. We won't join in
     * coroutine_release — instead pool cleanup happens when input closes
     * and workers drain naturally. The coroutine just closes channels. */
    memset(&c->thread, 0, sizeof(pthread_t));

    return c;
}

/* ========================================================================
 * Closures
 * ======================================================================== */

void fl_closure_retain(FL_Closure* c) {
    if (!c) return;
    atomic_fetch_add(&c->refcount, 1);
}

void fl_closure_release(FL_Closure* c) {
    if (!c) return;
    if (atomic_fetch_sub(&c->refcount, 1) == 1) {
        free(c->env);
        free(c);
    }
}

/* ========================================================================
 * Stream Helpers
 * ======================================================================== */

/* --- take --- */

typedef struct {
    FL_Stream* src;
    fl_int     remaining;
} FL_StreamTakeState;

static FL_Option_ptr fl__stream_take_next(FL_Stream* self) {
    FL_StreamTakeState* st = (FL_StreamTakeState*)self->state;
    if (st->remaining <= 0) return FL_NONE_PTR;
    st->remaining--;
    return fl_stream_next(st->src);
}

static void fl__stream_take_free(FL_Stream* self) {
    FL_StreamTakeState* st = (FL_StreamTakeState*)self->state;
    fl_stream_release(st->src);
    free(st);
}

FL_Stream* fl_stream_take(FL_Stream* src, fl_int n) {
    fl_stream_retain(src);
    FL_StreamTakeState* st = (FL_StreamTakeState*)malloc(sizeof(FL_StreamTakeState));
    if (!st) fl_panic("fl_stream_take: out of memory");
    st->src = src;
    st->remaining = n;
    return fl_stream_new(fl__stream_take_next, fl__stream_take_free, st);
}

/* --- skip --- */

typedef struct {
    FL_Stream* src;
    fl_int     to_skip;
    fl_bool    skipped;
} FL_StreamSkipState;

static FL_Option_ptr fl__stream_skip_next(FL_Stream* self) {
    FL_StreamSkipState* st = (FL_StreamSkipState*)self->state;
    if (!st->skipped) {
        st->skipped = fl_true;
        for (fl_int i = 0; i < st->to_skip; i++) {
            FL_Option_ptr item = fl_stream_next(st->src);
            if (item.tag == 0) return FL_NONE_PTR;
        }
    }
    return fl_stream_next(st->src);
}

static void fl__stream_skip_free(FL_Stream* self) {
    FL_StreamSkipState* st = (FL_StreamSkipState*)self->state;
    fl_stream_release(st->src);
    free(st);
}

FL_Stream* fl_stream_skip(FL_Stream* src, fl_int n) {
    fl_stream_retain(src);
    FL_StreamSkipState* st = (FL_StreamSkipState*)malloc(sizeof(FL_StreamSkipState));
    if (!st) fl_panic("fl_stream_skip: out of memory");
    st->src = src;
    st->to_skip = n;
    st->skipped = fl_false;
    return fl_stream_new(fl__stream_skip_next, fl__stream_skip_free, st);
}

/* --- map --- */

typedef struct {
    FL_Stream*  src;
    FL_Closure* fn;
} FL_StreamMapState;

static FL_Option_ptr fl__stream_map_next(FL_Stream* self) {
    FL_StreamMapState* st = (FL_StreamMapState*)self->state;
    FL_Option_ptr item = fl_stream_next(st->src);
    if (item.tag == 0) return FL_NONE_PTR;
    void* result = ((void*(*)(void*, void*))st->fn->fn)(st->fn->env, item.value);
    return FL_SOME_PTR(result);
}

static void fl__stream_map_free(FL_Stream* self) {
    FL_StreamMapState* st = (FL_StreamMapState*)self->state;
    fl_stream_release(st->src);
    free(st);
}

FL_Stream* fl_stream_map(FL_Stream* src, FL_Closure* fn) {
    fl_stream_retain(src);
    FL_StreamMapState* st = (FL_StreamMapState*)malloc(sizeof(FL_StreamMapState));
    if (!st) fl_panic("fl_stream_map: out of memory");
    st->src = src;
    st->fn = fn;
    return fl_stream_new(fl__stream_map_next, fl__stream_map_free, st);
}

/* --- filter --- */

typedef struct {
    FL_Stream*  src;
    FL_Closure* fn;
} FL_StreamFilterState;

static FL_Option_ptr fl__stream_filter_next(FL_Stream* self) {
    FL_StreamFilterState* st = (FL_StreamFilterState*)self->state;
    while (1) {
        FL_Option_ptr item = fl_stream_next(st->src);
        if (item.tag == 0) return FL_NONE_PTR;
        fl_bool keep = (fl_bool)(intptr_t)((void*(*)(void*, void*))st->fn->fn)(st->fn->env, item.value);
        if (keep) return item;
    }
}

static void fl__stream_filter_free(FL_Stream* self) {
    FL_StreamFilterState* st = (FL_StreamFilterState*)self->state;
    fl_stream_release(st->src);
    free(st);
}

FL_Stream* fl_stream_filter(FL_Stream* src, FL_Closure* fn) {
    fl_stream_retain(src);
    FL_StreamFilterState* st = (FL_StreamFilterState*)malloc(sizeof(FL_StreamFilterState));
    if (!st) fl_panic("fl_stream_filter: out of memory");
    st->src = src;
    st->fn = fn;
    return fl_stream_new(fl__stream_filter_next, fl__stream_filter_free, st);
}

/* --- reduce --- */

void* fl_stream_reduce(FL_Stream* src, void* init, FL_Closure* fn) {
    void* acc = init;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        acc = ((void*(*)(void*, void*, void*))fn->fn)(fn->env, acc, item.value);
    }
    return acc;
}

/* ========================================================================
 * Stream Construction (SL-5-2)
 * ======================================================================== */

/* --- range --- */

typedef struct {
    fl_int current;
    fl_int end;
} _FL_RangeState;

static FL_Option_ptr _fl_range_next(FL_Stream* self) {
    _FL_RangeState* st = (_FL_RangeState*)self->state;
    if (st->current >= st->end) return FL_NONE_PTR;
    fl_int val = st->current;
    st->current++;
    return FL_SOME_PTR((void*)(intptr_t)val);
}

static void _fl_range_free(FL_Stream* self) {
    free(self->state);
}

FL_Stream* fl_stream_range(fl_int start, fl_int end) {
    _FL_RangeState* st = (_FL_RangeState*)malloc(sizeof(_FL_RangeState));
    if (!st) fl_panic("fl_stream_range: out of memory");
    st->current = start;
    st->end = end;
    return fl_stream_new(_fl_range_next, _fl_range_free, st);
}

/* --- range_step --- */

typedef struct {
    fl_int current;
    fl_int end;
    fl_int step;
} _FL_RangeStepState;

static FL_Option_ptr _fl_range_step_next(FL_Stream* self) {
    _FL_RangeStepState* st = (_FL_RangeStepState*)self->state;
    if (st->step > 0 && st->current >= st->end) return FL_NONE_PTR;
    if (st->step < 0 && st->current <= st->end) return FL_NONE_PTR;
    fl_int val = st->current;
    st->current += st->step;
    return FL_SOME_PTR((void*)(intptr_t)val);
}

static void _fl_range_step_free(FL_Stream* self) {
    free(self->state);
}

FL_Stream* fl_stream_range_step(fl_int start, fl_int end, fl_int step) {
    if (step == 0) fl_panic("range_step: step cannot be zero");
    _FL_RangeStepState* st = (_FL_RangeStepState*)malloc(sizeof(_FL_RangeStepState));
    if (!st) fl_panic("fl_stream_range_step: out of memory");
    st->current = start;
    st->end = end;
    st->step = step;
    return fl_stream_new(_fl_range_step_next, _fl_range_step_free, st);
}

/* --- from_array --- */

typedef struct {
    FL_Array* arr;
    fl_int64 index;
} _FL_FromArrayState;

static FL_Option_ptr _fl_from_array_next(FL_Stream* self) {
    _FL_FromArrayState* st = (_FL_FromArrayState*)self->state;
    if (st->index >= st->arr->len) return FL_NONE_PTR;
    void* ptr = (char*)st->arr->data + st->index * st->arr->element_size;
    st->index++;
    /* For pointer-sized elements, dereference; for value types, copy */
    if (st->arr->element_size == sizeof(void*)) {
        void* val = *(void**)ptr;
        return FL_SOME_PTR(val);
    }
    /* For value types, cast through intptr_t (works for int-sized values) */
    if (st->arr->element_size <= (fl_int64)sizeof(intptr_t)) {
        intptr_t val = 0;
        memcpy(&val, ptr, (size_t)st->arr->element_size);
        return FL_SOME_PTR((void*)val);
    }
    /* For larger types, return pointer to data */
    return FL_SOME_PTR(ptr);
}

static void _fl_from_array_free(FL_Stream* self) {
    _FL_FromArrayState* st = (_FL_FromArrayState*)self->state;
    fl_array_release(st->arr);
    free(st);
}

FL_Stream* fl_stream_from_array(FL_Array* arr) {
    _FL_FromArrayState* st = (_FL_FromArrayState*)malloc(sizeof(_FL_FromArrayState));
    if (!st) fl_panic("fl_stream_from_array: out of memory");
    fl_array_retain(arr);
    st->arr = arr;
    st->index = 0;
    return fl_stream_new(_fl_from_array_next, _fl_from_array_free, st);
}

/* --- repeat --- */

typedef struct {
    void* val;
    fl_int remaining;
} _FL_RepeatState;

static FL_Option_ptr _fl_repeat_next(FL_Stream* self) {
    _FL_RepeatState* st = (_FL_RepeatState*)self->state;
    if (st->remaining <= 0) return FL_NONE_PTR;
    st->remaining--;
    return FL_SOME_PTR(st->val);
}

static void _fl_repeat_free(FL_Stream* self) {
    free(self->state);
}

FL_Stream* fl_stream_repeat(void* val, fl_int n) {
    _FL_RepeatState* st = (_FL_RepeatState*)malloc(sizeof(_FL_RepeatState));
    if (!st) fl_panic("fl_stream_repeat: out of memory");
    st->val = val;
    st->remaining = n;
    return fl_stream_new(_fl_repeat_next, _fl_repeat_free, st);
}

/* --- empty --- */

static FL_Option_ptr _fl_empty_next(FL_Stream* self) {
    (void)self;
    return FL_NONE_PTR;
}

static void _fl_empty_free(FL_Stream* self) {
    (void)self;
}

FL_Stream* fl_stream_empty(void) {
    return fl_stream_new(_fl_empty_next, _fl_empty_free, NULL);
}

/* ========================================================================
 * Stream Transformation (SL-5-3)
 * ======================================================================== */

/* --- enumerate --- */

typedef struct {
    FL_Stream* source;
    fl_int64   index;
} _FL_EnumerateState;

static FL_Option_ptr _fl_enumerate_next(FL_Stream* self) {
    _FL_EnumerateState* st = (_FL_EnumerateState*)self->state;
    FL_Option_ptr item = fl_stream_next(st->source);
    if (item.tag == 0) return FL_NONE_PTR;
    FL_Pair* pair = (FL_Pair*)malloc(sizeof(FL_Pair));
    if (!pair) fl_panic("fl_stream_enumerate: out of memory");
    pair->first = (void*)(intptr_t)(st->index++);
    pair->second = item.value;
    return FL_SOME_PTR(pair);
}

static void _fl_enumerate_free(FL_Stream* self) {
    _FL_EnumerateState* st = (_FL_EnumerateState*)self->state;
    fl_stream_release(st->source);
    free(st);
}

FL_Stream* fl_stream_enumerate(FL_Stream* source) {
    fl_stream_retain(source);
    _FL_EnumerateState* st = (_FL_EnumerateState*)malloc(sizeof(_FL_EnumerateState));
    if (!st) fl_panic("fl_stream_enumerate: out of memory");
    st->source = source;
    st->index = 0;
    return fl_stream_new(_fl_enumerate_next, _fl_enumerate_free, st);
}

/* --- zip --- */

typedef struct {
    FL_Stream* a;
    FL_Stream* b;
} _FL_ZipState;

static FL_Option_ptr _fl_zip_next(FL_Stream* self) {
    _FL_ZipState* st = (_FL_ZipState*)self->state;
    FL_Option_ptr item_a = fl_stream_next(st->a);
    if (item_a.tag == 0) return FL_NONE_PTR;
    FL_Option_ptr item_b = fl_stream_next(st->b);
    if (item_b.tag == 0) return FL_NONE_PTR;
    FL_Pair* pair = (FL_Pair*)malloc(sizeof(FL_Pair));
    if (!pair) fl_panic("fl_stream_zip: out of memory");
    pair->first = item_a.value;
    pair->second = item_b.value;
    return FL_SOME_PTR(pair);
}

static void _fl_zip_free(FL_Stream* self) {
    _FL_ZipState* st = (_FL_ZipState*)self->state;
    fl_stream_release(st->a);
    fl_stream_release(st->b);
    free(st);
}

FL_Stream* fl_stream_zip(FL_Stream* a, FL_Stream* b) {
    fl_stream_retain(a);
    fl_stream_retain(b);
    _FL_ZipState* st = (_FL_ZipState*)malloc(sizeof(_FL_ZipState));
    if (!st) fl_panic("fl_stream_zip: out of memory");
    st->a = a;
    st->b = b;
    return fl_stream_new(_fl_zip_next, _fl_zip_free, st);
}

/* --- chain --- */

typedef struct {
    FL_Stream* a;
    FL_Stream* b;
    fl_bool    a_done;
} _FL_ChainState;

static FL_Option_ptr _fl_chain_next(FL_Stream* self) {
    _FL_ChainState* st = (_FL_ChainState*)self->state;
    if (!st->a_done) {
        FL_Option_ptr item = fl_stream_next(st->a);
        if (item.tag == 1) return item;
        st->a_done = fl_true;
    }
    return fl_stream_next(st->b);
}

static void _fl_chain_free(FL_Stream* self) {
    _FL_ChainState* st = (_FL_ChainState*)self->state;
    fl_stream_release(st->a);
    fl_stream_release(st->b);
    free(st);
}

FL_Stream* fl_stream_chain(FL_Stream* a, FL_Stream* b) {
    fl_stream_retain(a);
    fl_stream_retain(b);
    _FL_ChainState* st = (_FL_ChainState*)malloc(sizeof(_FL_ChainState));
    if (!st) fl_panic("fl_stream_chain: out of memory");
    st->a = a;
    st->b = b;
    st->a_done = fl_false;
    return fl_stream_new(_fl_chain_next, _fl_chain_free, st);
}

/* --- flat_map --- */

typedef struct {
    FL_Stream*  source;
    FL_Closure* f;
    FL_Stream*  current_sub;
} _FL_FlatMapState;

static FL_Option_ptr _fl_flat_map_next(FL_Stream* self) {
    _FL_FlatMapState* st = (_FL_FlatMapState*)self->state;
    for (;;) {
        /* Try to pull from the current sub-stream */
        if (st->current_sub) {
            FL_Option_ptr item = fl_stream_next(st->current_sub);
            if (item.tag == 1) return item;
            /* Sub-stream exhausted */
            fl_stream_release(st->current_sub);
            st->current_sub = NULL;
        }
        /* Pull next element from source */
        FL_Option_ptr src_item = fl_stream_next(st->source);
        if (src_item.tag == 0) return FL_NONE_PTR;
        /* Call closure: FL_Stream* (*)(void* item, void* env) */
        typedef FL_Stream* (*FlatMapFn)(void*, void*);
        FlatMapFn fn = (FlatMapFn)st->f->fn;
        st->current_sub = fn(src_item.value, st->f->env);
    }
}

static void _fl_flat_map_free(FL_Stream* self) {
    _FL_FlatMapState* st = (_FL_FlatMapState*)self->state;
    fl_stream_release(st->source);
    if (st->current_sub) {
        fl_stream_release(st->current_sub);
    }
    free(st);
}

FL_Stream* fl_stream_flat_map(FL_Stream* source, FL_Closure* f) {
    fl_stream_retain(source);
    _FL_FlatMapState* st = (_FL_FlatMapState*)malloc(sizeof(_FL_FlatMapState));
    if (!st) fl_panic("fl_stream_flat_map: out of memory");
    st->source = source;
    st->f = f;
    st->current_sub = NULL;
    return fl_stream_new(_fl_flat_map_next, _fl_flat_map_free, st);
}

/* ========================================================================
 * Stream Consumption (SL-5-4)
 * ======================================================================== */

FL_Array* fl_stream_to_array(FL_Stream* src, fl_int64 element_size) {
    FL_Buffer* buf = fl_buffer_collect(src, element_size);
    FL_Array* arr = fl_array_new(buf->len, buf->element_size, buf->data);
    fl_buffer_release(buf);
    return arr;
}

void fl_stream_foreach(FL_Stream* src, FL_Closure* fn) {
    typedef void (*ForeachFn)(void*, void*);
    ForeachFn f = (ForeachFn)fn->fn;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        f(fn->env, item.value);
    }
}

fl_int fl_stream_count(FL_Stream* src) {
    fl_int count = 0;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        count++;
    }
    return count;
}

fl_bool fl_stream_any(FL_Stream* src, FL_Closure* fn) {
    typedef fl_bool (*PredFn)(void*, void*);
    PredFn pred = (PredFn)fn->fn;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        if (pred(fn->env, item.value)) return fl_true;
    }
    return fl_false;
}

fl_bool fl_stream_all(FL_Stream* src, FL_Closure* fn) {
    typedef fl_bool (*PredFn)(void*, void*);
    PredFn pred = (PredFn)fn->fn;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        if (!pred(fn->env, item.value)) return fl_false;
    }
    return fl_true;
}

FL_Option_ptr fl_stream_find(FL_Stream* src, FL_Closure* fn) {
    typedef fl_bool (*PredFn)(void*, void*);
    PredFn pred = (PredFn)fn->fn;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        if (pred(fn->env, item.value)) return item;
    }
    return FL_NONE_PTR;
}

fl_int fl_stream_sum_int(FL_Stream* src) {
    fl_int sum = 0;
    FL_Option_ptr item;
    while ((item = fl_stream_next(src)).tag == 1) {
        fl_int val = (fl_int)(intptr_t)item.value;
        FL_CHECKED_ADD(sum, val, &sum);
    }
    return sum;
}

/* ========================================================================
 * Map — open-addressing hash table (RT-1-6-1)
 * BOOTSTRAP: replace with production hash map
 * ======================================================================== */

#define FL_MAP_INITIAL_CAPACITY 16

typedef struct {
    void*    key;
    fl_int64 key_len;
    void*    val;
    fl_bool  occupied;
} FL_MapEntry;

struct FL_Map {
    _Atomic fl_int64 refcount;
    fl_int64     count;
    fl_int64     capacity;
    FL_MapEntry* entries;
    fl_bool      owns_entries;  /* false = shared entries, don't free on release */
    FL_ElemType  val_type;      /* value refcount kind; 0 = no cleanup */
    void (*val_destructor)(void*);  /* heap-boxed struct destructor: release internal fields */
    void (*val_retainer)(void*);    /* heap-boxed struct retainer: retain internal fields */
    fl_int64 val_elem_size;         /* sizeof(StructType) for deep copy; 0 = not set */
};

static fl_uint64 fl__fnv1a(const void* key, fl_int64 len) {
    const fl_byte* p = (const fl_byte*)key;
    fl_uint64 h = UINT64_C(14695981039346656037);
    for (fl_int64 i = 0; i < len; i++) {
        h ^= (fl_uint64)p[i];
        h *= UINT64_C(1099511628211);
    }
    return h;
}

static FL_Map* fl__map_alloc(fl_int64 capacity) {
    FL_Map* m = (FL_Map*)malloc(sizeof(FL_Map));
    if (!m) fl_panic("fl_map: out of memory");
    m->refcount = 1;
    m->count = 0;
    m->capacity = capacity;
    m->entries = (FL_MapEntry*)calloc((size_t)capacity, sizeof(FL_MapEntry));
    if (!m->entries) fl_panic("fl_map: out of memory");
    m->owns_entries = fl_true;
    m->val_type = FL_ELEM_NONE;
    m->val_destructor = NULL;
    m->val_retainer = NULL;
    m->val_elem_size = 0;
    return m;
}

static fl_int64 fl__map_probe(FL_Map* m, const void* key, fl_int64 key_len) {
    fl_uint64 h = fl__fnv1a(key, key_len);
    fl_int64 idx = (fl_int64)(h % (fl_uint64)m->capacity);
    for (;;) {
        FL_MapEntry* e = &m->entries[idx];
        if (!e->occupied) return idx;
        if (e->key_len == key_len && memcmp(e->key, key, (size_t)key_len) == 0)
            return idx;
        idx = (idx + 1) % m->capacity;
    }
}

FL_Map* fl_map_new(void) {
    return fl__map_alloc(FL_MAP_INITIAL_CAPACITY);
}

FL_Map* fl_map_set(FL_Map* m, void* key, fl_int64 key_len, void* val) {
    /* Determine if key already exists */
    fl_int64 existing_idx = fl__map_probe(m, key, key_len);
    fl_int64 new_count = m->count;
    if (!m->entries[existing_idx].occupied) new_count++;

    /* Check if resize needed (load factor >= 75%) */
    fl_bool needs_resize = (4 * new_count >= 3 * m->capacity);

    /* Sole owner, inserting new key, no resize → share the entries array.
     * Insert directly into the existing entries, then return a new header
     * pointing to the SAME array.  The old header is marked non-owning
     * and its refcount is bumped so release-on-reassignment in generated
     * code (m = map.set(m, k, v)) decrements instead of freeing.
     * Only for INSERT: overwrites would need to free the old key, which
     * the old header still references through the shared entries. */
    if (atomic_load(&m->refcount) == 1 && !needs_resize
            && !m->entries[existing_idx].occupied) {
        /* Insert directly into the shared entries array */
        FL_MapEntry* e = &m->entries[existing_idx];
        void* key_copy = malloc((size_t)key_len);
        if (!key_copy) fl_panic("fl_map: out of memory");
        memcpy(key_copy, key, (size_t)key_len);
        e->key = key_copy;
        e->key_len = key_len;
        e->val = val;
        e->occupied = fl_true;

        /* Old header becomes non-owning; bump refcount to prevent free */
        m->owns_entries = fl_false;
        atomic_fetch_add(&m->refcount, 1);

        /* New header sharing same entries array */
        FL_Map* out = (FL_Map*)malloc(sizeof(FL_Map));
        if (!out) fl_panic("fl_map: out of memory");
        out->refcount = 1;
        out->count = new_count;
        out->capacity = m->capacity;
        out->entries = m->entries;
        out->owns_entries = fl_true;
        out->val_type = m->val_type;
        out->val_destructor = m->val_destructor;
        out->val_retainer = m->val_retainer;
        out->val_elem_size = m->val_elem_size;
        /* Retain the inserted value */
        if (out->val_type != FL_ELEM_NONE) {
            _fl_elem_retain(out->val_type, &e->val, NULL);
        }
        return out;
    }

    /* Need resize, overwrite, or shared → full copy with per-key duplication.
     * Old and new maps are completely independent; no refcount bump needed.
     * Release-on-reassignment in generated code will free the old map. */
    fl_int64 new_cap = m->capacity;
    while (4 * new_count >= 3 * new_cap) new_cap *= 2;

    FL_Map* n = fl__map_alloc(new_cap);
    n->val_type = m->val_type;
    n->val_destructor = m->val_destructor;
    n->val_retainer = m->val_retainer;
    n->val_elem_size = m->val_elem_size;

    /* Copy existing entries (except the one being overwritten) */
    for (fl_int64 i = 0; i < m->capacity; i++) {
        FL_MapEntry* e = &m->entries[i];
        if (!e->occupied) continue;
        if (e->key_len == key_len && memcmp(e->key, key, (size_t)key_len) == 0)
            continue;
        void* key_copy = malloc((size_t)e->key_len);
        if (!key_copy) fl_panic("fl_map: out of memory");
        memcpy(key_copy, e->key, (size_t)e->key_len);
        fl_int64 idx = fl__map_probe(n, key_copy, e->key_len);
        n->entries[idx].key = key_copy;
        n->entries[idx].key_len = e->key_len;
        /* Deep-copy heap-boxed struct values; retain internal fields */
        if (n->val_destructor && n->val_elem_size > 0 && e->val) {
            void* val_copy = malloc((size_t)n->val_elem_size);
            if (!val_copy) fl_panic("fl_map: out of memory");
            memcpy(val_copy, e->val, (size_t)n->val_elem_size);
            if (n->val_retainer) n->val_retainer(val_copy);
            n->entries[idx].val = val_copy;
        } else {
            n->entries[idx].val = e->val;
            /* Retain all copied values (shared with old map) */
            if (n->val_type != FL_ELEM_NONE) {
                _fl_elem_retain(n->val_type, &n->entries[idx].val, NULL);
            }
        }
        n->entries[idx].occupied = fl_true;
        n->count++;
    }

    /* Insert the new/updated key */
    void* new_key_copy = malloc((size_t)key_len);
    if (!new_key_copy) fl_panic("fl_map: out of memory");
    memcpy(new_key_copy, key, (size_t)key_len);
    fl_int64 idx = fl__map_probe(n, new_key_copy, key_len);
    n->entries[idx].key = new_key_copy;
    n->entries[idx].key_len = key_len;
    n->entries[idx].val = val;
    n->entries[idx].occupied = fl_true;
    /* Retain the new/updated value */
    if (n->val_type != FL_ELEM_NONE) {
        _fl_elem_retain(n->val_type, &n->entries[idx].val, NULL);
    }
    n->count++;

    return n;
}

FL_Option_ptr fl_map_get(FL_Map* m, void* key, fl_int64 key_len) {
    if (m->count == 0) return FL_NONE_PTR;
    fl_int64 idx = fl__map_probe(m, key, key_len);
    if (!m->entries[idx].occupied) return FL_NONE_PTR;
    return FL_SOME_PTR(m->entries[idx].val);
}

fl_bool fl_map_has(FL_Map* m, void* key, fl_int64 key_len) {
    if (m->count == 0) return fl_false;
    fl_int64 idx = fl__map_probe(m, key, key_len);
    return m->entries[idx].occupied;
}

fl_int64 fl_map_len(FL_Map* m) {
    return m->count;
}

void fl_map_retain(FL_Map* m) {
    if (!m) return;
    atomic_fetch_add(&m->refcount, 1);
}

void fl_map_release(FL_Map* m) {
    if (!m) return;
    if (atomic_fetch_sub(&m->refcount, 1) != 1) return;
    if (m->owns_entries) {
        for (fl_int64 i = 0; i < m->capacity; i++) {
            if (m->entries[i].occupied) {
                if (m->val_destructor && m->entries[i].val) {
                    /* Heap-boxed struct: release internal fields then free */
                    m->val_destructor(m->entries[i].val);
                    free(m->entries[i].val);
                } else if (m->val_type != FL_ELEM_NONE) {
                    _fl_elem_release(m->val_type, &m->entries[i].val, NULL);
                }
                free(m->entries[i].key);
            }
        }
        free(m->entries);
    }
    /* Non-owning headers (from shared-entries path) don't free entries/keys */
    free(m);
}

/* ========================================================================
 * Set (RT-1-6-2)
 * ======================================================================== */

struct FL_Set {
    FL_Map*  map;
    _Atomic fl_int64 refcount;
};

FL_Set* fl_set_new(void) {
    FL_Set* s = (FL_Set*)malloc(sizeof(FL_Set));
    if (!s) fl_panic("fl_set: out of memory");
    s->refcount = 1;
    s->map = fl_map_new();
    return s;
}

fl_bool fl_set_add(FL_Set* s, void* key, fl_int64 key_len) {
    fl_bool already = fl_map_has(s->map, key, key_len);
    FL_Map* new_map = fl_map_set(s->map, key, key_len, NULL);
    fl_map_release(s->map);
    s->map = new_map;
    return !already;
}

fl_bool fl_set_has(FL_Set* s, void* key, fl_int64 key_len) {
    return fl_map_has(s->map, key, key_len);
}

fl_bool fl_set_remove(FL_Set* s, void* key, fl_int64 key_len) {
    if (!fl_map_has(s->map, key, key_len)) return fl_false;
    FL_Map* old = s->map;
    FL_Map* n = fl__map_alloc(old->capacity > FL_MAP_INITIAL_CAPACITY
                               ? old->capacity : FL_MAP_INITIAL_CAPACITY);
    for (fl_int64 i = 0; i < old->capacity; i++) {
        FL_MapEntry* e = &old->entries[i];
        if (!e->occupied) continue;
        if (e->key_len == key_len && memcmp(e->key, key, (size_t)key_len) == 0)
            continue;
        void* kc = malloc((size_t)e->key_len);
        if (!kc) fl_panic("fl_set: out of memory");
        memcpy(kc, e->key, (size_t)e->key_len);
        fl_int64 idx = fl__map_probe(n, kc, e->key_len);
        n->entries[idx].key = kc;
        n->entries[idx].key_len = e->key_len;
        n->entries[idx].val = NULL;
        n->entries[idx].occupied = fl_true;
        n->count++;
    }
    fl_map_release(old);
    s->map = n;
    return fl_true;
}

fl_int64 fl_set_len(FL_Set* s) {
    return fl_map_len(s->map);
}

void fl_set_retain(FL_Set* s) {
    if (!s) return;
    atomic_fetch_add(&s->refcount, 1);
}

void fl_set_release(FL_Set* s) {
    if (!s) return;
    if (atomic_fetch_sub(&s->refcount, 1) != 1) return;
    fl_map_release(s->map);
    free(s);
}

/* ========================================================================
 * Buffer (RT-1-7-1, RT-1-7-2)
 * ======================================================================== */

#define FL_BUFFER_INITIAL_CAPACITY 8

FL_Buffer* fl_buffer_new(fl_int64 element_size) {
    return fl_buffer_with_capacity(FL_BUFFER_INITIAL_CAPACITY, element_size);
}

FL_Buffer* fl_buffer_with_capacity(fl_int64 cap, fl_int64 element_size) {
    if (cap < 1) cap = 1;
    FL_Buffer* buf = (FL_Buffer*)malloc(sizeof(FL_Buffer));
    if (!buf) fl_panic("BufferOverflowError");
    buf->refcount = 1;
    buf->len = 0;
    buf->capacity = cap;
    buf->element_size = element_size;
    buf->data = malloc((size_t)(cap * element_size));
    if (!buf->data) fl_panic("BufferOverflowError");
    return buf;
}

void fl_buffer_push(FL_Buffer* buf, void* element) {
    if (buf->len == buf->capacity) {
        fl_int64 new_cap = buf->capacity * 2;
        void* new_data = realloc(buf->data, (size_t)(new_cap * buf->element_size));
        if (!new_data) fl_panic("BufferOverflowError");
        buf->data = new_data;
        buf->capacity = new_cap;
    }
    char* dest = (char*)buf->data + buf->len * buf->element_size;
    memcpy(dest, element, (size_t)buf->element_size);
    buf->len++;
}

FL_Option_ptr fl_buffer_get(FL_Buffer* buf, fl_int64 idx) {
    if (idx < 0 || idx >= buf->len) return FL_NONE_PTR;
    void* ptr = (char*)buf->data + idx * buf->element_size;
    return FL_SOME_PTR(ptr);
}

fl_int64 fl_buffer_len(FL_Buffer* buf) {
    return buf->len;
}

void fl_buffer_sort_by(FL_Buffer* buf, int (*cmp)(const void*, const void*)) {
    if (buf->len < 2) return;
    qsort(buf->data, (size_t)buf->len, (size_t)buf->element_size, cmp);
}

void fl_buffer_reverse(FL_Buffer* buf) {
    if (buf->len < 2) return;
    fl_int64 lo = 0, hi = buf->len - 1;
    fl_int64 esz = buf->element_size;
    void* tmp = malloc((size_t)esz);
    if (!tmp) fl_panic("BufferOverflowError");
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

void fl_buffer_retain(FL_Buffer* buf) {
    if (!buf) return;
    atomic_fetch_add(&buf->refcount, 1);
}

void fl_buffer_release(FL_Buffer* buf) {
    if (!buf) return;
    if (atomic_fetch_sub(&buf->refcount, 1) == 1) {
        free(buf->data);
        free(buf);
    }
}

FL_Buffer* fl_buffer_collect(FL_Stream* s, fl_int64 element_size) {
    FL_Buffer* buf = fl_buffer_new(element_size);
    FL_Option_ptr item;
    while ((item = fl_stream_next(s)).tag == 1) {
        fl_buffer_push(buf, &item.value);
    }
    return buf;
}

/* Buffer drain stream */
typedef struct {
    FL_Buffer* buf;
    fl_int64   idx;
} FL_BufferDrainState;

static FL_Option_ptr fl__buffer_drain_next(FL_Stream* self) {
    FL_BufferDrainState* st = (FL_BufferDrainState*)self->state;
    if (st->idx >= st->buf->len) return FL_NONE_PTR;
    void* ptr = (char*)st->buf->data + st->idx * st->buf->element_size;
    st->idx++;
    return FL_SOME_PTR(ptr);
}

static void fl__buffer_drain_free(FL_Stream* self) {
    FL_BufferDrainState* st = (FL_BufferDrainState*)self->state;
    fl_buffer_release(st->buf);
    free(st);
}

FL_Stream* fl_buffer_drain(FL_Buffer* buf) {
    fl_buffer_retain(buf);
    FL_BufferDrainState* st = (FL_BufferDrainState*)malloc(sizeof(FL_BufferDrainState));
    if (!st) fl_panic("BufferOverflowError");
    st->buf = buf;
    st->idx = 0;
    return fl_stream_new(fl__buffer_drain_next, fl__buffer_drain_free, st);
}

/* --- Buffer extensions (SL-4-3) --- */

FL_Array* fl_buffer_to_array(FL_Buffer* buf) {
    return fl_array_new(buf->len, buf->element_size, buf->data);
}

void fl_buffer_clear(FL_Buffer* buf) {
    buf->len = 0;
}

FL_Option_ptr fl_buffer_pop(FL_Buffer* buf) {
    if (buf->len == 0) return FL_NONE_PTR;
    buf->len--;
    void* ptr = (char*)buf->data + buf->len * buf->element_size;
    void* copy = malloc((size_t)buf->element_size);
    if (!copy) fl_panic("fl_buffer_pop: out of memory");
    memcpy(copy, ptr, (size_t)buf->element_size);
    return FL_SOME_PTR(copy);
}

FL_Option_ptr fl_buffer_last(FL_Buffer* buf) {
    if (buf->len == 0) return FL_NONE_PTR;
    void* ptr = (char*)buf->data + (buf->len - 1) * buf->element_size;
    void* copy = malloc((size_t)buf->element_size);
    if (!copy) fl_panic("fl_buffer_last: out of memory");
    memcpy(copy, ptr, (size_t)buf->element_size);
    return FL_SOME_PTR(copy);
}

void fl_buffer_set(FL_Buffer* buf, fl_int64 idx, void* element) {
    if (idx < 0 || idx >= buf->len) fl_panic_oob();
    void* ptr = (char*)buf->data + idx * buf->element_size;
    memcpy(ptr, element, (size_t)buf->element_size);
}

void fl_buffer_insert(FL_Buffer* buf, fl_int64 idx, void* element) {
    if (idx < 0 || idx > buf->len) fl_panic_oob();
    /* Ensure capacity */
    if (buf->len >= buf->capacity) {
        fl_int64 new_cap = buf->capacity < 8 ? 8 : buf->capacity * 2;
        buf->data = realloc(buf->data, (size_t)(new_cap * buf->element_size));
        if (!buf->data) fl_panic("fl_buffer_insert: out of memory");
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

FL_Option_ptr fl_buffer_remove(FL_Buffer* buf, fl_int64 idx) {
    if (idx < 0 || idx >= buf->len) return FL_NONE_PTR;
    void* ptr = (char*)buf->data + idx * buf->element_size;
    void* copy = malloc((size_t)buf->element_size);
    if (!copy) fl_panic("fl_buffer_remove: out of memory");
    memcpy(copy, ptr, (size_t)buf->element_size);
    /* Shift elements left */
    if (idx < buf->len - 1) {
        memmove(ptr,
                (char*)buf->data + (idx + 1) * buf->element_size,
                (size_t)((buf->len - idx - 1) * buf->element_size));
    }
    buf->len--;
    return FL_SOME_PTR(copy);
}

fl_bool fl_buffer_contains(FL_Buffer* buf, void* element, fl_int64 element_size) {
    for (fl_int64 i = 0; i < buf->len; i++) {
        void* ptr = (char*)buf->data + i * buf->element_size;
        if (memcmp(ptr, element, (size_t)element_size) == 0) return fl_true;
    }
    return fl_false;
}

FL_Buffer* fl_buffer_slice(FL_Buffer* buf, fl_int64 start, fl_int64 end) {
    if (start < 0) start = 0;
    if (end > buf->len) end = buf->len;
    if (start >= end) return fl_buffer_new(buf->element_size);
    fl_int64 count = end - start;
    FL_Buffer* result = fl_buffer_with_capacity(count, buf->element_size);
    memcpy(result->data, (char*)buf->data + start * buf->element_size,
           (size_t)(count * buf->element_size));
    result->len = count;
    return result;
}

/* ========================================================================
 * Sort (stdlib/sort)
 * ======================================================================== */

/* --- closure-based sort (fl_sort_array_by) --- */
/*
 * The comparator closure must have fn signature:
 *   fl_int (*)(void* env, const void* a_ptr, const void* b_ptr)
 * where a_ptr and b_ptr are pointers into the array's element buffer.
 *
 * The compiler generates a sort comparator wrapper (via _lower_sort_closure_wrapper
 * in lowering.py) that dereferences a_ptr and b_ptr to typed element values
 * before calling the user's typed comparator closure. This bridging is needed
 * because qsort passes element addresses, not element values.
 */

static _Thread_local FL_Closure* _fl_sort_closure;

static int _fl_sort_closure_cmp(const void* a, const void* b) {
    typedef fl_int (*CmpFn)(void*, const void*, const void*);
    CmpFn fn = (CmpFn)_fl_sort_closure->fn;
    return (int)fn(_fl_sort_closure->env, a, b);
}

FL_Array* fl_sort_array_by(FL_Array* arr, FL_Closure* cmp) {
    if (!arr) fl_panic("fl_sort_array_by: NULL array");
    if (!cmp) fl_panic("fl_sort_array_by: NULL closure");
    if (arr->len == 0) return fl_array_new(0, arr->element_size, NULL);

    /* Copy data into temp buffer */
    size_t total = (size_t)arr->len * (size_t)arr->element_size;
    void* tmp = malloc(total);
    if (!tmp) fl_panic("fl_sort_array_by: out of memory");
    memcpy(tmp, arr->data, total);

    /* Set thread-local closure and sort */
    _fl_sort_closure = cmp;
    qsort(tmp, (size_t)arr->len, (size_t)arr->element_size, _fl_sort_closure_cmp);

    FL_Array* result = fl_array_new(arr->len, arr->element_size, tmp);
    free(tmp);
    return result;
}

/* --- reverse --- */

FL_Array* fl_array_reverse(FL_Array* arr) {
    if (!arr) fl_panic("fl_array_reverse: NULL array");
    if (arr->len == 0) return fl_array_new(0, arr->element_size, NULL);

    fl_int64 esz = arr->element_size;
    size_t total = (size_t)arr->len * (size_t)esz;
    void* tmp = malloc(total);
    if (!tmp) fl_panic("fl_array_reverse: out of memory");

    for (fl_int64 i = 0; i < arr->len; i++) {
        char* src = (char*)arr->data + i * esz;
        char* dst = (char*)tmp + (arr->len - 1 - i) * esz;
        memcpy(dst, src, (size_t)esz);
    }

    FL_Array* result = fl_array_new(arr->len, arr->element_size, tmp);
    free(tmp);
    return result;
}

/* ========================================================================
 * Bytes (stdlib/bytes)
 * ======================================================================== */

FL_Array* fl_bytes_slice(FL_Array* arr, fl_int64 start, fl_int64 end) {
    if (!arr) fl_panic("fl_bytes_slice: NULL array");
    fl_int64 len = fl_array_len(arr);
    if (start < 0) start = 0;
    if (start > len) start = len;
    if (end < start) end = start;
    if (end > len) end = len;
    fl_int64 slice_len = end - start;
    if (slice_len == 0) return fl_array_new(0, 1, NULL);
    fl_byte* src = (fl_byte*)arr->data + start;
    return fl_array_new(slice_len, 1, src);
}

FL_Array* fl_bytes_concat(FL_Array* a, FL_Array* b) {
    if (!a) fl_panic("fl_bytes_concat: NULL first argument");
    if (!b) fl_panic("fl_bytes_concat: NULL second argument");
    fl_int64 a_len = fl_array_len(a);
    fl_int64 b_len = fl_array_len(b);
    fl_int64 total = a_len + b_len;
    if (total == 0) return fl_array_new(0, 1, NULL);
    fl_byte* buf = (fl_byte*)malloc((size_t)total);
    if (!buf) fl_panic("fl_bytes_concat: out of memory");
    if (a_len > 0) memcpy(buf, a->data, (size_t)a_len);
    if (b_len > 0) memcpy(buf + a_len, b->data, (size_t)b_len);
    FL_Array* result = fl_array_new(total, 1, buf);
    free(buf);
    return result;
}

FL_Option_ptr fl_bytes_index_of(FL_Array* haystack, fl_byte needle) {
    if (!haystack) fl_panic("fl_bytes_index_of: NULL array");
    fl_int64 len = fl_array_len(haystack);
    fl_byte* data = (fl_byte*)haystack->data;
    for (fl_int64 i = 0; i < len; i++) {
        if (data[i] == needle) {
            return FL_SOME_PTR((void*)(intptr_t)i);
        }
    }
    return FL_NONE_PTR;
}

fl_int64 fl_bytes_len(FL_Array* arr) {
    if (!arr) fl_panic("fl_bytes_len: NULL array");
    return fl_array_len(arr);
}

/* ========================================================================
 * I/O Primitives (RT-1-8-1, RT-1-8-2)
 * ======================================================================== */

void fl_print(FL_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stdout);
}

void fl_println(FL_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stdout);
    fputc('\n', stdout);
}

void fl_eprint(FL_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stderr);
}

void fl_eprintln(FL_String* s) {
    fwrite(s->data, 1, (size_t)s->len, stderr);
    fputc('\n', stderr);
}

/* Stdin byte stream */
typedef struct {
    int dummy;
} FL_StdinState;

static FL_Option_ptr fl__stdin_next(FL_Stream* self) {
    (void)self;
    int c = fgetc(stdin);
    if (c == EOF) return FL_NONE_PTR;
    fl_byte* bp = (fl_byte*)malloc(sizeof(fl_byte));
    if (!bp) fl_panic("fl_stdin_stream: out of memory");
    *bp = (fl_byte)c;
    return FL_SOME_PTR(bp);
}

static void fl__stdin_free(FL_Stream* self) {
    free(self->state);
}

FL_Stream* fl_stdin_stream(void) {
    FL_StdinState* st = (FL_StdinState*)malloc(sizeof(FL_StdinState));
    if (!st) fl_panic("fl_stdin_stream: out of memory");
    st->dummy = 0;
    return fl_stream_new(fl__stdin_next, fl__stdin_free, st);
}

FL_Option_ptr fl_read_line(void) {
    fl_int64 cap = 128;
    fl_int64 len = 0;
    char* buf = (char*)malloc((size_t)cap);
    if (!buf) fl_panic("fl_read_line: out of memory");

    int c;
    while ((c = fgetc(stdin)) != EOF) {
        if (len + 1 >= cap) {
            cap *= 2;
            char* nb = (char*)realloc(buf, (size_t)cap);
            if (!nb) { free(buf); fl_panic("fl_read_line: out of memory"); }
            buf = nb;
        }
        if (c == '\n') break;
        buf[len++] = (char)c;
    }

    if (len == 0 && c == EOF) {
        free(buf);
        return FL_NONE_PTR;
    }

    FL_String* s = fl_string_new(buf, len);
    free(buf);
    return FL_SOME_PTR(s);
}

FL_Option_ptr fl_read_byte(void) {
    int c = fgetc(stdin);
    if (c == EOF) return FL_NONE_PTR;
    return (FL_Option_ptr){.tag = 1, .value = (void*)(uintptr_t)(fl_byte)c};
}

FL_Option_ptr fl_read_stdin(void) {
    fl_int64 cap = 4096;
    fl_int64 len = 0;
    char* buf = (char*)malloc((size_t)cap);
    if (!buf) fl_panic("fl_read_stdin: out of memory");

    int c;
    while ((c = fgetc(stdin)) != EOF) {
        if (len + 1 >= cap) {
            cap *= 2;
            char* nb = (char*)realloc(buf, (size_t)cap);
            if (!nb) { free(buf); fl_panic("fl_read_stdin: out of memory"); }
            buf = nb;
        }
        buf[len++] = (char)c;
    }

    if (len == 0) {
        free(buf);
        return FL_NONE_PTR;
    }

    FL_String* s = fl_string_new(buf, len);
    free(buf);
    return FL_SOME_PTR(s);
}

/* ========================================================================
 * String Operations (stdlib/string — RB-1-1)
 * ======================================================================== */

FL_Option_char fl_string_char_at(FL_String* s, fl_int64 idx) {
    /* BOOTSTRAP SIMPLIFICATION: byte indexing, not codepoint indexing.
     * All bootstrap compiler source files are ASCII. */
    if (!s || idx < 0 || idx >= s->len) return (FL_Option_char){.tag = 0};
    fl_char c = (fl_char)(unsigned char)s->data[idx];
    return (FL_Option_char){.tag = 1, .value = c};
}

FL_String* fl_string_substring(FL_String* s, fl_int64 start, fl_int64 end) {
    if (!s) fl_panic("fl_string_substring: NULL pointer");
    if (start < 0) start = 0;
    if (end > s->len) end = s->len;
    if (start > end) fl_panic("fl_string_substring: start > end");
    return fl_string_new(s->data + start, end - start);
}

FL_Option_int fl_string_index_of(FL_String* haystack, FL_String* needle) {
    if (!haystack || !needle) return (FL_Option_int){.tag = 0};
    if (needle->len == 0) {
        return (FL_Option_int){.tag = 1, .value = 0};
    }
    if (needle->len > haystack->len) return (FL_Option_int){.tag = 0};
    for (fl_int64 i = 0; i <= haystack->len - needle->len; i++) {
        if (memcmp(haystack->data + i, needle->data, (size_t)needle->len) == 0) {
            return (FL_Option_int){.tag = 1, .value = (fl_int)i};
        }
    }
    return (FL_Option_int){.tag = 0};
}

fl_bool fl_string_contains(FL_String* s, FL_String* needle) {
    FL_Option_int result = fl_string_index_of(s, needle);
    return result.tag == 1;
}

fl_bool fl_string_starts_with(FL_String* s, FL_String* prefix) {
    if (!s || !prefix) return fl_false;
    if (prefix->len > s->len) return fl_false;
    return memcmp(s->data, prefix->data, (size_t)prefix->len) == 0;
}

fl_bool fl_string_ends_with(FL_String* s, FL_String* suffix) {
    if (!s || !suffix) return fl_false;
    if (suffix->len > s->len) return fl_false;
    return memcmp(s->data + s->len - suffix->len, suffix->data,
                  (size_t)suffix->len) == 0;
}

FL_Array* fl_string_split(FL_String* s, FL_String* sep) {
    if (!s || !sep) fl_panic("fl_string_split: NULL argument");

    /* Collect parts into a buffer, then convert to array. */
    FL_Buffer* buf = fl_buffer_new(sizeof(FL_String*));

    if (sep->len == 0) {
        /* Split into individual characters (bytes for bootstrap). */
        for (fl_int64 i = 0; i < s->len; i++) {
            FL_String* ch = fl_string_new(s->data + i, 1);
            fl_buffer_push(buf, &ch);
        }
    } else {
        fl_int64 start = 0;
        for (fl_int64 i = 0; i <= s->len - sep->len; i++) {
            if (memcmp(s->data + i, sep->data, (size_t)sep->len) == 0) {
                FL_String* part = fl_string_new(s->data + start, i - start);
                fl_buffer_push(buf, &part);
                i += sep->len - 1;
                start = i + 1;
            }
        }
        /* Last segment */
        FL_String* last = fl_string_new(s->data + start, s->len - start);
        fl_buffer_push(buf, &last);
    }

    /* Convert buffer to array. */
    FL_Array* arr = fl_array_new(buf->len, sizeof(FL_String*), buf->data);
    fl_buffer_release(buf);
    return arr;
}

static fl_bool fl__is_ascii_ws(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

FL_String* fl_string_trim(FL_String* s) {
    if (!s) fl_panic("fl_string_trim: NULL pointer");
    fl_int64 start = 0;
    fl_int64 end = s->len;
    while (start < end && fl__is_ascii_ws(s->data[start])) start++;
    while (end > start && fl__is_ascii_ws(s->data[end - 1])) end--;
    return fl_string_new(s->data + start, end - start);
}

FL_String* fl_string_trim_left(FL_String* s) {
    if (!s) fl_panic("fl_string_trim_left: NULL pointer");
    fl_int64 start = 0;
    while (start < s->len && fl__is_ascii_ws(s->data[start])) start++;
    return fl_string_new(s->data + start, s->len - start);
}

FL_String* fl_string_trim_right(FL_String* s) {
    if (!s) fl_panic("fl_string_trim_right: NULL pointer");
    fl_int64 end = s->len;
    while (end > 0 && fl__is_ascii_ws(s->data[end - 1])) end--;
    return fl_string_new(s->data, end);
}

FL_String* fl_string_replace(FL_String* s, FL_String* old_s, FL_String* new_s) {
    if (!s || !old_s || !new_s) fl_panic("fl_string_replace: NULL argument");
    if (old_s->len == 0) return fl_string_new(s->data, s->len);

    /* Count occurrences to pre-calculate size. */
    fl_int64 count = 0;
    for (fl_int64 i = 0; i <= s->len - old_s->len; i++) {
        if (memcmp(s->data + i, old_s->data, (size_t)old_s->len) == 0) {
            count++;
            i += old_s->len - 1;
        }
    }
    if (count == 0) return fl_string_new(s->data, s->len);

    fl_int64 new_len = s->len + count * (new_s->len - old_s->len);
    FL_String* result = (FL_String*)malloc(sizeof(FL_String) + (size_t)new_len + 1);
    if (!result) fl_panic("fl_string_replace: out of memory");
    result->refcount = 1;
    result->len = new_len;

    fl_int64 src = 0, dst = 0;
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


FL_String* fl_string_to_lower(FL_String* s) {
    if (!s) fl_panic("fl_string_to_lower: NULL pointer");
    FL_String* r = fl_string_new(s->data, s->len);
    for (fl_int64 i = 0; i < r->len; i++) {
        if (r->data[i] >= 'A' && r->data[i] <= 'Z') {
            r->data[i] = r->data[i] + ('a' - 'A');
        }
    }
    return r;
}

FL_String* fl_string_to_upper(FL_String* s) {
    if (!s) fl_panic("fl_string_to_upper: NULL pointer");
    FL_String* r = fl_string_new(s->data, s->len);
    for (fl_int64 i = 0; i < r->len; i++) {
        if (r->data[i] >= 'a' && r->data[i] <= 'z') {
            r->data[i] = r->data[i] - ('a' - 'A');
        }
    }
    return r;
}

FL_Array* fl_string_to_bytes(FL_String* s) {
    if (!s) fl_panic("fl_string_to_bytes: NULL pointer");
    return fl_array_new(s->len, sizeof(fl_byte), s->data);
}

FL_String* fl_string_from_bytes(FL_Array* data) {
    if (!data) fl_panic("fl_string_from_bytes: NULL pointer");
    return fl_string_new((const char*)data->data, data->len);
}

/* ========================================================================
 * Character Utilities (stdlib/char — RB-1-2)
 * is_digit, is_alpha, is_alphanumeric, is_whitespace, to_code, from_code
 * are now pure Flow in stdlib/char.flow.
 * ======================================================================== */

/* ========================================================================
 * File I/O (stdlib/io — RB-1-3)
 * ======================================================================== */

FL_Option_ptr fl_read_file(FL_String* path) {
    if (!path) return FL_NONE_PTR;
    FILE* f = fopen(path->data, "rb");
    if (!f) return FL_NONE_PTR;

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (sz < 0) { fclose(f); return FL_NONE_PTR; }

    char* buf = (char*)malloc((size_t)sz);
    if (!buf) { fclose(f); fl_panic("fl_read_file: out of memory"); }

    size_t read = fread(buf, 1, (size_t)sz, f);
    fclose(f);

    FL_String* s = fl_string_new(buf, (fl_int64)read);
    free(buf);
    return FL_SOME_PTR(s);
}

fl_bool fl_write_file(FL_String* path, FL_String* contents) {
    if (!path || !contents) return fl_false;
    FILE* f = fopen(path->data, "wb");
    if (!f) return fl_false;
    size_t written = fwrite(contents->data, 1, (size_t)contents->len, f);
    fclose(f);
    return written == (size_t)contents->len;
}

FL_Option_ptr fl_read_file_bytes(FL_String* path) {
    if (!path) return FL_NONE_PTR;
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)path->len, path->data);
    FILE* f = fopen(buf, "rb");
    if (!f) return FL_NONE_PTR;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    fl_byte* data = (fl_byte*)malloc(size > 0 ? (size_t)size : 1);
    if (!data) { fclose(f); fl_panic("fl_read_file_bytes: out of memory"); }
    fl_int64 n = (fl_int64)fread(data, 1, (size_t)size, f);
    fclose(f);
    FL_Array* arr = fl_array_new(n, sizeof(fl_byte), data);
    free(data);
    return FL_SOME_PTR(arr);
}

fl_bool fl_write_file_bytes(FL_String* path, FL_Array* data) {
    if (!path || !data) return fl_false;
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)path->len, path->data);
    FILE* f = fopen(buf, "wb");
    if (!f) return fl_false;
    size_t written = fwrite(data->data, 1, (size_t)(data->len * data->element_size), f);
    fclose(f);
    return written == (size_t)(data->len * data->element_size) ? fl_true : fl_false;
}

fl_bool fl_append_file(FL_String* path, FL_String* contents) {
    if (!path || !contents) return fl_false;
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)path->len, path->data);
    FILE* f = fopen(buf, "a");
    if (!f) return fl_false;
    size_t written = fwrite(contents->data, 1, (size_t)contents->len, f);
    fclose(f);
    return written == (size_t)contents->len ? fl_true : fl_false;
}

/* ========================================================================
 * Process Execution (stdlib/sys — RB-1-4)
 * ======================================================================== */

fl_int fl_run_process(FL_String* command, FL_Array* args) {
    if (!command) fl_panic("fl_run_process: NULL command");

    /* Build argv: [command, args..., NULL] */
    fl_int64 argc = args ? args->len : 0;
    char** argv = (char**)malloc(sizeof(char*) * (size_t)(argc + 2));
    if (!argv) fl_panic("fl_run_process: out of memory");

    argv[0] = command->data;
    for (fl_int64 i = 0; i < argc; i++) {
        FL_String** sp = (FL_String**)((char*)args->data +
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
    if (WIFEXITED(status)) return (fl_int)WEXITSTATUS(status);
    return -1;
}

FL_Option_ptr fl_run_process_capture(FL_String* command, FL_Array* args) {
    if (!command) fl_panic("fl_run_process_capture: NULL command");

    /* Build argv. */
    fl_int64 argc = args ? args->len : 0;
    char** argv = (char**)malloc(sizeof(char*) * (size_t)(argc + 2));
    if (!argv) fl_panic("fl_run_process_capture: out of memory");

    argv[0] = command->data;
    for (fl_int64 i = 0; i < argc; i++) {
        FL_String** sp = (FL_String**)((char*)args->data +
                         (size_t)i * (size_t)args->element_size);
        argv[i + 1] = (*sp)->data;
    }
    argv[argc + 1] = NULL;

    /* Create pipe for stderr. */
    int pipefd[2];
    if (pipe(pipefd) < 0) { free(argv); return FL_NONE_PTR; }

    pid_t pid = fork();
    if (pid < 0) {
        free(argv);
        close(pipefd[0]);
        close(pipefd[1]);
        return FL_NONE_PTR;
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

    FL_Buffer* buf = fl_buffer_new(1);
    char c;
    while (read(pipefd[0], &c, 1) == 1) {
        fl_buffer_push(buf, &c);
    }
    close(pipefd[0]);

    int status = 0;
    waitpid(pid, &status, 0);
    int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;

    if (exit_code != 0) {
        /* Return captured stderr as some(string). */
        FL_String* stderr_str = fl_string_new((const char*)buf->data, buf->len);
        fl_buffer_release(buf);
        return FL_SOME_PTR(stderr_str);
    }

    fl_buffer_release(buf);
    return FL_NONE_PTR;  /* Success: none. */
}

/* ========================================================================
 * Temporary File Support (stdlib/io — RB-1-5)
 * ======================================================================== */

FL_String* fl_tmpfile_create(FL_String* suffix, FL_String* contents) {
    if (!suffix || !contents) fl_panic("fl_tmpfile_create: NULL argument");

    /* Build template: /tmp/flow_XXXXXX<suffix> */
    const char* prefix = "/tmp/flow_XXXXXX";
    fl_int64 prefix_len = (fl_int64)strlen(prefix);
    fl_int64 total_len = prefix_len + suffix->len;
    char* tmpl = (char*)malloc((size_t)total_len + 1);
    if (!tmpl) fl_panic("fl_tmpfile_create: out of memory");
    memcpy(tmpl, prefix, (size_t)prefix_len);
    memcpy(tmpl + prefix_len, suffix->data, (size_t)suffix->len);
    tmpl[total_len] = '\0';

    int fd = mkstemps(tmpl, (int)suffix->len);
    if (fd < 0) {
        free(tmpl);
        fl_panic("fl_tmpfile_create: mkstemps failed");
    }

    /* Write contents. */
    ssize_t written = write(fd, contents->data, (size_t)contents->len);
    close(fd);
    (void)written;

    FL_String* path = fl_string_from_cstr(tmpl);
    free(tmpl);
    return path;
}

void fl_tmpfile_remove(FL_String* path) {
    if (!path) return;
    unlink(path->data);
}

/* ========================================================================
 * Path Utilities (stdlib/path — RB-1-6)
 * ======================================================================== */

FL_String* fl_path_cwd(void) {
    char buf[PATH_MAX];
    if (getcwd(buf, sizeof(buf)) == NULL) {
        fl_panic("fl_path_cwd: getcwd failed");
    }
    return fl_string_from_cstr(buf);
}

FL_String* fl_path_resolve(FL_String* path) {
    if (!path) fl_panic("fl_path_resolve: NULL pointer");
    char resolved[PATH_MAX];
    if (realpath(path->data, resolved) == NULL) {
        /* If file doesn't exist, return the path as-is. */
        return fl_string_new(path->data, path->len);
    }
    return fl_string_from_cstr(resolved);
}

fl_bool fl_path_exists(FL_String* path) {
    if (!path) return fl_false;
    return access(path->data, F_OK) == 0;
}

fl_bool fl_path_is_dir(FL_String* path) {
    if (!path) return fl_false;
    struct stat st;
    if (stat(path->data, &st) != 0) return fl_false;
    return S_ISDIR(st.st_mode) ? fl_true : fl_false;
}

fl_bool fl_path_is_file(FL_String* path) {
    if (!path) return fl_false;
    struct stat st;
    if (stat(path->data, &st) != 0) return fl_false;
    return S_ISREG(st.st_mode) ? fl_true : fl_false;
}


FL_Option_ptr fl_path_list_dir(FL_String* path) {
    if (!path) return FL_NONE_PTR;
    DIR* dir = opendir(path->data);
    if (!dir) return FL_NONE_PTR;

    FL_Buffer* buf = fl_buffer_new(sizeof(FL_String*));
    struct dirent* entry;
    while ((entry = readdir(dir)) != NULL) {
        /* Skip "." and ".." */
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;
        FL_String* name = fl_string_from_cstr(entry->d_name);
        fl_buffer_push(buf, &name);
    }
    closedir(dir);

    FL_Array* arr = fl_array_new(buf->len, sizeof(FL_String*), buf->data);
    fl_buffer_release(buf);
    return FL_SOME_PTR(arr);
}

/* ========================================================================
 * File Handle I/O (stdlib/file)
 * ======================================================================== */

struct FL_File {
    FILE*   fp;
    fl_bool is_binary;
};

/* --- Opening --- */

static FL_Option_ptr fl__file_open(FL_String* path, const char* mode, fl_bool is_binary) {
    if (!path) return FL_NONE_PTR;
    FILE* fp = fopen(path->data, mode);
    if (!fp) return FL_NONE_PTR;
    FL_File* f = (FL_File*)malloc(sizeof(FL_File));
    if (!f) { fclose(fp); fl_panic("fl_file_open: out of memory"); }
    f->fp = fp;
    f->is_binary = is_binary;
    return FL_SOME_PTR(f);
}

FL_Option_ptr fl_file_open_read(FL_String* path) {
    return fl__file_open(path, "r", fl_false);
}

FL_Option_ptr fl_file_open_write(FL_String* path) {
    return fl__file_open(path, "w", fl_false);
}

FL_Option_ptr fl_file_open_append(FL_String* path) {
    return fl__file_open(path, "a", fl_false);
}

FL_Option_ptr fl_file_open_read_bytes(FL_String* path) {
    return fl__file_open(path, "rb", fl_true);
}

FL_Option_ptr fl_file_open_write_bytes(FL_String* path) {
    return fl__file_open(path, "wb", fl_true);
}

/* --- Closing --- */

void fl_file_close(FL_File* f) {
    if (!f) return;
    if (f->fp) {
        fclose(f->fp);
        f->fp = NULL;
    }
    free(f);
}

/* --- Reading --- */

FL_Option_ptr fl_file_read_bytes(FL_File* f, fl_int n) {
    if (!f || !f->fp || n <= 0) return FL_NONE_PTR;
    fl_byte* buf = (fl_byte*)malloc((size_t)n);
    if (!buf) fl_panic("fl_file_read_bytes: out of memory");
    size_t read_count = fread(buf, 1, (size_t)n, f->fp);
    if (read_count == 0) {
        free(buf);
        return FL_NONE_PTR;
    }
    FL_Array* arr = fl_array_new((fl_int64)read_count, sizeof(fl_byte), buf);
    free(buf);
    return FL_SOME_PTR(arr);
}

FL_Option_ptr fl_file_read_line(FL_File* f) {
    if (!f || !f->fp) return FL_NONE_PTR;
    fl_int64 cap = 128;
    fl_int64 len = 0;
    char* buf = (char*)malloc((size_t)cap);
    if (!buf) fl_panic("fl_file_read_line: out of memory");

    int c;
    while ((c = fgetc(f->fp)) != EOF) {
        if (len + 1 >= cap) {
            cap *= 2;
            char* nb = (char*)realloc(buf, (size_t)cap);
            if (!nb) { free(buf); fl_panic("fl_file_read_line: out of memory"); }
            buf = nb;
        }
        if (c == '\n') break;
        buf[len++] = (char)c;
    }

    if (len == 0 && c == EOF) {
        free(buf);
        return FL_NONE_PTR;
    }

    /* Strip trailing \r for CRLF line endings */
    if (len > 0 && buf[len - 1] == '\r') len--;

    FL_String* s = fl_string_new(buf, len);
    free(buf);
    return FL_SOME_PTR(s);
}

FL_Option_ptr fl_file_read_all(FL_File* f) {
    if (!f || !f->fp) return FL_NONE_PTR;

    /* Save current position, seek to end to get remaining size */
    long cur = ftell(f->fp);
    if (cur < 0) return FL_NONE_PTR;
    fseek(f->fp, 0, SEEK_END);
    long end = ftell(f->fp);
    if (end < 0) { fseek(f->fp, cur, SEEK_SET); return FL_NONE_PTR; }
    fseek(f->fp, cur, SEEK_SET);

    long remaining = end - cur;
    if (remaining <= 0) {
        /* Try reading in a loop in case ftell doesn't work (e.g. pipes) */
        FL_Buffer* buf = fl_buffer_new(1);
        int c;
        while ((c = fgetc(f->fp)) != EOF) {
            char ch = (char)c;
            fl_buffer_push(buf, &ch);
        }
        if (buf->len == 0) {
            fl_buffer_release(buf);
            return FL_NONE_PTR;
        }
        FL_String* s = fl_string_new((const char*)buf->data, buf->len);
        fl_buffer_release(buf);
        return FL_SOME_PTR(s);
    }

    char* data = (char*)malloc((size_t)remaining);
    if (!data) fl_panic("fl_file_read_all: out of memory");
    size_t read_count = fread(data, 1, (size_t)remaining, f->fp);
    FL_String* s = fl_string_new(data, (fl_int64)read_count);
    free(data);
    return FL_SOME_PTR(s);
}

FL_Option_ptr fl_file_read_all_bytes(FL_File* f) {
    if (!f || !f->fp) return FL_NONE_PTR;

    long cur = ftell(f->fp);
    if (cur < 0) return FL_NONE_PTR;
    fseek(f->fp, 0, SEEK_END);
    long end = ftell(f->fp);
    if (end < 0) { fseek(f->fp, cur, SEEK_SET); return FL_NONE_PTR; }
    fseek(f->fp, cur, SEEK_SET);

    long remaining = end - cur;
    if (remaining <= 0) {
        /* Fallback: read in a loop */
        FL_Buffer* buf = fl_buffer_new(1);
        int c;
        while ((c = fgetc(f->fp)) != EOF) {
            fl_byte b = (fl_byte)c;
            fl_buffer_push(buf, &b);
        }
        if (buf->len == 0) {
            fl_buffer_release(buf);
            return FL_NONE_PTR;
        }
        FL_Array* arr = fl_array_new(buf->len, sizeof(fl_byte), buf->data);
        fl_buffer_release(buf);
        return FL_SOME_PTR(arr);
    }

    fl_byte* data = (fl_byte*)malloc((size_t)remaining);
    if (!data) fl_panic("fl_file_read_all_bytes: out of memory");
    size_t read_count = fread(data, 1, (size_t)remaining, f->fp);
    FL_Array* arr = fl_array_new((fl_int64)read_count, sizeof(fl_byte), data);
    free(data);
    return FL_SOME_PTR(arr);
}

/* --- Streams --- */

typedef struct {
    FL_File* file;
} _FL_FileLinesState;

static FL_Option_ptr _fl_file_lines_next(FL_Stream* self) {
    _FL_FileLinesState* st = (_FL_FileLinesState*)self->state;
    return fl_file_read_line(st->file);
}

static void _fl_file_lines_free(FL_Stream* self) {
    /* Does NOT close the file -- caller manages file lifetime */
    free(self->state);
}

FL_Stream* fl_file_lines(FL_File* f) {
    _FL_FileLinesState* st = (_FL_FileLinesState*)malloc(sizeof(_FL_FileLinesState));
    if (!st) fl_panic("fl_file_lines: out of memory");
    st->file = f;
    return fl_stream_new(_fl_file_lines_next, _fl_file_lines_free, st);
}

typedef struct {
    FL_File* file;
} _FL_FileByteStreamState;

static FL_Option_ptr _fl_file_byte_stream_next(FL_Stream* self) {
    _FL_FileByteStreamState* st = (_FL_FileByteStreamState*)self->state;
    if (!st->file || !st->file->fp) return FL_NONE_PTR;
    int c = fgetc(st->file->fp);
    if (c == EOF) return FL_NONE_PTR;
    return (FL_Option_ptr){.tag = 1, .value = (void*)(uintptr_t)(fl_byte)c};
}

static void _fl_file_byte_stream_free(FL_Stream* self) {
    /* Does NOT close the file -- caller manages file lifetime */
    free(self->state);
}

FL_Stream* fl_file_byte_stream(FL_File* f) {
    _FL_FileByteStreamState* st = (_FL_FileByteStreamState*)malloc(sizeof(_FL_FileByteStreamState));
    if (!st) fl_panic("fl_file_byte_stream: out of memory");
    st->file = f;
    return fl_stream_new(_fl_file_byte_stream_next, _fl_file_byte_stream_free, st);
}

/* --- Writing --- */

fl_bool fl_file_write_bytes(FL_File* f, FL_Array* data) {
    if (!f || !f->fp || !data) return fl_false;
    size_t total = (size_t)data->len * (size_t)data->element_size;
    size_t written = fwrite(data->data, 1, total, f->fp);
    return written == total ? fl_true : fl_false;
}

fl_bool fl_file_write_string(FL_File* f, FL_String* s) {
    if (!f || !f->fp || !s) return fl_false;
    size_t written = fwrite(s->data, 1, (size_t)s->len, f->fp);
    return written == (size_t)s->len ? fl_true : fl_false;
}

fl_bool fl_file_flush(FL_File* f) {
    if (!f || !f->fp) return fl_false;
    return fflush(f->fp) == 0 ? fl_true : fl_false;
}

/* --- Seeking --- */

fl_bool fl_file_seek(FL_File* f, fl_int64 offset) {
    if (!f || !f->fp) return fl_false;
    return fseek(f->fp, (long)offset, SEEK_SET) == 0 ? fl_true : fl_false;
}

fl_bool fl_file_seek_end(FL_File* f, fl_int64 offset) {
    if (!f || !f->fp) return fl_false;
    return fseek(f->fp, (long)offset, SEEK_END) == 0 ? fl_true : fl_false;
}

fl_int64 fl_file_position(FL_File* f) {
    if (!f || !f->fp) return -1;
    return (fl_int64)ftell(f->fp);
}

fl_int64 fl_file_size(FL_File* f) {
    if (!f || !f->fp) return -1;
    long cur = ftell(f->fp);
    if (cur < 0) return -1;
    fseek(f->fp, 0, SEEK_END);
    long sz = ftell(f->fp);
    fseek(f->fp, cur, SEEK_SET);
    return (fl_int64)sz;
}

/* Math functions (floor, ceil, round, pow, sqrt, log, fmod) are now
 * direct libm extern bindings in stdlib/math.flow. */

/* ========================================================================
 * Exception Handling (setjmp/longjmp)
 * ======================================================================== */

_Thread_local FL_ExceptionFrame* _fl_exception_current = NULL;

void _fl_exception_push(FL_ExceptionFrame* frame) {
    frame->parent = _fl_exception_current;
    frame->exception = NULL;
    frame->exception_tag = -1;
    _fl_exception_current = frame;
}

void _fl_exception_pop(void) {
    if (_fl_exception_current) {
        _fl_exception_current = _fl_exception_current->parent;
    }
}

void _fl_throw(void* exception, fl_int tag) {
    if (_fl_exception_current == NULL) {
        fprintf(stderr, "Flow runtime error: unhandled exception (tag %d)\n", tag);
        exit(1);
    }
    _fl_exception_current->exception = exception;
    _fl_exception_current->exception_tag = tag;
    longjmp(_fl_exception_current->jmp, 1);
}

void _fl_rethrow(void) {
    /* Re-throw the current exception up to the parent frame.
     * The exception pointer and tag are preserved from the catch dispatch. */
    if (_fl_exception_current == NULL) {
        fprintf(stderr, "Flow runtime error: unhandled exception (rethrow)\n");
        exit(1);
    }
    longjmp(_fl_exception_current->jmp, 1);
}

/* ========================================================================
 * Parallel Fan-out
 * ======================================================================== */

static void* _fl_fanout_worker(void* raw) {
    FL_FanoutBranch* task = (FL_FanoutBranch*)raw;
    task->has_exception = fl_false;
    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        task->result = task->fn(task->arg);
    } else {
        task->has_exception = fl_true;
        task->exception = ef.exception;
        task->exception_tag = ef.exception_tag;
    }
    _fl_exception_pop();
    return NULL;
}

void fl_fanout_run(FL_FanoutBranch* branches, fl_int count) {
    if (count <= 0) return;
    if (count == 1) {
        _fl_fanout_worker(&branches[0]);
        return;
    }
    pthread_t* threads = malloc(sizeof(pthread_t) * (size_t)count);
    /* Run branches 1..N-1 on new threads, branch 0 on current thread */
    for (fl_int i = 1; i < count; i++)
        pthread_create(&threads[i], NULL, _fl_fanout_worker, &branches[i]);
    /* Branch 0 on main thread (preserves exception frame stack) */
    _fl_fanout_worker(&branches[0]);
    for (fl_int i = 1; i < count; i++)
        pthread_join(threads[i], NULL);
    free(threads);
    /* Re-throw leftmost exception (sequential semantics) */
    for (fl_int i = 0; i < count; i++)
        if (branches[i].has_exception)
            _fl_throw(branches[i].exception, branches[i].exception_tag);
}

/* ========================================================================
 * Runtime Initialization
 * ======================================================================== */

static int    _fl_argc = 0;
static char** _fl_argv = NULL;

void _fl_runtime_init(int argc, char** argv) {
    _fl_argc = argc;
    _fl_argv = argv;
    signal(SIGPIPE, SIG_IGN);
}

/* ========================================================================
 * System Functions (stdlib/sys)
 * ======================================================================== */

void fl_sys_exit(fl_int code) {
    exit((int)code);
}

FL_Array* fl_sys_args(void) {
    FL_Array* arr = fl_array_new(_fl_argc, sizeof(FL_String*), NULL);
    for (int i = 0; i < _fl_argc; i++) {
        FL_String* s = fl_string_from_cstr(_fl_argv[i]);
        memcpy((char*)arr->data + (size_t)i * sizeof(FL_String*), &s, sizeof(FL_String*));
    }
    return arr;
}

FL_Option_ptr fl_env_get(FL_String* name) {
    char buf[4096];
    snprintf(buf, sizeof(buf), "%.*s", (int)name->len, name->data);
    const char* val = getenv(buf);
    if (!val) return FL_NONE_PTR;
    return FL_SOME_PTR(fl_string_from_cstr(val));
}

fl_int64 fl_clock_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (fl_int64)ts.tv_sec * 1000 + (fl_int64)ts.tv_nsec / 1000000;
}

/* ========================================================================
 * Random (stdlib/random) — xoshiro256** PRNG
 * ======================================================================== */

/* Thread-local xoshiro256** state */
static _Thread_local uint64_t _fl_rng_state[4];
static _Thread_local fl_bool _fl_rng_seeded = fl_false;

static uint64_t _fl_rotl(uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

static void _fl_rng_ensure_seeded(void) {
    if (_fl_rng_seeded) return;
    FILE* f = fopen("/dev/urandom", "rb");
    if (f) {
        size_t n = fread(_fl_rng_state, sizeof(uint64_t), 4, f);
        fclose(f);
        if (n == 4) { _fl_rng_seeded = fl_true; return; }
    }
    /* Fallback: seed from time + thread ID */
    uint64_t seed = (uint64_t)time(NULL) ^ ((uint64_t)(uintptr_t)&_fl_rng_state);
    _fl_rng_state[0] = seed;
    _fl_rng_state[1] = seed ^ 0x123456789ABCDEF0ULL;
    _fl_rng_state[2] = seed ^ 0xFEDCBA9876543210ULL;
    _fl_rng_state[3] = seed ^ 0xACEACEACEACEACEAULL;
    _fl_rng_seeded = fl_true;
}

static uint64_t _fl_rng_next_u64(void) {
    _fl_rng_ensure_seeded();
    uint64_t result = _fl_rotl(_fl_rng_state[1] * 5, 7) * 9;
    uint64_t t = _fl_rng_state[1] << 17;
    _fl_rng_state[2] ^= _fl_rng_state[0];
    _fl_rng_state[3] ^= _fl_rng_state[1];
    _fl_rng_state[1] ^= _fl_rng_state[2];
    _fl_rng_state[0] ^= _fl_rng_state[3];
    _fl_rng_state[2] ^= t;
    _fl_rng_state[3] = _fl_rotl(_fl_rng_state[3], 45);
    return result;
}

fl_int fl_random_int_range(fl_int min, fl_int max) {
    if (min > max) fl_panic("random.int_range: min > max");
    if (min == max) return min;
    uint64_t range = (uint64_t)(max - min) + 1;
    uint64_t limit = UINT64_MAX - (UINT64_MAX % range);
    uint64_t r;
    do { r = _fl_rng_next_u64(); } while (r >= limit);
    return min + (fl_int)(r % range);
}

fl_int64 fl_random_int64_range(fl_int64 min, fl_int64 max) {
    if (min > max) fl_panic("random.int64_range: min > max");
    if (min == max) return min;
    uint64_t range = (uint64_t)(max - min) + 1;
    uint64_t limit = UINT64_MAX - (UINT64_MAX % range);
    uint64_t r;
    do { r = _fl_rng_next_u64(); } while (r >= limit);
    return min + (fl_int64)(r % range);
}

fl_float fl_random_float_unit(void) {
    uint64_t r = _fl_rng_next_u64() >> 11;  /* 53 bits */
    return (fl_float)r * (1.0 / ((uint64_t)1 << 53));
}

fl_bool fl_random_bool(void) {
    return (_fl_rng_next_u64() & 1) ? fl_true : fl_false;
}

FL_Array* fl_random_bytes(fl_int n) {
    if (n <= 0) return fl_array_new(0, 1, NULL);
    fl_byte* buf = (fl_byte*)malloc((size_t)n);
    if (!buf) fl_panic("fl_random_bytes: out of memory");
    FILE* f = fopen("/dev/urandom", "rb");
    if (f) {
        size_t read = fread(buf, 1, (size_t)n, f);
        fclose(f);
        if (read < (size_t)n) {
            /* Fill remainder from PRNG */
            _fl_rng_ensure_seeded();
            for (fl_int i = (fl_int)read; i < n; i++) {
                buf[i] = (fl_byte)(_fl_rng_next_u64() & 0xFF);
            }
        }
    } else {
        _fl_rng_ensure_seeded();
        for (fl_int i = 0; i < n; i++) {
            buf[i] = (fl_byte)(_fl_rng_next_u64() & 0xFF);
        }
    }
    FL_Array* arr = fl_array_new(n, 1, buf);
    free(buf);
    return arr;
}

FL_Array* fl_random_shuffle(FL_Array* arr) {
    fl_int64 len = fl_array_len(arr);
    if (len <= 1) {
        fl_array_retain(arr);
        return arr;
    }
    fl_int64 elem_size = arr->element_size;
    fl_byte* buf = (fl_byte*)malloc((size_t)(len * elem_size));
    if (!buf) fl_panic("fl_random_shuffle: out of memory");
    memcpy(buf, arr->data, (size_t)(len * elem_size));
    _fl_rng_ensure_seeded();
    for (fl_int64 i = len - 1; i > 0; i--) {
        fl_int64 j = (fl_int64)(_fl_rng_next_u64() % (uint64_t)(i + 1));
        /* swap buf[i] and buf[j] */
        if (elem_size <= 16) {
            fl_byte tmp[16];
            memcpy(tmp, buf + i * elem_size, (size_t)elem_size);
            memcpy(buf + i * elem_size, buf + j * elem_size, (size_t)elem_size);
            memcpy(buf + j * elem_size, tmp, (size_t)elem_size);
        } else {
            fl_byte* t = (fl_byte*)malloc((size_t)elem_size);
            if (!t) fl_panic("fl_random_shuffle: out of memory");
            memcpy(t, buf + i * elem_size, (size_t)elem_size);
            memcpy(buf + i * elem_size, buf + j * elem_size, (size_t)elem_size);
            memcpy(buf + j * elem_size, t, (size_t)elem_size);
            free(t);
        }
    }
    FL_Array* result = fl_array_new(len, elem_size, buf);
    free(buf);
    return result;
}

FL_Option_ptr fl_random_choice(FL_Array* arr) {
    fl_int64 len = fl_array_len(arr);
    if (len == 0) return FL_NONE_PTR;
    fl_int64 idx = (fl_int64)(_fl_rng_next_u64() % (uint64_t)len);
    void* ptr = fl_array_get_ptr(arr, idx);
    /* For pointer-sized elements, dereference; for smaller, return pointer to data */
    if (arr->element_size == sizeof(void*)) {
        return FL_SOME_PTR(*(void**)ptr);
    }
    return FL_SOME_PTR(ptr);
}

/* ========================================================================
 * Time (stdlib/time)
 * ======================================================================== */

struct FL_Instant {
    struct timespec ts;
};

struct FL_DateTime {
    time_t     epoch;
    fl_int     utc_offset;
    struct tm  components;
};

/* --- Monotonic time --- */

FL_Instant* fl_time_now(void) {
    FL_Instant* inst = (FL_Instant*)malloc(sizeof(FL_Instant));
    if (!inst) fl_panic("fl_time_now: out of memory");
    clock_gettime(CLOCK_MONOTONIC, &inst->ts);
    return inst;
}

fl_int64 fl_time_elapsed_ms(FL_Instant* since) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    fl_int64 sec_diff = (fl_int64)(now.tv_sec - since->ts.tv_sec);
    fl_int64 nsec_diff = (fl_int64)(now.tv_nsec - since->ts.tv_nsec);
    return sec_diff * 1000 + nsec_diff / 1000000;
}

fl_int64 fl_time_elapsed_us(FL_Instant* since) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    fl_int64 sec_diff = (fl_int64)(now.tv_sec - since->ts.tv_sec);
    fl_int64 nsec_diff = (fl_int64)(now.tv_nsec - since->ts.tv_nsec);
    return sec_diff * 1000000 + nsec_diff / 1000;
}

fl_int64 fl_time_diff_ms(FL_Instant* start, FL_Instant* end) {
    fl_int64 sec_diff = (fl_int64)(end->ts.tv_sec - start->ts.tv_sec);
    fl_int64 nsec_diff = (fl_int64)(end->ts.tv_nsec - start->ts.tv_nsec);
    return sec_diff * 1000 + nsec_diff / 1000000;
}

void fl_instant_release(FL_Instant* inst) {
    free(inst);
}

/* --- Wall clock --- */

FL_DateTime* fl_time_datetime_now(void) {
    FL_DateTime* dt = (FL_DateTime*)malloc(sizeof(FL_DateTime));
    if (!dt) fl_panic("fl_time_datetime_now: out of memory");
    dt->epoch = time(NULL);
    localtime_r(&dt->epoch, &dt->components);
    dt->utc_offset = (fl_int)dt->components.tm_gmtoff;
    return dt;
}

FL_DateTime* fl_time_datetime_utc(void) {
    FL_DateTime* dt = (FL_DateTime*)malloc(sizeof(FL_DateTime));
    if (!dt) fl_panic("fl_time_datetime_utc: out of memory");
    dt->epoch = time(NULL);
    gmtime_r(&dt->epoch, &dt->components);
    dt->utc_offset = 0;
    return dt;
}

fl_int64 fl_time_unix_timestamp(void) {
    return (fl_int64)time(NULL);
}

fl_int64 fl_time_unix_timestamp_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (fl_int64)ts.tv_sec * 1000 + (fl_int64)ts.tv_nsec / 1000000;
}

void fl_time_sleep_ms(fl_int ms) {
    struct timespec req;
    req.tv_sec = ms / 1000;
    req.tv_nsec = (ms % 1000) * 1000000L;
    nanosleep(&req, NULL);
}

void fl_datetime_release(FL_DateTime* dt) {
    free(dt);
}

/* --- Formatting --- */

FL_String* fl_time_format_iso8601(FL_DateTime* dt) {
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
    return fl_string_from_cstr(full);
}

FL_String* fl_time_format_rfc2822(FL_DateTime* dt) {
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
    return fl_string_from_cstr(full);
}

FL_String* fl_time_format_http(FL_DateTime* dt) {
    /* HTTP date is always GMT. Convert to UTC if needed. */
    struct tm utc;
    gmtime_r(&dt->epoch, &utc);
    char buf[64];
    strftime(buf, sizeof(buf), "%a, %d %b %Y %H:%M:%S GMT", &utc);
    return fl_string_from_cstr(buf);
}

/* --- Component accessors --- */

fl_int fl_time_year(FL_DateTime* dt) { return (fl_int)(dt->components.tm_year + 1900); }
fl_int fl_time_month(FL_DateTime* dt) { return (fl_int)(dt->components.tm_mon + 1); }
fl_int fl_time_day(FL_DateTime* dt) { return (fl_int)dt->components.tm_mday; }
fl_int fl_time_hour(FL_DateTime* dt) { return (fl_int)dt->components.tm_hour; }
fl_int fl_time_minute(FL_DateTime* dt) { return (fl_int)dt->components.tm_min; }
fl_int fl_time_second(FL_DateTime* dt) { return (fl_int)dt->components.tm_sec; }

/* ========================================================================
 * Testing (stdlib/testing)
 * ======================================================================== */

static void _fl_test_throw(FL_String* msg) {
    _fl_throw(msg, FL_TEST_FAILURE_TAG);
}

/* assert_true and assert_false are now pure Flow in stdlib/testing.flow. */

void fl_test_assert_eq_float(fl_float expected, fl_float actual,
                              fl_float epsilon, FL_String* msg) {
    fl_float diff = expected - actual;
    if (diff < 0) diff = -diff;
    if (diff > epsilon) {
        char buf[128];
        snprintf(buf, sizeof(buf), "expected %f, got %f (epsilon %f): ",
                 expected, actual, epsilon);
        FL_String* prefix = fl_string_from_cstr(buf);
        FL_String* full = fl_string_concat(prefix, msg);
        fl_string_release(prefix);
        _fl_test_throw(full);
    }
}

void* fl_test_assert_some(FL_Option_ptr opt, FL_String* msg) {
    if (opt.tag == 0) {
        FL_String* prefix = fl_string_from_cstr("expected Some, got None: ");
        FL_String* full = fl_string_concat(prefix, msg);
        fl_string_release(prefix);
        _fl_test_throw(full);
    }
    return opt.value;
}

void fl_test_assert_none(FL_Option_ptr opt, FL_String* msg) {
    if (opt.tag != 0) {
        FL_String* prefix = fl_string_from_cstr("expected None, got Some: ");
        FL_String* full = fl_string_concat(prefix, msg);
        fl_string_release(prefix);
        _fl_test_throw(full);
    }
}

void fl_test_fail(FL_String* msg) {
    _fl_test_throw(msg);
}

FL_TestResult fl_test_run(FL_String* name, FL_Closure* test_fn) {
    FL_TestResult result;
    result.name = name;
    result.failure_msg = NULL;

    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        /* Call the test closure: void (*)(void* env) */
        typedef void (*TestFn)(void*);
        TestFn fn = (TestFn)test_fn->fn;
        fn(test_fn->env);
        result.passed = 1;
    } else {
        result.passed = 0;
        if (ef.exception_tag == FL_TEST_FAILURE_TAG) {
            result.failure_msg = (FL_String*)ef.exception;
        } else {
            result.failure_msg = fl_string_from_cstr("unexpected exception");
        }
    }
    _fl_exception_pop();
    return result;
}

void fl_test_report(FL_TestResult* result) {
    if (result->passed) {
        fprintf(stdout, "  PASS  %.*s\n",
                (int)fl_string_len(result->name), result->name->data);
    } else {
        fprintf(stdout, "  FAIL  %.*s: %.*s\n",
                (int)fl_string_len(result->name), result->name->data,
                (int)fl_string_len(result->failure_msg), result->failure_msg->data);
    }
}

fl_int fl_test_run_all(FL_Array* tests) {
    fl_int64 len = fl_array_len(tests);
    fl_int failures = 0;
    fl_int total = 0;

    for (fl_int64 i = 0; i < len; i++) {
        /* Each element is a pointer to a struct { FL_String* name; FL_Closure* fn; } */
        typedef struct { FL_String* name; FL_Closure* fn; } TestEntry;
        TestEntry* entry = *(TestEntry**)fl_array_get_ptr(tests, i);
        FL_TestResult result = fl_test_run(entry->name, entry->fn);
        fl_test_report(&result);
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

struct FL_Socket {
    int fd;
};

FL_Option_ptr fl_net_listen(FL_String* addr, fl_int port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return FL_NONE_PTR;

    int opt = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons((uint16_t)port);

    if (addr && fl_string_len(addr) > 0) {
        char buf[256];
        fl_int64 len = fl_string_len(addr);
        if (len >= (fl_int64)sizeof(buf)) len = (fl_int64)(sizeof(buf) - 1);
        memcpy(buf, addr->data, (size_t)len);
        buf[len] = '\0';
        inet_pton(AF_INET, buf, &sa.sin_addr);
    } else {
        sa.sin_addr.s_addr = INADDR_ANY;
    }

    if (bind(fd, (struct sockaddr*)&sa, sizeof(sa)) < 0) {
        close(fd);
        return FL_NONE_PTR;
    }

    if (listen(fd, 128) < 0) {
        close(fd);
        return FL_NONE_PTR;
    }

    FL_Socket* listener = (FL_Socket*)malloc(sizeof(FL_Socket));
    if (!listener) { close(fd); return FL_NONE_PTR; }
    listener->fd = fd;
    return FL_SOME_PTR(listener);
}

FL_Option_ptr fl_net_accept(FL_Socket* listener) {
    if (!listener || listener->fd < 0) return FL_NONE_PTR;

    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    int client_fd = accept(listener->fd, (struct sockaddr*)&client_addr, &client_len);
    if (client_fd < 0) return FL_NONE_PTR;

    FL_Socket* conn = (FL_Socket*)malloc(sizeof(FL_Socket));
    if (!conn) { close(client_fd); return FL_NONE_PTR; }
    conn->fd = client_fd;
    return FL_SOME_PTR(conn);
}

FL_Option_ptr fl_net_connect(FL_String* host, fl_int port) {
    if (!host) return FL_NONE_PTR;

    char host_buf[256];
    fl_int64 hlen = fl_string_len(host);
    if (hlen >= (fl_int64)sizeof(host_buf)) return FL_NONE_PTR;
    memcpy(host_buf, host->data, (size_t)hlen);
    host_buf[hlen] = '\0';

    char port_buf[16];
    snprintf(port_buf, sizeof(port_buf), "%d", port);

    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(host_buf, port_buf, &hints, &res) != 0) {
        return FL_NONE_PTR;
    }

    int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (fd < 0) {
        freeaddrinfo(res);
        return FL_NONE_PTR;
    }

    if (connect(fd, res->ai_addr, res->ai_addrlen) < 0) {
        close(fd);
        freeaddrinfo(res);
        return FL_NONE_PTR;
    }

    freeaddrinfo(res);
    FL_Socket* conn = (FL_Socket*)malloc(sizeof(FL_Socket));
    if (!conn) { close(fd); return FL_NONE_PTR; }
    conn->fd = fd;
    return FL_SOME_PTR(conn);
}

FL_Option_ptr fl_net_read(FL_Socket* conn, fl_int max_bytes) {
    if (!conn || conn->fd < 0 || max_bytes <= 0) return FL_NONE_PTR;

    fl_byte* buf = (fl_byte*)malloc((size_t)max_bytes);
    if (!buf) return FL_NONE_PTR;

    ssize_t n = recv(conn->fd, buf, (size_t)max_bytes, 0);
    if (n <= 0) {
        /* n < 0: error; n == 0: peer closed connection (EOF) */
        free(buf);
        return FL_NONE_PTR;
    }

    FL_Array* arr = fl_array_new((fl_int64)n, sizeof(fl_byte), NULL);
    memcpy(arr->data, buf, (size_t)n);
    free(buf);
    return FL_SOME_PTR(arr);
}

fl_bool fl_net_write(FL_Socket* conn, FL_Array* data) {
    if (!conn || conn->fd < 0 || !data) return fl_false;

    fl_int64 total = fl_array_len(data);
    fl_int64 sent = 0;
    while (sent < total) {
        ssize_t n = send(conn->fd, (char*)data->data + sent,
                         (size_t)(total - sent), MSG_NOSIGNAL);
        if (n <= 0) return fl_false;
        sent += n;
    }
    return fl_true;
}

fl_bool fl_net_write_string(FL_Socket* conn, FL_String* s) {
    if (!conn || conn->fd < 0 || !s) return fl_false;

    fl_int64 total = fl_string_len(s);
    fl_int64 sent = 0;
    while (sent < total) {
        ssize_t n = send(conn->fd, s->data + sent,
                         (size_t)(total - sent), MSG_NOSIGNAL);
        if (n <= 0) return fl_false;
        sent += n;
    }
    return fl_true;
}

void fl_net_close(FL_Socket* conn) {
    if (conn) {
        if (conn->fd >= 0) {
            close(conn->fd);
            conn->fd = -1;
        }
        free(conn);
    }
}

fl_bool fl_net_set_timeout(FL_Socket* conn, fl_int ms) {
    if (!conn || conn->fd < 0) return fl_false;

    struct timeval tv;
    tv.tv_sec = ms / 1000;
    tv.tv_usec = (ms % 1000) * 1000;

    if (setsockopt(conn->fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0) {
        return fl_false;
    }
    if (setsockopt(conn->fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv)) < 0) {
        return fl_false;
    }
    return fl_true;
}

FL_Option_ptr fl_net_remote_addr(FL_Socket* conn) {
    if (!conn || conn->fd < 0) return FL_NONE_PTR;

    struct sockaddr_in sa;
    socklen_t sa_len = sizeof(sa);
    if (getpeername(conn->fd, (struct sockaddr*)&sa, &sa_len) < 0) {
        return FL_NONE_PTR;
    }

    char ip_buf[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &sa.sin_addr, ip_buf, sizeof(ip_buf));
    int port = ntohs(sa.sin_port);

    char result[280];
    snprintf(result, sizeof(result), "%s:%d", ip_buf, port);

    FL_String* addr_str = fl_string_from_cstr(result);
    return FL_SOME_PTR(addr_str);
}

fl_int fl_net_fd(FL_Socket* conn) {
    if (!conn || conn->fd < 0) return -1;
    return conn->fd;
}

fl_bool fl_net_write_string_fd(fl_int fd, FL_String* s) {
    if (fd < 0 || !s) return fl_false;

    fl_int64 total = fl_string_len(s);
    fl_int64 sent = 0;
    while (sent < total) {
        ssize_t n = send(fd, s->data + sent, (size_t)(total - sent), MSG_NOSIGNAL);
        if (n <= 0) return fl_false;
        sent += n;
    }
    return fl_true;
}

/* ========================================================================
 * Array stdlib extensions
 * ======================================================================== */

FL_Option_int fl_array_get_int(FL_Array* arr, fl_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (FL_Option_int){.tag = 0, .value = 0};
    fl_int* ptr = (fl_int*)((char*)arr->data + idx * arr->element_size);
    return (FL_Option_int){.tag = 1, .value = *ptr};
}

FL_Option_int64 fl_array_get_int64(FL_Array* arr, fl_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (FL_Option_int64){.tag = 0, .value = 0};
    fl_int64* ptr = (fl_int64*)((char*)arr->data + idx * arr->element_size);
    return (FL_Option_int64){.tag = 1, .value = *ptr};
}

FL_Option_float fl_array_get_float(FL_Array* arr, fl_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (FL_Option_float){.tag = 0, .value = 0.0};
    fl_float* ptr = (fl_float*)((char*)arr->data + idx * arr->element_size);
    return (FL_Option_float){.tag = 1, .value = *ptr};
}

FL_Option_bool fl_array_get_bool(FL_Array* arr, fl_int64 idx) {
    if (!arr || idx < 0 || idx >= arr->len)
        return (FL_Option_bool){.tag = 0, .value = fl_false};
    fl_bool* ptr = (fl_bool*)((char*)arr->data + idx * arr->element_size);
    return (FL_Option_bool){.tag = 1, .value = *ptr};
}

fl_int fl_array_len_int(FL_Array* arr) {
    if (!arr) return 0;
    return (fl_int)arr->len;
}

FL_Array* fl_array_concat(FL_Array* a, FL_Array* b) {
    if (!a && !b) return fl_array_new(0, sizeof(void*), NULL);
    if (!a) { fl_array_retain(b); return b; }
    if (!b) { fl_array_retain(a); return a; }
    /* Empty arrays (from [] literals) have element_size 0; treat as compatible */
    if (a->len == 0) { fl_array_retain(b); return b; }
    if (b->len == 0) { fl_array_retain(a); return a; }
    if (a->element_size != b->element_size)
        fl_panic("fl_array_concat: element size mismatch");
    fl_int64 total = a->len + b->len;
    void* data = malloc((size_t)(total * a->element_size));
    if (!data) fl_panic("fl_array_concat: out of memory");
    memcpy(data, a->data, (size_t)(a->len * a->element_size));
    memcpy((char*)data + a->len * a->element_size,
           b->data, (size_t)(b->len * a->element_size));
    FL_Array* result = fl_array_new(total, a->element_size, data);
    free(data);
    /* Propagate elem_type, handlers, and retain all elements (both a and b contributed) */
    result->elem_type = a->elem_type;
    result->elem_destructor = a->elem_destructor;
    result->elem_retainer = a->elem_retainer;
    if (result->elem_type != FL_ELEM_NONE && result->data) {
        for (fl_int64 i = 0; i < result->len; i++) {
            void* slot = (char*)result->data + (size_t)i * (size_t)result->element_size;
            _fl_elem_retain(result->elem_type, slot, result->elem_retainer);
        }
    }
    return result;
}

void fl_array_set_elem_type(FL_Array* a, fl_int t) {
    if (a) a->elem_type = (FL_ElemType)t;
}

void fl_map_set_val_type(FL_Map* m, fl_int t) {
    if (m) m->val_type = (FL_ElemType)t;
}

void fl_map_set_val_destructor(FL_Map* m, void (*destructor)(void*),
                               void (*retainer)(void*), fl_int64 elem_size) {
    if (!m) return;
    m->val_destructor = destructor;
    m->val_retainer = retainer;
    m->val_elem_size = elem_size;
}

/* ========================================================================
 * String extensions: repeat, URL encode/decode
 * ======================================================================== */

FL_String* fl_string_repeat(FL_String* s, fl_int n) {
    if (!s || n <= 0) return fl_string_from_cstr("");
    fl_int64 total = s->len * (fl_int64)n;
    FL_String* result = (FL_String*)malloc(sizeof(FL_String) + (size_t)total + 1);
    if (!result) fl_panic("fl_string_repeat: out of memory");
    result->refcount = 1;
    result->len = total;
    for (fl_int i = 0; i < n; i++) {
        memcpy(result->data + (fl_int64)i * s->len, s->data, (size_t)s->len);
    }
    result->data[total] = '\0';
    return result;
}

static int _fl_hex_digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    return -1;
}

FL_String* fl_string_url_decode(FL_String* s) {
    if (!s) return fl_string_from_cstr("");
    char* buf = (char*)malloc((size_t)s->len + 1);
    if (!buf) fl_panic("fl_string_url_decode: out of memory");
    fl_int64 j = 0;
    for (fl_int64 i = 0; i < s->len; i++) {
        if (s->data[i] == '%' && i + 2 < s->len) {
            int hi = _fl_hex_digit(s->data[i + 1]);
            int lo = _fl_hex_digit(s->data[i + 2]);
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
    FL_String* result = fl_string_new(buf, j);
    free(buf);
    return result;
}

FL_String* fl_string_url_encode(FL_String* s) {
    if (!s) return fl_string_from_cstr("");
    /* Worst case: every byte becomes %XX = 3x expansion */
    char* buf = (char*)malloc((size_t)s->len * 3 + 1);
    if (!buf) fl_panic("fl_string_url_encode: out of memory");
    fl_int64 j = 0;
    for (fl_int64 i = 0; i < s->len; i++) {
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
    FL_String* result = fl_string_new(buf, j);
    free(buf);
    return result;
}

/* FFI helpers: string <-> raw pointer */
void* fl_string_to_cptr(FL_String* s) {
    if (!s) fl_panic("fl_string_to_cptr: NULL string");
    return (void*)s->data;
}

FL_String* fl_string_from_cptr(void* p, fl_int len) {
    if (!p) fl_panic("fl_string_from_cptr: NULL pointer");
    return fl_string_new((const char*)p, (fl_int64)len);
}

/* ========================================================================
 * Map string-key convenience wrappers
 * ======================================================================== */

FL_Map* fl_map_set_str(FL_Map* m, FL_String* key, void* val) {
    if (!key) fl_panic("fl_map_set_str: NULL key");
    return fl_map_set(m, key->data, key->len, val);
}

FL_Option_ptr fl_map_get_str(FL_Map* m, FL_String* key) {
    if (!key) return (FL_Option_ptr){.tag = 0, .value = NULL};
    return fl_map_get(m, key->data, key->len);
}

fl_bool fl_map_has_str(FL_Map* m, FL_String* key) {
    if (!key) return fl_false;
    return fl_map_has(m, key->data, key->len);
}

FL_Map* fl_map_remove_str(FL_Map* m, FL_String* key) {
    if (!m || !key) { fl_map_retain(m); return m; }
    /* Find and unoccupy the entry */
    uint64_t hash = 14695981039346656037ULL;
    for (fl_int64 i = 0; i < key->len; i++) {
        hash ^= (unsigned char)key->data[i];
        hash *= 1099511628211ULL;
    }
    fl_int64 idx = (fl_int64)(hash % (uint64_t)m->capacity);
    for (fl_int64 step = 0; step < m->capacity; step++) {
        FL_MapEntry* e = &m->entries[idx];
        if (!e->occupied) break;
        if (e->key_len == key->len && memcmp(e->key, key->data, (size_t)key->len) == 0) {
            if (m->val_destructor && e->val) {
                m->val_destructor(e->val);
                free(e->val);
            } else if (m->val_type != FL_ELEM_NONE) {
                _fl_elem_release(m->val_type, &e->val, NULL);
            }
            e->occupied = 0;
            m->count--;
            break;
        }
        idx = (idx + 1) % m->capacity;
    }
    /* Bump refcount: caller gets a new reference to the same map.
     * This matches fl_map_set's convention of returning a value the
     * caller "owns", allowing scope-exit cleanup to release it
     * without double-freeing an aliased pointer. */
    fl_map_retain(m);
    return m;
}

FL_Array* fl_map_keys(FL_Map* m) {
    if (!m) return fl_array_new(0, sizeof(FL_String*), NULL);
    FL_String** keys = (FL_String**)malloc((size_t)m->count * sizeof(FL_String*));
    if (!keys) fl_panic("fl_map_keys: out of memory");
    fl_int64 j = 0;
    for (fl_int64 i = 0; i < m->capacity && j < m->count; i++) {
        FL_MapEntry* e = &m->entries[i];
        if (e->occupied) {
            keys[j++] = fl_string_new((const char*)e->key, e->key_len);
        }
    }
    FL_Array* arr = fl_array_new(j, sizeof(FL_String*), keys);
    free(keys);
    /* Keys are newly created FL_String* objects owned by this array */
    arr->elem_type = FL_ELEM_STRING;
    return arr;
}

FL_Array* fl_map_values(FL_Map* m) {
    if (!m) return fl_array_new(0, sizeof(void*), NULL);
    void** vals = (void**)malloc((size_t)m->count * sizeof(void*));
    if (!vals) fl_panic("fl_map_values: out of memory");
    fl_int64 j = 0;
    for (fl_int64 i = 0; i < m->capacity && j < m->count; i++) {
        FL_MapEntry* e = &m->entries[i];
        if (e->occupied) {
            vals[j++] = e->val;
        }
    }
    FL_Array* arr = fl_array_new(j, sizeof(void*), vals);
    free(vals);
    /* Values are shared with the map; set elem_type and retain all */
    arr->elem_type = m->val_type;
    if (arr->elem_type != FL_ELEM_NONE && arr->data) {
        for (fl_int64 i = 0; i < arr->len; i++) {
            void* slot = (char*)arr->data + (size_t)i * sizeof(void*);
            _fl_elem_retain(arr->elem_type, slot, NULL);
        }
    }
    return arr;
}

/* ========================================================================
 * FFI Memory Support (stdlib/mem)
 * ======================================================================== */

void* fl_mem_alloc(fl_int64 size) {
    return malloc((size_t)size);
}

void* fl_mem_realloc(void* p, fl_int64 size) {
    return realloc(p, (size_t)size);
}

void fl_mem_free(void* p) {
    free(p);
}

fl_byte fl_mem_read_byte(void* p, fl_int64 offset) {
    return ((uint8_t*)p)[offset];
}

void fl_mem_write_byte(void* p, fl_int64 offset, fl_byte val) {
    ((uint8_t*)p)[offset] = val;
}

fl_int fl_mem_read_int(void* p, fl_int64 offset) {
    fl_int v;
    memcpy(&v, (char*)p + offset, sizeof(fl_int));
    return v;
}

fl_int64 fl_mem_read_int64(void* p, fl_int64 offset) {
    fl_int64 v;
    memcpy(&v, (char*)p + offset, sizeof(fl_int64));
    return v;
}

void fl_mem_write_int64(void* p, fl_int64 offset, fl_int64 val) {
    memcpy((char*)p + offset, &val, sizeof(fl_int64));
}

void* fl_mem_read_ptr(void* p, fl_int64 offset) {
    void* v;
    memcpy(&v, (char*)p + offset, sizeof(void*));
    return v;
}

void fl_mem_write_ptr(void* p, fl_int64 offset, void* val) {
    memcpy((char*)p + offset, &val, sizeof(void*));
}

void fl_mem_copy(void* dst, void* src, fl_int64 len) {
    memcpy(dst, src, (size_t)len);
}

void fl_mem_copy_str(void* dst, fl_int64 offset, FL_String* s) {
    if (!s) return;
    memcpy((char*)dst + offset, s->data, (size_t)s->len);
}

FL_String* fl_mem_to_string(void* p, fl_int64 len) {
    if (!p || len <= 0) return fl_string_from_cstr("");
    return fl_string_new((const char*)p, len);
}

fl_bool fl_ptr_is_null(void* p) {
    return p == NULL ? fl_true : fl_false;
}

void* fl_ptr_null(void) {
    return NULL;
}

FL_Option_ptr fl_ptr_to_option(void* p) {
    if (!p) return FL_NONE_PTR;
    return FL_SOME_PTR(p);
}
