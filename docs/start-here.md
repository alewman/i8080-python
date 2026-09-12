# Start here: the 8080A as this core will model it

This page is for someone who has read z80-python's `docs/start-here.md` and
wants the same key for the Intel 8080A: the register file, the flag byte and
its fixed bits, the way an opcode byte splits into fields, the complete
instruction table with state counts, the interrupt model, DAA, and the
undocumented opcodes. There is no core yet; when there is, the code is the
reference and this page is the map. Every claim names its source. Sources are
listed at the end with their URLs and licenses; `[UM]` is Intel's 1975 User's
Manual, `[ALP]` the 1981 Assembly Language Programming Manual, `[EXM]` the
hardware-captured exerciser CRCs described in [validation.md](validation.md).

## Register file

| Name | Width | Notes |
| --- | --- | --- |
| A | 8 | Accumulator. With F it forms the PSW, the pair `PUSH PSW`/`POP PSW` move |
| F | 8 | Five flags and three fixed bits, below |
| B, C, D, E, H, L | 8 | General registers; pairs BC ("B"), DE ("D"), HL ("H") in Intel's operand syntax |
| SP | 16 | Stack pointer; grows down; `PUSH` writes the high byte to SP-1, then the low byte to SP-2 `[UM ch. 4, PUSH rp]` |
| PC | 16 | Program counter |
| INTE | 1 | Interrupt-enable flip-flop; set by `EI`, cleared by `DI`, by interrupt acceptance, and by RESET `[UM ch. 2]` |
| halted | 1 | Whether `HLT` has been executed and not yet exited |

HL is the memory-pointer register: `M` in Intel syntax means "the byte at
HL" and takes register slot 6 in every register-operand instruction. BC and
DE address memory only through `LDAX`/`STAX`. The 8080 has internal W and Z
temporaries used to assemble addresses, but unlike the Z80's WZ they never
leak into any architecturally visible result, so the core need not model them
(there is no `BIT n,(HL)` on this chip and no undocumented flag bits copy from
an address latch). There is also no refresh register, no alternate set, no
index registers, and no interrupt mode.

The complete processor-owned state is therefore: A, F, B, C, D, E, H, L, SP,
PC, INTE, halted, plus the one-instruction EI delay and any pending interrupt
request the host has made.

## The F byte (the low byte of the PSW)

```text
bit:   7   6   5   4   3   2   1   0
flag:  S   Z   0   AC  0   P   1   CY
```

- **S** sign: bit 7 of the result. **Z** zero. **CY** carry out of bit 7 on
  add, borrow on subtract and compare, the bit shifted out on rotates.
- **AC** auxiliary carry: carry out of bit 3. Not testable by any branch; it
  exists for `DAA` `[ALP 1-11]`. Its rules per instruction family are in
  [undocumented-behavior.md](undocumented-behavior.md) because the manuals
  leave some of them implicit.
- **P** parity: 1 for an even number of set bits in the result `[ALP 1-11]`.
- **Bits 5 and 3 are always 0 and bit 1 is always 1.** `PUSH PSW` "adds three
  bits of filler" and `POP PSW` "strips out these filler bits" `[ALP 1-14]`;
  the exerciser's author notes that, unlike the 8085 and Z80, the 8080 does
  define these bits, `[S Z 0 AC 0 P 1 C]`, and the hardware CRCs were
  captured with an all-ones flag mask, so real 8080As produce exactly these
  values `[EXM]`.

A core that stores F as one byte must force bits 5, 3, and 1 whenever it
writes F, including on `POP PSW`; one that stores five booleans must compose
the byte on `PUSH PSW`. Either way the value a program can observe is fixed.

## How an opcode byte is decoded

Every opcode is three bit fields, and the tables below are in the same order
the Z80's are because the Z80 kept them:

```text
opcode = xx yyy zzz        x = opcode >> 6      y = (opcode >> 3) & 7      z = opcode & 7
```

