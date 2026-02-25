# The Flow Programming Language — Book Plan

## Goal

A practitioner-oriented book that teaches Flow by building real programs.
Each chapter introduces one major concept, shows it in isolation, then
combines it with everything learned so far. By Chapter 13 the reader builds
a complete networked application using every feature in the language.

---

## Audience

- Working programmers comfortable in at least one typed language (TypeScript,
  Rust, Go, Swift, Kotlin).
- No prior experience with Flow, linear types, or stream-based concurrency
  required.

---

## Conventions

- **Code-first.** Every concept is introduced with a runnable program before
  the prose explains it.
- **One concept per chapter.** Chapters do not forward-reference features
  introduced later.
- **Error-driven.** Each chapter includes a "What goes wrong" section showing
  compiler errors the reader will hit and how to fix them.
- **Spec-aligned.** All semantics match `flow_spec.md` exactly. Where the
  spec is silent the book says so explicitly.

---

## Chapter Outline

### Preface
- Who this book is for
- How to read this book
- Setting up the Flow toolchain
- Typographic conventions

### Chapter 1: A First Program
- Hello, Flow
- The `main` function
- Compiling and running
- Comments and whitespace
- What goes wrong: common first errors

### Chapter 2: Values and Types
- Integers, floats, booleans, bytes
- Strings and string interpolation
- The `let` binding
- Type annotations vs. inference
- Immutability by default, `:mut` bindings
- Type conversions
- What goes wrong: type mismatches

### Chapter 3: Functions and Purity
- Defining functions
- Parameters and return types
- Expression-bodied functions
- Pure functions and the purity contract
- Calling conventions and argument passing
- Recursion
- What goes wrong: purity violations

### Chapter 4: Composition
- The pipe operator `|>`
- Chaining pure transformations
- Partial application and closures
- Lambda expressions
- Function types
- Building pipelines
- What goes wrong: type mismatches in pipelines

### Chapter 5: Making Decisions
- `if` / `else` as expressions
- `match` expressions
- Pattern matching on values
- Exhaustiveness checking
- Guard clauses
- What goes wrong: non-exhaustive matches

### Chapter 6: Data Structures
- Structs
- Named fields and construction
- Struct spread (`..`)
- Sum types (tagged unions)
- Generic types
- Arrays
- Maps
- What goes wrong: missing fields, wrong variant

### Chapter 7: Absence, Failure, and Recovery
- `option<T>` and `none`
- Option chaining and `if let`
- `result<T, E>` and `ok` / `err`
- The `try` operator
- Exception model: `throw`, `catch`, `retry`
- Defining error types
- What goes wrong: unhandled results, uncaught exceptions

### Chapter 8: Ownership and Memory
- Linear ownership model
- Move semantics
- Borrowing with `:imut` and `:mut`
- The copy rule
- Ownership and function boundaries
- What goes wrong: use-after-move, double ownership

### Chapter 9: Streams
- What is a stream
- Creating streams
- Consuming streams with `for`
- Stream operators: `map`, `filter`, `take`, `reduce`
- Single-consumer rule
- Capacity and backpressure (`[N]` syntax)
- What goes wrong: double consumption, capacity deadlocks

### Chapter 10: Coroutines and Concurrency
- The `:<` operator
- Lazy (non-threaded) coroutines
- Receivable coroutines and threads
- Sending to a coroutine
- Pipelines and worker pools
- Synchronization patterns
- What goes wrong: deadlocks, unbounded queues

### Chapter 11: Interfaces and Contracts
- Defining interfaces
- Implementing interfaces on structs
- Interface constraints on generics
- Built-in interfaces: `Stringable`, `Equatable`, `Hashable`
- Static dispatch
- What goes wrong: missing implementations

### Chapter 12: Modules and Programs
- Module declarations
- Imports and visibility
- Public vs. private
- The standard library
- Multi-file programs
- What goes wrong: circular imports, visibility errors

### Chapter 13: A Complete Application
- Designing a networked key-value store
- Structuring the project
- Implementing the protocol
- Server with coroutines and streams
- Client implementation
- Error handling and graceful shutdown
- Testing the application

### Appendix A: Language Reference
- Complete grammar summary
- Operator precedence table
- Keyword list
- Built-in types

### Appendix B: Standard Library
- `io` module
- `math` module
- `string` module
- `array` module
- `map` module
- `net` module
- `time` module
- `json` module

### Appendix C: The Flow Toolchain
- Installing Flow
- The `flow` compiler CLI
- Compiler flags and options
- Debugging compiled programs
- Performance considerations

---

## Production Notes

- Target length: 250-350 pages in print.
- Each chapter should be self-contained enough to serve as a reference after
  first reading.
- Code examples must compile against the current compiler. Broken examples
  are bugs.
- The book tracks `flow_spec.md` — when the spec changes, the book updates.
