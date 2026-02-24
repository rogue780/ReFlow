# Plan: TCP Chat Server

## Overview

A multi-client TCP chat server written in ReFlow. Users connect with `nc` or
`telnet`, pick a nickname, and exchange messages in real time. Each client
connection is handled by a coroutine on its own thread.

**File:** `apps/chat/server.reflow`

**Usage:**
```
python main.py run apps/chat/server.reflow -- [port]
```
Connect with: `nc localhost <port>`

**Stdlib modules used:** `net`, `io`, `string`, `array`, `map`, `conv`, `sys`, `time`

---

## Conventions

- **Epic**: A major phase of the application.
- **Story**: A coherent unit of work within an epic.
- **Ticket**: A single implementable task with a clear definition of done.
- Tickets are numbered `CHAT-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Core Server Infrastructure

Stand up the TCP listener, accept loop, and per-client coroutine model.

---

## Story 1-1: TCP Accept Loop

**CHAT-1-1-1** `[BLOCKER]`
Create `apps/chat/server.reflow` with a `main()` that:
- Reads port from `sys.args()` (default 9000).
- Calls `net.listen("0.0.0.0", port)`.
- Prints "Chat server listening on port NNNN".
- Loops calling `net.accept(sock)` to accept connections.
- For now, immediately closes each accepted socket.

**Definition of done:** Server starts, accepts a connection from `nc`, closes
it, and loops back to accept another.

**CHAT-1-1-2**
Add a `handle_client(client: Socket)` function that:
- Reads the remote address with `net.remote_addr`.
- Prints "[connect] <addr>" to the server console.
- Enters a read loop: `net.read(client, 1024)`.
- Echoes each received message back to the sender.
- On read returning `none`, prints "[disconnect] <addr>" and closes.

**Definition of done:** Connecting with `nc` echoes back whatever you type.

**CHAT-1-1-3**
Wrap `handle_client` in a coroutine spawn so each client runs on its own thread:
```
let handler :< handle_client(client_sock)
```
The accept loop no longer blocks on a single client.

**Definition of done:** Two `nc` sessions can connect simultaneously and each
gets echo independently.

---

## Story 1-2: Client Registry

**CHAT-1-2-1** `[BLOCKER]`
Create a `ClientRegistry` approach using a mutable `map<string, string>` that
maps client ID (remote address) to nickname. Since map is `string→string` only,
store socket handles separately in a parallel array or encode them.

Design decision: because the stdlib `map` is string-keyed only and sockets
aren't strings, maintain two parallel structures:
- `nicknames: map<string, string>` — addr → nickname
- Track active client sockets via the coroutine model (each coroutine owns its socket)

**CHAT-1-2-2**
On connect, auto-assign a nickname: `"user_" + addr_hash`. Register in the
nicknames map. On disconnect, remove from the map.

**Definition of done:** Server console shows "[connect] user_127.0.0.1:54321"
and "[disconnect] user_127.0.0.1:54321" with generated nicknames.

---

# EPIC 2: Chat Protocol

Implement the message protocol: plain text lines, with `/commands` for
control messages.

---

## Story 2-1: Message Parsing

**CHAT-2-1-1**
Create `fn:pure parse_message(raw: string): (string, string)` that splits a
raw line into (command, argument):
- Lines starting with `/` are commands: `/nick bob` → `("/nick", "bob")`
- All other lines are chat messages: `"hello"` → `("/say", "hello")`

**CHAT-2-1-2**
Implement command dispatch in `handle_client`:
```
match command {
    "/nick": { ... }
    "/quit": { ... }
    "/list": { ... }
    "/help": { ... }
    "/say":  { ... broadcast ... }
    _:       { ... send "Unknown command" ... }
}
```
For now, each command just echoes a confirmation back to the sender.

**Definition of done:** Typing `/help` returns a help message. `/quit` closes
the connection. Unknown commands return an error.

---

## Story 2-2: Nickname Management

**CHAT-2-2-1**
Implement `/nick <name>`:
- Validate: non-empty, no spaces, <= 20 chars.
- Check uniqueness against the nicknames map.
- Update the map entry.
- Send confirmation: "You are now known as <name>".

**CHAT-2-2-2**
Implement `/list`:
- Iterate `map.keys(nicknames)` to get all addresses.
- Look up each nickname.
- Send the list to the requesting client.

**Definition of done:** `/nick bob` changes nickname, `/list` shows all
connected users.

---

# EPIC 3: Message Broadcasting

The core feature: messages from one client are delivered to all others.

---

## Story 3-1: Broadcast Mechanism

**CHAT-3-1-1** `[BLOCKER]`
Design the broadcast approach. Since each client runs in its own coroutine
and ReFlow doesn't have shared mutable state across threads, broadcasting
requires a coordination mechanism.

Approach: Use a dedicated broadcast coroutine that owns the client socket list.
Client coroutines send messages to the broadcaster via a channel-like pattern.
Alternatively, since `net.write` is thread-safe at the OS level, each client
coroutine can write directly to other clients' sockets if socket handles are
stored in a shared (immutable, snapshot-based) structure.

Simplest viable approach: maintain a global mutable array of socket file
descriptors (encoded as ints), and have each client coroutine iterate and
write to all others. Use `try/catch` around writes to handle disconnected
clients gracefully.

**CHAT-3-1-2**
Implement `broadcast(sender_addr: string, message: string)`:
- Format: `"[nickname] message\n"`
- Iterate all known client sockets.
- Skip the sender.
- Write to each, catching errors for dead connections.

**CHAT-3-1-3**
Wire `/say` (plain text messages) to the broadcast function.

**Definition of done:** Three `nc` sessions connected. A message typed in one
appears in the other two, prefixed with the sender's nickname.

---

## Story 3-2: Join/Leave Notifications

**CHAT-3-2-1**
On connect, broadcast: `"*** user_xxx has joined ***"` to all existing clients.

**CHAT-3-2-2**
On disconnect (read returns `none` or `/quit`), broadcast:
`"*** user_xxx has left ***"` to all remaining clients.

**CHAT-3-2-3**
On `/nick` change, broadcast: `"*** old_name is now known as new_name ***"`.

**Definition of done:** All clients see join, leave, and nick-change
notifications.

---

# EPIC 4: Polish and Robustness

---

## Story 4-1: Error Handling

**CHAT-4-1-1**
Wrap all `net.read` / `net.write` calls in `try/catch`. A failed write should
not crash the server — just remove the dead client.

**CHAT-4-1-2**
Add a welcome message sent on connect:
```
Welcome to ReFlow Chat!
Type /help for commands.
Your nickname is: user_xxx
```

**CHAT-4-1-3**
Handle partial reads: buffer incoming data and split on `\n` boundaries.
Lines without a trailing newline are buffered until the next read.

---

## Story 4-2: Server Console

**CHAT-4-2-1**
Print all activity to the server console with timestamps:
```
[12:34:56] [connect] user_1 from 127.0.0.1:54321
[12:34:58] [chat] user_1: hello everyone
[12:35:01] [command] user_1: /nick alice
[12:35:10] [disconnect] alice
```

**CHAT-4-2-2**
Print a periodic status line every 60 seconds (or on SIGUSR1 if feasible):
`"[status] 3 clients connected"`.

---

## Story 4-3: Testing

**CHAT-4-3-1**
Create `tests/programs/app_chat_server.reflow` — a self-test version that:
- Starts the server on a random high port.
- Spawns a coroutine client that connects, sends `/nick testbot`, sends
  "hello", reads back the echo/broadcast, and disconnects.
- Verifies expected output.
- Shuts down after the test completes.

**CHAT-4-3-2**
Create `tests/expected_stdout/app_chat_server.txt` with expected output.

---

## Dependency Map

```
EPIC 1 (Infrastructure) → EPIC 2 (Protocol) → EPIC 3 (Broadcasting) → EPIC 4 (Polish)
```

All epics are sequential — each depends on the previous.

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| TCP networking (`net` module) | Accept loop, client read/write |
| Coroutines (`:< `) | One per client connection |
| `map<string, string>` | Nickname registry |
| Pattern matching (`match`) | Command dispatch |
| `option<T>` / `??` | Safe socket reads, map lookups |
| `try/catch` | Graceful handling of dead connections |
| `fn:pure` | Message parsing, validation |
| Records | `Severity`, message structures |
| String manipulation | Protocol parsing, formatting |
| `sys.args()` | CLI port argument |
| `time` module | Timestamps on console output |