| x | Meaning | Example |
| --- | --- | --- |
| 01 | `MOV r[y], r[z]`; 0x76 (`MOV M,M`) is `HLT` | 0x78 = `MOV A,B` |
| 10 | `alu[y] r[z]` | 0x91 = `SUB C` |
| 00, 11 | Loads, 16-bit ops, jumps, calls, stack, I/O, control; selected by z and y | 0xC3 = `JMP` |

| Table | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r (DDD/SSS in `[UM]`) | B | C | D | E | H | L | M | A |
| rp (RP), index `(opcode >> 4) & 3` | B (BC) | D (DE) | H (HL) | SP | | | | |
| rp2 for `PUSH`/`POP` | B | D | H | PSW | | | | |
| cc (CCC) | NZ | Z | NC | C | PO | PE | P | M |
| alu | ADD | ADC | SUB | SBB | ANA | XRA | ORA | CMP |

`RST n` jumps to `y * 8` (the manual says the three-bit code is moved into
bits 3-5 of PC `[ALP, RST]`). Conditional jumps, calls, and returns use y as
cc. Immediate ALU instructions are `11 yyy 110`. In this encoding there are
exactly 244 distinct documented instructions; the 12 remaining byte values
are the undocumented aliases at the end of this page.

## Addressing

| Mode | Instructions | Operand bytes |
| --- | --- | --- |
| Register | `MOV`, ALU, `INR`/`DCR`, rotates, `XCHG`, `SPHL`, `PCHL` | 0 |
| Register indirect via HL (`M`) | any r-operand instruction with r = 6 | 0 |
| Register indirect via BC/DE | `LDAX`, `STAX` | 0 |
| Immediate | `MVI`, `LXI`, `ADI`... `CPI` | 1 or 2 (little-endian) |
| Direct | `LDA`, `STA`, `LHLD`, `SHLD`, `JMP`/`Jcc`, `CALL`/`Ccc` | 2 (little-endian) |
| Stack | `PUSH`, `POP`, `XTHL`, `CALL`, `RET`, `RST` | 0 |
| Port | `IN p`, `OUT p` | 1; the port number is driven on both halves of the address bus `[ALP 1-14]` |

Operand bytes are read from PC in order, low byte first, and the 8080 has no
displacement, relative, or indexed modes.

## The instruction set

States are T-states at the CPU clock (1.9968 MHz on the Midway board, so one
state is about 0.5 µs). Two values `a/b` mean condition false / condition
true. The totals are those of the "Summary of Processor Instructions" table
in `[UM p. 4-15]`; MAME 0.285's `lut_cycles_8080` agrees with every entry.
`[timing.md](timing.md)` shows how each total decomposes into machine cycles.

### Data transfer

| Mnemonic | Encoding | Bytes | States | Flags | Notes |
| --- | --- | --- | --- | --- | --- |
| `MOV r1,r2` | `01 DDD SSS` | 1 | 5 | none | |
| `MOV r,M` | `01 DDD 110` | 1 | 7 | none | |
| `MOV M,r` | `01 110 SSS` | 1 | 7 | none | `01 110 110` is `HLT` |
| `MVI r,d8` | `00 DDD 110` | 2 | 7 | none | |
| `MVI M,d8` | `00 110 110` | 2 | 10 | none | |
| `LXI rp,d16` | `00 RP0 001` | 3 | 10 | none | |
| `LDA a16` | `00 111 010` (3A) | 3 | 13 | none | |
| `STA a16` | `00 110 010` (32) | 3 | 13 | none | |
| `LHLD a16` | `00 101 010` (2A) | 3 | 16 | none | L from a16, H from a16+1 |
| `SHLD a16` | `00 100 010` (22) | 3 | 16 | none | |
| `LDAX rp` | `00 RP1 010` (0A, 1A) | 1 | 7 | none | rp = B or D only |
| `STAX rp` | `00 RP0 010` (02, 12) | 1 | 7 | none | rp = B or D only |
| `XCHG` | EB | 1 | 4 | none | swaps HL and DE |

