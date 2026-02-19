---
name: c-runtime
description: Documents the conventions, struct layouts, and callable functions of the ReFlow C runtime library. Read this skill before writing any emitter or lowering code that interacts with the runtime.
---

# ReFlow C Runtime Reference

The runtime lives in `runtime/reflow_runtime.h` and `runtime/reflow_runtime.c`. Every generated `.c` file begins with `#include "reflow_runtime.h"`. This skill documents what the runtime provides so the lowering and emitter passes use it correctly.

---

## Type Aliases

All ReFlow value types map to C typedef aliases. Use the typedef name, not the underlying type:

| ReFlow type | C typedef | Underlying C type |
|-------------|-----------|-------------------|
| `int` | `rf_int` | `int32_t` |
| `int16` | `rf_int16` | `int16_t` |
| `int32` | `rf_int32` | `int32_t` |
| `int64` | `rf_int64` | `int64_t` |
| `uint` | `rf_uint` | `uint32_t` |
| `uint16` | `rf_uint16` | `uint16_t` |
| `uint32` | `rf_uint32` | `uint32_t` |
| `uint64` | `rf_uint64` | `uint64_t` |
| `float` / `float64` | `rf_float` / `rf_float64` | `double` |
| `float32` | `rf_float32` | `float` |
| `bool` | `rf_bool` | `bool` |
| `byte` | `rf_byte` | `uint8_t` |
| `char` | `rf_char` | `uint32_t` (Unicode scalar) |

---

## Checked Arithmetic Macros

Integer arithmetic that can overflow **must** use these macros. Never emit a plain `+` for integer addition in generated code.

```c
RF_CHECKED_ADD(a, b, &result)    /* result = a + b, panics on overflow */
RF_CHECKED_SUB(a, b, &result)    /* result = a - b, panics on underflow */
RF_CHECKED_MUL(a, b, &result)    /* result = a * b, panics on overflow */
```

Usage pattern in generated C:
```c
rf_int _rf_tmp_1;
RF_CHECKED_ADD(x, y, &_rf_tmp_1);
/* use _rf_tmp_1 */
```

Float arithmetic uses plain C operators. Integer division by zero calls `rf_panic_divzero()` — emit an explicit zero check before integer division.

---

## String: RF_String*

Strings are heap-allocated, reference-counted. Always use the API — never touch the struct fields directly.

```c
/* Structure (do not access directly from generated code) */
typedef struct RF_String {
    rf_int64 refcount;
    rf_int64 len;
    char     data[];
} RF_String;
```

**API:**
```c
RF_String* rf_string_from_cstr(const char* cstr);   /* create from string literal */
void       rf_string_retain(RF_String* s);           /* increment refcount */
void       rf_string_release(RF_String* s);          /* decrement; frees at 0 */
RF_String* rf_string_concat(RF_String* a, RF_String* b);
rf_bool    rf_string_eq(RF_String* a, RF_String* b);
rf_int64   rf_string_len(RF_String* s);
rf_int     rf_string_cmp(RF_String* a, RF_String* b);

/* Numeric conversions */
rf_bool    rf_string_to_int(RF_String* s, rf_int* out);
rf_bool    rf_string_to_int64(RF_String* s, rf_int64* out);
rf_bool    rf_string_to_float(RF_String* s, rf_float* out);
RF_String* rf_int_to_string(rf_int v);
RF_String* rf_int64_to_string(rf_int64 v);
RF_String* rf_float_to_string(rf_float v);
```

**String literals in generated C:** always use `rf_string_from_cstr("literal")`. Never use a bare `char*` where `RF_String*` is expected.

**F-string lowering:** lower `f"Hello {name}!"` to a chain of `rf_string_concat` calls:
```c
RF_String* _rf_tmp_1 = rf_string_from_cstr("Hello ");
RF_String* _rf_tmp_2 = rf_int_to_string(name);   /* if name is int */
RF_String* _rf_tmp_3 = rf_string_concat(_rf_tmp_1, _rf_tmp_2);
RF_String* _rf_tmp_4 = rf_string_from_cstr("!");
RF_String* _rf_tmp_5 = rf_string_concat(_rf_tmp_3, _rf_tmp_4);
/* _rf_tmp_5 is the result */
```

---

## Option Types: RF_Option_*

Option types are structs with a `tag` field and a `value` field. Tag `0` = none, tag `1` = some.

Pre-defined option types in the runtime header:
```c
RF_Option_int       /* tag + rf_int value */
RF_Option_int64     /* tag + rf_int64 value */
RF_Option_float     /* tag + rf_float value */
RF_Option_bool      /* tag + rf_bool value */
RF_Option_ptr       /* tag + void* value — used for all heap types */
```

