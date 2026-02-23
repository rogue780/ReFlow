/*
 * C-level tests for the JSON runtime module (stdlib/json).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
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

    RF_String* input = rf_string_from_cstr("null");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_is_null(val) == rf_true);
    assert(rf_json_type_tag(val) == RF_JSON_NULL);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 2: parse true
 * ======================================================================== */

static void test_parse_true(void) {
    TEST(parse_true);

    RF_String* input = rf_string_from_cstr("true");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_BOOL);

    RF_Option_bool b = rf_json_as_bool(val);
    assert(b.tag == 1);
    assert(b.value == rf_true);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 3: parse false
 * ======================================================================== */

static void test_parse_false(void) {
    TEST(parse_false);

    RF_String* input = rf_string_from_cstr("false");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_BOOL);

    RF_Option_bool b = rf_json_as_bool(val);
    assert(b.tag == 1);
    assert(b.value == rf_false);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 4: parse integer
 * ======================================================================== */

static void test_parse_integer(void) {
    TEST(parse_integer);

    RF_String* input = rf_string_from_cstr("42");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_INT);

    RF_Option_int64 i = rf_json_as_int(val);
    assert(i.tag == 1);
    assert(i.value == 42);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 5: parse negative integer
 * ======================================================================== */

static void test_parse_negative_integer(void) {
    TEST(parse_negative_integer);

    RF_String* input = rf_string_from_cstr("-123");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_INT);

    RF_Option_int64 i = rf_json_as_int(val);
    assert(i.tag == 1);
    assert(i.value == -123);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 6: parse float
 * ======================================================================== */

static void test_parse_float(void) {
    TEST(parse_float);

    RF_String* input = rf_string_from_cstr("3.14");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_FLOAT);

    RF_Option_float f = rf_json_as_float(val);
    assert(f.tag == 1);
    assert(fabs(f.value - 3.14) < 0.001);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 7: parse string
 * ======================================================================== */

static void test_parse_string(void) {
    TEST(parse_string);

    RF_String* input = rf_string_from_cstr("\"hello\"");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_STRING);

    RF_Option_ptr s = rf_json_as_string(val);
    assert(s.tag == 1);
    RF_String* str = (RF_String*)s.value;
    RF_String* expected = rf_string_from_cstr("hello");
    assert(rf_string_eq(str, expected) == rf_true);

    rf_string_release(expected);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 8: parse string with escape sequences
 * ======================================================================== */

