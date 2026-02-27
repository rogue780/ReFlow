/*
 * Flow Runtime Library
 * runtime/flow_runtime.h — Runtime type and function declarations.
 */
#ifndef FLOW_RUNTIME_H
#define FLOW_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <stdatomic.h>
#include <pthread.h>
#include <math.h>

/* Boolean constants for use in generated code */
#define fl_true  ((fl_bool)1)
#define fl_false ((fl_bool)0)

/* ========================================================================
 * Value Type Aliases (RT-1-1-1)
 * ======================================================================== */

typedef int16_t  fl_int16;
typedef int32_t  fl_int;
typedef int32_t  fl_int32;
typedef int64_t  fl_int64;
typedef uint8_t  fl_byte;
typedef uint16_t fl_uint16;
typedef uint32_t fl_uint;
typedef uint32_t fl_uint32;
typedef uint64_t fl_uint64;
typedef float    fl_float32;
typedef double   fl_float;
typedef double   fl_float64;
typedef bool     fl_bool;
typedef uint32_t fl_char; /* Unicode scalar value */

/* ========================================================================
 * Panic Functions (RT-1-1-3)
 * ======================================================================== */

void fl_panic(const char* msg);
void fl_panic_overflow(void);
void fl_panic_divzero(void);
void fl_panic_oob(void);

/* ========================================================================
 * Checked Arithmetic Macros (RT-1-1-2)
 * ======================================================================== */

#define FL_CHECKED_ADD(a, b, result) \
    do { if (__builtin_add_overflow((a), (b), (result))) fl_panic_overflow(); } while(0)

#define FL_CHECKED_SUB(a, b, result) \
    do { if (__builtin_sub_overflow((a), (b), (result))) fl_panic_overflow(); } while(0)

#define FL_CHECKED_MUL(a, b, result) \
    do { if (__builtin_mul_overflow((a), (b), (result))) fl_panic_overflow(); } while(0)

#define FL_CHECKED_DIV(a, b, result) \
    do { if ((b) == 0) fl_panic_divzero(); *(result) = (a) / (b); } while(0)

#define FL_CHECKED_MOD(a, b, result) \
    do { if ((b) == 0) fl_panic_divzero(); *(result) = (a) % (b); } while(0)

#define FL_CHECKED_FLOOR_DIV(a, b, result) \
    do { if ((b) == 0) fl_panic_divzero(); \
         *(result) = (a) / (b) - ((a) % (b) != 0 && (((a) ^ (b)) < 0)); \
    } while(0)

#define FL_CHECKED_FMOD(a, b, result) \
    do { if ((b) == 0.0) fl_panic_divzero(); *(result) = fmod((a), (b)); } while(0)

/* ========================================================================
 * Option Types (RT-1-3-1)
 *
 * Tag values: 0 = none, 1 = some.
 * ======================================================================== */

#define FL_OPTION_TYPE(T, name) \
    typedef struct { fl_byte tag; T value; } name;

FL_OPTION_TYPE(fl_int,     FL_Option_int)
FL_OPTION_TYPE(fl_int16,   FL_Option_int16)
FL_OPTION_TYPE(fl_int32,   FL_Option_int32)
FL_OPTION_TYPE(fl_int64,   FL_Option_int64)
FL_OPTION_TYPE(fl_uint,    FL_Option_uint)
FL_OPTION_TYPE(fl_uint16,  FL_Option_uint16)
FL_OPTION_TYPE(fl_uint32,  FL_Option_uint32)
FL_OPTION_TYPE(fl_uint64,  FL_Option_uint64)
FL_OPTION_TYPE(fl_float,   FL_Option_float)
FL_OPTION_TYPE(fl_float32, FL_Option_float32)
FL_OPTION_TYPE(fl_float64, FL_Option_float64)
FL_OPTION_TYPE(fl_bool,    FL_Option_bool)
FL_OPTION_TYPE(fl_byte,    FL_Option_byte)
FL_OPTION_TYPE(fl_char,    FL_Option_char)

/* Heap option — used for FL_String*, FL_Array*, and all pointer types */
typedef struct { fl_byte tag; void* value; } FL_Option_ptr;

/* Option constructors */
#define FL_NONE         {.tag = 0}
#define FL_SOME(v)      {.tag = 1, .value = (v)}
#define FL_NONE_PTR     ((FL_Option_ptr){.tag = 0, .value = NULL})
#define FL_SOME_PTR(v)  ((FL_Option_ptr){.tag = 1, .value = (void*)(v)})

