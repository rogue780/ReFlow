# Validation: File Processor

## Category
Standard Library & I/O Stress Test

## What It Validates
- Large file reading and writing (buffered I/O through runtime)
- Line-by-line file processing (`file.open_read`, `file.read_line`, `file.close`)
- File writing (`file.open_write`, `file.write_string`)
- Temp file creation and cleanup (`io.tmpfile_create`, `io.tmpfile_remove`)
- String manipulation at scale (`string.to_upper`, `string.contains`, `string.replace`, `string.trim`, `string.len`)
- Mutable counters and accumulators
- Option handling on every `file.read_line` call
- Error handling for missing files

## Why It Matters
File I/O is the most basic form of real-world interaction. This program
generates a large test file, then processes it through multiple
transformation passes — uppercasing, filtering, line numbering, word
replacement. This validates that the runtime's file I/O is correct,
doesn't leak file handles, and handles large volumes without crashing.

## File
`validation/file_processor/file_processor.flow`

## Structure

**Module:** `module validation.file_processor`
**Imports:** `io`, `file`, `string`, `conv`, `sys`

### Functions

1. **`fn generate_test_file(path: string, num_lines: int): none`**
   - Write `num_lines` lines of synthetic data
   - Mix of: `"INFO: operation completed successfully"`, `"WARN: disk usage at 80%"`,
     `"ERROR: connection timeout"`, `"DEBUG: entering function process_data"`,
     `"INFO: user login from 192.168.1.x"`
   - Cycle through patterns using modulo on line number
   - Each line prefixed with line number

2. **`fn count_lines(path: string): int`**
   - Open, read line-by-line, count, close
   - Return count

3. **`fn filter_lines(input_path: string, output_path: string, pattern: string): int`**
   - Read input, write lines containing `pattern` to output
   - Return count of matching lines

4. **`fn transform_uppercase(input_path: string, output_path: string): none`**
   - Read each line, write `string.to_upper(line)` to output

5. **`fn add_line_numbers(input_path: string, output_path: string): none`**
   - Read each line, write `"NNNN: line_text"` with zero-padded line numbers
   - (Or simple numbering if zero-padding is complex)

6. **`fn replace_in_file(input_path: string, output_path: string, old: string, new_str: string): int`**
   - Read each line, apply `string.replace`, write to output
   - Return count of lines where replacement occurred

7. **`fn main(): none`**
   - Generate test file with 1000 lines
   - Run each transformation
   - Print summary statistics (line counts, match counts)
   - Clean up temp files

## Test Program
`tests/programs/val_file_processor.flow`

Uses small files (10 lines) for deterministic output:
- Generate 10-line file
- Count lines -> 10
- Filter for "ERROR" -> count matching
- Transform to uppercase -> verify first line
- Replace "INFO" with "LOG" -> count replacements
- Clean up

## Expected Output (test)
```
generated: 10
counted: 10
errors found: 2
first upper: 1: INFO: OPERATION COMPLETED SUCCESSFULLY
replacements: 4
done
```

(Exact numbers depend on the cycling pattern chosen)

## Estimated Size
~130 lines (app), ~60 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `file.open_read/write` | every function |
| `file.read_line` + option | line-by-line loop |
| `file.write_string` | output writing |
| `file.close` | resource cleanup |
| `io.tmpfile_create/remove` | test file management |
| `string.to_upper` | transformation |
| `string.contains` | filtering |
| `string.replace` | substitution |
| `conv.to_string` | line number formatting |
| `:mut` counters | line counting, match counting |

## Known Risks
- File handle leaks: if a function returns early without `file.close`,
  handles accumulate. Flow has no `defer` or RAII — must be careful.
- Large file generation (1000+ lines) may be slow if `file.write_string`
  flushes on every call. The test uses 10 lines to keep it fast.
