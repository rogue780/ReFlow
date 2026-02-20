/*
 * ReFlow Runtime Library
 * runtime/reflow_runtime.c — Runtime implementations.
 */
#include "reflow_runtime.h"

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