**Constructors (macros):**
```c
RF_NONE             /* {.tag = 0} */
RF_SOME(v)          /* {.tag = 1, .value = (v)} */
```

**Usage in generated C:**
```c
/* Creating some(42) */
RF_Option_int result = RF_SOME(42);

/* Checking and unwrapping */
if (result.tag == 1) {
    rf_int val = result.value;
    /* use val */
}

/* The ?? operator: opt ?? default */
rf_int x = (opt.tag == 1) ? opt.value : default_value;
```

---

## Result Types: RF_Result_*

Result types are generated per (ok_type, err_type) combination encountered in the program. The emitter maintains a registry and emits one typedef per unique combination.

Tag values: `0` = ok, `1` = err.

Generated typedef example for `result<int, string>`:
```c
typedef struct {
    uint8_t tag;
    union {
        rf_int   ok_val;
        RF_String* err_val;
    } payload;
} RF_Result_int_String;
```

**Macros:**
```c
rf_result_is_ok(res)     /* res.tag == 0 */
rf_result_is_err(res)    /* res.tag == 1 */
```

**The `?` propagation operator** lowers to:
```c
/* let n = parse(raw)? */
RF_Result_int_String _rf_tmp_1 = parse(raw);
if (rf_result_is_err(_rf_tmp_1)) {
    return _rf_tmp_1;   /* propagate the err, casting to caller's result type */
}
rf_int n = _rf_tmp_1.payload.ok_val;
```

---

## Arrays: RF_Array*

Arrays are heap-allocated, reference-counted, and immutable. Transformations return new arrays.

```c
RF_Array* rf_array_new(rf_int64 len, rf_int64 element_size, void* initial_data);
void      rf_array_retain(RF_Array* arr);
void      rf_array_release(RF_Array* arr);
void*     rf_array_get_ptr(RF_Array* arr, rf_int64 idx);   /* panics on OOB */
RF_Option_ptr rf_array_get_safe(RF_Array* arr, rf_int64 idx);
rf_int64  rf_array_len(RF_Array* arr);
RF_Array* rf_array_push(RF_Array* arr, void* element);    /* returns new array */
```

**Array literal lowering:** `[1, 2, 3]` as `array<int>` lowers to:
```c
rf_int _rf_arr_data[] = {1, 2, 3};
RF_Array* _rf_tmp_1 = rf_array_new(3, sizeof(rf_int), _rf_arr_data);
```

**For loop over array lowers to:**
```c
rf_int64 _rf_len = rf_array_len(arr);
for (rf_int64 _rf_i = 0; _rf_i < _rf_len; _rf_i++) {
    ElementType* _rf_ptr = (ElementType*)rf_array_get_ptr(arr, _rf_i);
    ElementType item = *_rf_ptr;
    /* loop body */
}
```

---

## Streams: RF_Stream*

Streams are state machines. The runtime provides the frame and dispatch; the compiler generates the `next` and `free` functions.

```c
typedef RF_Option_ptr (*RF_StreamNext)(RF_Stream* self);
typedef void          (*RF_StreamFree)(RF_Stream* self);

struct RF_Stream {
    RF_StreamNext next_fn;
    RF_StreamFree free_fn;
    void*         state;       /* pointer to the compiler-generated frame struct */
    rf_int        refcount;
};

RF_Stream* rf_stream_new(RF_StreamNext next_fn, RF_StreamFree free_fn, void* state);
void       rf_stream_retain(RF_Stream* s);
void       rf_stream_release(RF_Stream* s);  /* calls free_fn then frees */
RF_Option_ptr rf_stream_next(RF_Stream* s);  /* calls next_fn */
```

**How a streaming function compiles:** A ReFlow function `fn count(n: int): stream<int>` compiles to three C artifacts:

```c
/* 1. Frame struct — holds all locals and state counter */
typedef struct {
    rf_int32 _state;     /* which yield point to resume at */
    rf_int   n;          /* parameter, stored in frame */
    rf_int   i;          /* local variable */
} _rf_frame_count;

/* 2. next function — called each time the consumer pulls */
RF_Option_ptr _rf_next_count(RF_Stream* self) {
    _rf_frame_count* frame = (_rf_frame_count*)self->state;
    switch (frame->_state) {
        case 0: goto _state_0;
        case 1: goto _state_1;
        /* ... */
    }
    _state_0:
        frame->i = 0;
        /* fall through to first yield */
    _state_1:
        if (frame->i >= frame->n) {
            frame->_state = -1;
            return RF_NONE;
        }
        frame->_state = 2;
        return RF_SOME((void*)(uintptr_t)frame->i);
    _state_2:
        frame->i++;
        goto _state_1;
}

/* 3. free function */
void _rf_free_count(RF_Stream* self) {
    _rf_frame_count* frame = (_rf_frame_count*)self->state;
    /* release any heap values held in frame */
    free(frame);
}

/* 4. factory function — this IS the ReFlow function */
RF_Stream* rf_module_count(rf_int n) {
    _rf_frame_count* frame = malloc(sizeof(_rf_frame_count));
    frame->_state = 0;
    frame->n = n;
    return rf_stream_new(_rf_next_count, _rf_free_count, frame);
}
```

