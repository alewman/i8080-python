# i8080-python

A readable, dependency-free Python 3.12+ Intel 8080A **instruction core**, to be
built in the shape of [z80-python](https://github.com/alewman/z80-python) and
[6502-python](https://github.com/alewman/6502-python): the host owns memory
and the 256 I/O ports and supplies `read_byte`, `write_byte`, `read_port`,
`write_port`; the core owns registers, flags, instruction semantics, documented
state counts, and the INT/INTE/HLT lifecycle at instruction boundaries; every
correctness claim is pinned to an external oracle whose tier is stated.

## Status: documents and oracles only, no core yet

This repository currently holds the groundwork a later session builds from:

- the processor as the core will model it ([docs/start-here.md](docs/start-here.md)),
- state counts and what a Space Invaders host needs from them ([docs/timing.md](docs/timing.md)),
- undocumented opcodes and flag results with their evidence ([docs/undocumented-behavior.md](docs/undocumented-behavior.md)),
- every oracle found for the 8080, ranked by tier ([docs/validation.md](docs/validation.md)),
- a script that fetches the CP/M exercisers with pinned hashes ([scripts/fetch_exercisers.py](scripts/fetch_exercisers.py)),
- a working MAME 0.285 trace recipe ([docs/mame-oracle.md](docs/mame-oracle.md)),
- the brief for the session that writes the core ([docs/handoff-brief.md](docs/handoff-brief.md)).

There is no `src/` directory, no package, and no test suite. Nothing here is a
correctness claim about any code.

## The chip and the boards

The Intel 8080 (1974) was replaced within months by the **8080A**, a corrected
mask with the same instruction set; the boards below carry the 8080A or a
second-source of it. The most widely emulated user is Space Invaders:

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

The intended 8080/8080A/8085 pointers and sources are in
[docs/start-here.md](docs/start-here.md). The original non-A 8080 is out of
scope; its differences are electrical and timing-related, not architectural
(see the same page).

## Embedding contract (planned)

Identical in shape to z80-python. A machine subclasses the CPU and supplies its
memory and port spaces; `step()` executes one instruction or one accepted
lifecycle boundary and returns its documented state count:

```python
class Machine(I8080CPU):
    def read_byte(self, addr): ...
    def write_byte(self, addr, value): ...
    def read_port(self, port): ...      # 8-bit port number
    def write_port(self, port, value): ...
```

Interrupts are requested between steps with the instruction byte the board
puts on the bus (`request_interrupt(0xCF)` for Space Invaders' `RST 1`),
never by mutating PC or SP.

## Documents

See [docs/README.md](docs/README.md) for the index and the reading order.

## License

MIT (this repository's own documents and scripts). The exercisers, MAME, and
ROM sets are external and retain their own licenses; none is bundled. The
fetch script downloads GPL-2.0 exerciser programs into an ignored directory
and refuses to fetch the one proprietary program unless asked.