static void test_parse_string_escapes(void) {
    TEST(parse_string_escapes);

    RF_String* input = rf_string_from_cstr("\"hello\\nworld\"");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    RF_Option_ptr s = rf_json_as_string(val);
    assert(s.tag == 1);
    RF_String* str = (RF_String*)s.value;
    RF_String* expected = rf_string_from_cstr("hello\nworld");
    assert(rf_string_eq(str, expected) == rf_true);

    rf_string_release(expected);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 9: parse empty array
 * ======================================================================== */

static void test_parse_empty_array(void) {
    TEST(parse_empty_array);

    RF_String* input = rf_string_from_cstr("[]");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_ARRAY);

    RF_Option_ptr a = rf_json_as_array(val);
    assert(a.tag == 1);
    RF_Array* arr = (RF_Array*)a.value;
    assert(rf_array_len(arr) == 0);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 10: parse integer array
 * ======================================================================== */

static void test_parse_int_array(void) {
    TEST(parse_int_array);

    RF_String* input = rf_string_from_cstr("[1,2,3]");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_ARRAY);

    RF_Option_ptr a = rf_json_as_array(val);
    assert(a.tag == 1);
    RF_Array* arr = (RF_Array*)a.value;
    assert(rf_array_len(arr) == 3);

    /* Check first element */
    RF_Option_ptr e0 = rf_json_get_index(val, 0);
    assert(e0.tag == 1);
    RF_Option_int64 i0 = rf_json_as_int((RF_JsonValue*)e0.value);
    assert(i0.tag == 1);
    assert(i0.value == 1);

    /* Check third element */
    RF_Option_ptr e2 = rf_json_get_index(val, 2);
    assert(e2.tag == 1);
    RF_Option_int64 i2 = rf_json_as_int((RF_JsonValue*)e2.value);
    assert(i2.tag == 1);
    assert(i2.value == 3);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 11: parse empty object
 * ======================================================================== */

static void test_parse_empty_object(void) {
    TEST(parse_empty_object);

    RF_String* input = rf_string_from_cstr("{}");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_OBJECT);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 12: parse simple object
 * ======================================================================== */

static void test_parse_simple_object(void) {
    TEST(parse_simple_object);

    RF_String* input = rf_string_from_cstr("{\"key\":\"value\"}");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_OBJECT);

    RF_String* key = rf_string_from_cstr("key");
    RF_Option_ptr got = rf_json_get(val, key);
    assert(got.tag == 1);
    RF_JsonValue* child = (RF_JsonValue*)got.value;
    RF_Option_ptr s = rf_json_as_string(child);
    assert(s.tag == 1);
    RF_String* str = (RF_String*)s.value;
    RF_String* expected = rf_string_from_cstr("value");
    assert(rf_string_eq(str, expected) == rf_true);

    rf_string_release(expected);
    rf_string_release(key);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 13: parse nested object
 * ======================================================================== */

static void test_parse_nested_object(void) {
    TEST(parse_nested_object);

    RF_String* input = rf_string_from_cstr("{\"a\":{\"b\":1}}");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    RF_String* key_a = rf_string_from_cstr("a");
    RF_Option_ptr got_a = rf_json_get(val, key_a);
    assert(got_a.tag == 1);
    RF_JsonValue* inner = (RF_JsonValue*)got_a.value;
    assert(rf_json_type_tag(inner) == RF_JSON_OBJECT);

    RF_String* key_b = rf_string_from_cstr("b");
    RF_Option_ptr got_b = rf_json_get(inner, key_b);
    assert(got_b.tag == 1);
    RF_JsonValue* b_val = (RF_JsonValue*)got_b.value;
    RF_Option_int64 i = rf_json_as_int(b_val);
    assert(i.tag == 1);
    assert(i.value == 1);

    rf_string_release(key_b);
    rf_string_release(key_a);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 14: parse mixed array
 * ======================================================================== */

static void test_parse_mixed_array(void) {
    TEST(parse_mixed_array);

    RF_String* input = rf_string_from_cstr("[1, \"two\", true, null]");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    /* Element 0: integer 1 */
    RF_Option_ptr e0 = rf_json_get_index(val, 0);
    assert(e0.tag == 1);
    assert(rf_json_type_tag((RF_JsonValue*)e0.value) == RF_JSON_INT);

    /* Element 1: string "two" */
    RF_Option_ptr e1 = rf_json_get_index(val, 1);
    assert(e1.tag == 1);
    assert(rf_json_type_tag((RF_JsonValue*)e1.value) == RF_JSON_STRING);

    /* Element 2: bool true */
    RF_Option_ptr e2 = rf_json_get_index(val, 2);
    assert(e2.tag == 1);
    assert(rf_json_type_tag((RF_JsonValue*)e2.value) == RF_JSON_BOOL);

    /* Element 3: null */
    RF_Option_ptr e3 = rf_json_get_index(val, 3);
    assert(e3.tag == 1);
    assert(rf_json_is_null((RF_JsonValue*)e3.value) == rf_true);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 15: serialize null
 * ======================================================================== */

static void test_serialize_null(void) {
    TEST(serialize_null);

    RF_JsonValue* val = rf_json_null();
    RF_String* s = rf_json_to_string(val);
    RF_String* expected = rf_string_from_cstr("null");
    assert(rf_string_eq(s, expected) == rf_true);

    rf_string_release(expected);
    rf_string_release(s);
    rf_json_release(val);
    PASS();
}

/* ========================================================================
 * Test 16: serialize int
 * ======================================================================== */

static void test_serialize_int(void) {
    TEST(serialize_int);

    RF_JsonValue* val = rf_json_int(42);
    RF_String* s = rf_json_to_string(val);
    RF_String* expected = rf_string_from_cstr("42");
    assert(rf_string_eq(s, expected) == rf_true);

    rf_string_release(expected);
    rf_string_release(s);
    rf_json_release(val);
    PASS();
}

/* ========================================================================
 * Test 17: serialize string
 * ======================================================================== */

static void test_serialize_string(void) {
    TEST(serialize_string);

    RF_String* inner = rf_string_from_cstr("hi");
    RF_JsonValue* val = rf_json_string(inner);
    RF_String* s = rf_json_to_string(val);
    RF_String* expected = rf_string_from_cstr("\"hi\"");
    assert(rf_string_eq(s, expected) == rf_true);

    rf_string_release(expected);
    rf_string_release(s);
    rf_json_release(val);
    rf_string_release(inner);
    PASS();
}

/* ========================================================================
 * Test 18: serialize array
 * ======================================================================== */

static void test_serialize_array(void) {
    TEST(serialize_array);

    /* Build array [1, 2, 3] */
    RF_JsonValue* items[3];
    items[0] = rf_json_int(1);
    items[1] = rf_json_int(2);
    items[2] = rf_json_int(3);
    RF_Array* arr = rf_array_new(3, sizeof(RF_JsonValue*), items);
    RF_JsonValue* val = rf_json_array(arr);

    RF_String* s = rf_json_to_string(val);
    RF_String* expected = rf_string_from_cstr("[1,2,3]");
    assert(rf_string_eq(s, expected) == rf_true);

    rf_string_release(expected);
    rf_string_release(s);
    rf_json_release(val);
    rf_array_release(arr);
    /* Don't release items individually — the array owns them through rf_json_release */
    PASS();
}

/* ========================================================================
 * Test 19: serialize roundtrip
 * ======================================================================== */

static void test_serialize_roundtrip(void) {
    TEST(serialize_roundtrip);

    RF_String* input = rf_string_from_cstr("{\"name\":\"test\",\"value\":42}");
    RF_Option_ptr r1 = rf_json_parse(input);
    assert(r1.tag == 1);
    RF_JsonValue* val1 = (RF_JsonValue*)r1.value;

    RF_String* serialized = rf_json_to_string(val1);

    /* Parse the serialized output again */
    RF_Option_ptr r2 = rf_json_parse(serialized);
    assert(r2.tag == 1);
    RF_JsonValue* val2 = (RF_JsonValue*)r2.value;
    assert(rf_json_type_tag(val2) == RF_JSON_OBJECT);

    /* Check that key "name" still gives "test" */
    RF_String* key_name = rf_string_from_cstr("name");
    RF_Option_ptr got = rf_json_get(val2, key_name);
    assert(got.tag == 1);
    RF_Option_ptr s = rf_json_as_string((RF_JsonValue*)got.value);
    assert(s.tag == 1);
    RF_String* expected_name = rf_string_from_cstr("test");
    assert(rf_string_eq((RF_String*)s.value, expected_name) == rf_true);

    /* Check that key "value" still gives 42 */
    RF_String* key_value = rf_string_from_cstr("value");
    RF_Option_ptr got2 = rf_json_get(val2, key_value);
    assert(got2.tag == 1);
    RF_Option_int64 iv = rf_json_as_int((RF_JsonValue*)got2.value);
    assert(iv.tag == 1);
    assert(iv.value == 42);

    rf_string_release(key_value);
    rf_string_release(expected_name);
    rf_string_release(key_name);
    rf_json_release(val2);
    rf_string_release(serialized);
    rf_json_release(val1);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 20: parse invalid returns none
 * ======================================================================== */

static void test_parse_invalid_returns_none(void) {
    TEST(parse_invalid_returns_none);

    RF_String* input = rf_string_from_cstr("{bad");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 0);

    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 21: accessor type mismatch
 * ======================================================================== */

static void test_accessor_type_mismatch(void) {
    TEST(accessor_type_mismatch);

    RF_String* input = rf_string_from_cstr("\"hello\"");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    /* Try to get int from a string value */
    RF_Option_int64 i = rf_json_as_int(val);
    assert(i.tag == 0);

    /* Try to get bool from a string value */
    RF_Option_bool b = rf_json_as_bool(val);
    assert(b.tag == 0);

    /* Try to get array from a string value */
    RF_Option_ptr a = rf_json_as_array(val);
    assert(a.tag == 0);

    /* is_null on a string should be false */
    assert(rf_json_is_null(val) == rf_false);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 22: get missing key
 * ======================================================================== */

static void test_get_missing_key(void) {
    TEST(get_missing_key);

    RF_String* input = rf_string_from_cstr("{\"key\":\"value\"}");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    RF_String* missing = rf_string_from_cstr("missing");
    RF_Option_ptr got = rf_json_get(val, missing);
    assert(got.tag == 0);

    rf_string_release(missing);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 23: parse whitespace handling
 * ======================================================================== */

static void test_parse_whitespace(void) {
    TEST(parse_whitespace);

    RF_String* input = rf_string_from_cstr("  {  \"key\"  :  42  }  ");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_OBJECT);

    RF_String* key = rf_string_from_cstr("key");
    RF_Option_ptr got = rf_json_get(val, key);
    assert(got.tag == 1);
    RF_Option_int64 i = rf_json_as_int((RF_JsonValue*)got.value);
    assert(i.tag == 1);
    assert(i.value == 42);

    rf_string_release(key);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 24: get_index out of bounds
 * ======================================================================== */

static void test_get_index_oob(void) {
    TEST(get_index_oob);

    RF_String* input = rf_string_from_cstr("[1, 2]");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    RF_Option_ptr oob = rf_json_get_index(val, 5);
    assert(oob.tag == 0);

    RF_Option_ptr neg = rf_json_get_index(val, -1);
    assert(neg.tag == 0);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 25: serialize bool
 * ======================================================================== */

static void test_serialize_bool(void) {
    TEST(serialize_bool);

    RF_JsonValue* t = rf_json_bool(rf_true);
    RF_String* ts = rf_json_to_string(t);
    RF_String* expected_t = rf_string_from_cstr("true");
    assert(rf_string_eq(ts, expected_t) == rf_true);

    RF_JsonValue* f = rf_json_bool(rf_false);
    RF_String* fs = rf_json_to_string(f);
    RF_String* expected_f = rf_string_from_cstr("false");
    assert(rf_string_eq(fs, expected_f) == rf_true);

    rf_string_release(expected_f);
    rf_string_release(fs);
    rf_json_release(f);
    rf_string_release(expected_t);
    rf_string_release(ts);
    rf_json_release(t);
    PASS();
}

/* ========================================================================
 * Test 26: serialize string with escapes
 * ======================================================================== */

static void test_serialize_string_escapes(void) {
    TEST(serialize_string_escapes);

    RF_String* inner = rf_string_from_cstr("line1\nline2\ttab");
    RF_JsonValue* val = rf_json_string(inner);
    RF_String* s = rf_json_to_string(val);
    RF_String* expected = rf_string_from_cstr("\"line1\\nline2\\ttab\"");
    assert(rf_string_eq(s, expected) == rf_true);

    rf_string_release(expected);
    rf_string_release(s);
    rf_json_release(val);
    rf_string_release(inner);
    PASS();
}

/* ========================================================================
 * Test 27: parse scientific notation float
 * ======================================================================== */

static void test_parse_scientific_float(void) {
    TEST(parse_scientific_float);

    RF_String* input = rf_string_from_cstr("1.5e2");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_FLOAT);

    RF_Option_float f = rf_json_as_float(val);
    assert(f.tag == 1);
    assert(fabs(f.value - 150.0) < 0.001);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 28: parse trailing garbage is rejected
 * ======================================================================== */

static void test_parse_trailing_garbage(void) {
    TEST(parse_trailing_garbage);

    RF_String* input = rf_string_from_cstr("42 extra");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 0);

    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 29: constructors and type_tag
 * ======================================================================== */

static void test_constructor_type_tags(void) {
    TEST(constructor_type_tags);

    RF_JsonValue* n = rf_json_null();
    assert(rf_json_type_tag(n) == RF_JSON_NULL);
    rf_json_release(n);

    RF_JsonValue* b = rf_json_bool(rf_true);
    assert(rf_json_type_tag(b) == RF_JSON_BOOL);
    rf_json_release(b);

    RF_JsonValue* i = rf_json_int(10);
    assert(rf_json_type_tag(i) == RF_JSON_INT);
    rf_json_release(i);

    RF_JsonValue* f = rf_json_float(1.5);
    assert(rf_json_type_tag(f) == RF_JSON_FLOAT);
    rf_json_release(f);

    RF_String* s_val = rf_string_from_cstr("test");
    RF_JsonValue* s = rf_json_string(s_val);
    assert(rf_json_type_tag(s) == RF_JSON_STRING);
    rf_json_release(s);
    rf_string_release(s_val);

    PASS();
}

/* ========================================================================
 * Test 30: parse unicode escape
 * ======================================================================== */

static void test_parse_unicode_escape(void) {
    TEST(parse_unicode_escape);

    /* \u0041 is 'A' */
    RF_String* input = rf_string_from_cstr("\"\\u0041\"");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    RF_Option_ptr s = rf_json_as_string(val);
    assert(s.tag == 1);
    RF_String* str = (RF_String*)s.value;
    RF_String* expected = rf_string_from_cstr("A");
    assert(rf_string_eq(str, expected) == rf_true);

    rf_string_release(expected);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 31: pretty print
 * ======================================================================== */

static void test_pretty_print(void) {
    TEST(pretty_print);

    RF_String* input = rf_string_from_cstr("{\"a\":1}");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;

    RF_String* pretty = rf_json_to_string_pretty(val, 2);
    /* Should contain newlines and indentation */
    assert(rf_string_contains(pretty, rf_string_from_cstr("\n")) == rf_true);
    assert(rf_string_contains(pretty, rf_string_from_cstr("  ")) == rf_true);

    rf_string_release(pretty);
    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Test 32: parse zero
 * ======================================================================== */

static void test_parse_zero(void) {
    TEST(parse_zero);

    RF_String* input = rf_string_from_cstr("0");
    RF_Option_ptr result = rf_json_parse(input);
    assert(result.tag == 1);
    RF_JsonValue* val = (RF_JsonValue*)result.value;
    assert(rf_json_type_tag(val) == RF_JSON_INT);

    RF_Option_int64 i = rf_json_as_int(val);
    assert(i.tag == 1);
    assert(i.value == 0);

    rf_json_release(val);
    rf_string_release(input);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("RF_JsonValue tests\n");
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