### Arithmetic

| Mnemonic | Encoding | Bytes | States | Flags | Notes |
| --- | --- | --- | --- | --- | --- |
| `ADD r` / `ADC r` | `10 000 SSS` / `10 001 SSS` | 1 | 4 (M: 7) | Z S P CY AC | |
| `SUB r` / `SBB r` | `10 010 SSS` / `10 011 SSS` | 1 | 4 (M: 7) | Z S P CY AC | CY = borrow |
| `ADI` / `ACI` / `SUI` / `SBI d8` | C6 / CE / D6 / DE | 2 | 7 | Z S P CY AC | |
| `INR r` / `DCR r` | `00 DDD 100` / `00 DDD 101` | 1 | 5 (M: 10) | Z S P AC | CY untouched |
| `INX rp` / `DCX rp` | `00 RP0 011` / `00 RP1 011` | 1 | 5 | none | |
| `DAD rp` | `00 RP1 001` | 1 | 10 | CY only | HL += rp |
| `DAA` | 27 | 1 | 4 | Z S P CY AC | below |

### Logical

| Mnemonic | Encoding | Bytes | States | Flags | Notes |
| --- | --- | --- | --- | --- | --- |
| `ANA r` | `10 100 SSS` | 1 | 4 (M: 7) | Z S P CY AC | CY = 0; AC = OR of bit 3 of the operands `[ALP 1-12]` |
| `XRA r` / `ORA r` | `10 101 SSS` / `10 110 SSS` | 1 | 4 (M: 7) | Z S P CY AC | CY = AC = 0 `[ALP ch. 3]` |
| `CMP r` | `10 111 SSS` | 1 | 4 (M: 7) | Z S P CY AC | A - r, result discarded |
| `ANI` / `XRI` / `ORI` / `CPI d8` | E6 / EE / F6 / FE | 2 | 7 | Z S P CY AC | same rules as the register forms |
| `RLC` / `RRC` | 07 / 0F | 1 | 4 | CY only | rotate, bit out to CY |
| `RAL` / `RAR` | 17 / 1F | 1 | 4 | CY only | rotate through CY |
| `CMA` | 2F | 1 | 4 | none | |
| `CMC` / `STC` | 3F / 37 | 1 | 4 | CY only | |

### Branch

| Mnemonic | Encoding | Bytes | States | Flags | Notes |
| --- | --- | --- | --- | --- | --- |
| `JMP a16` | C3 | 3 | 10 | none | |
| `Jcc a16` | `11 CCC 010` | 3 | 10 | none | 10 whether or not taken (the 8085 spends 7/10) |
| `CALL a16` | CD | 3 | 17 | none | pushes the address of the next instruction |
| `Ccc a16` | `11 CCC 100` | 3 | 11/17 | none | |
| `RET` | C9 | 1 | 10 | none | |
| `Rcc` | `11 CCC 000` | 1 | 5/11 | none | |
| `RST n` | `11 NNN 111` | 1 | 11 | none | pushes PC, jumps to `8n` |
| `PCHL` | E9 | 1 | 5 | none | PC = HL |

### Stack, I/O, and machine control

| Mnemonic | Encoding | Bytes | States | Flags | Notes |
| --- | --- | --- | --- | --- | --- |
| `PUSH rp` | `11 RP0 101` | 1 | 11 | none | rp2 table: B, D, H, PSW |
| `POP rp` | `11 RP0 001` | 1 | 10 | `POP PSW` loads F | fixed bits stay fixed |
| `XTHL` | E3 | 1 | 18 | none | swaps HL with the word at SP |
| `SPHL` | F9 | 1 | 5 | none | SP = HL |
| `IN p8` | DB | 2 | 10 | none | A = port |
| `OUT p8` | D3 | 2 | 10 | none | port = A |
| `EI` / `DI` | FB / F3 | 1 | 4 | none | INTE set (delayed, below) / cleared |
| `HLT` | 76 | 1 | 7 | none | below |
| `NOP` | 00 | 1 | 4 | none | |

