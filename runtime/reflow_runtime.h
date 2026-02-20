/*
 * ReFlow Runtime Library
 * runtime/reflow_runtime.h — Runtime type and function declarations.
 */
#ifndef REFLOW_RUNTIME_H
#define REFLOW_RUNTIME_H

#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

/* Boolean constants for use in generated code */
#define rf_true  ((rf_bool)1)
#define rf_false ((rf_bool)0)

/* ========================================================================
 * Value Type Aliases (RT-1-1-1)
 * ======================================================================== */

typedef int16_t  rf_int16;
typedef int32_t  rf_int;
typedef int32_t  rf_int32;
typedef int64_t  rf_int64;
typedef uint8_t  rf_byte;
typedef uint16_t rf_uint16;
typedef uint32_t rf_uint;
typedef uint32_t rf_uint32;
typedef uint64_t rf_uint64;
typedef float    rf_float32;
typedef double   rf_float;
typedef double   rf_float64;
typedef bool     rf_bool;
typedef uint32_t rf_char; /* Unicode scalar value */

/* ========================================================================
 * Panic Functions (RT-1-1-3)
 * ======================================================================== */

void rf_panic(const char* msg);
void rf_panic_overflow(void);
void rf_panic_divzero(void);
void rf_panic_oob(void);

/* ========================================================================
 * Checked Arithmetic Macros (RT-1-1-2)
 * ======================================================================== */

