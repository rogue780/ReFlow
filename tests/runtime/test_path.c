/*
 * C-level tests for path utility functions.
 *
 * Compile and run via: make test-runtime-path
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "../../runtime/reflow_runtime.h"
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
 * Test 1: rf_path_is_dir
 * ======================================================================== */

static void test_is_dir(void) {
    TEST(is_dir_current_dir);
    {
        RF_String* p = rf_string_from_cstr(".");
        assert(rf_path_is_dir(p) == rf_true);
        rf_string_release(p);
    }
    PASS();

    TEST(is_dir_on_file);
    {
        RF_String* p = rf_string_from_cstr("runtime/reflow_runtime.h");
        assert(rf_path_is_dir(p) == rf_false);
        rf_string_release(p);
    }
    PASS();

    TEST(is_dir_nonexistent);
    {
        RF_String* p = rf_string_from_cstr("/nonexistent_path_12345");
        assert(rf_path_is_dir(p) == rf_false);
        rf_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Test 2: rf_path_is_file
 * ======================================================================== */

static void test_is_file(void) {
    TEST(is_file_on_known_file);
    {
        RF_String* p = rf_string_from_cstr("runtime/reflow_runtime.h");
        assert(rf_path_is_file(p) == rf_true);
        rf_string_release(p);
    }
    PASS();

    TEST(is_file_on_directory);
    {
        RF_String* p = rf_string_from_cstr(".");
        assert(rf_path_is_file(p) == rf_false);
        rf_string_release(p);
    }
    PASS();

    TEST(is_file_nonexistent);
    {
        RF_String* p = rf_string_from_cstr("/nonexistent_file_12345");
        assert(rf_path_is_file(p) == rf_false);
        rf_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Test 3: rf_path_extension
 * ======================================================================== */

static void test_extension(void) {
    TEST(extension_simple);
    {
        RF_String* p = rf_string_from_cstr("foo.txt");
        RF_Option_ptr result = rf_path_extension(p);
        assert(result.tag == 1);
        RF_String* ext = (RF_String*)result.value;
        assert(rf_string_eq(ext, rf_string_from_cstr(".txt")));
        rf_string_release(p);
    }
    PASS();

    TEST(extension_double);
    {
        RF_String* p = rf_string_from_cstr("foo.tar.gz");
        RF_Option_ptr result = rf_path_extension(p);
        assert(result.tag == 1);
        RF_String* ext = (RF_String*)result.value;
        RF_String* expected = rf_string_from_cstr(".gz");
        assert(rf_string_eq(ext, expected));
        rf_string_release(p);
    }
    PASS();

    TEST(extension_no_dot);
    {
        RF_String* p = rf_string_from_cstr("Makefile");
        RF_Option_ptr result = rf_path_extension(p);
        assert(result.tag == 0);
        rf_string_release(p);
    }
    PASS();

    TEST(extension_no_dot_with_path);
    {
        RF_String* p = rf_string_from_cstr("foo/bar");
        RF_Option_ptr result = rf_path_extension(p);
        assert(result.tag == 0);
        rf_string_release(p);
    }
    PASS();

    TEST(extension_hidden_file);
    {
        /* A dotfile like ".gitignore" — the dot is at base_start,
         * so no extension is returned */
        RF_String* p = rf_string_from_cstr(".gitignore");
        RF_Option_ptr result = rf_path_extension(p);
        assert(result.tag == 0);
        rf_string_release(p);
    }
    PASS();

    TEST(extension_dir_with_dot_file_without);
    {
        /* "dir.d/file" — dot is in directory component, not file */
        RF_String* p = rf_string_from_cstr("dir.d/file");
        RF_Option_ptr result = rf_path_extension(p);
        assert(result.tag == 0);
        rf_string_release(p);
    }
    PASS();
}

/* ========================================================================
 * Test 4: rf_path_list_dir
 * ======================================================================== */

static void test_list_dir(void) {
    TEST(list_dir_current);
    {
        RF_String* p = rf_string_from_cstr(".");
        RF_Option_ptr result = rf_path_list_dir(p);
        assert(result.tag == 1);
        RF_Array* arr = (RF_Array*)result.value;
        assert(rf_array_len(arr) > 0);
        rf_string_release(p);
    }
    PASS();

    TEST(list_dir_nonexistent);
    {
        RF_String* p = rf_string_from_cstr("/nonexistent_dir_12345");
        RF_Option_ptr result = rf_path_list_dir(p);
        assert(result.tag == 0);
        rf_string_release(p);
    }
    PASS();

    TEST(list_dir_no_dot_dotdot);
    {
        RF_String* p = rf_string_from_cstr(".");
        RF_Option_ptr result = rf_path_list_dir(p);
        assert(result.tag == 1);
        RF_Array* arr = (RF_Array*)result.value;
        /* Verify . and .. are not included */
        RF_String* dot = rf_string_from_cstr(".");
        RF_String* dotdot = rf_string_from_cstr("..");
        for (rf_int64 i = 0; i < rf_array_len(arr); i++) {
            RF_String** sp = (RF_String**)rf_array_get_ptr(arr, i);
            assert(!rf_string_eq(*sp, dot));
            assert(!rf_string_eq(*sp, dotdot));
        }
        rf_string_release(dot);
        rf_string_release(dotdot);
        rf_string_release(p);
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