/* Option helpers (RT-1-3-3) */
#define fl_option_unwrap_or(opt, default) \
    ((opt).tag == 1 ? (opt).value : (default))

/* ========================================================================
 * Value-type boxing/unboxing for generic containers (Gap-2)
 *
 * Maps and other generic containers store void*.  For value types (int,
 * float, bool, ...) we need to round-trip through void* without heap
 * allocation.  Since sizeof(void*) >= sizeof(double) on our 64-bit
 * target, we use memcpy-based type punning (well-defined in C99+).
 * ======================================================================== */

static inline void* fl_box_int(fl_int v) {
    void* p = NULL; memcpy(&p, &v, sizeof(v)); return p;
}
static inline fl_int fl_unbox_int(void* p) {
    fl_int v = 0; memcpy(&v, &p, sizeof(v)); return v;
}

static inline void* fl_box_int64(fl_int64 v) {
    void* p = NULL; memcpy(&p, &v, sizeof(v)); return p;
}
static inline fl_int64 fl_unbox_int64(void* p) {
    fl_int64 v = 0; memcpy(&v, &p, sizeof(v)); return v;
}

static inline void* fl_box_float(fl_float v) {
    void* p = NULL; memcpy(&p, &v, sizeof(v)); return p;
}
static inline fl_float fl_unbox_float(void* p) {
    fl_float v = 0; memcpy(&v, &p, sizeof(v)); return v;
}

static inline void* fl_box_bool(fl_bool v) {
    return (void*)(uintptr_t)v;
}
static inline fl_bool fl_unbox_bool(void* p) {
    return (fl_bool)(uintptr_t)p;
}

static inline void* fl_box_byte(fl_byte v) {
    return (void*)(uintptr_t)v;
}
static inline fl_byte fl_unbox_byte(void* p) {
    return (fl_byte)(uintptr_t)p;
}

/* Repack FL_Option_ptr → FL_Option_<valuetype> */
static inline FL_Option_int fl_opt_unbox_int(FL_Option_ptr o) {
    FL_Option_int r = {.tag = o.tag};
    if (o.tag) r.value = fl_unbox_int(o.value);
    return r;
}
static inline FL_Option_int64 fl_opt_unbox_int64(FL_Option_ptr o) {
    FL_Option_int64 r = {.tag = o.tag};
    if (o.tag) r.value = fl_unbox_int64(o.value);
    return r;
}
static inline FL_Option_float fl_opt_unbox_float(FL_Option_ptr o) {
    FL_Option_float r = {.tag = o.tag};
    if (o.tag) r.value = fl_unbox_float(o.value);
    return r;
}
static inline FL_Option_bool fl_opt_unbox_bool(FL_Option_ptr o) {
    FL_Option_bool r = {.tag = o.tag};
    if (o.tag) r.value = fl_unbox_bool(o.value);
    return r;
}
static inline FL_Option_byte fl_opt_unbox_byte(FL_Option_ptr o) {
    FL_Option_byte r = {.tag = o.tag};
    if (o.tag) r.value = fl_unbox_byte(o.value);
    return r;
}

/* Generic option repack: FL_Option_ptr → FL_Option_<ValueType>
 * Used when fl_array_get_safe returns FL_Option_ptr but the element type
 * is a value type (struct, sum type, etc.) whose void* value is a pointer
 * to the element data that needs to be dereferenced. */
#define FL_OPT_DEREF_AS(opt_ptr, ValType, OptType) \
    ((opt_ptr).tag \
     ? (OptType){.tag = 1, .value = *(ValType*)(opt_ptr).value} \
     : (OptType){.tag = 0})

/* ========================================================================
 * String Type (RT-1-2-1)
 * ======================================================================== */

typedef struct FL_String {
    _Atomic fl_int64 refcount;
    fl_int64 len;    /* byte length, not char count; excludes null terminator */
    char     data[]; /* flexible array member, UTF-8, always null-terminated */
} FL_String;

FL_String* fl_string_new(const char* data, fl_int64 len);
FL_String* fl_string_from_cstr(const char* cstr);
void       fl_string_retain(FL_String* s);
void       fl_string_release(FL_String* s);
FL_String* fl_string_copy(FL_String* s);
FL_String* fl_string_concat(FL_String* a, FL_String* b);
fl_bool    fl_string_eq(FL_String* a, FL_String* b);
fl_int64   fl_string_len(FL_String* s);
fl_int     fl_string_cmp(FL_String* a, FL_String* b);

