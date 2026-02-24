/*
 * C-level tests for the JSON runtime module (stdlib/json).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: parse null
 * ======================================================================== */

static void test_parse_null(void) {
    TEST(parse_null);

    FL_String* input = fl_string_from_cstr("null");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_is_null(val) == fl_true);
    assert(fl_json_type_tag(val) == FL_JSON_NULL);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 2: parse true
 * ======================================================================== */

static void test_parse_true(void) {
    TEST(parse_true);

    FL_String* input = fl_string_from_cstr("true");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_BOOL);

    FL_Option_bool b = fl_json_as_bool(val);
    assert(b.tag == 1);
    assert(b.value == fl_true);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 3: parse false
 * ======================================================================== */

static void test_parse_false(void) {
    TEST(parse_false);

    FL_String* input = fl_string_from_cstr("false");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_BOOL);

    FL_Option_bool b = fl_json_as_bool(val);
    assert(b.tag == 1);
    assert(b.value == fl_false);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 4: parse integer
 * ======================================================================== */

static void test_parse_integer(void) {
    TEST(parse_integer);

    FL_String* input = fl_string_from_cstr("42");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_INT);

    FL_Option_int64 i = fl_json_as_int(val);
    assert(i.tag == 1);
    assert(i.value == 42);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 5: parse negative integer
 * ======================================================================== */

static void test_parse_negative_integer(void) {
    TEST(parse_negative_integer);

    FL_String* input = fl_string_from_cstr("-123");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_INT);

    FL_Option_int64 i = fl_json_as_int(val);
    assert(i.tag == 1);
    assert(i.value == -123);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 6: parse float
 * ======================================================================== */

static void test_parse_float(void) {
    TEST(parse_float);

    FL_String* input = fl_string_from_cstr("3.14");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_FLOAT);

    FL_Option_float f = fl_json_as_float(val);
    assert(f.tag == 1);
    assert(fabs(f.value - 3.14) < 0.001);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 7: parse string
 * ======================================================================== */

static void test_parse_string(void) {
    TEST(parse_string);

    FL_String* input = fl_string_from_cstr("\"hello\"");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_STRING);

    FL_Option_ptr s = fl_json_as_string(val);
    assert(s.tag == 1);
    FL_String* str = (FL_String*)s.value;
    FL_String* expected = fl_string_from_cstr("hello");
    assert(fl_string_eq(str, expected) == fl_true);

    fl_string_release(expected);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 8: parse string with escape sequences
 * ======================================================================== */

