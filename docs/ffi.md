# Foreign Function Interface (FFI)

Flow's FFI lets any `.flow` module bind C libraries using three `extern`
declaration forms, plus the `ptr` builtin type for raw pointer marshaling.

## Quick Example

```flow
module crypto

extern lib "ssl"
extern lib "crypto"
extern type SSL_CTX
extern type SSL

extern fn SSL_CTX_new():SSL_CTX?
extern fn SSL_CTX_free(ctx:SSL_CTX):none
extern fn SSL_write(ssl:SSL, buf:ptr, n:int):int

// Public API — Flow wrappers
export fn create_context():SSL_CTX? {
    return SSL_CTX_new()
}

export fn write(ssl:SSL, data:string):int {
    return SSL_write(ssl, string.to_cptr(data), string.len(data))
}
```

## Declarations

### `extern lib "name"`

Links a shared library. Generates a `-l<name>` flag for the linker.

```flow
extern lib "ssl"       // -lssl
extern lib "z"         // -lz
extern lib "sqlite3"   // -lsqlite3
```

Cannot be exported — library linkage is a build concern.

### `extern type Name`

Declares an opaque C type, represented as `void*`. Flow code can pass it
around but cannot inspect its contents.

```flow
extern type SSL_CTX
extern type sqlite3
```

Can be exported: `export extern type SSL_CTX`

### `extern fn name(params):RetType`

Declares a C function by its exact name. No name mangling is applied.

```flow
extern fn abs(x:int):int
extern fn sqrt(x:float):float
extern fn SSL_CTX_new():ptr
```

An alias form allows the Flow name to differ from the C name:

```flow
extern fn "fl_sort_array_by" sort_by<T>(arr:array<T>, cmp:fn(T, T):int):array<T>
```

Generic type parameters are supported. They are used for type inference at
call sites but erased in the C call:

```flow
extern fn "fl_array_push_ptr" push<T>(arr:array<T>, val:T):array<T>
extern fn "fl_map_get_str" get<V>(m:map<string, V>, key:string):V?
```

## Type Mapping

| Flow | C | Notes |
|------|---|-------|
| `int` | `int32_t` | |
| `int64` | `int64_t` | |
| `float` | `double` | |
| `float32` | `float` | |
| `bool` | `int32_t` | 0 = false, 1 = true |
| `byte` | `uint8_t` | |
| `ptr` | `void*` | Opaque, no dereference |
| `string` | `FL_String*` | Use `string.to_cptr()` for `char*` |
| `fn(A):B` | `B (*)(A)` | Non-capturing only |

## The `ptr` Type

`ptr` is a built-in opaque type for FFI. You cannot dereference it, index
it, or do arithmetic on it. Supported operations:

```flow
let p:ptr = none                         // null pointer
let p:ptr = string.to_cptr(my_string)    // string → char*
let s:string = string.from_cptr(p, len)  // char* → string
some_extern_fn(p)                        // pass to C
```

## String Marshaling

```flow
import string

// string → raw pointer (char*)
let p:ptr = string.to_cptr(my_string)

// raw pointer + length → new string
let s:string = string.from_cptr(p, byte_count)
```

`to_cptr` returns a pointer to the string's internal data. The pointer is
valid as long as the string is alive.

`from_cptr` copies `len` bytes from the pointer into a new Flow string.

## Function Pointer Callbacks

Named, non-capturing Flow functions can be passed as C function pointer
arguments:

```flow
extern fn register_callback(cb:fn(int):int):none

fn my_handler(x:int):int {
    return x * 2
}

fn setup() {
    register_callback(my_handler)
}
```

Lambdas and closures that capture variables cannot be passed to extern
functions — the compiler will reject this.

## Best Practices

1. **Wrap extern fns.** Keep `extern` declarations private to the module.
   Export clean Flow functions with Flow-friendly types.

2. **Avoid standard C names.** Functions like `strlen`, `printf`, `malloc`
   are already declared by system headers. Binding them with Flow types
   that don't match exactly will cause C compilation errors. Wrap them
   in a small C helper instead.

3. **Use `extern type` for handles.** If a C library uses opaque struct
   pointers (e.g., `SSL*`, `sqlite3*`), declare them as `extern type`
   rather than using raw `ptr`. This gives you type safety — you can't
   accidentally pass an `SSL_CTX` where an `SSL` is expected.

4. **Group related bindings.** Put all extern declarations for one C
   library in a single module (e.g., `stdlib/ssl.flow`) with Flow
   wrappers as the public interface.
