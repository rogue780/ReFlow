/*
 * C-level tests for FL_File handle-based I/O (stdlib/file).
 *
 * Compile and run via: make test-runtime
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
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

    FL_String* path = fl_string_from_cstr("tests/runtime/test_file.c");
    FL_Option_ptr opt = fl_file_open_read(path);
    assert(opt.tag == 1);

    FL_File* f = (FL_File*)opt.value;
    FL_Option_ptr content_opt = fl_file_read_all(f);
    assert(content_opt.tag == 1);

    FL_String* content = (FL_String*)content_opt.value;
    assert(content->len > 0);

    /* Verify it starts with the expected comment */
    assert(strncmp(content->data, "/*", 2) == 0);

    fl_string_release(content);
    fl_file_close(f);
    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 2: Write a string, close, open, read back, verify match
 * ======================================================================== */

static void test_open_write_and_read_back(void) {
    TEST(open_write_and_read_back);

    const char* tmp_path = "/tmp/fl_test_file_write.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* message = fl_string_from_cstr("Hello, Flow file handles!");

    /* Write */
    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_bool ok = fl_file_write_string(wf, message);
    assert(ok == fl_true);
    fl_file_close(wf);

    /* Read back */
    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    FL_Option_ptr content_opt = fl_file_read_all(fl_);
    assert(content_opt.tag == 1);
    FL_String* content = (FL_String*)content_opt.value;
    assert(fl_string_eq(content, message) == fl_true);

    fl_string_release(content);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(message);
    PASS();
}

/* ========================================================================
 * Test 3: read_line strips newline
 * ======================================================================== */

