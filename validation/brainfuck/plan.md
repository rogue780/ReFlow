# Validation: Brainfuck Interpreter

## Category
Complex "Real-World" Application — Tiny Interpreter

## What It Validates
- Character-level string processing (`string.char_at`, `string.len`)
- Array as mutable memory tape (`array<int>` with index arithmetic)
- Bracket matching (finding matching `[` and `]`) — stack-based or scan-based
- Byte-to-character conversion for output
- Loop constructs interpreting loop semantics (while cell != 0)
- Whole-program interpretation: parsing + execution in one pass
- Instruction pointer management with mutable state
- Nested loop handling (brackets inside brackets)

## Why It Matters
Writing an interpreter for another language is the classic "can your language
handle real complexity?" test. Brainfuck is ideal: the spec is tiny (8
instructions), but a correct interpreter requires bracket matching, memory
management, and I/O — all things that stress a language's string and array
handling. If Flow can interpret Brainfuck correctly, it can handle the
core patterns needed for the self-hosted compiler.

## File
`validation/brainfuck/brainfuck.flow`

## Structure

**Module:** `module validation.brainfuck`
**Imports:** `io`, `string`, `array`, `conv`

### Constants
- Tape size: 30000 cells (standard Brainfuck)

### Functions

1. **`fn:pure find_matching_bracket(program: string, pos: int, direction: int): int`**
   - From pos, scan forward (direction=1) or backward (direction=-1)
   - Track bracket depth to find the matching pair
   - Returns position of matching bracket

2. **`fn run(program: string): string`**
   - Initialize tape: array of 30000 zeros (or smaller for validation)
   - State: `ip` (instruction pointer), `dp` (data pointer), both `:mut`
   - Output buffer: `string:mut`
   - Main loop: while ip < program length
     - `>` : dp += 1
     - `<` : dp -= 1
     - `+` : tape[dp] += 1
     - `-` : tape[dp] -= 1
     - `.` : append char(tape[dp]) to output
     - `,` : skip (no stdin in validation)
     - `[` : if tape[dp] == 0, jump to matching `]`
     - `]` : if tape[dp] != 0, jump back to matching `[`
   - Return output string

3. **`fn:pure build_tape(size: int): array<int>`**
   - Create array of `size` zeros

4. **`fn main(): none`**
   - Run several Brainfuck programs, print output
   - Include: Hello World, simple counter, loop test

### Classic Brainfuck Programs

**Hello World:**
```
++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>.>---.+++++++..+++.>>.<-.<.+++.------.--------.>>+.>++.
```
Output: `Hello World!`

**Simple add (3 + 2):**
```
+++>++<[->+<]>.
```
Output: character with ASCII value 5 (non-printable, so use numeric output)

**Cat-like echo (simplified):**
```
>+++++++++[<++++++++>-]<.>+++++++[<++++>-]<+.+++++++..+++.
```
Output: `Hello`

## Test Program
`tests/programs/val_brainfuck.flow`

Tests with known outputs:
- Empty program: no output
- Single `.` on zeroed tape: outputs null character (or handle as empty)
- `+++++++++++++++++++++++++++++++++.` (33 pluses + dot): outputs `!` (ASCII 33)
- Addition program `+++>++<[->+<]>` then read dp value: verify cell = 5
- Nested loops: `++[>++[>+<-]<-]>>` -> verify final cell value
- Hello World (if feasible in test) or a shorter greeting

## Expected Output (test)
```
empty: (ok)
exclaim: !
add 3+2: 5
hello: Hello
nested: 4
done
```

## Estimated Size
~120 lines (app), ~60 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `string.char_at` | instruction fetch |
| `string.len` | program bounds |
| `array<int>` | memory tape |
| `array.get_int/set` | cell read/write |
| `while` loop | main interpreter loop |
| `:mut` variables | ip, dp, tape, output |
| `match` or `if/else` chain | instruction dispatch |
| Nested control flow | bracket matching |
| `conv.to_string` / char output | tape cell to character |

## Known Risks
- **Array mutation**: Flow arrays are immutable — each `+`/`-` instruction
  creates a new array. For a tape of 30000 cells, this is expensive. May
  need to use a smaller tape (256 or 1000 cells) for validation.
  This is a critical performance finding if it makes the interpreter
  unusably slow.
- **Char from int**: Converting an integer tape cell to a character for `.`
  output requires `char.from_byte` or similar. If this doesn't exist, use
  numeric output instead.
- **Array set**: Flow may not have `array.set(arr, idx, val)`. If not,
  building a new array with one element changed is O(n). This would be a
  major stdlib gap.
- The array mutation cost is the most important finding from this
  validation. It directly impacts whether Flow can handle mutable-state
  algorithms efficiently.
