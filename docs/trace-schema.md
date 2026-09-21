# Trace schema (version 1)

A trace is the observable behavior of an 8080 core written down one processor
boundary at a time. Two cores that produce equal traces for the same program
and host are, as far as software can tell, the same CPU. The record shape is
z80-python's version-1 trace with an 8080 state object. Everything here is
implemented by `src/i8080_python/trace.py`; if the two disagree, the code is
the specification and this page has a bug.

## Producing one

From Python, `trace_steps(cpu, peek, max_steps=N, between=hook)` yields a
`StepRecord` per boundary and `write_trace` writes them;
`iter_session_steps(session, max_steps=N)` does the same through a
`DebugSession`, adding `accesses` when the session tracks the bus. For a
CP/M exerciser:

```text
python -m validation.cpm tests/exercisers/TST8080.COM --trace tst8080.jsonl --trace-steps 100000
```

The `cpm-minimal` traps (BDOS at 0x0005, warm boot at 0x0000) are host
behavior. They run between records and produce none; their effect shows only
as the difference between one record's `after` and the next record's `before`.
The TST8080 trace is 646 records totalling 4,874 states.

## File format

JSON Lines: UTF-8, one JSON object per line, `\n` terminated, blank lines
ignored. This package writes sorted keys and no whitespace; readers must not
depend on either. Records are aligned by line position when two traces are
compared; `sequence` is informational.

## Record

| Key | Type | Meaning |
| --- | --- | --- |
| `version` | integer | Always `1`. A reader rejects any other value. |
| `sequence` | integer >= 0 | Producer-local counter. |
| `kind` | string | One of the four boundary kinds below. |
| `states` | integer > 0 | States the boundary consumed, exactly as `step()` returned them. |
| `instruction` | object or `null` | The instruction fetched at an `instruction` boundary; `null` for every other kind. |
| `before` | state object | Processor state at the boundary's start. |
| `after` | state object | Processor state at its end. |
| `accesses` | array, optional | Every bus access the boundary made, in order, when the producer recorded them. |

No other keys are allowed. (z80-python calls the count `t_states`; the 8080
manuals say "states", and so does this schema.)

### `kind`

| Value | When | States |
| --- | --- | --- |
| `instruction` | An opcode was fetched from memory and executed. | Intel's summary table |
| `halt_idle` | The CPU was halted and nothing could wake it. | 7, a modeling choice (`HALT_IDLE_STATES`) |
| `reset` | RESET was asserted. | 3, a modeling choice |
| `interrupt` | A pending INT was accepted: the device's byte executed with PC not advanced and INTE cleared. | the injected instruction's own count; 11 for `RST n` |

The kind is decided from `before`, in this order: `reset_pending`; then a
non-null `interrupt_vector` with `inte` true and `ei_delay` 0; then
`halted`; otherwise `instruction`. A record whose `kind` contradicts its
`before` state is rejected.

### `accesses`

Each entry is `[kind, address, value]`: `"r"` or `"w"` for a memory read or
write, `"in"` or `"out"` for a port, with the 8-bit value. The key is present
only when the producer tracked the bus -- `iter_session_steps` over a
`DebugSession(track_accesses=True)` ([debug-session.md](debug-session.md)) --
and two records are compared on it **only when both carry it**, since a trace
written without tracking says nothing about the bus either way. Without it a
trace is byte-for-byte what a producer wrote before the key existed, so the
schema version stays 1; a reader that predates the key rejects a record
carrying it, because unknown keys are rejected.

### `instruction`

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `address` | integer 0..0xFFFF | yes | PC at fetch. |
| `data` | lowercase hex string | yes | Every byte the instruction occupies, e.g. `"c31301"`. |
| `mnemonic` | string | optional | As this package's disassembler prints it, e.g. `"JMP"`. |
| `operands` | array of strings | optional | Likewise, e.g. `["0113H"]`. |

`mnemonic` and `operands` are present together or absent together. **A
producer in another language should omit both**; the reader decodes `data`
with this package's disassembler, so a port only has to get the bytes right.

### State object

Every key is required and no others are allowed. These are the fields of
`CPUState`.

| Key | Type | Meaning |
| --- | --- | --- |
| `a` `b` `c` `d` `e` `h` `l` | 0..255 | Registers. |
| `f` | 0..255 | The whole flag byte, `S Z 0 AC 0 P 1 CY`: bits 5 and 3 are 0 and bit 1 is 1, always. |
| `sp` `pc` | 0..65535 | Stack pointer, program counter. |
| `inte` | boolean | Interrupt-enable flip-flop. |
| `halted` | boolean | HLT executed and not yet exited. |
| `ei_delay` | 0 or 1 | 1 at the one boundary after `EI`, where an interrupt cannot be accepted. |
| `reset_pending` | boolean | The host holds RESET asserted. |
| `interrupt_vector` | 0..255 or `null` | The byte a device has placed on the bus with INT asserted; `null` when INT is not asserted. |

The handoff brief's sketch named this last field `interrupt_pending`. It
carries the vector instead of a boolean because the byte the device supplies
is part of what the CPU will do, and `null` still means "not pending".

## Comparison

`first_trace_divergence(left, right)` walks both traces lazily and reports
the first record index and field path that differ (`kind`, `states`,
`instruction.address`, `instruction.data`, `before.<field>`, `after.<field>`,
and `accesses` when both records carry it), or `record` when one trace ends
first.

## Versioning

Any change to the set of keys, their types, or their meaning is a new
`version`, and readers reject versions they do not know.