static void test_parse_string_escapes(void) {
    TEST(parse_string_escapes);

    FL_String* input = fl_string_from_cstr("\"hello\\nworld\"");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    FL_Option_ptr s = fl_json_as_string(val);
    assert(s.tag == 1);
    FL_String* str = (FL_String*)s.value;
    FL_String* expected = fl_string_from_cstr("hello\nworld");
    assert(fl_string_eq(str, expected) == fl_true);

    fl_string_release(expected);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 9: parse empty array
 * ======================================================================== */

static void test_parse_empty_array(void) {
    TEST(parse_empty_array);

    FL_String* input = fl_string_from_cstr("[]");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_ARRAY);

    FL_Option_ptr a = fl_json_as_array(val);
    assert(a.tag == 1);
    FL_Array* arr = (FL_Array*)a.value;
    assert(fl_array_len(arr) == 0);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 10: parse integer array
 * ======================================================================== */

static void test_parse_int_array(void) {
    TEST(parse_int_array);

    FL_String* input = fl_string_from_cstr("[1,2,3]");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_ARRAY);

    FL_Option_ptr a = fl_json_as_array(val);
    assert(a.tag == 1);
    FL_Array* arr = (FL_Array*)a.value;
    assert(fl_array_len(arr) == 3);

    /* Check first element */
    FL_Option_ptr e0 = fl_json_get_index(val, 0);
    assert(e0.tag == 1);
    FL_Option_int64 i0 = fl_json_as_int((FL_JsonValue*)e0.value);
    assert(i0.tag == 1);
    assert(i0.value == 1);

    /* Check third element */
    FL_Option_ptr e2 = fl_json_get_index(val, 2);
    assert(e2.tag == 1);
    FL_Option_int64 i2 = fl_json_as_int((FL_JsonValue*)e2.value);
    assert(i2.tag == 1);
    assert(i2.value == 3);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 11: parse empty object
 * ======================================================================== */

static void test_parse_empty_object(void) {
    TEST(parse_empty_object);

    FL_String* input = fl_string_from_cstr("{}");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_OBJECT);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 12: parse simple object
 * ======================================================================== */

static void test_parse_simple_object(void) {
    TEST(parse_simple_object);

    FL_String* input = fl_string_from_cstr("{\"key\":\"value\"}");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_OBJECT);

    FL_String* key = fl_string_from_cstr("key");
    FL_Option_ptr got = fl_json_get(val, key);
    assert(got.tag == 1);
    FL_JsonValue* child = (FL_JsonValue*)got.value;
    FL_Option_ptr s = fl_json_as_string(child);
    assert(s.tag == 1);
    FL_String* str = (FL_String*)s.value;
    FL_String* expected = fl_string_from_cstr("value");
    assert(fl_string_eq(str, expected) == fl_true);

    fl_string_release(expected);
    fl_string_release(key);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 13: parse nested object
 * ======================================================================== */

static void test_parse_nested_object(void) {
    TEST(parse_nested_object);

    FL_String* input = fl_string_from_cstr("{\"a\":{\"b\":1}}");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    FL_String* key_a = fl_string_from_cstr("a");
    FL_Option_ptr got_a = fl_json_get(val, key_a);
    assert(got_a.tag == 1);
    FL_JsonValue* inner = (FL_JsonValue*)got_a.value;
    assert(fl_json_type_tag(inner) == FL_JSON_OBJECT);

    FL_String* key_b = fl_string_from_cstr("b");
    FL_Option_ptr got_b = fl_json_get(inner, key_b);
    assert(got_b.tag == 1);
    FL_JsonValue* b_val = (FL_JsonValue*)got_b.value;
    FL_Option_int64 i = fl_json_as_int(b_val);
    assert(i.tag == 1);
    assert(i.value == 1);

    fl_string_release(key_b);
    fl_string_release(key_a);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 14: parse mixed array
 * ======================================================================== */

static void test_parse_mixed_array(void) {
    TEST(parse_mixed_array);

    FL_String* input = fl_string_from_cstr("[1, \"two\", true, null]");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    /* Element 0: integer 1 */
    FL_Option_ptr e0 = fl_json_get_index(val, 0);
    assert(e0.tag == 1);
    assert(fl_json_type_tag((FL_JsonValue*)e0.value) == FL_JSON_INT);

    /* Element 1: string "two" */
    FL_Option_ptr e1 = fl_json_get_index(val, 1);
    assert(e1.tag == 1);
    assert(fl_json_type_tag((FL_JsonValue*)e1.value) == FL_JSON_STRING);

    /* Element 2: bool true */
    FL_Option_ptr e2 = fl_json_get_index(val, 2);
    assert(e2.tag == 1);
    assert(fl_json_type_tag((FL_JsonValue*)e2.value) == FL_JSON_BOOL);

    /* Element 3: null */
    FL_Option_ptr e3 = fl_json_get_index(val, 3);
    assert(e3.tag == 1);
    assert(fl_json_is_null((FL_JsonValue*)e3.value) == fl_true);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 15: serialize null
 * ======================================================================== */

static void test_serialize_null(void) {
    TEST(serialize_null);

    FL_JsonValue* val = fl_json_null();
    FL_String* s = fl_json_to_string(val);
    FL_String* expected = fl_string_from_cstr("null");
    assert(fl_string_eq(s, expected) == fl_true);

    fl_string_release(expected);
    fl_string_release(s);
    fl_json_release(val);
    PASS();
}

/* ========================================================================
 * Test 16: serialize int
 * ======================================================================== */

static void test_serialize_int(void) {
    TEST(serialize_int);

    FL_JsonValue* val = fl_json_int(42);
    FL_String* s = fl_json_to_string(val);
    FL_String* expected = fl_string_from_cstr("42");
    assert(fl_string_eq(s, expected) == fl_true);

    fl_string_release(expected);
    fl_string_release(s);
    fl_json_release(val);
    PASS();
}

/* ========================================================================
 * Test 17: serialize string
 * ======================================================================== */

static void test_serialize_string(void) {
    TEST(serialize_string);

    FL_String* inner = fl_string_from_cstr("hi");
    FL_JsonValue* val = fl_json_string(inner);
    FL_String* s = fl_json_to_string(val);
    FL_String* expected = fl_string_from_cstr("\"hi\"");
    assert(fl_string_eq(s, expected) == fl_true);

    fl_string_release(expected);
    fl_string_release(s);
    fl_json_release(val);
    fl_string_release(inner);
    PASS();
}

/* ========================================================================
 * Test 18: serialize array
 * ======================================================================== */

static void test_serialize_array(void) {
    TEST(serialize_array);

    /* Build array [1, 2, 3] */
    FL_JsonValue* items[3];
    items[0] = fl_json_int(1);
    items[1] = fl_json_int(2);
    items[2] = fl_json_int(3);
    FL_Array* arr = fl_array_new(3, sizeof(FL_JsonValue*), items);
    FL_JsonValue* val = fl_json_array(arr);

    FL_String* s = fl_json_to_string(val);
    FL_String* expected = fl_string_from_cstr("[1,2,3]");
    assert(fl_string_eq(s, expected) == fl_true);

    fl_string_release(expected);
    fl_string_release(s);
    fl_json_release(val);
    fl_array_release(arr);
    /* Don't release items individually — the array owns them through fl_json_release */
    PASS();
}

/* ========================================================================
 * Test 19: serialize roundtrip
 * ======================================================================== */

static void test_serialize_roundtrip(void) {
    TEST(serialize_roundtrip);

    FL_String* input = fl_string_from_cstr("{\"name\":\"test\",\"value\":42}");
    FL_Option_ptr r1 = fl_json_parse(input);
    assert(r1.tag == 1);
    FL_JsonValue* val1 = (FL_JsonValue*)r1.value;

    FL_String* serialized = fl_json_to_string(val1);

    /* Parse the serialized output again */
    FL_Option_ptr r2 = fl_json_parse(serialized);
    assert(r2.tag == 1);
    FL_JsonValue* val2 = (FL_JsonValue*)r2.value;
    assert(fl_json_type_tag(val2) == FL_JSON_OBJECT);

    /* Check that key "name" still gives "test" */
    FL_String* key_name = fl_string_from_cstr("name");
    FL_Option_ptr got = fl_json_get(val2, key_name);
    assert(got.tag == 1);
    FL_Option_ptr s = fl_json_as_string((FL_JsonValue*)got.value);
    assert(s.tag == 1);
    FL_String* expected_name = fl_string_from_cstr("test");
    assert(fl_string_eq((FL_String*)s.value, expected_name) == fl_true);

    /* Check that key "value" still gives 42 */
    FL_String* key_value = fl_string_from_cstr("value");
    FL_Option_ptr got2 = fl_json_get(val2, key_value);
    assert(got2.tag == 1);
    FL_Option_int64 iv = fl_json_as_int((FL_JsonValue*)got2.value);
    assert(iv.tag == 1);
    assert(iv.value == 42);

    fl_string_release(key_value);
    fl_string_release(expected_name);
    fl_string_release(key_name);
    fl_json_release(val2);
    fl_string_release(serialized);
    fl_json_release(val1);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 20: parse invalid returns none
 * ======================================================================== */

static void test_parse_invalid_returns_none(void) {
    TEST(parse_invalid_returns_none);

    FL_String* input = fl_string_from_cstr("{bad");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 0);

    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 21: accessor type mismatch
 * ======================================================================== */

static void test_accessor_type_mismatch(void) {
    TEST(accessor_type_mismatch);

    FL_String* input = fl_string_from_cstr("\"hello\"");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    /* Try to get int from a string value */
    FL_Option_int64 i = fl_json_as_int(val);
    assert(i.tag == 0);

    /* Try to get bool from a string value */
    FL_Option_bool b = fl_json_as_bool(val);
    assert(b.tag == 0);

    /* Try to get array from a string value */
    FL_Option_ptr a = fl_json_as_array(val);
    assert(a.tag == 0);

    /* is_null on a string should be false */
    assert(fl_json_is_null(val) == fl_false);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 22: get missing key
 * ======================================================================== */

static void test_get_missing_key(void) {
    TEST(get_missing_key);

    FL_String* input = fl_string_from_cstr("{\"key\":\"value\"}");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    FL_String* missing = fl_string_from_cstr("missing");
    FL_Option_ptr got = fl_json_get(val, missing);
    assert(got.tag == 0);

    fl_string_release(missing);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 23: parse whitespace handling
 * ======================================================================== */

static void test_parse_whitespace(void) {
    TEST(parse_whitespace);

    FL_String* input = fl_string_from_cstr("  {  \"key\"  :  42  }  ");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_OBJECT);

    FL_String* key = fl_string_from_cstr("key");
    FL_Option_ptr got = fl_json_get(val, key);
    assert(got.tag == 1);
    FL_Option_int64 i = fl_json_as_int((FL_JsonValue*)got.value);
    assert(i.tag == 1);
    assert(i.value == 42);

    fl_string_release(key);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 24: get_index out of bounds
 * ======================================================================== */

static void test_get_index_oob(void) {
    TEST(get_index_oob);

    FL_String* input = fl_string_from_cstr("[1, 2]");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    FL_Option_ptr oob = fl_json_get_index(val, 5);
    assert(oob.tag == 0);

    FL_Option_ptr neg = fl_json_get_index(val, -1);
    assert(neg.tag == 0);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 25: serialize bool
 * ======================================================================== */

static void test_serialize_bool(void) {
    TEST(serialize_bool);

    FL_JsonValue* t = fl_json_bool(fl_true);
    FL_String* ts = fl_json_to_string(t);
    FL_String* expected_t = fl_string_from_cstr("true");
    assert(fl_string_eq(ts, expected_t) == fl_true);

    FL_JsonValue* f = fl_json_bool(fl_false);
    FL_String* fs = fl_json_to_string(f);
    FL_String* expected_f = fl_string_from_cstr("false");
    assert(fl_string_eq(fs, expected_f) == fl_true);

    fl_string_release(expected_f);
    fl_string_release(fs);
    fl_json_release(f);
    fl_string_release(expected_t);
    fl_string_release(ts);
    fl_json_release(t);
    PASS();
}

/* ========================================================================
 * Test 26: serialize string with escapes
 * ======================================================================== */

static void test_serialize_string_escapes(void) {
    TEST(serialize_string_escapes);

    FL_String* inner = fl_string_from_cstr("line1\nline2\ttab");
    FL_JsonValue* val = fl_json_string(inner);
    FL_String* s = fl_json_to_string(val);
    FL_String* expected = fl_string_from_cstr("\"line1\\nline2\\ttab\"");
    assert(fl_string_eq(s, expected) == fl_true);

    fl_string_release(expected);
    fl_string_release(s);
    fl_json_release(val);
    fl_string_release(inner);
    PASS();
}

/* ========================================================================
 * Test 27: parse scientific notation float
 * ======================================================================== */

static void test_parse_scientific_float(void) {
    TEST(parse_scientific_float);

    FL_String* input = fl_string_from_cstr("1.5e2");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_FLOAT);

    FL_Option_float f = fl_json_as_float(val);
    assert(f.tag == 1);
    assert(fabs(f.value - 150.0) < 0.001);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 28: parse trailing garbage is rejected
 * ======================================================================== */

static void test_parse_trailing_garbage(void) {
    TEST(parse_trailing_garbage);

    FL_String* input = fl_string_from_cstr("42 extra");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 0);

    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 29: constructors and type_tag
 * ======================================================================== */

static void test_constructor_type_tags(void) {
    TEST(constructor_type_tags);

    FL_JsonValue* n = fl_json_null();
    assert(fl_json_type_tag(n) == FL_JSON_NULL);
    fl_json_release(n);

    FL_JsonValue* b = fl_json_bool(fl_true);
    assert(fl_json_type_tag(b) == FL_JSON_BOOL);
    fl_json_release(b);

    FL_JsonValue* i = fl_json_int(10);
    assert(fl_json_type_tag(i) == FL_JSON_INT);
    fl_json_release(i);

    FL_JsonValue* f = fl_json_float(1.5);
    assert(fl_json_type_tag(f) == FL_JSON_FLOAT);
    fl_json_release(f);

    FL_String* s_val = fl_string_from_cstr("test");
    FL_JsonValue* s = fl_json_string(s_val);
    assert(fl_json_type_tag(s) == FL_JSON_STRING);
    fl_json_release(s);
    fl_string_release(s_val);

    PASS();
}

/* ========================================================================
 * Test 30: parse unicode escape
 * ======================================================================== */

static void test_parse_unicode_escape(void) {
    TEST(parse_unicode_escape);

    /* \u0041 is 'A' */
    FL_String* input = fl_string_from_cstr("\"\\u0041\"");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    FL_Option_ptr s = fl_json_as_string(val);
    assert(s.tag == 1);
    FL_String* str = (FL_String*)s.value;
    FL_String* expected = fl_string_from_cstr("A");
    assert(fl_string_eq(str, expected) == fl_true);

    fl_string_release(expected);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 31: pretty print
 * ======================================================================== */

static void test_pretty_print(void) {
    TEST(pretty_print);

    FL_String* input = fl_string_from_cstr("{\"a\":1}");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;

    FL_String* pretty = fl_json_to_string_pretty(val, 2);
    /* Should contain newlines and indentation */
    assert(fl_string_contains(pretty, fl_string_from_cstr("\n")) == fl_true);
    assert(fl_string_contains(pretty, fl_string_from_cstr("  ")) == fl_true);

    fl_string_release(pretty);
    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 32: parse zero
 * ======================================================================== */

static void test_parse_zero(void) {
    TEST(parse_zero);

    FL_String* input = fl_string_from_cstr("0");
    FL_Option_ptr result = fl_json_parse(input);
    assert(result.tag == 1);
    FL_JsonValue* val = (FL_JsonValue*)result.value;
    assert(fl_json_type_tag(val) == FL_JSON_INT);

    FL_Option_int64 i = fl_json_as_int(val);
    assert(i.tag == 1);
    assert(i.value == 0);

    fl_json_release(val);
    fl_string_release(input);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("FL_JsonValue tests\n");
    printf("========================================\n");

    test_parse_null();
    test_parse_true();
    test_parse_false();
    test_parse_integer();
    test_parse_negative_integer();
    test_parse_float();
    test_parse_string();
    test_parse_string_escapes();
    test_parse_empty_array();
    test_parse_int_array();
    test_parse_empty_object();
    test_parse_simple_object();
    test_parse_nested_object();
    test_parse_mixed_array();
    test_serialize_null();
    test_serialize_int();
    test_serialize_string();
    test_serialize_array();
    test_serialize_roundtrip();
    test_parse_invalid_returns_none();
    test_accessor_type_mismatch();
    test_get_missing_key();
    test_parse_whitespace();
    test_get_index_oob();
    test_serialize_bool();
    test_serialize_string_escapes();
    test_parse_scientific_float();
    test_parse_trailing_garbage();
    test_constructor_type_tags();
    test_parse_unicode_escape();
    test_pretty_print();
    test_parse_zero();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
