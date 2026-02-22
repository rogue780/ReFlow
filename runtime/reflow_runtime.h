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
#include <setjmp.h>

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
 * Coroutines
 * ======================================================================== */

typedef struct RF_Coroutine {
    RF_Stream* stream;
    rf_bool    done;
} RF_Coroutine;

RF_Coroutine* rf_coroutine_new(RF_Stream* stream);
RF_Option_ptr rf_coroutine_next(RF_Coroutine* c);
rf_bool       rf_coroutine_done(RF_Coroutine* c);
void          rf_coroutine_release(RF_Coroutine* c);

/* ========================================================================
 * Closures
 * ======================================================================== */
typedef struct RF_Closure {
    void* fn;
    void* env;
} RF_Closure;

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
 * String Operations (stdlib/string — RB-1-1)
 * ======================================================================== */

RF_Option_char rf_string_char_at(RF_String* s, rf_int64 idx);
RF_String*     rf_string_substring(RF_String* s, rf_int64 start, rf_int64 end);
RF_Option_int  rf_string_index_of(RF_String* haystack, RF_String* needle);
rf_bool       rf_string_contains(RF_String* s, RF_String* needle);
rf_bool       rf_string_starts_with(RF_String* s, RF_String* prefix);
rf_bool       rf_string_ends_with(RF_String* s, RF_String* suffix);
RF_Array*     rf_string_split(RF_String* s, RF_String* sep);
RF_String*    rf_string_trim(RF_String* s);
RF_String*    rf_string_trim_left(RF_String* s);
RF_String*    rf_string_trim_right(RF_String* s);
RF_String*    rf_string_replace(RF_String* s, RF_String* old_s, RF_String* new_s);
RF_String*    rf_string_join(RF_Array* parts, RF_String* sep);
RF_String*    rf_string_to_lower(RF_String* s);
RF_String*    rf_string_to_upper(RF_String* s);

/* ========================================================================
 * Character Utilities (stdlib/char — RB-1-2)
 * ======================================================================== */

rf_bool    rf_char_is_digit(rf_char c);
rf_bool    rf_char_is_alpha(rf_char c);
rf_bool    rf_char_is_alphanumeric(rf_char c);
rf_bool    rf_char_is_whitespace(rf_char c);
rf_int     rf_char_to_int(rf_char c);
rf_char    rf_int_to_char(rf_int n);
RF_String* rf_char_to_string(rf_char c);

/* ========================================================================
 * File I/O (stdlib/io — RB-1-3)
 * ======================================================================== */

RF_Option_ptr rf_read_file(RF_String* path);
rf_bool       rf_write_file(RF_String* path, RF_String* contents);

/* ========================================================================
 * Process Execution (stdlib/sys — RB-1-4)
 * ======================================================================== */

rf_int        rf_run_process(RF_String* command, RF_Array* args);
RF_Option_ptr rf_run_process_capture(RF_String* command, RF_Array* args);

/* ========================================================================
 * Temporary File Support (stdlib/io — RB-1-5)
 * ======================================================================== */

RF_String* rf_tmpfile_create(RF_String* suffix, RF_String* contents);
void       rf_tmpfile_remove(RF_String* path);

/* ========================================================================
 * Path Utilities (stdlib/path — RB-1-6)
 * ======================================================================== */

RF_String* rf_path_join(RF_String* a, RF_String* b);
RF_String* rf_path_stem(RF_String* path);
RF_String* rf_path_parent(RF_String* path);
RF_String* rf_path_with_suffix(RF_String* path, RF_String* suffix);
RF_String* rf_path_cwd(void);
RF_String* rf_path_resolve(RF_String* path);
rf_bool    rf_path_exists(RF_String* path);

/* ========================================================================
 * Exception Handling (setjmp/longjmp)
 * ======================================================================== */

typedef struct RF_ExceptionFrame {
    jmp_buf jmp;
    struct RF_ExceptionFrame* parent;
    void* exception;       /* heap-allocated exception value */
    rf_int exception_tag;  /* integer type tag for catch dispatch */
} RF_ExceptionFrame;

extern RF_ExceptionFrame* _rf_exception_current;

void _rf_exception_push(RF_ExceptionFrame* frame);
void _rf_exception_pop(void);
_Noreturn void _rf_throw(void* exception, rf_int tag);
_Noreturn void _rf_rethrow(void);

/* ========================================================================
 * Runtime Initialization
 * ======================================================================== */

void _rf_runtime_init(int argc, char** argv);

#endif /* REFLOW_RUNTIME_H */