/* Numeric conversions (RT-1-2-3) */
fl_bool    fl_string_to_int(FL_String* s, fl_int* out);
fl_bool    fl_string_to_int64(FL_String* s, fl_int64* out);
fl_bool    fl_string_to_float(FL_String* s, fl_float* out);
FL_String* fl_int_to_string(fl_int v);
FL_String* fl_int64_to_string(fl_int64 v);
FL_String* fl_float_to_string(fl_float v);
FL_String* fl_bool_to_string(fl_bool v);
FL_String* fl_byte_to_string(fl_byte v);

/* ========================================================================
 * Built-in Interface Method Helpers (SG-3-5-2)
 *
 * These support the synthetic Comparable / Equatable / Showable methods
 * on built-in types that the compiler emits for monomorphized generic code.
 * ======================================================================== */

/* _fl_compare: Comparable.compare for numeric/char/byte types.
 * Returns negative if a < b, zero if a == b, positive if a > b. */
#define _fl_compare(a, b) ((a) < (b) ? -1 : ((a) > (b) ? 1 : 0))

/* _fl_identity_string: Showable.to_string for string (identity).
 * Retains the string (caller's responsibility to release) and returns it.
 * NOTE: The self-hosted compiler could detect this as a no-op and elide
 * the call. For the reference compiler the overhead is negligible. */
static inline FL_String* _fl_identity_string(FL_String* s) {
    fl_string_retain(s);
    return s;
}

/* ========================================================================
 * Result Types (RT-1-3-2)
 *
 * Tag values: 0 = ok, 1 = err.
 * The emitter instantiates FL_RESULT_TYPE once per unique (ok, err) pair.
 * ======================================================================== */

#define FL_RESULT_TYPE(T_ok, T_err, name) \
    typedef struct {                       \
        fl_byte tag;                       \
        union {                            \
            T_ok  ok_val;                  \
            T_err err_val;                 \
        } payload;                         \
    } name;

/* Baseline instantiations */
FL_RESULT_TYPE(fl_int,  FL_String*, FL_Result_int_String)
FL_RESULT_TYPE(void*,   void*,      FL_Result_ptr_ptr)

/* Result helpers (RT-1-3-3) */
#define fl_result_is_ok(res)  ((res).tag == 0)
#define fl_result_is_err(res) ((res).tag == 1)
#define FL_OK(v)  {.tag = 0, .payload.ok_val  = (v)}
#define FL_ERR(v) {.tag = 1, .payload.err_val = (v)}

/* ========================================================================
 * Array (RT-1-4-1)
 * ======================================================================== */

typedef struct FL_Array {
    _Atomic fl_int64  refcount;
    fl_int64  len;
    void*     data;
    fl_int64  element_size;
} FL_Array;

FL_Array*     fl_array_new(fl_int64 len, fl_int64 element_size, void* initial_data);
void          fl_array_retain(FL_Array* arr);
void          fl_array_release(FL_Array* arr);
FL_Array*     fl_array_copy(FL_Array* arr);
void*         fl_array_get_ptr(FL_Array* arr, fl_int64 idx);
FL_Option_ptr fl_array_get_safe(FL_Array* arr, fl_int64 idx);
fl_int64      fl_array_len(FL_Array* arr);
FL_Array*     fl_array_push(FL_Array* arr, void* element);
FL_Array*     fl_array_push_sized(FL_Array* arr, void* element, fl_int64 elem_size);
FL_Array*     fl_array_push_ptr(FL_Array* arr, void* element);
FL_Array*     fl_array_push_int(FL_Array* arr, fl_int val);
FL_Array*     fl_array_push_int64(FL_Array* arr, fl_int64 val);
FL_Array*     fl_array_push_float(FL_Array* arr, fl_float val);
FL_Array*     fl_array_push_bool(FL_Array* arr, fl_bool val);
FL_Array*     fl_array_push_byte(FL_Array* arr, fl_byte val);

/* Array stdlib extensions */
FL_Option_int   fl_array_get_int(FL_Array* arr, fl_int64 idx);
FL_Option_int64 fl_array_get_int64(FL_Array* arr, fl_int64 idx);
FL_Option_float fl_array_get_float(FL_Array* arr, fl_int64 idx);
FL_Option_bool  fl_array_get_bool(FL_Array* arr, fl_int64 idx);
fl_int          fl_array_len_int(FL_Array* arr);
FL_Array*       fl_array_concat(FL_Array* a, FL_Array* b);

/* ========================================================================
 * Stream (RT-1-5-1)
 * ======================================================================== */

typedef struct FL_Stream FL_Stream;

typedef FL_Option_ptr (*FL_StreamNext)(FL_Stream* self);
typedef void          (*FL_StreamFree)(FL_Stream* self);

