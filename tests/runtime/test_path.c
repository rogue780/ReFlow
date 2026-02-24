/*
 * C-level tests for path utility functions.
 *
 * Compile and run via: make test-runtime-path
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/flow_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Test 1: fl_path_is_dir
 * ======================================================================== */

static void test_is_dir(void) {
    TEST(is_dir_current_dir);
    {
        FL_String* p = fl_string_from_cstr(".");
        assert(fl_path_is_dir(p) == fl_true);
        fl_string_release(p);
    }
    PASS();

    TEST(is_dir_on_file);
    {
        FL_String* p = fl_string_from_cstr("runtime/flow_runtime.h");
        assert(fl_path_is_dir(p) == fl_false);
        fl_string_release(p);
    }
    PASS();

    TEST(is_dir_nonexistent);
    {
        FL_String* p = fl_string_from_cstr("/nonexistent_path_12345");
        assert(fl_path_is_dir(p) == fl_false);
        fl_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Test 2: fl_path_is_file
 * ======================================================================== */

static void test_is_file(void) {
    TEST(is_file_on_known_file);
    {
        FL_String* p = fl_string_from_cstr("runtime/flow_runtime.h");
        assert(fl_path_is_file(p) == fl_true);
        fl_string_release(p);
    }
    PASS();

    TEST(is_file_on_directory);
    {
        FL_String* p = fl_string_from_cstr(".");
        assert(fl_path_is_file(p) == fl_false);
        fl_string_release(p);
    }
    PASS();

    TEST(is_file_nonexistent);
    {
        FL_String* p = fl_string_from_cstr("/nonexistent_file_12345");
        assert(fl_path_is_file(p) == fl_false);
        fl_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Test 3: fl_path_extension
 * ======================================================================== */

static void test_extension(void) {
    TEST(extension_simple);
    {
        FL_String* p = fl_string_from_cstr("foo.txt");
        FL_Option_ptr result = fl_path_extension(p);
        assert(result.tag == 1);
        FL_String* ext = (FL_String*)result.value;
        assert(fl_string_eq(ext, fl_string_from_cstr(".txt")));
        fl_string_release(p);
    }
    PASS();

    TEST(extension_double);
    {
        FL_String* p = fl_string_from_cstr("foo.tar.gz");
        FL_Option_ptr result = fl_path_extension(p);
        assert(result.tag == 1);
        FL_String* ext = (FL_String*)result.value;
        FL_String* expected = fl_string_from_cstr(".gz");
        assert(fl_string_eq(ext, expected));
        fl_string_release(p);
    }
    PASS();

    TEST(extension_no_dot);
    {
        FL_String* p = fl_string_from_cstr("Makefile");
        FL_Option_ptr result = fl_path_extension(p);
        assert(result.tag == 0);
        fl_string_release(p);
    }
    PASS();

    TEST(extension_no_dot_with_path);
    {
        FL_String* p = fl_string_from_cstr("foo/bar");
        FL_Option_ptr result = fl_path_extension(p);
        assert(result.tag == 0);
        fl_string_release(p);
    }
    PASS();

    TEST(extension_hidden_file);
    {
        /* A dotfile like ".gitignore" — the dot is at base_start,
         * so no extension is returned */
        FL_String* p = fl_string_from_cstr(".gitignore");
        FL_Option_ptr result = fl_path_extension(p);
        assert(result.tag == 0);
        fl_string_release(p);
    }
    PASS();

    TEST(extension_dir_with_dot_file_without);
    {
        /* "dir.d/file" — dot is in directory component, not file */
        FL_String* p = fl_string_from_cstr("dir.d/file");
        FL_Option_ptr result = fl_path_extension(p);
        assert(result.tag == 0);
        fl_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Test 4: fl_path_list_dir
 * ======================================================================== */

static void test_list_dir(void) {
    TEST(list_dir_current);
    {
        FL_String* p = fl_string_from_cstr(".");
        FL_Option_ptr result = fl_path_list_dir(p);
        assert(result.tag == 1);
        FL_Array* arr = (FL_Array*)result.value;
        assert(fl_array_len(arr) > 0);
        fl_string_release(p);
    }
    PASS();

    TEST(list_dir_nonexistent);
    {
        FL_String* p = fl_string_from_cstr("/nonexistent_dir_12345");
        FL_Option_ptr result = fl_path_list_dir(p);
        assert(result.tag == 0);
        fl_string_release(p);
    }
    PASS();

    TEST(list_dir_no_dot_dotdot);
    {
        FL_String* p = fl_string_from_cstr(".");
        FL_Option_ptr result = fl_path_list_dir(p);
        assert(result.tag == 1);
        FL_Array* arr = (FL_Array*)result.value;
        /* Verify . and .. are not included */
        FL_String* dot = fl_string_from_cstr(".");
        FL_String* dotdot = fl_string_from_cstr("..");
        for (fl_int64 i = 0; i < fl_array_len(arr); i++) {
            FL_String** sp = (FL_String**)fl_array_get_ptr(arr, i);
            assert(!fl_string_eq(*sp, dot));
            assert(!fl_string_eq(*sp, dotdot));
        }
        fl_string_release(dot);
        fl_string_release(dotdot);
        fl_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("Path utility function tests\n");
    printf("========================================\n");

    test_is_dir();
    test_is_file();
    test_extension();
    test_list_dir();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
