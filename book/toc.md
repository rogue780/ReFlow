# The Flow Programming Language

### Composition, Ownership, and Streaming

---

## Table of Contents

### [Preface](preface.md)
- Who this book is for
- How to read this book
- Setting up the Flow toolchain
- Typographic conventions

---

### [Chapter 1: A First Program](ch01_first_program.md)
- 1.1 Hello, Flow
- 1.2 The `main` function
- 1.3 Compiling and running
- 1.4 Comments and whitespace
- 1.5 What goes wrong: common first errors

### [Chapter 2: Values and Types](ch02_values_types.md)
- 2.1 Integers, floats, booleans, bytes
- 2.2 Strings and string interpolation
- 2.3 The `let` binding
- 2.4 Type annotations vs. inference
- 2.5 Immutability by default, `:mut` bindings
- 2.6 Type conversions
- 2.7 What goes wrong: type mismatches

### [Chapter 3: Functions and Purity](ch03_functions.md)
- 3.1 Defining functions
- 3.2 Parameters and return types
- 3.3 Expression-bodied functions
- 3.4 Pure functions and the purity contract
- 3.5 Calling conventions and argument passing
- 3.6 Recursion
- 3.7 What goes wrong: purity violations

### [Chapter 4: Composition](ch04_composition.md)
- 4.1 The pipe operator `|>`
- 4.2 Chaining pure transformations
- 4.3 Partial application and closures
- 4.4 Lambda expressions
- 4.5 Function types
- 4.6 Building pipelines
- 4.7 What goes wrong: type mismatches in pipelines

### [Chapter 5: Making Decisions](ch05_decisions.md)
- 5.1 `if` / `else` as expressions
- 5.2 `match` expressions
- 5.3 Pattern matching on values
- 5.4 Exhaustiveness checking
- 5.5 Guard clauses
- 5.6 What goes wrong: non-exhaustive matches

### [Chapter 6: Data Structures](ch06_data_structures.md)
- 6.1 Structs
- 6.2 Named fields and construction
- 6.3 Struct spread (`..`)
- 6.4 Sum types (tagged unions)
- 6.5 Generic types
- 6.6 Arrays
- 6.7 Maps
- 6.8 What goes wrong: missing fields, wrong variant

### [Chapter 7: Absence, Failure, and Recovery](ch07_errors.md)
- 7.1 `option<T>` and `none`
- 7.2 Option chaining and `if let`
- 7.3 `result<T, E>` and `ok` / `err`
- 7.4 The `try` operator
- 7.5 Exception model: `throw`, `catch`, `retry`
- 7.6 Defining error types
- 7.7 What goes wrong: unhandled results, uncaught exceptions

### [Chapter 8: Ownership and Memory](ch08_ownership.md)
- 8.1 Linear ownership model
- 8.2 Move semantics
- 8.3 Borrowing with `:imut` and `:mut`
- 8.4 The copy rule
- 8.5 Ownership and function boundaries
- 8.6 What goes wrong: use-after-move, double ownership

### [Chapter 9: Streams](ch09_streams.md)
- 9.1 What is a stream
- 9.2 Creating streams
- 9.3 Consuming streams with `for`
- 9.4 Stream operators: `map`, `filter`, `take`, `reduce`
- 9.5 Single-consumer rule
- 9.6 Capacity and backpressure (`[N]` syntax)
- 9.7 What goes wrong: double consumption, capacity deadlocks

### [Chapter 10: Coroutines and Concurrency](ch10_coroutines.md)
- 10.1 The `:<` operator
- 10.2 Lazy (non-threaded) coroutines
- 10.3 Receivable coroutines and threads
- 10.4 Sending to a coroutine
- 10.5 Pipelines and worker pools
- 10.6 Synchronization patterns
- 10.7 What goes wrong: deadlocks, unbounded queues

### [Chapter 11: Interfaces and Contracts](ch11_interfaces.md)
- 11.1 Defining interfaces
- 11.2 Implementing interfaces on structs
- 11.3 Interface constraints on generics
- 11.4 Built-in interfaces: `Stringable`, `Equatable`, `Hashable`
- 11.5 Static dispatch
- 11.6 What goes wrong: missing implementations

### [Chapter 12: Modules and Programs](ch12_modules.md)
- 12.1 Module declarations
- 12.2 Imports and visibility
- 12.3 Public vs. private
- 12.4 The standard library
- 12.5 Multi-file programs
- 12.6 What goes wrong: circular imports, visibility errors

### [Chapter 13: A Complete Application](ch13_application.md)
- 13.1 Designing a networked key-value store
- 13.2 Structuring the project
- 13.3 Implementing the protocol
- 13.4 Server with coroutines and streams
- 13.5 Client implementation
- 13.6 Error handling and graceful shutdown
- 13.7 Testing the application

---

## Appendices

### [Appendix A: Language Reference](appendix_a_reference.md)
- A.1 Complete grammar summary
- A.2 Operator precedence table
- A.3 Keyword list
- A.4 Built-in types

### [Appendix B: Standard Library](appendix_b_stdlib.md)
- B.1 `io` module
- B.2 `math` module
- B.3 `string` module
- B.4 `array` module
- B.5 `map` module
- B.6 `net` module
- B.7 `time` module
- B.8 `json` module

### [Appendix C: The Flow Toolchain](appendix_c_toolchain.md)
- C.1 Installing Flow
- C.2 The `flow` compiler CLI
- C.3 Compiler flags and options
- C.4 Debugging compiled programs
- C.5 Performance considerations