struct FL_Stream {
    FL_StreamNext next_fn;
    FL_StreamFree free_fn;
    void*         state;
    _Atomic fl_int refcount;
};

FL_Stream*    fl_stream_new(FL_StreamNext next_fn, FL_StreamFree free_fn, void* state);
void          fl_stream_retain(FL_Stream* s);
void          fl_stream_release(FL_Stream* s);
FL_Option_ptr fl_stream_next(FL_Stream* s);

/* ========================================================================
 * Channel — bounded, thread-safe FIFO queue
 * ======================================================================== */

typedef struct FL_Channel FL_Channel;

FL_Channel*   fl_channel_new(fl_int capacity);
fl_bool       fl_channel_send(FL_Channel* ch, void* val);
FL_Option_ptr fl_channel_recv(FL_Channel* ch);
void          fl_channel_close(FL_Channel* ch);
fl_int        fl_channel_len(FL_Channel* ch);
fl_bool       fl_channel_is_closed(FL_Channel* ch);
void          fl_channel_set_exception(FL_Channel* ch, void* exception, fl_int tag);
void          fl_channel_retain(FL_Channel* ch);
void          fl_channel_release(FL_Channel* ch);

/* Non-blocking channel operations (SL-5-5) */
fl_bool       fl_channel_try_send(FL_Channel* ch, void* val);
FL_Option_ptr fl_channel_try_recv(FL_Channel* ch);

/* ========================================================================
 * Coroutines
 * ======================================================================== */

typedef struct FL_Coroutine {
    FL_Stream*  stream;          /* non-threaded: set; threaded: NULL */
    FL_Channel* channel;         /* non-threaded: NULL; threaded: set (output) */
    FL_Channel* input_channel;   /* receivable: set; otherwise: NULL */
    pthread_t   thread;          /* only valid when channel != NULL */
    fl_bool     done;
    _Atomic fl_bool cancelled;   /* set by stop/kill to signal producer */
} FL_Coroutine;

FL_Coroutine* fl_coroutine_new(FL_Stream* stream);
FL_Coroutine* fl_coroutine_new_threaded(FL_Stream* stream, fl_int capacity);
FL_Option_ptr fl_coroutine_next(FL_Coroutine* c);
FL_Option_ptr fl_coroutine_try_next(FL_Coroutine* c);
fl_bool       fl_coroutine_done(FL_Coroutine* c);
void          fl_coroutine_release(FL_Coroutine* c);
void          fl_coroutine_send(FL_Coroutine* c, void* val);
fl_bool       fl_coroutine_try_send(FL_Coroutine* c, void* val);
void          fl_coroutine_set_input(FL_Coroutine* c, FL_Channel* input);
FL_Channel*   fl_coroutine_get_channel(FL_Coroutine* c);
void          fl_coroutine_stop(FL_Coroutine* c);
void          fl_coroutine_kill(FL_Coroutine* c);
FL_Stream*    fl_stream_from_channel(FL_Channel* ch);
FL_Stream*    fl_stream_from_channel_nonblocking(FL_Channel* ch);

/* --- Worker pools --- */
typedef struct FL_Pool FL_Pool;

FL_Pool*      fl_pool_new(void* (*fn)(void*), fl_int max_workers,
                          FL_Channel* input, fl_int output_capacity);
FL_Coroutine* fl_pool_as_coroutine(FL_Pool* pool);

/* ========================================================================
 * Closures
 * ======================================================================== */
typedef struct FL_Closure {
    void* fn;
    void* env;
} FL_Closure;

/* ========================================================================
 * Stream Helpers
 * ======================================================================== */

FL_Stream* fl_stream_take(FL_Stream* src, fl_int n);
FL_Stream* fl_stream_skip(FL_Stream* src, fl_int n);
FL_Stream* fl_stream_map(FL_Stream* src, FL_Closure* fn);
FL_Stream* fl_stream_filter(FL_Stream* src, FL_Closure* fn);
void*      fl_stream_reduce(FL_Stream* src, void* init, FL_Closure* fn);

/* Stream Construction (SL-5-2) */
FL_Stream* fl_stream_range(fl_int start, fl_int end);
FL_Stream* fl_stream_range_step(fl_int start, fl_int end, fl_int step);
FL_Stream* fl_stream_from_array(FL_Array* arr);
FL_Stream* fl_stream_repeat(void* val, fl_int n);
FL_Stream* fl_stream_empty(void);

/* Stream Transformation (SL-5-3) */

/* Pair struct for enumerate and zip */
typedef struct {
    void* first;
    void* second;
} FL_Pair;