## Interrupts, HLT, and RESET

The 8080 has one interrupt input, INT, and no vectoring of its own. The model,
from `[UM ch. 2, "Interrupt Sequences"]` and `[ALP, RST]`:

1. INT is sampled at the end of each instruction. If INTE is set, the CPU
   accepts: it runs an instruction-fetch machine cycle with the INTA status
   instead of a memory read, and **PC is not incremented** for that fetch, so
   the return address that gets pushed is the address of the instruction that
   would have run next.
2. INTE is cleared on acceptance. The service routine must `EI` before
   returning.
3. The device (on the arcade boards, a few gates; in an Intel system the 8228
   controller or an 8214/8259) places an instruction byte on the data bus.
   The CPU executes it as if it had been fetched. `RST n` is the instruction of
   choice `[ALP, RST]`: 11 states, pushes PC, jumps to `8n`. A board may
   instead supply all three bytes of a `CALL` across successive INTA cycles
   (the 8228 supports this, `[UM ch. 5, 8228]`); that costs 17 states like a
   normal `CALL`. The core needs only the first form for the arcade boards, and
   should treat any other injected byte the way z80-python treats IM 0: run it,
   with a stated limit that only one-byte instructions are supported.
4. **EI delay.** "The interrupt system is enabled following the execution of
   the next instruction" `[UM ch. 4, EI]`. So `EI` then `RET` returns before
   any pending interrupt is accepted, and `EI; HLT` halts with interrupts
   enabled. `DI` takes effect immediately. No interrupt is accepted between
   `EI` and the following instruction.
5. **HLT.** 7 states; the CPU enters the halt state with PC pointing at the
   instruction after `HLT` `[ALP, HLT]`. The three exits are RESET, HOLD (bus
   sharing, out of scope), and INT while INTE is set: the interrupt is
   accepted exactly as above and the pushed return address is the byte after
   `HLT`. If INTE was clear when `HLT` ran, only RESET can restart the CPU
   `[UM ch. 2, "Halt Sequences"; ALP, HLT]`. A halted core's `step()` should
   return a fixed idle count (z80-python uses 4 for the Z80's re-fetch; the
   8080 sits in the TWH state, so any positive constant is a modeling choice
   and must be documented as one).
6. **RESET** clears PC, INTE, and the halt state `[UM ch. 2, "Start-up"]`. It
   does not define the other registers, and the core should leave them alone
   the way z80-python's RESET does.

The Space Invaders board supplies `RST 1` (0xCF) on one interrupt and `RST 2`
(0xD7) on the other, and holds INT asserted until the CPU acknowledges it, so
a request made while INTE is clear is delivered when the program next enables
interrupts. [timing.md](timing.md) has the numbers.

## DAA and the auxiliary carry

`[ALP ch. 3, DAA]` states the algorithm:

1. If the low nibble of A is greater than 9, **or AC is set**, add 6 to A.
2. If the high nibble of A (after step 1) is greater than 9, **or CY is set**,
   add 6 to the high nibble (0x60).

CY is set when step 2 produced a carry out of bit 7 and is otherwise left as
it was: the 8080's `DAA` never clears CY. AC is set when step 1 carried out of
bit 3, otherwise cleared. Z, S, and P come from the final A. The exerciser's
`<daa,cma,stc,cmc>` test runs `DAA` over all 256 values of A and all 256
values of F and its CRC was captured on real chips `[EXM]`, so a core's DAA is
right if and only if that test passes; the formulation above is the one that
does (MAME 0.285 `i8085.cpp` and superzazu/8080 both implement it and both
report the CRC). There is no N flag, so DAA has no "after subtraction" mode:
what the 8080 does after `SUB` is whatever the addition rules above give.

The remaining AC rules (INR/DCR, subtraction, `ANA`) are collected in
[undocumented-behavior.md](undocumented-behavior.md), because the manuals
state some only by example.

