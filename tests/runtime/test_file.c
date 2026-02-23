/*
 * C-level tests for RF_File handle-based I/O (stdlib/file).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: Open this test file itself and read_all
 * ======================================================================== */

static void test_open_read_and_read_all(void) {
    TEST(open_read_and_read_all);

    RF_String* path = rf_string_from_cstr("tests/runtime/test_file.c");
    RF_Option_ptr opt = rf_file_open_read(path);
    assert(opt.tag == 1);

    RF_File* f = (RF_File*)opt.value;
    RF_Option_ptr content_opt = rf_file_read_all(f);
    assert(content_opt.tag == 1);

    RF_String* content = (RF_String*)content_opt.value;
    assert(content->len > 0);

    /* Verify it starts with the expected comment */
    assert(strncmp(content->data, "/*", 2) == 0);

    rf_string_release(content);
    rf_file_close(f);
    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 2: Write a string, close, open, read back, verify match
 * ======================================================================== */

static void test_open_write_and_read_back(void) {
    TEST(open_write_and_read_back);

    const char* tmp_path = "/tmp/rf_test_file_write.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* message = rf_string_from_cstr("Hello, ReFlow file handles!");

    /* Write */
    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_bool ok = rf_file_write_string(wf, message);
    assert(ok == rf_true);
    rf_file_close(wf);

    /* Read back */
    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    RF_Option_ptr content_opt = rf_file_read_all(rf_);
    assert(content_opt.tag == 1);
    RF_String* content = (RF_String*)content_opt.value;
    assert(rf_string_eq(content, message) == rf_true);

    rf_string_release(content);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(message);
    PASS();
}

/* ========================================================================
 * Test 3: read_line strips newline
 * ======================================================================== */

static void test_read_line_strips_newline(void) {
    TEST(read_line_strips_newline);

    const char* tmp_path = "/tmp/rf_test_file_readline.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("hello\nworld\n");

    /* Write data */
    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    /* Read lines */
    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;

    RF_Option_ptr l1 = rf_file_read_line(rf_);
    assert(l1.tag == 1);
    RF_String* line1 = (RF_String*)l1.value;
    RF_String* expected1 = rf_string_from_cstr("hello");
    assert(rf_string_eq(line1, expected1) == rf_true);

    RF_Option_ptr l2 = rf_file_read_line(rf_);
    assert(l2.tag == 1);
    RF_String* line2 = (RF_String*)l2.value;
    RF_String* expected2 = rf_string_from_cstr("world");
    assert(rf_string_eq(line2, expected2) == rf_true);

    rf_string_release(line1);
    rf_string_release(line2);
    rf_string_release(expected1);
    rf_string_release(expected2);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 4: read_line at EOF returns NONE
 * ======================================================================== */

static void test_read_line_eof_returns_none(void) {
    TEST(read_line_eof_returns_none);

    const char* tmp_path = "/tmp/rf_test_file_eof.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("only\n");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;

    RF_Option_ptr l1 = rf_file_read_line(rf_);
    assert(l1.tag == 1);
    RF_String* line1 = (RF_String*)l1.value;
    rf_string_release(line1);

    /* Next read should return NONE */
    RF_Option_ptr l2 = rf_file_read_line(rf_);
    assert(l2.tag == 0);

    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 5: read_bytes exact count
 * ======================================================================== */

static void test_read_bytes_exact(void) {
    TEST(read_bytes_exact);

    const char* tmp_path = "/tmp/rf_test_file_readbytes.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("ABCDEFGHIJ");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;

    RF_Option_ptr bopt = rf_file_read_bytes(rf_, 5);
    assert(bopt.tag == 1);
    RF_Array* arr = (RF_Array*)bopt.value;
    assert(arr->len == 5);
    rf_byte* bytes = (rf_byte*)arr->data;
    assert(bytes[0] == 'A');
    assert(bytes[4] == 'E');

    rf_array_release(arr);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 6: read_all_bytes
 * ======================================================================== */

static void test_read_all_bytes(void) {
    TEST(read_all_bytes);

    const char* tmp_path = "/tmp/rf_test_file_readallbytes.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);

    /* Write known bytes */
    rf_byte known[] = {0x00, 0x01, 0xFF, 0x42, 0x80};
    RF_Option_ptr wopt = rf_file_open_write_bytes(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    RF_Array* write_arr = rf_array_new(5, sizeof(rf_byte), known);
    rf_file_write_bytes(wf, write_arr);
    rf_file_close(wf);

    /* Read back */
    RF_Option_ptr ropt = rf_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    RF_Option_ptr bopt = rf_file_read_all_bytes(rf_);
    assert(bopt.tag == 1);
    RF_Array* arr = (RF_Array*)bopt.value;
    assert(arr->len == 5);
    rf_byte* data = (rf_byte*)arr->data;
    assert(data[0] == 0x00);
    assert(data[1] == 0x01);
    assert(data[2] == 0xFF);
    assert(data[3] == 0x42);
    assert(data[4] == 0x80);

    rf_array_release(write_arr);
    rf_array_release(arr);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 7: write_bytes from array
 * ======================================================================== */

static void test_write_bytes_from_array(void) {
    TEST(write_bytes_from_array);

    const char* tmp_path = "/tmp/rf_test_file_writebytes.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);

    rf_byte vals[] = {10, 20, 30, 40, 50};
    RF_Array* arr = rf_array_new(5, sizeof(rf_byte), vals);

    RF_Option_ptr wopt = rf_file_open_write_bytes(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_bool ok = rf_file_write_bytes(wf, arr);
    assert(ok == rf_true);
    rf_file_close(wf);

    /* Read back and verify */
    RF_Option_ptr ropt = rf_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    RF_Option_ptr bopt = rf_file_read_all_bytes(rf_);
    assert(bopt.tag == 1);
    RF_Array* read_arr = (RF_Array*)bopt.value;
    assert(read_arr->len == 5);
    rf_byte* data = (rf_byte*)read_arr->data;
    assert(data[0] == 10);
    assert(data[2] == 30);
    assert(data[4] == 50);

    rf_array_release(arr);
    rf_array_release(read_arr);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 8: file_position and seek
 * ======================================================================== */

static void test_file_position_and_seek(void) {
    TEST(file_position_and_seek);

    const char* tmp_path = "/tmp/rf_test_file_seek.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("0123456789");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;

    /* Position should start at 0 */
    assert(rf_file_position(rf_) == 0);

    /* Read 5 bytes to advance */
    RF_Option_ptr bopt = rf_file_read_bytes(rf_, 5);
    assert(bopt.tag == 1);
    RF_Array* arr = (RF_Array*)bopt.value;
    rf_array_release(arr);

    /* Position should now be 5 */
    assert(rf_file_position(rf_) == 5);

    /* Seek back to 0 */
    rf_bool ok = rf_file_seek(rf_, 0);
    assert(ok == rf_true);
    assert(rf_file_position(rf_) == 0);

    /* Read first 3 bytes again */
    bopt = rf_file_read_bytes(rf_, 3);
    assert(bopt.tag == 1);
    arr = (RF_Array*)bopt.value;
    assert(arr->len == 3);
    rf_byte* bytes = (rf_byte*)arr->data;
    assert(bytes[0] == '0');
    assert(bytes[1] == '1');
    assert(bytes[2] == '2');
    rf_array_release(arr);

    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 9: seek_end
 * ======================================================================== */

static void test_file_seek_end(void) {
    TEST(file_seek_end);

    const char* tmp_path = "/tmp/rf_test_file_seekend.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("ABCDE");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;

    rf_bool ok = rf_file_seek_end(rf_, 0);
    assert(ok == rf_true);
    assert(rf_file_position(rf_) == 5);

    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 10: file_size
 * ======================================================================== */

static void test_file_size(void) {
    TEST(file_size);

    const char* tmp_path = "/tmp/rf_test_file_size.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("Hello World!");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    assert(rf_file_size(rf_) == 12);  /* "Hello World!" is 12 bytes */

    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 11: flush
 * ======================================================================== */

static void test_file_flush(void) {
    TEST(file_flush);

    const char* tmp_path = "/tmp/rf_test_file_flush.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("flush me");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_bool ok = rf_file_flush(wf);
    assert(ok == rf_true);

    /* Verify data is written by reading from another handle */
    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    RF_Option_ptr content_opt = rf_file_read_all(rf_);
    assert(content_opt.tag == 1);
    RF_String* content = (RF_String*)content_opt.value;
    assert(rf_string_eq(content, data) == rf_true);

    rf_string_release(content);
    rf_file_close(rf_);
    rf_file_close(wf);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 12: close with NULL fp is safe
 * ======================================================================== */

static void test_file_close_null_safe(void) {
    TEST(file_close_null_safe);

    /* Close a NULL file pointer -- should not crash */
    rf_file_close(NULL);

    PASS();
}

/* ========================================================================
 * Test 13: open nonexistent file returns NONE
 * ======================================================================== */

static void test_open_nonexistent_returns_none(void) {
    TEST(open_nonexistent_returns_none);

    RF_String* path = rf_string_from_cstr("/tmp/rf_test_file_nonexistent_99999.tmp");
    RF_Option_ptr opt = rf_file_open_read(path);
    assert(opt.tag == 0);

    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 14: file_lines stream
 * ======================================================================== */

static void test_file_lines_stream(void) {
    TEST(file_lines_stream);

    const char* tmp_path = "/tmp/rf_test_file_lines.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);
    RF_String* data = rf_string_from_cstr("line1\nline2\nline3\n");

    RF_Option_ptr wopt = rf_file_open_write(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    rf_file_write_string(wf, data);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    RF_Stream* lines = rf_file_lines(rf_);

    int count = 0;
    RF_Option_ptr item;
    while ((item = rf_stream_next(lines)).tag == 1) {
        RF_String* line = (RF_String*)item.value;
        count++;
        if (count == 1) {
            RF_String* exp = rf_string_from_cstr("line1");
            assert(rf_string_eq(line, exp) == rf_true);
            rf_string_release(exp);
        }
        if (count == 3) {
            RF_String* exp = rf_string_from_cstr("line3");
            assert(rf_string_eq(line, exp) == rf_true);
            rf_string_release(exp);
        }
        rf_string_release(line);
    }
    assert(count == 3);

    rf_stream_release(lines);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    rf_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 15: file_byte_stream
 * ======================================================================== */

static void test_file_byte_stream(void) {
    TEST(file_byte_stream);

    const char* tmp_path = "/tmp/rf_test_file_bytestream.tmp";
    RF_String* path = rf_string_from_cstr(tmp_path);

    rf_byte known[] = {0xAA, 0xBB, 0xCC};
    RF_Option_ptr wopt = rf_file_open_write_bytes(path);
    assert(wopt.tag == 1);
    RF_File* wf = (RF_File*)wopt.value;
    RF_Array* warr = rf_array_new(3, sizeof(rf_byte), known);
    rf_file_write_bytes(wf, warr);
    rf_file_close(wf);

    RF_Option_ptr ropt = rf_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    RF_File* rf_ = (RF_File*)ropt.value;
    RF_Stream* bs = rf_file_byte_stream(rf_);

    RF_Option_ptr b1 = rf_stream_next(bs);
    assert(b1.tag == 1);
    assert((rf_byte)(uintptr_t)b1.value == 0xAA);

    RF_Option_ptr b2 = rf_stream_next(bs);
    assert(b2.tag == 1);
    assert((rf_byte)(uintptr_t)b2.value == 0xBB);

    RF_Option_ptr b3 = rf_stream_next(bs);
    assert(b3.tag == 1);
    assert((rf_byte)(uintptr_t)b3.value == 0xCC);

    RF_Option_ptr b4 = rf_stream_next(bs);
    assert(b4.tag == 0);  /* EOF */

    rf_stream_release(bs);
    rf_array_release(warr);
    rf_file_close(rf_);
    remove(tmp_path);
    rf_string_release(path);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("RF_File handle I/O tests (stdlib/file)\n");
    printf("========================================\n");

    test_open_read_and_read_all();
    test_open_write_and_read_back();
    test_read_line_strips_newline();
    test_read_line_eof_returns_none();
    test_read_bytes_exact();
    test_read_all_bytes();
    test_write_bytes_from_array();
    test_file_position_and_seek();
    test_file_seek_end();
    test_file_size();
    test_file_flush();
    test_file_close_null_safe();
    test_open_nonexistent_returns_none();
    test_file_lines_stream();
    test_file_byte_stream();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