FL_Stream* fl_stream_enumerate(FL_Stream* source);
FL_Stream* fl_stream_zip(FL_Stream* a, FL_Stream* b);
FL_Stream* fl_stream_chain(FL_Stream* a, FL_Stream* b);
FL_Stream* fl_stream_flat_map(FL_Stream* source, FL_Closure* f);

/* Stream Consumption (SL-5-4) */
FL_Array*     fl_stream_to_array(FL_Stream* src, fl_int64 element_size);
void          fl_stream_foreach(FL_Stream* src, FL_Closure* fn);
fl_int        fl_stream_count(FL_Stream* src);
fl_bool       fl_stream_any(FL_Stream* src, FL_Closure* fn);
fl_bool       fl_stream_all(FL_Stream* src, FL_Closure* fn);
FL_Option_ptr fl_stream_find(FL_Stream* src, FL_Closure* fn);
fl_int        fl_stream_sum_int(FL_Stream* src);

/* ========================================================================
 * Map — open-addressing hash table (RT-1-6-1)
 * BOOTSTRAP: replace with production hash map
 * ======================================================================== */

typedef struct FL_Map FL_Map;

FL_Map*       fl_map_new(void);
FL_Map*       fl_map_set(FL_Map* m, void* key, fl_int64 key_len, void* val);
FL_Option_ptr fl_map_get(FL_Map* m, void* key, fl_int64 key_len);
fl_bool       fl_map_has(FL_Map* m, void* key, fl_int64 key_len);
fl_int64      fl_map_len(FL_Map* m);
void          fl_map_retain(FL_Map* m);
void          fl_map_release(FL_Map* m);

/* Map string-key convenience wrappers (stdlib/map) */
FL_Map*       fl_map_set_str(FL_Map* m, FL_String* key, void* val);
FL_Option_ptr fl_map_get_str(FL_Map* m, FL_String* key);
fl_bool       fl_map_has_str(FL_Map* m, FL_String* key);
FL_Map*       fl_map_remove_str(FL_Map* m, FL_String* key);
FL_Array*     fl_map_keys(FL_Map* m);
FL_Array*     fl_map_values(FL_Map* m);

/* ========================================================================
 * Set (RT-1-6-2)
 * ======================================================================== */

typedef struct FL_Set FL_Set;

FL_Set*  fl_set_new(void);
fl_bool  fl_set_add(FL_Set* s, void* key, fl_int64 key_len);
fl_bool  fl_set_has(FL_Set* s, void* key, fl_int64 key_len);
fl_bool  fl_set_remove(FL_Set* s, void* key, fl_int64 key_len);
fl_int64 fl_set_len(FL_Set* s);
void     fl_set_retain(FL_Set* s);
void     fl_set_release(FL_Set* s);

/* ========================================================================
 * Buffer (RT-1-7-1)
 * ======================================================================== */

typedef struct FL_Buffer {
    _Atomic fl_int64 refcount;
    fl_int64 len;
    fl_int64 capacity;
    fl_int64 element_size;
    void*    data;
} FL_Buffer;

FL_Buffer*    fl_buffer_new(fl_int64 element_size);
FL_Buffer*    fl_buffer_with_capacity(fl_int64 cap, fl_int64 element_size);
FL_Buffer*    fl_buffer_collect(FL_Stream* s, fl_int64 element_size);
void          fl_buffer_push(FL_Buffer* buf, void* element);
FL_Option_ptr fl_buffer_get(FL_Buffer* buf, fl_int64 idx);
FL_Stream*    fl_buffer_drain(FL_Buffer* buf);
fl_int64      fl_buffer_len(FL_Buffer* buf);
void          fl_buffer_sort_by(FL_Buffer* buf, int (*cmp)(const void*, const void*));
void          fl_buffer_reverse(FL_Buffer* buf);
void          fl_buffer_retain(FL_Buffer* buf);
void          fl_buffer_release(FL_Buffer* buf);

/* Buffer extensions (SL-4-3) */
FL_Array*     fl_buffer_to_array(FL_Buffer* buf);
void          fl_buffer_clear(FL_Buffer* buf);
FL_Option_ptr fl_buffer_pop(FL_Buffer* buf);
FL_Option_ptr fl_buffer_last(FL_Buffer* buf);
void          fl_buffer_set(FL_Buffer* buf, fl_int64 idx, void* element);
void          fl_buffer_insert(FL_Buffer* buf, fl_int64 idx, void* element);
FL_Option_ptr fl_buffer_remove(FL_Buffer* buf, fl_int64 idx);
fl_bool       fl_buffer_contains(FL_Buffer* buf, void* element, fl_int64 element_size);
FL_Buffer*    fl_buffer_slice(FL_Buffer* buf, fl_int64 start, fl_int64 end);