## Undocumented opcodes

Twelve byte values have no documented meaning. They execute as the instruction
whose encoding they collide with once the 8080's decoder ignores the bit that
would distinguish them:

| Bytes | Executes as | States | Reason |
| --- | --- | --- | --- |
| 08, 10, 18, 20, 28, 30, 38 | `NOP` | 4 | `00 yyy 000` with y != 0 is undefined; the decoder treats it as `NOP` |
| CB | `JMP a16` | 10 | `11 001 011` collides with `JMP` (`11 000 011`) |
| D9 | `RET` | 10 | `11 011 001` collides with `RET` (`11 001 001`) |
| DD, ED, FD | `CALL a16` | 17 | `11 x11 101` collides with `CALL` (`11 001 101`) |

This is the community rule and it is what MAME's `I8080` device and
superzazu/8080 implement, but **no hardware-captured oracle covers these
bytes**: the exercisers never emit them. [undocumented-behavior.md](undocumented-behavior.md)
marks the status precisely. On the 8085 every one of these bytes is a
different, real instruction (`DSUB`, `ARHL`, `RDEL`, `RIM`, `LDHI`, `SIM`,
`LDSI`, `RSTV`, `SHLX`, `JNK`, `LHLX`, `JK`), which is the main reason the
core is 8080A-only.

## 8080, 8080A, and second sources

The 1975 User's Manual already documents the **8080A** (and the faster
8080A-1 and 8080A-2 grades); the instruction set and state counts are the
8080A's. The original 1974 8080 was replaced within months; the differences
reported by people who used both are electrical (output drive into TTL) and
in the HOLD/HALT/interrupt timing corners, not in the instruction set
(comp.os.cpm and cctalk discussions, cited in [validation.md](validation.md)
as background only, not as an oracle). Second-source 8080As (NEC, National,
TI, AMD, Soviet KR580VM80A) all produced the same exerciser CRCs **except AMD's
9080A/8080A**, whose `ANA`/`ANI` clear AC like `ORA` does `[EXM]`. The core
models the Intel behavior.

## Suggested reading order

1. This page.
2. [timing.md](timing.md), then [undocumented-behavior.md](undocumented-behavior.md).
3. [validation.md](validation.md) for what can be proven and how.
4. [mame-oracle.md](mame-oracle.md) and [handoff-brief.md](handoff-brief.md).

## Sources

- `[UM]` Intel, *Intel 8080 Microcomputer Systems User's Manual*, September
  1975 (order 98-153B), 262 pages. Copyright Intel; scanned and hosted by
  bitsavers: <https://bitsavers.org/components/intel/MCS80/98-153B_Intel_8080_Microcomputer_Systems_Users_Manual_197509.pdf>.
  Chapter 2 (interrupt, hold, halt, and start-up sequences), chapter 4
  (instruction set, with the "Summary of Processor Instructions" on page
  4-15), chapter 5 (8228 System Controller). Page references were checked
  against the OCR text layer of that scan on 2026-09-11.
- `[ALP]` Intel, *8080/8085 Assembly Language Programming Manual*, May 1981
  (order 9800301D), 222 pages. Copyright Intel; bitsavers:
  <https://bitsavers.org/components/intel/MCS80/9800301D_8080_8085_Assembly_Language_Programming_Manual_May81.pdf>.
  Pages 1-11 to 1-14 (flags, PSW, ports) and chapter 3 (per-instruction
  descriptions: DAA, HLT, EI, RST, the logical instructions).
- `[EXM]` Ian Bartholomew's 8080/8085 CPU Exerciser results page and the
  `8080EXM.COM` CRC table, GPL-2.0-or-later; provenance, hashes, and the
  list of chips in [validation.md](validation.md).
- MAME 0.285, `src/devices/cpu/i8085/i8085.cpp` (BSD-3-Clause), used only to
  cross-check the state-count table and as the emulator-derived oracle.
