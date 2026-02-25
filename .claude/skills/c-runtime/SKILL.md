---
name: c-runtime
description: Documents the conventions, struct layouts, and callable functions of the Flow C runtime library. Read this skill before writing any emitter or lowering code that interacts with the runtime.
---

# Flow C Runtime Reference

The runtime lives in `runtime/flow_runtime.h` and `runtime/flow_runtime.c`. Every generated `.c` file begins with `#include "flow_runtime.h"`. This skill documents what the runtime provides so the lowering and emitter passes use it correctly.

---

## Type Aliases

All Flow value types map to C typedef aliases. Use the typedef name, not the underlying type:

| Flow type | C typedef | Underlying C type |
|-------------|-----------|-------------------|
| `int` | `fl_int` | `int32_t` |
| `int16` | `fl_int16` | `int16_t` |
| `int32` | `fl_int32` | `int32_t` |
| `int64` | `fl_int64` | `int64_t` |
| `uint` | `fl_uint` | `uint32_t` |
| `uint16` | `fl_uint16` | `uint16_t` |
| `uint32` | `fl_uint32` | `uint32_t` |
| `uint64` | `fl_uint64` | `uint64_t` |
| `float` / `float64` | `fl_float` / `fl_float64` | `double` |
| `float32` | `fl_float32` | `float` |
| `bool` | `fl_bool` | `bool` |
| `byte` | `fl_byte` | `uint8_t` |
| `char` | `fl_char` | `uint32_t` (Unicode scalar) |

---

## Checked Arithmetic Macros

Integer arithmetic that can overflow **must** use these macros. Never emit a plain `+` for integer addition in generated code.

```c
FL_CHECKED_ADD(a, b, &result)    /* result = a + b, panics on overflow */
FL_CHECKED_SUB(a, b, &result)    /* result = a - b, panics on underflow */
FL_CHECKED_MUL(a, b, &result)    /* result = a * b, panics on overflow */
FL_CHECKED_FMOD(a, b, &result)   /* result = fmod(a, b), panics on divzero */
```

Usage pattern in generated C:
```c
fl_int _fl_tmp_1;
FL_CHECKED_ADD(x, y, &_fl_tmp_1);
/* use _fl_tmp_1 */
```

Float arithmetic uses plain C operators for `+`, `-`, `*`, `/`. Integer division by zero calls `fl_panic_divzero()` — emit an explicit zero check before integer division.

Float modulo (`%` on floats) uses `FL_CHECKED_FMOD` which calls `fmod()` from `<math.h>` and panics on division by zero (unlike float division which follows IEEE 754).

---

## String: FL_String*

Strings are heap-allocated, reference-counted. Always use the API — never touch the struct fields directly.

```c
/* Structure (do not access directly from generated code) */
typedef struct FL_String {
    fl_int64 refcount;
    fl_int64 len;
    char     data[];
} FL_String;
```

**API:**
```c
FL_String* fl_string_from_cstr(const char* cstr);   /* create from string literal */
void       fl_string_retain(FL_String* s);           /* increment refcount */
void       fl_string_release(FL_String* s);          /* decrement; frees at 0 */
FL_String* fl_string_concat(FL_String* a, FL_String* b);
fl_bool    fl_string_eq(FL_String* a, FL_String* b);
fl_int64   fl_string_len(FL_String* s);
fl_int     fl_string_cmp(FL_String* a, FL_String* b);

/* Numeric conversions */
fl_bool    fl_string_to_int(FL_String* s, fl_int* out);
fl_bool    fl_string_to_int64(FL_String* s, fl_int64* out);
fl_bool    fl_string_to_float(FL_String* s, fl_float* out);
FL_String* fl_int_to_string(fl_int v);
FL_String* fl_int64_to_string(fl_int64 v);
FL_String* fl_float_to_string(fl_float v);
```

**String literals in generated C:** always use `fl_string_from_cstr("literal")`. Never use a bare `char*` where `FL_String*` is expected.

**F-string lowering:** lower `f"Hello {name}!"` to a chain of `fl_string_concat` calls:
```c
FL_String* _fl_tmp_1 = fl_string_from_cstr("Hello ");
FL_String* _fl_tmp_2 = fl_int_to_string(name);   /* if name is int */
FL_String* _fl_tmp_3 = fl_string_concat(_fl_tmp_1, _fl_tmp_2);
FL_String* _fl_tmp_4 = fl_string_from_cstr("!");
FL_String* _fl_tmp_5 = fl_string_concat(_fl_tmp_3, _fl_tmp_4);
/* _fl_tmp_5 is the result */
```

---

## Option Types: FL_Option_*

Option types are structs with a `tag` field and a `value` field. Tag `0` = none, tag `1` = some.