/* ========================================================================
 * Sort (stdlib/sort)
 * ======================================================================== */

FL_Array* fl_sort_array_by(FL_Array* arr, FL_Closure* cmp);
FL_Array* fl_array_reverse(FL_Array* arr);

/* ========================================================================
 * Bytes (stdlib/bytes)
 * ======================================================================== */

FL_Array* fl_bytes_slice(FL_Array* arr, fl_int64 start, fl_int64 end);
FL_Array* fl_bytes_concat(FL_Array* a, FL_Array* b);
FL_Option_ptr fl_bytes_index_of(FL_Array* haystack, fl_byte needle);
fl_int64  fl_bytes_len(FL_Array* arr);

/* ========================================================================
 * I/O Primitives (RT-1-8-1)
 * ======================================================================== */

void          fl_print(FL_String* s);
void          fl_println(FL_String* s);
void          fl_eprint(FL_String* s);
void          fl_eprintln(FL_String* s);
FL_Stream*    fl_stdin_stream(void);
FL_Option_ptr fl_read_line(void);
FL_Option_ptr fl_read_byte(void);
FL_Option_ptr fl_read_stdin(void);

/* ========================================================================
 * System Functions (stdlib/sys)
 * ======================================================================== */

void          fl_sys_exit(fl_int code);
FL_Array*     fl_sys_args(void);
FL_Option_ptr fl_env_get(FL_String* name);
fl_int64      fl_clock_ms(void);

/* ========================================================================
 * String Operations (stdlib/string — RB-1-1)
 * ======================================================================== */

FL_Option_char fl_string_char_at(FL_String* s, fl_int64 idx);
FL_String*     fl_string_substring(FL_String* s, fl_int64 start, fl_int64 end);
FL_Option_int  fl_string_index_of(FL_String* haystack, FL_String* needle);
fl_bool       fl_string_contains(FL_String* s, FL_String* needle);
fl_bool       fl_string_starts_with(FL_String* s, FL_String* prefix);
fl_bool       fl_string_ends_with(FL_String* s, FL_String* suffix);
FL_Array*     fl_string_split(FL_String* s, FL_String* sep);
FL_String*    fl_string_trim(FL_String* s);
FL_String*    fl_string_trim_left(FL_String* s);
FL_String*    fl_string_trim_right(FL_String* s);
FL_String*    fl_string_replace(FL_String* s, FL_String* old_s, FL_String* new_s);
FL_String*    fl_string_join(FL_Array* parts, FL_String* sep);
FL_String*    fl_string_to_lower(FL_String* s);
FL_String*    fl_string_to_upper(FL_String* s);
FL_Array*     fl_string_to_bytes(FL_String* s);
FL_String*    fl_string_from_bytes(FL_Array* data);
FL_String*    fl_string_repeat(FL_String* s, fl_int n);
FL_String*    fl_string_url_decode(FL_String* s);
FL_String*    fl_string_url_encode(FL_String* s);

/* FFI helpers: string <-> raw pointer conversion */
void*         fl_string_to_cptr(FL_String* s);
FL_String*    fl_string_from_cptr(void* p, fl_int len);

/* ========================================================================
 * String Builder (stdlib/string_builder)
 * ======================================================================== */

typedef struct FL_StringBuilder {
    _Atomic fl_int64 refcount;
    char*    data;
    fl_int64 len;
    fl_int64 capacity;
} FL_StringBuilder;

FL_StringBuilder* fl_sb_new(void);
FL_StringBuilder* fl_sb_with_capacity(fl_int64 cap);
void              fl_sb_append(FL_StringBuilder* sb, FL_String* s);
void              fl_sb_append_cstr(FL_StringBuilder* sb, const char* s);
void              fl_sb_append_char(FL_StringBuilder* sb, fl_char c);
void              fl_sb_append_int(FL_StringBuilder* sb, fl_int v);
void              fl_sb_append_int64(FL_StringBuilder* sb, fl_int64 v);
void              fl_sb_append_float(FL_StringBuilder* sb, fl_float v);
FL_String*        fl_sb_build(FL_StringBuilder* sb);
fl_int64          fl_sb_len(FL_StringBuilder* sb);
void              fl_sb_clear(FL_StringBuilder* sb);
void              fl_sb_retain(FL_StringBuilder* sb);
void              fl_sb_release(FL_StringBuilder* sb);

