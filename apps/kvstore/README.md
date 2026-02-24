# KV Store (Mini Redis)

An in-memory key-value store with a TCP text protocol, concurrent client
handling via coroutines, and optional disk persistence.

## Usage

```bash
# Start the server (default port 6379)
python main.py run apps/kvstore/server.flow

# Specify a custom port
python main.py run apps/kvstore/server.flow -- 7000
```

Connect with netcat:

```bash
nc localhost 6379
```

## Commands

| Command | Description | Response |
|---------|-------------|----------|
| `PING` | Health check | `+PONG` |
| `SET key value` | Store a key-value pair | `+OK` |
| `GET key` | Retrieve a value by key | `+value` or `-ERR key not found` |
| `DEL key` | Delete a key | `+1` (deleted) or `+0` (not found) |
| `EXISTS key` | Check if a key exists | `+1` or `+0` |
| `KEYS` | List all keys | `+key1 key2 key3 ...` |
| `COUNT` | Number of keys in the store | `+N` |
| `FLUSHALL` | Delete all keys | `+OK` |
| `SAVE` | Persist store to `kvstore.dat` | `+OK` |
| `LOAD` | Restore store from `kvstore.dat` | `+OK (N keys loaded)` |
| `QUIT` | Disconnect | `+Goodbye` |

Responses are prefixed with `+` on success and `-ERR` on error.

Values can contain spaces: `SET greeting hello world` stores `hello world`.

## Persistence

`SAVE` serializes the store as JSON to `kvstore.dat` in the working directory.
`LOAD` restores from that file. The server also auto-loads `kvstore.dat` on
startup if it exists.

## Example Session

```
$ nc localhost 6379
SET user alice
+OK
SET score 42
+OK
GET user
+alice
KEYS
+user score
COUNT
+2
SAVE
+OK
DEL user
+1
COUNT
+1
LOAD
+OK (2 keys loaded)
GET user
+alice
QUIT
+Goodbye
```

## Architecture

- Coroutine-per-client with a single-writer main thread
- Client coroutines read lines from sockets and yield them to the main loop
- The main loop polls all coroutines, dispatches commands against the store,
  and sends responses back via file descriptors
- The store (`map<string, string>`) is owned exclusively by `main()`,
  so there are no concurrent mutation issues

## Multi-Client

Multiple clients can connect simultaneously. They all share the same store,
so a `SET` from one client is immediately visible to a `GET` from another.

Dead clients are detected when a write fails and cleaned up automatically.
