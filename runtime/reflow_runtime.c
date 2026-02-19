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