/* ========================================================================
 * Character Utilities (stdlib/char — RB-1-2)
 * ======================================================================== */

/* is_digit, is_alpha, is_alphanumeric, is_whitespace, to_code, from_code
 * are now pure Flow in stdlib/char.flow — no runtime needed. */
FL_String* fl_char_to_string(fl_char c);

/* ========================================================================
 * File I/O (stdlib/io — RB-1-3)
 * ======================================================================== */

FL_Option_ptr fl_read_file(FL_String* path);
fl_bool       fl_write_file(FL_String* path, FL_String* contents);
FL_Option_ptr fl_read_file_bytes(FL_String* path);
fl_bool       fl_write_file_bytes(FL_String* path, FL_Array* data);
fl_bool       fl_append_file(FL_String* path, FL_String* contents);

/* ========================================================================
 * Process Execution (stdlib/sys — RB-1-4)
 * ======================================================================== */

fl_int        fl_run_process(FL_String* command, FL_Array* args);
FL_Option_ptr fl_run_process_capture(FL_String* command, FL_Array* args);

/* ========================================================================
 * Temporary File Support (stdlib/io — RB-1-5)
 * ======================================================================== */

FL_String* fl_tmpfile_create(FL_String* suffix, FL_String* contents);
void       fl_tmpfile_remove(FL_String* path);

/* ========================================================================
 * Path Utilities (stdlib/path — RB-1-6)
 * ======================================================================== */

FL_String* fl_path_cwd(void);
FL_String* fl_path_resolve(FL_String* path);
fl_bool    fl_path_exists(FL_String* path);
fl_bool    fl_path_is_dir(FL_String* path);
fl_bool    fl_path_is_file(FL_String* path);
FL_Option_ptr fl_path_list_dir(FL_String* path);

/* Math functions (floor, ceil, round, pow, sqrt, log, fmod) are now
 * direct libm extern bindings in stdlib/math.flow — no runtime needed. */

/* ========================================================================
 * File Handle I/O (stdlib/file)
 * ======================================================================== */

typedef struct FL_File FL_File;

/* Opening */
FL_Option_ptr fl_file_open_read(FL_String* path);
FL_Option_ptr fl_file_open_write(FL_String* path);
FL_Option_ptr fl_file_open_append(FL_String* path);
FL_Option_ptr fl_file_open_read_bytes(FL_String* path);
FL_Option_ptr fl_file_open_write_bytes(FL_String* path);

/* Closing */
void fl_file_close(FL_File* f);

/* Reading */
FL_Option_ptr fl_file_read_bytes(FL_File* f, fl_int n);
FL_Option_ptr fl_file_read_line(FL_File* f);
FL_Option_ptr fl_file_read_all(FL_File* f);
FL_Option_ptr fl_file_read_all_bytes(FL_File* f);

/* Streams */
FL_Stream* fl_file_lines(FL_File* f);
FL_Stream* fl_file_byte_stream(FL_File* f);

/* Writing */
fl_bool fl_file_write_bytes(FL_File* f, FL_Array* data);
fl_bool fl_file_write_string(FL_File* f, FL_String* s);
fl_bool fl_file_flush(FL_File* f);

/* Seeking */
fl_bool fl_file_seek(FL_File* f, fl_int64 offset);
fl_bool fl_file_seek_end(FL_File* f, fl_int64 offset);
fl_int64 fl_file_position(FL_File* f);
fl_int64 fl_file_size(FL_File* f);

/* ========================================================================
 * Exception Handling (setjmp/longjmp)
 * ======================================================================== */

typedef struct FL_ExceptionFrame {
    jmp_buf jmp;
    struct FL_ExceptionFrame* parent;
    void* exception;       /* heap-allocated exception value */
    fl_int exception_tag;  /* integer type tag for catch dispatch */
} FL_ExceptionFrame;

extern _Thread_local FL_ExceptionFrame* _fl_exception_current;

void _fl_exception_push(FL_ExceptionFrame* frame);
void _fl_exception_pop(void);
_Noreturn void _fl_throw(void* exception, fl_int tag);
_Noreturn void _fl_rethrow(void);

/* ========================================================================
 * Parallel Fan-out
 * ======================================================================== */

typedef struct FL_FanoutBranch {
    void* (*fn)(void*);
    void*   arg;
    void*   result;
    void*   exception;
    fl_int  exception_tag;
    fl_bool has_exception;
} FL_FanoutBranch;

void fl_fanout_run(FL_FanoutBranch* branches, fl_int count);

/* ========================================================================
 * Random (stdlib/random)
 * ======================================================================== */

