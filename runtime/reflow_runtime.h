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
 *
 * Integer arithmetic that can overflow MUST use these macros.
 * Never emit plain + for integer addition in generated code.
 * ======================================================================== */

#define RF_CHECKED_ADD(a, b, result) \
    do { if (__builtin_add_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)

#define RF_CHECKED_SUB(a, b, result) \
    do { if (__builtin_sub_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)

#define RF_CHECKED_MUL(a, b, result) \
    do { if (__builtin_mul_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)

/* Integer division — caller must check for zero before calling */
#define RF_CHECKED_DIV(a, b, result) \
    do { if ((b) == 0) rf_panic_divzero(); *(result) = (a) / (b); } while(0)

#define RF_CHECKED_MOD(a, b, result) \
    do { if ((b) == 0) rf_panic_divzero(); *(result) = (a) % (b); } while(0)

#endif /* REFLOW_RUNTIME_H */