#define RF_CHECKED_ADD(a, b, result) \
    do { if (__builtin_add_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)

#define RF_CHECKED_SUB(a, b, result) \
    do { if (__builtin_sub_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)

#define RF_CHECKED_MUL(a, b, result) \
    do { if (__builtin_mul_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)

#define RF_CHECKED_DIV(a, b, result) \
    do { if ((b) == 0) rf_panic_divzero(); *(result) = (a) / (b); } while(0)

#define RF_CHECKED_MOD(a, b, result) \
    do { if ((b) == 0) rf_panic_divzero(); *(result) = (a) % (b); } while(0)

/* ========================================================================
 * Option Types (RT-1-3-1)
 *
 * Tag values: 0 = none, 1 = some.
 * ======================================================================== */

#define RF_OPTION_TYPE(T, name) \
    typedef struct { rf_byte tag; T value; } name;

RF_OPTION_TYPE(rf_int,     RF_Option_int)
RF_OPTION_TYPE(rf_int16,   RF_Option_int16)
RF_OPTION_TYPE(rf_int32,   RF_Option_int32)
RF_OPTION_TYPE(rf_int64,   RF_Option_int64)
RF_OPTION_TYPE(rf_uint,    RF_Option_uint)
RF_OPTION_TYPE(rf_uint16,  RF_Option_uint16)
RF_OPTION_TYPE(rf_uint32,  RF_Option_uint32)
RF_OPTION_TYPE(rf_uint64,  RF_Option_uint64)
RF_OPTION_TYPE(rf_float,   RF_Option_float)
RF_OPTION_TYPE(rf_float32, RF_Option_float32)
RF_OPTION_TYPE(rf_float64, RF_Option_float64)
RF_OPTION_TYPE(rf_bool,    RF_Option_bool)
RF_OPTION_TYPE(rf_byte,    RF_Option_byte)
RF_OPTION_TYPE(rf_char,    RF_Option_char)

/* Heap option — used for RF_String*, RF_Array*, and all pointer types */
typedef struct { rf_byte tag; void* value; } RF_Option_ptr;

/* Option constructors */
#define RF_NONE         {.tag = 0}
#define RF_SOME(v)      {.tag = 1, .value = (v)}
#define RF_NONE_PTR     ((RF_Option_ptr){.tag = 0, .value = NULL})
#define RF_SOME_PTR(v)  ((RF_Option_ptr){.tag = 1, .value = (void*)(v)})

/* Option helpers (RT-1-3-3) */
#define rf_option_unwrap_or(opt, default) \
    ((opt).tag == 1 ? (opt).value : (default))

/* ========================================================================
 * String Type (RT-1-2-1)
 * ======================================================================== */

typedef struct RF_String {
    rf_int64 refcount;
    rf_int64 len;    /* byte length, not char count; excludes null terminator */
    char     data[]; /* flexible array member, UTF-8, always null-terminated */
} RF_String;

RF_String* rf_string_new(const char* data, rf_int64 len);
RF_String* rf_string_from_cstr(const char* cstr);
void       rf_string_retain(RF_String* s);
void       rf_string_release(RF_String* s);
RF_String* rf_string_concat(RF_String* a, RF_String* b);
rf_bool    rf_string_eq(RF_String* a, RF_String* b);
rf_int64   rf_string_len(RF_String* s);
rf_int     rf_string_cmp(RF_String* a, RF_String* b);

/* Numeric conversions (RT-1-2-3) */
rf_bool    rf_string_to_int(RF_String* s, rf_int* out);
rf_bool    rf_string_to_int64(RF_String* s, rf_int64* out);
rf_bool    rf_string_to_float(RF_String* s, rf_float* out);
RF_String* rf_int_to_string(rf_int v);
RF_String* rf_int64_to_string(rf_int64 v);
RF_String* rf_float_to_string(rf_float v);
RF_String* rf_bool_to_string(rf_bool v);

/* ========================================================================
 * Result Types (RT-1-3-2)
 *
 * Tag values: 0 = ok, 1 = err.
 * The emitter instantiates RF_RESULT_TYPE once per unique (ok, err) pair.
 * ======================================================================== */

#define RF_RESULT_TYPE(T_ok, T_err, name) \
    typedef struct {                       \
        rf_byte tag;                       \
        union {                            \
            T_ok  ok_val;                  \
            T_err err_val;                 \
        } payload;                         \
    } name;

/* Baseline instantiations */
RF_RESULT_TYPE(rf_int,  RF_String*, RF_Result_int_String)
RF_RESULT_TYPE(void*,   void*,      RF_Result_ptr_ptr)

/* Result helpers (RT-1-3-3) */
#define rf_result_is_ok(res)  ((res).tag == 0)
#define rf_result_is_err(res) ((res).tag == 1)
#define RF_OK(v)  {.tag = 0, .payload.ok_val  = (v)}
#define RF_ERR(v) {.tag = 1, .payload.err_val = (v)}

/* ========================================================================
 * Array (RT-1-4-1)
 * ======================================================================== */

typedef struct RF_Array {
    rf_int64  refcount;
    rf_int64  len;
    void*     data;
    rf_int64  element_size;
} RF_Array;

RF_Array*     rf_array_new(rf_int64 len, rf_int64 element_size, void* initial_data);
void          rf_array_retain(RF_Array* arr);
void          rf_array_release(RF_Array* arr);
void*         rf_array_get_ptr(RF_Array* arr, rf_int64 idx);
RF_Option_ptr rf_array_get_safe(RF_Array* arr, rf_int64 idx);
rf_int64      rf_array_len(RF_Array* arr);
RF_Array*     rf_array_push(RF_Array* arr, void* element);

/* ========================================================================
 * Stream (RT-1-5-1)
 * ======================================================================== */

typedef struct RF_Stream RF_Stream;

typedef RF_Option_ptr (*RF_StreamNext)(RF_Stream* self);
typedef void          (*RF_StreamFree)(RF_Stream* self);

struct RF_Stream {
    RF_StreamNext next_fn;
    RF_StreamFree free_fn;
    void*         state;
    rf_int        refcount;
};

RF_Stream*    rf_stream_new(RF_StreamNext next_fn, RF_StreamFree free_fn, void* state);
void          rf_stream_retain(RF_Stream* s);
void          rf_stream_release(RF_Stream* s);
RF_Option_ptr rf_stream_next(RF_Stream* s);

/* ========================================================================
 * Map — open-addressing hash table (RT-1-6-1)
 * BOOTSTRAP: replace with production hash map
 * ======================================================================== */

typedef struct RF_Map RF_Map;

RF_Map*       rf_map_new(void);
RF_Map*       rf_map_set(RF_Map* m, void* key, rf_int64 key_len, void* val);
RF_Option_ptr rf_map_get(RF_Map* m, void* key, rf_int64 key_len);
rf_bool       rf_map_has(RF_Map* m, void* key, rf_int64 key_len);
rf_int64      rf_map_len(RF_Map* m);
void          rf_map_retain(RF_Map* m);
void          rf_map_release(RF_Map* m);

/* ========================================================================
 * Set (RT-1-6-2)
 * ======================================================================== */

typedef struct RF_Set RF_Set;

RF_Set*  rf_set_new(void);
rf_bool  rf_set_add(RF_Set* s, void* key, rf_int64 key_len);
rf_bool  rf_set_has(RF_Set* s, void* key, rf_int64 key_len);
rf_bool  rf_set_remove(RF_Set* s, void* key, rf_int64 key_len);
rf_int64 rf_set_len(RF_Set* s);
void     rf_set_retain(RF_Set* s);
void     rf_set_release(RF_Set* s);

/* ========================================================================
 * Buffer (RT-1-7-1)
 * ======================================================================== */

typedef struct RF_Buffer {
    rf_int64 refcount;
    rf_int64 len;
    rf_int64 capacity;
    rf_int64 element_size;
    void*    data;
} RF_Buffer;

RF_Buffer*    rf_buffer_new(rf_int64 element_size);
RF_Buffer*    rf_buffer_with_capacity(rf_int64 cap, rf_int64 element_size);
RF_Buffer*    rf_buffer_collect(RF_Stream* s, rf_int64 element_size);
void          rf_buffer_push(RF_Buffer* buf, void* element);
RF_Option_ptr rf_buffer_get(RF_Buffer* buf, rf_int64 idx);
RF_Stream*    rf_buffer_drain(RF_Buffer* buf);
rf_int64      rf_buffer_len(RF_Buffer* buf);
void          rf_buffer_sort_by(RF_Buffer* buf, int (*cmp)(const void*, const void*));
void          rf_buffer_reverse(RF_Buffer* buf);
void          rf_buffer_retain(RF_Buffer* buf);
void          rf_buffer_release(RF_Buffer* buf);

/* ========================================================================
 * I/O Primitives (RT-1-8-1)
 * ======================================================================== */

void          rf_print(RF_String* s);
void          rf_println(RF_String* s);
void          rf_eprint(RF_String* s);
void          rf_eprintln(RF_String* s);
RF_Stream*    rf_stdin_stream(void);
RF_Option_ptr rf_read_line(void);
RF_Option_ptr rf_read_byte(void);

/* ========================================================================
 * System Functions (stdlib/sys)
 * ======================================================================== */

void          rf_sys_exit(rf_int code);
RF_Array*     rf_sys_args(void);

/* ========================================================================
 * Conversion Wrappers (stdlib/conv) — option-returning variants
 * ======================================================================== */

RF_Option_ptr rf_string_to_int_opt(RF_String* s);
RF_Option_ptr rf_string_to_int64_opt(RF_String* s);
RF_Option_ptr rf_string_to_float_opt(RF_String* s);

/* ========================================================================
 * Runtime Initialization
 * ======================================================================== */

void _rf_runtime_init(int argc, char** argv);

#endif /* REFLOW_RUNTIME_H */