fl_int    fl_random_int_range(fl_int min, fl_int max);
fl_int64  fl_random_int64_range(fl_int64 min, fl_int64 max);
fl_float  fl_random_float_unit(void);
fl_bool   fl_random_bool(void);
FL_Array* fl_random_bytes(fl_int n);
FL_Array* fl_random_shuffle(FL_Array* arr);
FL_Option_ptr fl_random_choice(FL_Array* arr);

/* ========================================================================
 * Time (stdlib/time)
 * ======================================================================== */

typedef struct FL_Instant FL_Instant;
typedef struct FL_DateTime FL_DateTime;

/* Monotonic time */
FL_Instant* fl_time_now(void);
fl_int64    fl_time_elapsed_ms(FL_Instant* since);
fl_int64    fl_time_elapsed_us(FL_Instant* since);
fl_int64    fl_time_diff_ms(FL_Instant* start, FL_Instant* end);
void        fl_instant_release(FL_Instant* inst);

/* Wall clock */
FL_DateTime* fl_time_datetime_now(void);
FL_DateTime* fl_time_datetime_utc(void);
fl_int64     fl_time_unix_timestamp(void);
fl_int64     fl_time_unix_timestamp_ms(void);
void         fl_time_sleep_ms(fl_int ms);
void         fl_datetime_release(FL_DateTime* dt);

/* Formatting */
FL_String* fl_time_format_iso8601(FL_DateTime* dt);
FL_String* fl_time_format_rfc2822(FL_DateTime* dt);
FL_String* fl_time_format_http(FL_DateTime* dt);

/* Component accessors */
fl_int fl_time_year(FL_DateTime* dt);
fl_int fl_time_month(FL_DateTime* dt);
fl_int fl_time_day(FL_DateTime* dt);
fl_int fl_time_hour(FL_DateTime* dt);
fl_int fl_time_minute(FL_DateTime* dt);
fl_int fl_time_second(FL_DateTime* dt);

/* ========================================================================
 * Testing (stdlib/testing)
 * ======================================================================== */

#define FL_TEST_FAILURE_TAG 9999

/* Assertions — assert_true/assert_false are now pure Flow in stdlib/testing.flow */
void fl_test_assert_eq_float(fl_float expected, fl_float actual, fl_float epsilon, FL_String* msg);
void* fl_test_assert_some(FL_Option_ptr opt, FL_String* msg);
void fl_test_assert_none(FL_Option_ptr opt, FL_String* msg);
void fl_test_fail(FL_String* msg);

/* Test runner */
typedef struct {
    FL_String* name;
    fl_int     passed;
    FL_String* failure_msg;
} FL_TestResult;

FL_TestResult fl_test_run(FL_String* name, FL_Closure* test_fn);
fl_int fl_test_run_all(FL_Array* tests);
void fl_test_report(FL_TestResult* result);

/* ========================================================================
 * Net (stdlib/net)
 * ======================================================================== */

typedef struct FL_Socket FL_Socket;

FL_Option_ptr fl_net_listen(FL_String* addr, fl_int port);
FL_Option_ptr fl_net_accept(FL_Socket* listener);
FL_Option_ptr fl_net_connect(FL_String* host, fl_int port);
FL_Option_ptr fl_net_read(FL_Socket* sock, fl_int max_bytes);
fl_bool       fl_net_write(FL_Socket* sock, FL_Array* data);
fl_bool       fl_net_write_string(FL_Socket* sock, FL_String* s);
void          fl_net_close(FL_Socket* sock);
fl_bool       fl_net_set_timeout(FL_Socket* sock, fl_int ms);
FL_Option_ptr fl_net_remote_addr(FL_Socket* sock);
fl_int        fl_net_fd(FL_Socket* conn);
fl_bool       fl_net_write_string_fd(fl_int fd, FL_String* s);

/* ========================================================================
 * FFI Memory Support (stdlib/mem)
 * ======================================================================== */

void*         fl_mem_alloc(fl_int64 size);
void          fl_mem_free(void* p);
fl_byte       fl_mem_read_byte(void* p, fl_int64 offset);
void          fl_mem_write_byte(void* p, fl_int64 offset, fl_byte val);
fl_int        fl_mem_read_int(void* p, fl_int64 offset);
fl_bool       fl_ptr_is_null(void* p);
void*         fl_ptr_null(void);
FL_Option_ptr fl_ptr_to_option(void* p);

/* ========================================================================
 * Runtime Initialization
 * ======================================================================== */

void _fl_runtime_init(int argc, char** argv);

#endif /* FLOW_RUNTIME_H */
