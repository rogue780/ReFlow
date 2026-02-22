/*
 * ReFlow Runtime Library
 * runtime/reflow_runtime.c — Runtime implementations.
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "reflow_runtime.h"
#include <limits.h>
#include <sys/wait.h>
#include <unistd.h>

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
    s->refcount++;
}

void rf_string_release(RF_String* s) {
    if (!s) return;
    s->refcount--;
    if (s->refcount == 0) {
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
    arr->refcount++;
}

void rf_array_release(RF_Array* arr) {
    if (!arr) return;
    arr->refcount--;
    if (arr->refcount <= 0) {
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
    s->refcount++;
}

void rf_stream_release(RF_Stream* s) {
    if (!s) return;
    s->refcount--;
    if (s->refcount <= 0) {
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
 * Coroutines
 * ======================================================================== */

RF_Coroutine* rf_coroutine_new(RF_Stream* stream) {
    RF_Coroutine* c = (RF_Coroutine*)malloc(sizeof(RF_Coroutine));
    if (!c) rf_panic("rf_coroutine_new: out of memory");
    c->stream = stream;
    c->done = rf_false;
    return c;
}

RF_Option_ptr rf_coroutine_next(RF_Coroutine* c) {
    RF_Option_ptr result = rf_stream_next(c->stream);
    if (result.tag == 0) c->done = rf_true;
    return result;
}

rf_bool rf_coroutine_done(RF_Coroutine* c) {
    return c->done;
}

void rf_coroutine_release(RF_Coroutine* c) {
    if (c) {
        rf_stream_release(c->stream);
        free(c);
    }
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
    rf_int64     refcount;
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
    m->refcount++;
}

void rf_map_release(RF_Map* m) {
    if (!m) return;
    m->refcount--;
    if (m->refcount > 0) return;
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
    rf_int64 refcount;
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
    s->refcount++;
}

void rf_set_release(RF_Set* s) {
    if (!s) return;
    s->refcount--;
    if (s->refcount > 0) return;
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
    buf->refcount++;
}

void rf_buffer_release(RF_Buffer* buf) {
    if (!buf) return;
    buf->refcount--;
    if (buf->refcount > 0) return;
    free(buf->data);
    free(buf);
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
    rf_int64 last_slash = -1;
    for (rf_int64 i = path->len - 1; i >= 0; i--) {
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

/* ========================================================================
 * Exception Handling (setjmp/longjmp)
 * ======================================================================== */

RF_ExceptionFrame* _rf_exception_current = NULL;

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

/* ========================================================================
 * Conversion Wrappers (stdlib/conv)
 * ======================================================================== */

RF_Option_ptr rf_string_to_int_opt(RF_String* s) {
    rf_int val;
    if (rf_string_to_int(s, &val)) {
        return (RF_Option_ptr){.tag = 1, .value = (void*)(uintptr_t)val};
    }
    return RF_NONE_PTR;
}

RF_Option_ptr rf_string_to_int64_opt(RF_String* s) {
    rf_int64 val;
    if (rf_string_to_int64(s, &val)) {
        return (RF_Option_ptr){.tag = 1, .value = (void*)(uintptr_t)val};
    }
    return RF_NONE_PTR;
}

RF_Option_ptr rf_string_to_float_opt(RF_String* s) {
    rf_float val;
    if (rf_string_to_float(s, &val)) {
        void* p;
        memcpy(&p, &val, sizeof(val));
        return (RF_Option_ptr){.tag = 1, .value = p};
    }
    return RF_NONE_PTR;
}