**For loop over stream lowers to:**
```c
RF_Option_ptr _rf_item_opt;
while ((_rf_item_opt = rf_stream_next(stream)).tag == 1) {
    ElementType item = (ElementType)(uintptr_t)_rf_item_opt.value;
    /* loop body */
}
```

---

## Buffers: RF_Buffer*

Buffers are mutable, in-memory containers that can collect from streams.

```c
RF_Buffer* rf_buffer_new(rf_int64 element_size);
RF_Buffer* rf_buffer_collect(RF_Stream* s, rf_int64 element_size); /* drains stream */
void       rf_buffer_push(RF_Buffer* buf, void* element);
RF_Option_ptr rf_buffer_get(RF_Buffer* buf, rf_int64 idx);
RF_Stream* rf_buffer_drain(RF_Buffer* buf);   /* consumes buf, returns stream */
rf_int64   rf_buffer_len(RF_Buffer* buf);
void       rf_buffer_sort_by(RF_Buffer* buf, int (*cmp)(void*, void*));
void       rf_buffer_reverse(RF_Buffer* buf);
void       rf_buffer_retain(RF_Buffer* buf);
void       rf_buffer_release(RF_Buffer* buf);
```

---

## Maps and Sets

```c
RF_Map* rf_map_new(void);
RF_Map* rf_map_set(RF_Map* m, void* key, rf_int64 key_len, void* val);
RF_Option_ptr rf_map_get(RF_Map* m, void* key, rf_int64 key_len);
rf_bool rf_map_has(RF_Map* m, void* key, rf_int64 key_len);
rf_int64 rf_map_len(RF_Map* m);
void    rf_map_retain(RF_Map* m);
void    rf_map_release(RF_Map* m);

RF_Set* rf_set_new(void);
rf_bool rf_set_add(RF_Set* s, void* key, rf_int64 key_len);
rf_bool rf_set_has(RF_Set* s, void* key, rf_int64 key_len);
rf_bool rf_set_remove(RF_Set* s, void* key, rf_int64 key_len);
rf_int64 rf_set_len(RF_Set* s);
void    rf_set_retain(RF_Set* s);
void    rf_set_release(RF_Set* s);
```

String keys: pass `s->data` as key and `s->len` as key_len.

---

## Panic Functions

These terminate the program with a message to stderr. Use them in generated code for conditions the spec says are runtime panics:

```c
void rf_panic(const char* msg);          /* generic: prints msg and exits 1 */
void rf_panic_overflow(void);            /* "OverflowError" */
void rf_panic_divzero(void);             /* "DivisionByZeroError" */
void rf_panic_oob(void);                 /* "IndexOutOfBoundsError" */
```

The spec defines exactly which conditions trigger each panic — do not add new panic conditions not defined in the spec.

---

## I/O Functions

```c
void       rf_print(RF_String* s);
void       rf_println(RF_String* s);
void       rf_eprint(RF_String* s);
void       rf_eprintln(RF_String* s);
RF_Stream* rf_stdin_stream(void);         /* stream<byte> */
RF_Option_ptr rf_read_line(void);        /* option<RF_String*> */
```

These are not pure. Any generated function that calls them must not be marked `pure`.

---

## Reference Counting Rules

The rules for when to call `retain` and `release`:

- **Allocating** a heap value: starts at refcount 1. No explicit retain needed.
- **Passing to a function that stores it** (return value, stored in a struct): call `retain` before passing, the callee will `release` when done.
- **Passing to a function that only reads it** (most function calls): no retain/release needed. The callee does not outlive the call.
- **Assigning to a struct field**: call `retain`. Call `release` on the old value in that field if any.
- **End of scope** for a local heap binding: call `release`.
- **Returning a heap value from a function**: the caller inherits the refcount. No extra retain.

For the bootstrap compiler, implement a conservative approximation: retain on every assignment to a field, release at end of scope for all local heap variables. This will be correct but may retain/release more than strictly necessary.