static void test_read_line_strips_newline(void) {
    TEST(read_line_strips_newline);

    const char* tmp_path = "/tmp/fl_test_file_readline.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("hello\nworld\n");

    /* Write data */
    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    /* Read lines */
    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;

    FL_Option_ptr l1 = fl_file_read_line(fl_);
    assert(l1.tag == 1);
    FL_String* line1 = (FL_String*)l1.value;
    FL_String* expected1 = fl_string_from_cstr("hello");
    assert(fl_string_eq(line1, expected1) == fl_true);

    FL_Option_ptr l2 = fl_file_read_line(fl_);
    assert(l2.tag == 1);
    FL_String* line2 = (FL_String*)l2.value;
    FL_String* expected2 = fl_string_from_cstr("world");
    assert(fl_string_eq(line2, expected2) == fl_true);

    fl_string_release(line1);
    fl_string_release(line2);
    fl_string_release(expected1);
    fl_string_release(expected2);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 4: read_line at EOF returns NONE
 * ======================================================================== */

static void test_read_line_eof_returns_none(void) {
    TEST(read_line_eof_returns_none);

    const char* tmp_path = "/tmp/fl_test_file_eof.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("only\n");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;

    FL_Option_ptr l1 = fl_file_read_line(fl_);
    assert(l1.tag == 1);
    FL_String* line1 = (FL_String*)l1.value;
    fl_string_release(line1);

    /* Next read should return NONE */
    FL_Option_ptr l2 = fl_file_read_line(fl_);
    assert(l2.tag == 0);

    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 5: read_bytes exact count
 * ======================================================================== */

static void test_read_bytes_exact(void) {
    TEST(read_bytes_exact);

    const char* tmp_path = "/tmp/fl_test_file_readbytes.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("ABCDEFGHIJ");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;

    FL_Option_ptr bopt = fl_file_read_bytes(fl_, 5);
    assert(bopt.tag == 1);
    FL_Array* arr = (FL_Array*)bopt.value;
    assert(arr->len == 5);
    fl_byte* bytes = (fl_byte*)arr->data;
    assert(bytes[0] == 'A');
    assert(bytes[4] == 'E');

    fl_array_release(arr);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 6: read_all_bytes
 * ======================================================================== */

static void test_read_all_bytes(void) {
    TEST(read_all_bytes);

    const char* tmp_path = "/tmp/fl_test_file_readallbytes.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);

    /* Write known bytes */
    fl_byte known[] = {0x00, 0x01, 0xFF, 0x42, 0x80};
    FL_Option_ptr wopt = fl_file_open_write_bytes(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    FL_Array* write_arr = fl_array_new(5, sizeof(fl_byte), known);
    fl_file_write_bytes(wf, write_arr);
    fl_file_close(wf);

    /* Read back */
    FL_Option_ptr ropt = fl_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    FL_Option_ptr bopt = fl_file_read_all_bytes(fl_);
    assert(bopt.tag == 1);
    FL_Array* arr = (FL_Array*)bopt.value;
    assert(arr->len == 5);
    fl_byte* data = (fl_byte*)arr->data;
    assert(data[0] == 0x00);
    assert(data[1] == 0x01);
    assert(data[2] == 0xFF);
    assert(data[3] == 0x42);
    assert(data[4] == 0x80);

    fl_array_release(write_arr);
    fl_array_release(arr);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 7: write_bytes from array
 * ======================================================================== */

static void test_write_bytes_from_array(void) {
    TEST(write_bytes_from_array);

    const char* tmp_path = "/tmp/fl_test_file_writebytes.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);

    fl_byte vals[] = {10, 20, 30, 40, 50};
    FL_Array* arr = fl_array_new(5, sizeof(fl_byte), vals);

    FL_Option_ptr wopt = fl_file_open_write_bytes(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_bool ok = fl_file_write_bytes(wf, arr);
    assert(ok == fl_true);
    fl_file_close(wf);

    /* Read back and verify */
    FL_Option_ptr ropt = fl_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    FL_Option_ptr bopt = fl_file_read_all_bytes(fl_);
    assert(bopt.tag == 1);
    FL_Array* read_arr = (FL_Array*)bopt.value;
    assert(read_arr->len == 5);
    fl_byte* data = (fl_byte*)read_arr->data;
    assert(data[0] == 10);
    assert(data[2] == 30);
    assert(data[4] == 50);

    fl_array_release(arr);
    fl_array_release(read_arr);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 8: file_position and seek
 * ======================================================================== */

static void test_file_position_and_seek(void) {
    TEST(file_position_and_seek);

    const char* tmp_path = "/tmp/fl_test_file_seek.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("0123456789");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;

    /* Position should start at 0 */
    assert(fl_file_position(fl_) == 0);

    /* Read 5 bytes to advance */
    FL_Option_ptr bopt = fl_file_read_bytes(fl_, 5);
    assert(bopt.tag == 1);
    FL_Array* arr = (FL_Array*)bopt.value;
    fl_array_release(arr);

    /* Position should now be 5 */
    assert(fl_file_position(fl_) == 5);

    /* Seek back to 0 */
    fl_bool ok = fl_file_seek(fl_, 0);
    assert(ok == fl_true);
    assert(fl_file_position(fl_) == 0);

    /* Read first 3 bytes again */
    bopt = fl_file_read_bytes(fl_, 3);
    assert(bopt.tag == 1);
    arr = (FL_Array*)bopt.value;
    assert(arr->len == 3);
    fl_byte* bytes = (fl_byte*)arr->data;
    assert(bytes[0] == '0');
    assert(bytes[1] == '1');
    assert(bytes[2] == '2');
    fl_array_release(arr);

    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 9: seek_end
 * ======================================================================== */

static void test_file_seek_end(void) {
    TEST(file_seek_end);

    const char* tmp_path = "/tmp/fl_test_file_seekend.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("ABCDE");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;

    fl_bool ok = fl_file_seek_end(fl_, 0);
    assert(ok == fl_true);
    assert(fl_file_position(fl_) == 5);

    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 10: file_size
 * ======================================================================== */

static void test_file_size(void) {
    TEST(file_size);

    const char* tmp_path = "/tmp/fl_test_file_size.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("Hello World!");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    assert(fl_file_size(fl_) == 12);  /* "Hello World!" is 12 bytes */

    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 11: flush
 * ======================================================================== */

static void test_file_flush(void) {
    TEST(file_flush);

    const char* tmp_path = "/tmp/fl_test_file_flush.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("flush me");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_bool ok = fl_file_flush(wf);
    assert(ok == fl_true);

    /* Verify data is written by reading from another handle */
    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    FL_Option_ptr content_opt = fl_file_read_all(fl_);
    assert(content_opt.tag == 1);
    FL_String* content = (FL_String*)content_opt.value;
    assert(fl_string_eq(content, data) == fl_true);

    fl_string_release(content);
    fl_file_close(fl_);
    fl_file_close(wf);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 12: close with NULL fp is safe
 * ======================================================================== */

static void test_file_close_null_safe(void) {
    TEST(file_close_null_safe);

    /* Close a NULL file pointer -- should not crash */
    fl_file_close(NULL);

    PASS();
}

/* ========================================================================
 * Test 13: open nonexistent file returns NONE
 * ======================================================================== */

static void test_open_nonexistent_returns_none(void) {
    TEST(open_nonexistent_returns_none);

    FL_String* path = fl_string_from_cstr("/tmp/fl_test_file_nonexistent_99999.tmp");
    FL_Option_ptr opt = fl_file_open_read(path);
    assert(opt.tag == 0);

    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Test 14: file_lines stream
 * ======================================================================== */

static void test_file_lines_stream(void) {
    TEST(file_lines_stream);

    const char* tmp_path = "/tmp/fl_test_file_lines.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);
    FL_String* data = fl_string_from_cstr("line1\nline2\nline3\n");

    FL_Option_ptr wopt = fl_file_open_write(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    fl_file_write_string(wf, data);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    FL_Stream* lines = fl_file_lines(fl_);

    int count = 0;
    FL_Option_ptr item;
    while ((item = fl_stream_next(lines)).tag == 1) {
        FL_String* line = (FL_String*)item.value;
        count++;
        if (count == 1) {
            FL_String* exp = fl_string_from_cstr("line1");
            assert(fl_string_eq(line, exp) == fl_true);
            fl_string_release(exp);
        }
        if (count == 3) {
            FL_String* exp = fl_string_from_cstr("line3");
            assert(fl_string_eq(line, exp) == fl_true);
            fl_string_release(exp);
        }
        fl_string_release(line);
    }
    assert(count == 3);

    fl_stream_release(lines);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    fl_string_release(data);
    PASS();
}

/* ========================================================================
 * Test 15: file_byte_stream
 * ======================================================================== */

static void test_file_byte_stream(void) {
    TEST(file_byte_stream);

    const char* tmp_path = "/tmp/fl_test_file_bytestream.tmp";
    FL_String* path = fl_string_from_cstr(tmp_path);

    fl_byte known[] = {0xAA, 0xBB, 0xCC};
    FL_Option_ptr wopt = fl_file_open_write_bytes(path);
    assert(wopt.tag == 1);
    FL_File* wf = (FL_File*)wopt.value;
    FL_Array* warr = fl_array_new(3, sizeof(fl_byte), known);
    fl_file_write_bytes(wf, warr);
    fl_file_close(wf);

    FL_Option_ptr ropt = fl_file_open_read_bytes(path);
    assert(ropt.tag == 1);
    FL_File* fl_ = (FL_File*)ropt.value;
    FL_Stream* bs = fl_file_byte_stream(fl_);

    FL_Option_ptr b1 = fl_stream_next(bs);
    assert(b1.tag == 1);
    assert((fl_byte)(uintptr_t)b1.value == 0xAA);

    FL_Option_ptr b2 = fl_stream_next(bs);
    assert(b2.tag == 1);
    assert((fl_byte)(uintptr_t)b2.value == 0xBB);

    FL_Option_ptr b3 = fl_stream_next(bs);
    assert(b3.tag == 1);
    assert((fl_byte)(uintptr_t)b3.value == 0xCC);

    FL_Option_ptr b4 = fl_stream_next(bs);
    assert(b4.tag == 0);  /* EOF */

    fl_stream_release(bs);
    fl_array_release(warr);
    fl_file_close(fl_);
    remove(tmp_path);
    fl_string_release(path);
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("FL_File handle I/O tests (stdlib/file)\n");
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
