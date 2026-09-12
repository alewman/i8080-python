# Handoff: build `i8080-python`, a pure-Python 8080A core in z80-python's shape

## Context you are inheriting

`/data/emu/i8080-python` holds documents and oracles, no code. It was written
so that the core can be built the way `z80-python` (`/data/emu/z80-python`,
GitHub alewman/z80-python) and `6502-python` (`/data/emu/6502-python`) were:
readable handlers, host-owned memory and ports, every claim pinned to an
external oracle whose tier is stated, nothing vendored. Read these, in this
order, before writing any Python:

1. `docs/start-here.md`: registers, the PSW byte with its three fixed bits,
   opcode fields, the full instruction table with state counts, the
   interrupt model, DAA, the twelve undocumented opcodes.
2. `docs/timing.md`: where the state counts come from and the Space Invaders
   board's two interrupts per frame.
3. `docs/undocumented-behavior.md`: the AC rules and every `[unverified]`.
4. `docs/validation.md`: the oracles, their tiers, hashes, and the
   `cpm-minimal` harness plan.
5. `docs/mame-oracle.md`: the verified MAME trace recipe and its line format.
6. `/data/emu/z80-python/docs/start-here.md`, `conformance.md`,
   `trace-schema.md`, and `src/z80_python/` for the shape to copy: module
   layout (`_core`, `_alu`, `_loads`, `_control`, `_dispatch`), handler
   docstrings that start with the Intel mnemonic, hardware reasons as
   comments on the lines that encode them, `tests/test_readability.py`,
   `validation/zex.py`, `validation/vector_utils.py`.

The oracle-tier rule: hardware-captured > hardware-corrected >
emulator-derived; a lower tier is a detector, never a judge. For the 8080 the
only hardware-captured oracle is `8080EXM.COM`'s CRC table; there is no
SingleStepTests corpus; MAME is the detector.

## Your task

Create the package `i8080_python` (distribution `i8080-python`, Python
3.12+, no runtime dependencies, CPython and PyPy) with:

- `I8080CPU`: a host subclasses it and supplies `read_byte`, `write_byte`,
  `read_port`, `write_port`; `step()` runs one instruction or one accepted
  lifecycle boundary and returns its state count from the table in
  `docs/start-here.md`; `request_interrupt(instruction_byte)`,
  `clear_interrupt()`, `request_reset()` / `clear_reset()` as z80-python has
  them; the EI delay, INTE clearing on acceptance, PC not advanced on the
  acknowledge fetch, HLT wakeup, and the fixed PSW bits exactly as documented.
- An immutable `CPUState` with every processor-owned field, a disassembler
  with a side-effect-free reader, and a conformance trace producer in
  z80-python's JSON Lines shape with an 8080 state object.
- A `validation/` package with the `cpm-minimal` host and runners for the
  four exercisers, and a MAME lockstep comparer that reads the `error.log`
  line format.

## Milestones, each with its acceptance test, in oracle-tier order

1. **Skeleton and per-opcode unit tests from the datasheet.** Every one of
   the 256 byte values has a handler and at least one unit test asserting its
   state count and its documented flag effects from `docs/start-here.md`,
   including `Jcc` 10 either way, `Ccc` 11/17, `Rcc` 5/11, the twelve
   aliases, `MOV M,M` = `HLT`, and `POP PSW` forcing bits 5, 3, 1.
   Acceptance: `pytest -q` green, a readability test that every handler
   docstring begins with its mnemonic, `ruff check .` clean.
2. **`8080PRE` and `TST8080` under `cpm-minimal`.** Acceptance: the exact
   success strings in `docs/validation.md`, within the instruction budgets
   there, with the state totals 7,817 and 4,924 reported (superzazu's
   emulator-derived totals; a difference is a lead, not a failure).
3. **`8080EXM` under `cpm-minimal`.** Acceptance: all 25 groups print
   `PASS!` with the CRCs in `docs/validation.md` and `Tests complete`
   appears; record interpreter, wall-clock, and state total
   (23,803,381,171 expected). Run it under PyPy if available; under CPython
   expect hours. `CPUTEST` is optional and opt-in (`--include-cputest`);
   if you run it, `CPU TESTS OK`.
4. **Lifecycle tests.** Unit tests for: EI delay (an interrupt requested
   before `EI` is accepted only after the following instruction), INTE
   cleared on acceptance, pushed return address equals the interrupted PC,
   `HLT` then interrupt pushes the address after `HLT`, `HLT` with INTE clear
   never wakes on INT, RESET clears PC/INTE/halt and nothing else, an
   interrupt accepted with `RST n` costs 11. No hardware oracle covers these;
   cite the manual section on each test.
5. **MAME lockstep on `invaders` as the detector.** Build the `invaders` host
   from `docs/timing.md` and `docs/mame-oracle.md`, produce MAME's
   `error.log` for 60 frames with the recipe there, and diff every line.
   Acceptance: identical `pc a b c d e h l sp`, `f` masked to the five flags,
   and cumulative states equal to `totalcycles`, for the full 60 frames
   (about 230,000 instructions), or the first divergence reported with ten
   lines of context from each side and resolved by consulting the datasheet
   and the CRCs, never by copying MAME. If MAME turns out to be wrong, say
   so with the evidence and keep the datasheet behavior.

Do not skip or reorder rungs; each one's failure is cheapest to diagnose
before the next.

## Constraints

- **No vendoring.** The exercisers stay in the gitignored
  `tests/exercisers/` (`python scripts/fetch_exercisers.py`); ROMs are read
  in place from the MAME ROM path; MAME logs stay out of the repository.
  `CPUTEST.COM` is proprietary and must never be committed.
- **Pin everything.** Every claim names the exerciser hashes, the MAME
  version (0.285), the interpreter, and the commit of this repository it was
  reproduced at. "The whole suite" means every rung; do not say it if a rung
  was skipped.
- **Report failures with their output.** A CRC mismatch is reported with the
  group name and both CRCs; a MAME divergence with the line numbers and both
  lines; a budget overrun with the last PC.
- **Keep the tier discipline in the prose.** Anything checked only against
  MAME or superzazu is "cross-checked against an emulator"; only the CRC
  table earns "verified against real 8080A hardware".
- **Transcribe the shape, do not redesign it.** Explicit if-chain dispatch
  as z80-python uses (it is what PyPy compiles well and what makes every
  opcode greppable); one byte for F with named accessors that keep bits 5,
  3, 1 fixed.
- Commit in reviewable units with messages that say what the change rests
  on. Push and open PRs only when the user asks. Attribution trailer on
  commits: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Python 3.14 is at `/usr/bin/python3`; z80-python's venvs are at
  `/data/emu/z80-python/.venv` and `.venv-pypy`. Do not modify any other
  directory under `/data/emu`.

## What done looks like

A README that states, with the four numbers (this repository's commit, the
exerciser hashes, the MAME version, the interpreter), which rungs pass; a CI
job that reproduces rungs 1, 2, and 4 on every push and runs rung 3 weekly or
on demand; and `docs/validation.md` rewritten from "oracles available" into a
certification record in z80-python's form, with the `[unverified]` entries in
`docs/undocumented-behavior.md` either still marked or replaced by evidence.

Before starting, tell the user in a few sentences how you read this brief and
what you will do first.
