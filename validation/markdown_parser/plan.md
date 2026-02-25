# Validation: Markdown Parser

## Category
Complex "Real-World" Application — Text Processing

## What It Validates
- Complex string processing (multi-pass parsing)
- Line-by-line text analysis with state tracking
- String prefix matching (`string.starts_with`)
- String slicing and trimming (`string.substring`, `string.trim`)
- State machine pattern (tracking whether we're in a code block, list, etc.)
- Output string building (generating HTML or structured output)
- Handling of edge cases (empty lines, nested formatting, escaped characters)

## Why It Matters
A Markdown parser is a real-world text processing application that requires
multi-pass string analysis, state tracking across lines, and generation of
structured output. Unlike the JSON parser (which is character-level recursive
descent), Markdown is line-oriented with inline formatting — a different
parsing pattern that tests Flow's string operations in a realistic scenario.

## File
`validation/markdown_parser/markdown_parser.flow`

## Supported Subset
Full Markdown is too complex. This parser handles:

**Block-level:**
- Headings: `# H1`, `## H2`, `### H3` (up to 6 levels)
- Paragraphs: consecutive non-empty lines
- Code blocks: triple backtick fences (` ``` `)
- Unordered lists: `- item` or `* item`
- Horizontal rules: `---`
- Blank line separators

**Inline:** (stretch goal — skip if block-level alone is complex enough)
- Bold: `**text**`
- Italic: `*text*`
- Inline code: `` `code` ``

## Structure

**Module:** `module validation.markdown_parser`
**Imports:** `io`, `string`, `array`, `conv`, `file`

### Types

```flow
type Block = Heading { level: int, text: string }
           | Paragraph { text: string }
           | CodeBlock { language: string, code: string }
           | ListItem { text: string }
           | HorizontalRule
           | BlankLine
```

### Functions

1. **`fn:pure count_prefix(line: string, ch: string): int`**
   - Count how many times `ch` appears at the start of `line`
   - For heading level detection (`###` -> 3)

2. **`fn:pure parse_line(line: string, in_code_block: bool): Block`**
   - If in_code_block and not closing fence: treat as code content
   - If starts with `#`: Heading with appropriate level
   - If starts with `- ` or `* `: ListItem
   - If `---` or `***`: HorizontalRule
   - If ` ``` `: toggle code block
   - If empty: BlankLine
   - Else: Paragraph

3. **`fn parse_document(input: string): array<Block>`**
   - Split input by newlines (or read line-by-line)
   - Track code block state across lines
   - Merge consecutive code lines into single CodeBlock
   - Merge consecutive paragraph lines into single Paragraph
   - Return array of blocks

4. **`fn:pure block_to_html(block: Block): string`**
   - `Heading(n, text)` -> `<h{n}>{text}</h{n}>`
   - `Paragraph(text)` -> `<p>{text}</p>`
   - `CodeBlock(lang, code)` -> `<pre><code>{code}</code></pre>`
   - `ListItem(text)` -> `<li>{text}</li>`
   - `HorizontalRule` -> `<hr>`
   - `BlankLine` -> empty string

5. **`fn:pure blocks_to_html(blocks: array<Block>): string`**
   - Map block_to_html over blocks, join with newlines
   - Wrap adjacent ListItems in `<ul>...</ul>`

6. **`fn:pure block_to_string(block: Block): string`**
   - Debug representation: `"Heading(2, 'title')"`

7. **`fn main(): none`**
   - Read a Markdown file (or use embedded test string)
   - Parse to blocks
   - Output as HTML

## Test Program
`tests/programs/val_markdown_parser.flow`

Test input (embedded string):
```markdown
# Hello

This is a paragraph
with two lines.

## Features

- Item one
- Item two
- Item three

---

```code
let x = 42
```

Done.
```

Tests:
- Block count is correct
- Heading levels are correct
- Paragraph merges consecutive lines
- List items are parsed
- Code block captures content
- Horizontal rule detected
- HTML output is well-formed

## Expected Output (test)
```
blocks: 8
block 0: Heading(1, Hello)
block 1: Paragraph
block 2: Heading(2, Features)
block 3: ListItem(Item one)
block 4: ListItem(Item two)
block 5: ListItem(Item three)
block 6: HorizontalRule
block 7: CodeBlock
html heading: <h1>Hello</h1>
html para: <p>This is a paragraph with two lines.</p>
html hr: <hr>
done
```

## Estimated Size
~200 lines (app), ~80 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Sum type (6 variants) | `Block` |
| `match` on sum type | block_to_html, block_to_string |
| `string.starts_with` | line classification |
| `string.substring` | extracting heading text, list text |
| `string.trim` | cleaning whitespace |
| `string.len` | empty line detection |
| `string.split` | splitting document into lines |
| State machine (`:mut` bool) | tracking code block state |
| `array<Block>` | sum type array (non-pointer push) |
| `fn:pure` | all parsing functions |

## Known Risks
- `array<Block>` where Block is a sum type: tests Known Decision #9
  (array.push_sized for non-pointer types). If this fails, it's a
  critical finding.
- Merging consecutive paragraph lines requires look-ahead or a second
  pass. A two-pass approach (parse lines, then merge) is cleaner.
- `string.split(doc, "\n")` may not work if the separator is a single
  character escape. Test this.
- Code block content concatenation may require building strings
  incrementally. If `string_builder` is available, use it.
