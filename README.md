# i8080-python

A readable, dependency-free Intel 8080A **instruction core**, in
the shape of [z80-python](https://github.com/alewman/z80-python) and
[6502-python](https://github.com/alewman/6502-python). The host owns memory
and the 256 I/O ports and passes them in as four callables, the embedding
contract z80-python 0.4.0 and m6800-python share. The core owns registers,
flags, instruction semantics, Intel's
documented state counts, and the INT/INTE/HLT/RESET lifecycle at instruction
boundaries. Every correctness claim is pinned to an external oracle whose tier
is stated.

## Status

Certified at commit `fd47550` (2026-09-21) on Linux x86_64, CPython 3.14.4 and
PyPy 7.3.20 (Python 3.11.13). Every rung of the ladder in
[docs/handoff-brief.md](docs/handoff-brief.md) passes:

| Rung | Oracle and tier | Result |
| --- | --- | --- |
| 1. Per-opcode tests | Intel's summary table [UM p. 4-15] and flag rules, transcribed by hand (the specification) | all 256 opcodes; 1,354 tests pass on both interpreters |
| 2. `8080PRE`, `TST8080` | self-checking CP/M programs (specification-derived) | `8080 Preliminary tests complete`; `CPU IS OPERATIONAL` |
| 3. `8080EXM` | **hardware-captured**: CRCs from 13 real 8080A chips | **all 25 CRCs match**, 159 s under PyPy |
| 3. `CPUTEST` (opt-in) | self-checking, proprietary, not fetched by default | `CPU TESTS OK` |
| 4. Lifecycle | Intel's manuals, section by section; no hardware oracle exists | 18 tests pass |
| 5. MAME lockstep, `invaders`, 60 frames | MAME 0.285 (emulator-derived, a detector) | 230,313 instructions and 102 interrupt acceptances identical |

The instruction set is **verified against real 8080A hardware** where
8080EXM reaches: every documented ALU, INR/DCR, INX/DCX, DAD, load, store,
MVI, MOV, rotate, and DAA instruction, with all eight flag bits. State counts,
branches, I/O, and the interrupt lifecycle are checked against the manuals and
**cross-checked against an emulator** (MAME, and superzazu/8080's state
totals, which every exerciser run matches exactly). The twelve undocumented
opcodes follow emulator consensus and are unverified on hardware. The pinned
hashes, commands, and timings are in [docs/validation.md](docs/validation.md).

## Using it

The memory bus is two callables, so a flat 64 KiB host is two arguments:

```python
from i8080_python import I8080CPU

memory = bytearray(0x10000)
memory[0:2] = bytes((0x3E, 0x2A))  # MVI A,2AH

cpu = I8080CPU(memory.__getitem__, memory.__setitem__)
assert cpu.step() == 7 and cpu.a == 0x2A
```

The I/O bus is two more, by keyword, and defaults to nothing connected: `IN`
reads 0xFF and `OUT` goes nowhere. A board supplies its own and keeps whatever
state it likes:

```python
class Board:
    def __init__(self, rom: bytes):
        self.rom = rom
        self.ram = bytearray(0x2000)
        self.cpu = I8080CPU(
            self.read_byte, self.write_byte, read_port=self.read_port, write_port=self.write_port
        )
```

`step()` runs one instruction or one lifecycle boundary and returns its state
count. Interrupts are requested between steps with the byte the board puts on
the bus, `request_interrupt(0xCF)` for `RST 1`. The request is level-held and
is accepted when INTE allows, after the EI delay. RESET is
`request_reset()` / `clear_reset()`. `capture_state()` returns an immutable
`CPUState`. `disassemble()` decodes Intel syntax from a side-effect-free
reader. `trace_steps()` produces the JSON Lines conformance trace described
in [docs/trace-schema.md](docs/trace-schema.md).

To step through code, `DebugSession` adds breakpoints, bounded runs,
watchpoints and bus-access tracking, `CommandDebugger` is a text frontend
over it, and the two are wired together by:

```text
python -m i8080_python --load 8080pre.com@0x100 --pc 0x100
```

See [docs/debug-session.md](docs/debug-session.md).

Stated limitations: only one-byte instructions can be injected on interrupt
acknowledge (the 8228's three-byte `CALL` is refused), and the halt idle (7
states) and RESET (3 states) counts are modeling choices, documented as such.

## Reading the code

`src/i8080_python/` has one mixin per group of Intel's instruction-set
chapter: `_transfer.py`, `_arithmetic.py`, `_logical.py`, `_branch.py`,
`_machine.py` (stack, I/O, machine control). `_dispatch.py` holds one explicit
if-chain over all 256 bytes, and every handler's docstring starts with its
Intel mnemonic, so `grep -n "DAA" src/` finds the code.
`tests/test_readability.py` enforces that the way the oracles enforce
correctness.

## Reproducing the certification

```text
python -m pip install -e ".[dev]"
python scripts/fetch_exercisers.py          # pinned by SHA-256; --include-cputest is opt-in
python -m pytest -q                         # rungs 1, 2, 4 (and 5 if the trace exists)
python -m validation.cpm tests/exercisers/8080EXM.COM   # rung 3; use PyPy
python scripts/mame_trace.py                # MAME 0.285 + invaders ROM set
python -m validation.mame_lockstep tests/mame_traces/run60/error.log   # rung 5
```

CI runs rungs 1, 2, and 4 on every push (CPython 3.12-3.14, PyPy 3.11) and
8080EXM weekly under PyPy.

## The chip and the boards

The Intel 8080 (1974) was replaced within months by the **8080A**, a corrected
mask with the same instruction set. The boards below carry the 8080A or a
second source of it. The most widely emulated user is Space Invaders:

- **Taito 8080 boards** (1978 onward): Space Invaders, Space Invaders Part II,
  Lunar Rescue, Space Chaser, Balloon Bomber, Polaris, Indian Battle. MAME
  models these in `src/mame/midw8080/8080bw.cpp`.
- **Midway 8080 black-and-white boards** (1975-1980, Dave Nutting Associates /
  Midway): Gun Fight, Sea Wolf, 280-ZZZAP, Boot Hill, Clowns, Space Invaders M
  (Midway's licensed set, MAME `invaders`), Space Invaders II. MAME models
  these in `src/mame/midw8080/mw8080bw.cpp`, with a 1.9968 MHz 8080 and two
  interrupts per frame.

The board lists above are restated from the `GAME` tables of those two MAME
0.285 source files (BSD-3-Clause), not copied.

### Scope decision: 8080A only, 8085 differences noted

The core targets the Intel 8080A as the arcade boards use it. The 8085 shares
the instruction set but differs in ways that matter to an emulator, and the
documents mark each place where they diverge rather than modeling the 8085:

| Area | 8080A | 8085 |
| --- | --- | --- |
| Flags | S Z 0 AC 0 P 1 CY; bits 5, 3, 1 fixed | undocumented V (bit 1) and K/X5 (bit 5) flags |
| `ANA`/`ANI` auxiliary carry | OR of bit 3 of the two operands | always set |
| Opcodes 08/10/18/20/28/30/38, CB, D9, DD, ED, FD | NOP, JMP, RET, CALL aliases | DSUB, ARHL, RDEL, RIM, LDHI, SIM, LDSI, RSTV, SHLX, JNK, LHLX, JK |
| States | e.g. MOV r,r 5, CALL 17, Jcc always 10, XTHL 18 | MOV r,r 4, CALL 18, Jcc 7/10, XTHL 16; many others differ |
| Interrupts | INT with a bus-supplied instruction | plus TRAP, RST 5.5/6.5/7.5 |

AMD's 9080A/8080A second sources clear AC on `ANA` and fail the Intel CRCs;
the core models Intel. The original non-A 8080 is out of scope; its
differences are electrical and timing-related, not architectural (see
[docs/start-here.md](docs/start-here.md)).

## Documents

See [docs/README.md](docs/README.md) for the index and the reading order.

## License

MIT (this repository's code, documents, and scripts). The exercisers, MAME,
and ROM sets are external and keep their own licenses; none is bundled. The
fetch script downloads the GPL-2.0 exerciser programs into an ignored
directory and fetches the one proprietary program only when asked.
