# Preface

Flow is a strongly-typed functional language with composition-first design, linear ownership, and first-class streaming. It compiles to C and links via clang, producing native binaries with no runtime interpreter and no garbage collector. It was designed for data transformation workloads --- parsing, reshaping, filtering, aggregating --- but it is a general-purpose language, and this book treats it as one.

The central idea behind Flow is that every function can be built by composing smaller functions, and every function can be decomposed into smaller ones. This is not a slogan. It is an engineering constraint that shapes the entire language. Flow's composition operator (`->`) chains values and functions left to right, making pipelines the natural unit of program structure rather than an afterthought bolted onto an imperative core. When you read Flow code, data flows visibly from input to output. When you write it, you assemble programs the way you assemble pipes in a shell: one stage at a time, each stage testable in isolation.

All data in Flow is immutable by default. Mutation exists, but it is explicit, visible, and confined. You opt into it with the `:mut` qualifier, and the type system tracks it. Immutable data is freely shareable across threads and coroutines with zero copying --- no locks, no synchronized blocks, no defensive clones. Mutable data has exactly one owner at a time. Ownership transfers are visible in the code; the compiler rejects programs that violate them. If you have programmed in Rust, this will feel familiar. If you have not, the ownership chapter will get you there without requiring you to learn Rust first.

Functions in Flow can only interact with their parameters, local variables, imported functions, and static type members. There are no global variables. A function marked `pure` is verifiably free of side effects --- the compiler checks this, not a convention. Pure functions are safe to cache and safe to parallelize. The language does not force purity everywhere; it gives you the tools to be precise about where effects occur and where they do not.

Errors in Flow are values. The `result<T, E>` type represents operations that may fail; `option<T>` represents values that may be absent. You handle both with pattern matching, composition, or the `?` propagation operator. Exceptions exist for genuinely exceptional conditions --- hardware faults, invariant violations, resource exhaustion --- not for ordinary control flow. The type system enforces this distinction: a function that can fail says so in its return type.

Flow also has first-class streaming. Streams are typed channels that connect coroutines. A producer yields values into a stream; a consumer reads from it. The language provides fan-out, worker pools, and backpressure as built-in constructs, not library abstractions. If you work with data pipelines, event processing, or concurrent services, this is where Flow earns its name.

Why another language? Because the design space between "scripting language with bolted-on types" and "systems language with a PhD-required type system" is not as crowded as it looks. Flow aims to be a language where correctness is the default, composition is the primary abstraction, and the gap between what you write and what executes is small and predictable. The compiler emits C, not LLVM IR, not bytecode. You can read the output. You can link it with existing C libraries. There is no virtual machine between your program and the hardware.

---

## Who This Book Is For

This book is for programmers who already know how to program. You should have experience with at least one statically typed language --- Java, C#, TypeScript, Rust, Go, Swift, or similar. You should be comfortable with types, functions, variables, conditionals, and loops. That is enough.

You do not need to know functional programming. You do not need to know what a monad is, what linear types are, or how ownership systems work. This book introduces all of these concepts from scratch, in the context of Flow, with concrete examples. If you already know them, you will move faster through the early chapters, but the material does not assume prior exposure.

You also do not need to know C, though a passing familiarity helps when reading compiler output or debugging at the boundary between Flow and native libraries. The book does not teach C; it occasionally shows the generated output to explain what the compiler does and why.

The book serves two audiences. If you are learning Flow for the first time, read it front to back. The chapters are ordered so that each one builds on what came before, and the examples accumulate. If you are an experienced Flow programmer looking for a reference, the chapters are self-contained enough to be useful individually, and the appendices provide quick-reference material for types, operators, and the standard library.

---

## How to Read This Book

The book is divided into three tiers.

**Chapters 1 through 5** cover the core language: types, bindings, functions, composition, and control flow. Read these in order. They establish the vocabulary and mental model that the rest of the book depends on. Skipping ahead to streams or ownership without understanding composition will cost you more time than it saves.

**Chapters 6 through 8** cover data structures, error handling, and ownership. These chapters build on the core but are relatively independent of each other. If you are primarily interested in error handling, you can read Chapter 7 before Chapter 6 without difficulty. All three assume you have completed Chapters 1 through 5.

**Chapters 9 and 10** cover streams and coroutines --- the features that distinguish Flow from most other languages. Read these in order. Streams depend on coroutines, and the examples in Chapter 10 assume you understand the stream primitives introduced in Chapter 9.

**Chapters 11 and 12** cover interfaces and modules. These are the language's mechanisms for abstraction at scale. They can be read independently or in either order.

**Chapter 13** is a capstone project that ties everything together. It builds a complete, nontrivial application from scratch, using every major feature introduced in the preceding chapters. Read it last.

**The appendices** are reference material: a complete operator table, a type compatibility chart, the standard library API, and a grammar summary. They are designed for lookup, not sequential reading.

Every code example in this book is complete. Every one compiles. Every one runs. There are no fragments that silently depend on hidden preamble, no "imagine this is inside a function" hand-waving. If you see a code block, you can type it in and execute it. Many sections end with "Try it" suggestions --- small modifications or experiments that reinforce the concept just introduced. Do them. Reading about composition is not the same as composing.

---

## Typographic Conventions

Code examples appear in fenced blocks tagged with `flow`:

```flow
fn greet(name: string): string {
    return f"hello, {name}"
}
```

Comments in Flow use the semicolon character:

```flow
// this is a comment
let x: int = 42  // so is this
```

**Bold text** marks the first use of an important term. After its introduction, the term appears in normal weight.

`Code style` is used for file names (`main.flow`), function names (`parse_command`), type names (`option<int>`), operators (`->`), and short inline code references.

Each chapter ends with a set of numbered exercises. They are ordered by increasing difficulty: early exercises check comprehension; later ones require you to design and build something. Solutions are not provided. The best way to check your answer is to compile it and run it.
