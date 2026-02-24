/*
 * C-level tests for fl_string_to_bytes and fl_string_from_bytes.
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: fl_string_to_bytes on "hello"
 * ======================================================================== */

static void test_to_bytes_hello(void) {
    TEST(to_bytes_hello);

    FL_String* s = fl_string_from_cstr("hello");
    FL_Array* arr = fl_string_to_bytes(s);

    assert(fl_array_len(arr) == 5);

    fl_byte expected[] = {'h', 'e', 'l', 'l', 'o'};
    for (fl_int64 i = 0; i < 5; i++) {
        fl_byte* bp = (fl_byte*)fl_array_get_ptr(arr, i);
        assert(*bp == expected[i]);
    }

    fl_array_release(arr);
    fl_string_release(s);
    PASS();
}

/* ========================================================================
 * Test 2: fl_string_to_bytes on empty string
 * ======================================================================== */

static void test_to_bytes_empty(void) {
    TEST(to_bytes_empty);

    FL_String* s = fl_string_from_cstr("");
    FL_Array* arr = fl_string_to_bytes(s);

    assert(fl_array_len(arr) == 0);

    fl_array_release(arr);
    fl_string_release(s);
    PASS();
}

/* ========================================================================
 * Test 3: Round-trip: string -> bytes -> string
 * ======================================================================== */

static void test_round_trip(void) {
    TEST(round_trip_to_bytes_from_bytes);

    FL_String* original = fl_string_from_cstr("Hello, Flow!");
    FL_Array* bytes = fl_string_to_bytes(original);
    FL_String* restored = fl_string_from_bytes(bytes);

    assert(fl_string_eq(original, restored));

    fl_string_release(restored);
    fl_array_release(bytes);
    fl_string_release(original);
    PASS();
}

/* ========================================================================
 * Test 4: fl_string_from_bytes on known byte values
 * ======================================================================== */

static void test_from_bytes_known(void) {
    TEST(from_bytes_known_values);

    fl_byte data[] = {'R', 'e', 'F', 'l', 'o', 'w'};
    FL_Array* arr = fl_array_new(6, sizeof(fl_byte), data);
    FL_String* s = fl_string_from_bytes(arr);

    FL_String* expected = fl_string_from_cstr("Flow");
    assert(fl_string_eq(s, expected));

    fl_string_release(expected);
    fl_string_release(s);
    fl_array_release(arr);
    PASS();
}

/* ========================================================================
 * Test 5: to_bytes produces an independent copy
 * ======================================================================== */

static void test_to_bytes_independent_copy(void) {
    TEST(to_bytes_independent_copy);

    FL_String* s = fl_string_from_cstr("test");
    FL_Array* arr = fl_string_to_bytes(s);

    /* Verify the data pointer is different (independent copy) */
    assert(arr->data != (void*)s->data);

    /* Verify the content is the same */
    assert(memcmp(arr->data, s->data, 4) == 0);

    fl_array_release(arr);
    fl_string_release(s);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("fl_string_to_bytes / fl_string_from_bytes tests\n");
    printf("================================================\n");

    test_to_bytes_hello();
    test_to_bytes_empty();
    test_round_trip();
    test_from_bytes_known();
    test_to_bytes_independent_copy();

    printf("================================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