Pre-defined option types in the runtime header:
```c
FL_Option_int       /* tag + fl_int value */
FL_Option_int64     /* tag + fl_int64 value */
FL_Option_float     /* tag + fl_float value */
FL_Option_bool      /* tag + fl_bool value */
FL_Option_ptr       /* tag + void* value — used for all heap types */
```

**Constructors (macros):**
```c
FL_NONE             /* {.tag = 0} */
FL_SOME(v)          /* {.tag = 1, .value = (v)} */
```

**Usage in generated C:**
```c
/* Creating some(42) */
FL_Option_int result = FL_SOME(42);

/* Checking and unwrapping */
if (result.tag == 1) {
    fl_int val = result.value;
    /* use val */
}

/* The ?? operator: opt ?? default */
fl_int x = (opt.tag == 1) ? opt.value : default_value;
```

---

## Result Types: FL_Result_*

Result types are generated per (ok_type, err_type) combination encountered in the program. The emitter maintains a registry and emits one typedef per unique combination.

Tag values: `0` = ok, `1` = err.

Generated typedef example for `result<int, string>`:
```c
typedef struct {
    uint8_t tag;
    union {
        fl_int   ok_val;
        FL_String* err_val;
    } payload;
} FL_Result_int_String;
```

**Macros:**
```c
fl_result_is_ok(res)     /* res.tag == 0 */
fl_result_is_err(res)    /* res.tag == 1 */
```

**The `?` propagation operator** lowers to:
```c
/* let n = parse(raw)? */
FL_Result_int_String _fl_tmp_1 = parse(raw);
if (fl_result_is_err(_fl_tmp_1)) {
    return _fl_tmp_1;   /* propagate the err, casting to caller's result type */
}
fl_int n = _fl_tmp_1.payload.ok_val;
```

---

## Arrays: FL_Array*

Arrays are heap-allocated, reference-counted, and immutable. Transformations return new arrays.

```c
FL_Array* fl_array_new(fl_int64 len, fl_int64 element_size, void* initial_data);
void      fl_array_retain(FL_Array* arr);
void      fl_array_release(FL_Array* arr);
void*     fl_array_get_ptr(FL_Array* arr, fl_int64 idx);   /* panics on OOB */
FL_Option_ptr fl_array_get_safe(FL_Array* arr, fl_int64 idx);
fl_int64  fl_array_len(FL_Array* arr);
FL_Array* fl_array_push(FL_Array* arr, void* element);    /* returns new array */
FL_Array* fl_array_push_sized(FL_Array* arr, void* element, fl_int64 elem_size);
```

**Array literal lowering:** `[1, 2, 3]` as `array<int>` lowers to:
```c
fl_int _fl_arr_data[] = {1, 2, 3};
FL_Array* _fl_tmp_1 = fl_array_new(3, sizeof(fl_int), _fl_arr_data);
```

**Generic push for non-pointer types (sum types, structs):**
When `array.push<T>` is called where T is a non-pointer type, the lowering
emits `fl_array_push_sized(arr, &val, sizeof(ValType))` instead of
`fl_array_push_ptr(arr, val)`. This ensures correct `element_size` even for
empty arrays (where `element_size` starts at 0).

**Generic get for non-pointer types:**
When `array.get_any<T>` is called where T is a non-pointer type,
`fl_array_get_safe` returns `FL_Option_ptr` where `.value` is a pointer to
the element data. The lowering wraps this with `FL_OPT_DEREF_AS(opt, ValType,
OptType)` to cast, dereference, and repack into the correct option struct.

**For loop over array lowers to:**
```c
fl_int64 _fl_len = fl_array_len(arr);
for (fl_int64 _fl_i = 0; _fl_i < _fl_len; _fl_i++) {
    ElementType* _fl_ptr = (ElementType*)fl_array_get_ptr(arr, _fl_i);
    ElementType item = *_fl_ptr;
    /* loop body */
}
```

---

## Streams: FL_Stream*

Streams are state machines. The runtime provides the frame and dispatch; the compiler generates the `next` and `free` functions.

```c
typedef FL_Option_ptr (*FL_StreamNext)(FL_Stream* self);
typedef void          (*FL_StreamFree)(FL_Stream* self);

struct FL_Stream {
    FL_StreamNext next_fn;
    FL_StreamFree free_fn;
    void*         state;       /* pointer to the compiler-generated frame struct */
    fl_int        refcount;
};

FL_Stream* fl_stream_new(FL_StreamNext next_fn, FL_StreamFree free_fn, void* state);
void       fl_stream_retain(FL_Stream* s);
void       fl_stream_release(FL_Stream* s);  /* calls free_fn then frees */
FL_Option_ptr fl_stream_next(FL_Stream* s);  /* calls next_fn */
```

**How a streaming function compiles:** A Flow function `fn count(n: int): stream<int>` compiles to three C artifacts:

```c
/* 1. Frame struct — holds all locals and state counter */
typedef struct {
    fl_int32 _state;     /* which yield point to resume at */
    fl_int   n;          /* parameter, stored in frame */
    fl_int   i;          /* local variable */
} _fl_frame_count;

/* 2. next function — called each time the consumer pulls */
FL_Option_ptr _fl_next_count(FL_Stream* self) {
    _fl_frame_count* frame = (_fl_frame_count*)self->state;
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
            return FL_NONE;
        }
        frame->_state = 2;
        return FL_SOME((void*)(uintptr_t)frame->i);
    _state_2:
        frame->i++;
        goto _state_1;
}

/* 3. free function */
void _fl_free_count(FL_Stream* self) {
    _fl_frame_count* frame = (_fl_frame_count*)self->state;
    /* release any heap values held in frame */
    free(frame);
}

/* 4. factory function — this IS the Flow function */
FL_Stream* fl_module_count(fl_int n) {
    _fl_frame_count* frame = malloc(sizeof(_fl_frame_count));
    frame->_state = 0;
    frame->n = n;
    return fl_stream_new(_fl_next_count, _fl_free_count, frame);
}
```

**For loop over stream lowers to:**
```c
FL_Option_ptr _fl_item_opt;
while ((_fl_item_opt = fl_stream_next(stream)).tag == 1) {
    ElementType item = (ElementType)(uintptr_t)_fl_item_opt.value;
    /* loop body */
}
```

---

## Buffers: FL_Buffer*

Buffers are mutable, in-memory containers that can collect from streams.

```c
FL_Buffer* fl_buffer_new(fl_int64 element_size);
FL_Buffer* fl_buffer_collect(FL_Stream* s, fl_int64 element_size); /* drains stream */
void       fl_buffer_push(FL_Buffer* buf, void* element);
FL_Option_ptr fl_buffer_get(FL_Buffer* buf, fl_int64 idx);
FL_Stream* fl_buffer_drain(FL_Buffer* buf);   /* consumes buf, returns stream */
fl_int64   fl_buffer_len(FL_Buffer* buf);
void       fl_buffer_sort_by(FL_Buffer* buf, int (*cmp)(void*, void*));
void       fl_buffer_reverse(FL_Buffer* buf);
void       fl_buffer_retain(FL_Buffer* buf);
void       fl_buffer_release(FL_Buffer* buf);
```

---

## Maps and Sets

```c
FL_Map* fl_map_new(void);
FL_Map* fl_map_set(FL_Map* m, void* key, fl_int64 key_len, void* val);
FL_Option_ptr fl_map_get(FL_Map* m, void* key, fl_int64 key_len);
fl_bool fl_map_has(FL_Map* m, void* key, fl_int64 key_len);
fl_int64 fl_map_len(FL_Map* m);
void    fl_map_retain(FL_Map* m);
void    fl_map_release(FL_Map* m);

FL_Set* fl_set_new(void);
fl_bool fl_set_add(FL_Set* s, void* key, fl_int64 key_len);
fl_bool fl_set_has(FL_Set* s, void* key, fl_int64 key_len);
fl_bool fl_set_remove(FL_Set* s, void* key, fl_int64 key_len);
fl_int64 fl_set_len(FL_Set* s);
void    fl_set_retain(FL_Set* s);
void    fl_set_release(FL_Set* s);
```

String keys: pass `s->data` as key and `s->len` as key_len.

**Value-type boxing for maps:** Maps store values as `void*`. When the value
type `V` in `map<string, V>` is a value type (int, float, bool, byte), the
lowering inserts `fl_box_<type>(val)` calls for `map.set` arguments and
`fl_opt_unbox_<type>(result)` calls to repack `map.get` results from
`FL_Option_ptr` to the correct typed option struct. The box/unbox helpers use
`memcpy`-based type punning (well-defined in C99+) for zero-cost round-tripping
through `void*`.

---

## Panic Functions

These terminate the program with a message to stderr. Use them in generated code for conditions the spec says are runtime panics:

```c
void fl_panic(const char* msg);          /* generic: prints msg and exits 1 */
void fl_panic_overflow(void);            /* "OverflowError" */
void fl_panic_divzero(void);             /* "DivisionByZeroError" */
void fl_panic_oob(void);                 /* "IndexOutOfBoundsError" */
```

The spec defines exactly which conditions trigger each panic — do not add new panic conditions not defined in the spec.

---

## I/O Functions

```c
void       fl_print(FL_String* s);
void       fl_println(FL_String* s);
void       fl_eprint(FL_String* s);
void       fl_eprintln(FL_String* s);
FL_Stream* fl_stdin_stream(void);         /* stream<byte> */
FL_Option_ptr fl_read_line(void);        /* option<FL_String*> */
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
