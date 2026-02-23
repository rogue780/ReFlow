/*
 * C-level tests for RF_TcpListener, RF_TcpConnection, and net functions.
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
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

/* Re-declare opaque structs so tests can access fd for port discovery */
struct RF_TcpListener { int fd; };
struct RF_TcpConnection { int fd; };

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) \
    do { tests_run++; printf("  %-50s ", #name); } while(0)

#define PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

/* ========================================================================
 * Helper: start a listener on loopback with OS-assigned port
 * ======================================================================== */

static RF_TcpListener* _start_listener(rf_int* out_port) {
    RF_String* addr = rf_string_from_cstr("127.0.0.1");
    RF_Option_ptr opt = rf_net_listen(addr, 0);
    rf_string_release(addr);
    if (opt.tag == 0) return NULL;
    RF_TcpListener* listener = (RF_TcpListener*)opt.value;

    /* Get the actual assigned port */
    struct sockaddr_in sa;
    socklen_t sa_len = sizeof(sa);
    getsockname(listener->fd, (struct sockaddr*)&sa, &sa_len);
    *out_port = ntohs(sa.sin_port);
    return listener;
}

/* Helper: connect to loopback on a given port */
static RF_TcpConnection* _connect_to(rf_int port) {
    RF_String* host = rf_string_from_cstr("127.0.0.1");
    RF_Option_ptr opt = rf_net_connect(host, port);
    rf_string_release(host);
    if (opt.tag == 0) return NULL;
    return (RF_TcpConnection*)opt.value;
}

/* ========================================================================
 * Test 1: Listen on random port
 * ======================================================================== */

static void test_listen_on_random_port(void) {
    TEST(listen_on_random_port);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);
    assert(port > 0);

    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 2: Listen and close
 * ======================================================================== */

static void test_listen_and_close(void) {
    TEST(listen_and_close);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    /* Close — should not crash */
    rf_net_close_listener(listener);

    /* Close NULL — should not crash */
    rf_net_close_listener(NULL);

    PASS();
}

/* ========================================================================
 * Test 3: Connect and accept
 * ======================================================================== */

static void test_connect_and_accept(void) {
    TEST(connect_and_accept);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;
    assert(server != NULL);

    rf_net_close(client);
    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 4: Write/read byte roundtrip
 * ======================================================================== */

static void test_write_read_roundtrip(void) {
    TEST(write_read_roundtrip);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Send bytes from client */
    rf_byte data[] = {0x48, 0x65, 0x6C, 0x6C, 0x6F}; /* "Hello" */
    RF_Array* send_arr = rf_array_new(5, sizeof(rf_byte), data);
    rf_bool wrote = rf_net_write(client, send_arr);
    assert(wrote == rf_true);
    rf_array_release(send_arr);

    /* Read bytes on server side */
    RF_Option_ptr read_opt = rf_net_read(server, 1024);
    assert(read_opt.tag == 1);
    RF_Array* recv_arr = (RF_Array*)read_opt.value;
    assert(rf_array_len(recv_arr) == 5);
    rf_byte* recv_data = (rf_byte*)recv_arr->data;
    assert(recv_data[0] == 0x48);
    assert(recv_data[1] == 0x65);
    assert(recv_data[2] == 0x6C);
    assert(recv_data[3] == 0x6C);
    assert(recv_data[4] == 0x6F);
    rf_array_release(recv_arr);

    rf_net_close(client);
    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 5: Write string roundtrip
 * ======================================================================== */

static void test_write_string_roundtrip(void) {
    TEST(write_string_roundtrip);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Send string from client */
    RF_String* msg = rf_string_from_cstr("Hello, network!");
    rf_bool wrote = rf_net_write_string(client, msg);
    assert(wrote == rf_true);

    /* Read on server side */
    RF_Option_ptr read_opt = rf_net_read(server, 1024);
    assert(read_opt.tag == 1);
    RF_Array* recv_arr = (RF_Array*)read_opt.value;
    assert(rf_array_len(recv_arr) == rf_string_len(msg));
    assert(memcmp(recv_arr->data, msg->data, (size_t)rf_string_len(msg)) == 0);
    rf_array_release(recv_arr);
    rf_string_release(msg);

    rf_net_close(client);
    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 6: Close connection
 * ======================================================================== */

static void test_close_connection(void) {
    TEST(close_connection);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Close both — should not crash */
    rf_net_close(client);
    rf_net_close(server);

    /* Close NULL — should not crash */
    rf_net_close(NULL);

    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 7: Read after close returns empty array (connection closed)
 * ======================================================================== */

static void test_read_after_close(void) {
    TEST(read_after_close);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Close the sender side */
    rf_net_close(client);

    /* Small delay to let the TCP stack propagate the close */
    usleep(10000);

    /* Read should return SOME with empty array (connection closed gracefully) */
    RF_Option_ptr read_opt = rf_net_read(server, 1024);
    assert(read_opt.tag == 1);
    RF_Array* recv_arr = (RF_Array*)read_opt.value;
    assert(rf_array_len(recv_arr) == 0);
    rf_array_release(recv_arr);

    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 8: Remote addr format
 * ======================================================================== */

static void test_remote_addr_format(void) {
    TEST(remote_addr_format);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Get remote addr of client as seen by server */
    RF_Option_ptr addr_opt = rf_net_remote_addr(server);
    assert(addr_opt.tag == 1);
    RF_String* addr_str = (RF_String*)addr_opt.value;

    /* Should contain "127.0.0.1" */
    RF_String* expected_ip = rf_string_from_cstr("127.0.0.1");
    assert(rf_string_contains(addr_str, expected_ip) == rf_true);
    rf_string_release(expected_ip);
    rf_string_release(addr_str);

    rf_net_close(client);
    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 9: Set timeout
 * ======================================================================== */

static void test_set_timeout(void) {
    TEST(set_timeout);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Set timeout — should return true */
    rf_bool ok = rf_net_set_timeout(client, 5000);
    assert(ok == rf_true);

    rf_bool ok2 = rf_net_set_timeout(server, 1000);
    assert(ok2 == rf_true);

    rf_net_close(client);
    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 10: Connect to nonexistent port returns NONE
 * ======================================================================== */

static void test_connect_to_nonexistent(void) {
    TEST(connect_to_nonexistent);

    /* Use a port that is very unlikely to have anything listening.
     * Port 1 requires root and almost never has a service. */
    RF_String* host = rf_string_from_cstr("127.0.0.1");
    RF_Option_ptr opt = rf_net_connect(host, 1);
    rf_string_release(host);

    /* Should be NONE — connection refused */
    assert(opt.tag == 0);

    PASS();
}

/* ========================================================================
 * Test 11: Multiple writes and reads
 * ======================================================================== */

static void test_multiple_writes_reads(void) {
    TEST(multiple_writes_reads);

    rf_int port = 0;
    RF_TcpListener* listener = _start_listener(&port);
    assert(listener != NULL);

    RF_TcpConnection* client = _connect_to(port);
    assert(client != NULL);

    RF_Option_ptr accept_opt = rf_net_accept(listener);
    assert(accept_opt.tag == 1);
    RF_TcpConnection* server = (RF_TcpConnection*)accept_opt.value;

    /* Send multiple strings from client */
    RF_String* msg1 = rf_string_from_cstr("AAA");
    RF_String* msg2 = rf_string_from_cstr("BBB");
    rf_net_write_string(client, msg1);
    rf_net_write_string(client, msg2);
    rf_string_release(msg1);
    rf_string_release(msg2);

    /* Small delay for data to arrive */
    usleep(10000);

    /* Read — may get all 6 bytes in one read (TCP is a byte stream) */
    RF_Option_ptr read_opt = rf_net_read(server, 1024);
    assert(read_opt.tag == 1);
    RF_Array* recv_arr = (RF_Array*)read_opt.value;
    assert(rf_array_len(recv_arr) == 6);
    assert(memcmp(recv_arr->data, "AAABBB", 6) == 0);
    rf_array_release(recv_arr);

    rf_net_close(client);
    rf_net_close(server);
    rf_net_close_listener(listener);
    PASS();
}

/* ========================================================================
 * Test 12: Accept on NULL listener returns NONE
 * ======================================================================== */

static void test_accept_null_listener(void) {
    TEST(accept_null_listener);

    RF_Option_ptr opt = rf_net_accept(NULL);
    assert(opt.tag == 0);

    PASS();
}

/* ========================================================================
 * Main
 * ======================================================================== */

int main(void) {
    printf("RF_Net TCP tests\n");
    printf("========================================\n");

    test_listen_on_random_port();
    test_listen_and_close();
    test_connect_and_accept();
    test_write_read_roundtrip();
    test_write_string_roundtrip();
    test_close_connection();
    test_read_after_close();
    test_remote_addr_format();
    test_set_timeout();
    test_connect_to_nonexistent();
    test_multiple_writes_reads();
    test_accept_null_listener();

    printf("========================================\n");
    printf("%d/%d tests passed\n", tests_passed, tests_run);

    return tests_passed == tests_run ? 0 : 1;
}
