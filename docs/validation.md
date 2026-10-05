# Validation: evidence, certification record, and the oracles

## Claim

`i8080-python` is an **8080EXM-certified pure-Python Intel 8080A instruction
core**. Its instruction results, including all eight bits of the flag byte,
are **verified against real 8080A hardware** wherever the hardware-captured
8080EXM CRCs reach. Its state counts, branches, stack, I/O, and interrupt
lifecycle are checked against Intel's manuals and **cross-checked against an
emulator**: MAME 0.285 in lockstep over 60 frames of Space Invaders, and
superzazu/8080's state totals for every exerciser. The claim does not cover
per-state bus timing (the core returns totals), the 8228's multi-byte
interrupt injection (refused), HOLD, or any machine beyond the CPU.

## Certification record: commit `fd47550` (2026-09-21)

Reproduced on Linux x86_64 under CPython 3.14.4 and PyPy 7.3.20 (Python
3.11.13), with the exercisers at the SHA-256 values in
[Pinned artifacts](#pinned-artifacts), MAME 0.285 (`$MAME`, here
`/usr/games/mame`), and the non-merged `invaders.zip` read in place from
`$MAME_ROMPATH`. Every figure below was produced
at `fd47550` from a clean tree. That commit is the 0.2.0 development line:
the bus became four callables the host passes in, and the debugger, console
and CLI were added. The instruction semantics did not change, and re-running
every rung is what says so.

| Rung | Gate | Tier | Result | CPython 3.14.4 | PyPy 7.3.20 |
| --- | --- | --- | --- | ---: | ---: |
| 1, 2, 4 | `pytest -q`: 256-opcode state grid, flag-effect classes, ALU sweep against an independent formulation, worked examples, disassembler, trace, debugger, console, CLI, readability contract, 8080PRE, TST8080, 18 lifecycle tests, MAME lockstep | specification; self-checks; emulator-derived | 1,354 passed | 3.3 s | 4.3 s |
| 2 | `8080PRE.COM` | specification-derived | `8080 Preliminary tests complete`; 1,058 instructions, 7,787 states | < 0.1 s | < 0.1 s |
| 2 | `TST8080.COM` | specification-derived | `CPU IS OPERATIONAL`; 646 instructions, 4,874 states | < 0.1 s | < 0.1 s |
| 3 | `8080EXM.COM` | **hardware-captured** | **25 of 25 CRCs match the hardware table**, `Tests complete`; 2,919,050,143 instructions, 23,803,375,621 states | 2,588.7 s | 159.2 s |
| 3 | `CPUTEST.COM` (opt-in) | specification-derived | `CPU TESTS OK`; 33,970,946 instructions, 255,649,733 states | 22.9 s | 2.0 s |
| 5 | MAME 0.285 `invaders` lockstep, 60 frames | emulator-derived | 230,313 lines and 102 interrupt acceptances identical: `pc a b c d e h l sp`, F masked to its five flags, cumulative states = `totalcycles` | 3.1 s | 1.4 s |

**Interpreter for rung 3.** Both interpreters run 8080EXM; PyPy is roughly
an order of magnitude faster, so it is the one to use. The previous record,
at `6c08ccd`, had the same instruction and state totals with CPython at
1,890.1 s and PyPy at 160.1 s. Read the CPython figures as wall-clock on a
shared machine, not as a benchmark: this run overlapped other users' work at
load average ~32, against ~13 for the previous one. PyPy, 159.2 s against
160.1 s for the same 2.9 billion instructions, is the like-for-like
comparison, and it shows the 0.2.0 bus change costing nothing measurable.

**State totals against superzazu/8080.** This host traps BDOS and warm boot
outside the CPU for free. superzazu's harness (`i8080_tests.c` at `274ffd7`)
runs a real `OUT 1,A; RET` at 0x0005 (20 states per BDOS call) and `OUT 0,A`
at 0x0000 (10 states, once). Converted to that accounting, every total above
equals superzazu's published number exactly: 7,817, 4,924, 23,803,381,171,
and 255,653,383. The conversion is computed in `validation/cpm.py`
(`CPMResult.superzazu_states`) and asserted by `tests/test_exercisers.py`.
superzazu is emulator-derived, so this is a detector agreeing, not a judge.

**The CRCs are checked by the harness, not taken from the program.**
`validation.cpm.failures()` parses each printed `crc is:` value and compares
it with the 25-entry hardware table below, so a core that corrupted the
program's own compiled-in table could not pass.

**What the MAME run exercised.** The 60 frames execute 56 distinct opcodes,
including `EI` 103 times, `IN` 102 times, and `OUT` 51 times. They execute
no `HLT`, `DI`, `DAA`, `XTHL`, or undocumented byte. So the lockstep
cross-checks interrupt acceptance timing, the EI delay, and the vector and
return-address mechanics on real code. HLT wakeup and RESET rest on the
manual-cited unit tests alone (rung 4).

**A longer run, beyond the rung.** `python scripts/mame_trace.py --seconds
30 --out DIR` into the attract mode's demo game, then the same lockstep,
matched **6,944,603 lines and 3,556 interrupt acceptances** with no
divergence (26.5 s under PyPy at `6c08ccd`; the 328 MB log is not kept).
That run executes 118 distinct opcodes, 54 of Intel's 78 mnemonics. It
never executes `ACI ADC CC CM CMC CP CPE CPO DAA DI HLT JP JPE JPO RAL RM RP
RPE RPO SBB SPHL STAX XRI`, or `RST` from memory; `RST` runs only as the
injected interrupt byte. Those rest on rungs 1 to 4 and, for their register
and flag results, on 8080EXM.

**One divergence on the way, in the harness.** The first lockstep attempt
matched 55,478 lines and then diverged at `error.log` line 55,480: MAME took
an interrupt at state 435,967, one state before the whole-number trigger at
13 x 33,536. The cause was MAME's clock arithmetic, not the CPU. MAME
truncates `1e18 / clock` to whole attoseconds, which makes a 128-state line
128 as longer than a scanline. Its scheduler then hands the CPU
`floor(delta / attoseconds_per_cycle)` cycles per timeslice, so every
trigger is seen one state early. The host now keeps board time in
attoseconds as MAME does (`validation/mame_lockstep.py`), and no core change
was needed.

## The tier rule

Rank oracles by where their expected values came from:

1. **hardware-captured**: the expected values were read off a real 8080A;
2. **hardware-corrected**: generated by software, then corrected wherever a
   hardware run disagreed;
3. **emulator-derived**: produced by another emulator, or by a program whose
   pass criterion is its own author's reading of the specification.

A low-tier oracle is a **detector**, never a judge: a disagreement with it
means "look here", and the question is settled by a higher tier or by the
datasheet. Every oracle below states its tier.

## Summary table

| Oracle | Tier | Covers | Cannot cover | License | Pinned |
| --- | --- | --- | --- | --- | --- |
| SingleStepTests | none exists for the 8080 | | | | checked 2026-09-11 |
| `8080EXM.COM` (Bartholomew/Cringle exerciser with hardware CRCs, Douglas 2013) | **hardware-captured** | flags and registers of every documented ALU, INR/DCR, INX/DCX, DAD, load, store, MVI, MOV, rotate, DAA instruction, across huge input spaces, as one 32-bit CRC per group | branch/call/return/stack/I/O instructions (used but not CRC'd), state counts, interrupts, undocumented opcodes, which case failed | GPL-2.0-or-later | SHA-256 below; superzazu/8080@`274ffd7`; altairclone.com 2013-05-20 |
| `8080EXER.COM` (same, without compiled-in CRCs) | hardware-captured, via the published results table | same | same; prints every group as ERROR with the found CRC | GPL-2.0-or-later | same |
| `8080PRE.COM` | specification-derived self-check (treat as emulator-derived) | jumps, calls, `MVI`, basic ALU: the instructions the exerciser itself needs | everything else | GPL-2.0-or-later | same |
| `TST8080.COM` (Microcosm Associates 1980, Douglas 2012 update) | specification-derived self-check | every documented instruction with one or a few values each; the classic "cpudiag" | flag corner cases exhaustively, timing, interrupts | copyright 1980, donated to SIG/M; no formal license | same |
| `CPUTEST.COM` (SuperSoft Diagnostics II, 1981) | specification-derived self-check | documented instructions, register/flag results across a table of sequences | timing, interrupts | copyright 1981, no license; opt-in fetch | same |
| MAME 0.285 `i8085.cpp` running `invaders` | emulator-derived | whole-board instruction stream with registers per instruction, state counts (`totalcycles`), interrupt acceptance timing, the game's real code paths | anything the game does not execute; correctness of MAME itself | BSD-3-Clause (MAME); ROMs used in place, never copied | MAME 0.285 at `/usr/games/mame` |
| superzazu/8080 exerciser cycle totals | emulator-derived | total state counts of the four CP/M programs, as a whole-run timing checksum | which instruction is wrong | MIT | `274ffd7` |
| Intel manuals `[UM]` 1975, `[ALP]` 1981 | the specification | state counts, encodings, lifecycle rules | undocumented opcodes; AC details stated only by example | copyright Intel; scans hosted by bitsavers | URLs in [start-here.md](start-here.md) |

## SingleStepTests: no 8080 corpus

The SingleStepTests organization (<https://github.com/SingleStepTests>) held
22 repositories on 2026-09-11: 65x02, 65816, 680x0, m68000, 8086, 8088, 80186,
80286, 80386, ARM7TDMI, huc6280, r3000, sh4, sm83, spc700, tlcs900h, v20, z80,
and their ares/JSMoo variants and the older `ProcessorTests` umbrella. **None
is for the 8080 or 8085.** The NEC V20 repository's README mentions a planned
`v1_emulation` set for the V20's 8080-emulation mode, which would be a
hardware-generated corpus of 8080-instruction-set behavior on a different
chip, not on an 8080A, so even when it appears it would be a detector for this
core, not a judge. There is therefore no per-instruction hardware-generated
JSON corpus for the 8080, and the per-opcode unit tests in the handoff brief
have to be written from the datasheet.

## `8080EXM.COM`: the hardware-captured oracle

### Provenance

- Frank Cringle wrote `zexlax`/`zexall`, the Z80 instruction exerciser
  (GPL-2.0-or-later, 1994).
- Ian Bartholomew ported it to the 8080 in February 2009 (`8080EXER.MAC`:
  8080 mnemonics, IX/IY replaced by two extra HL copies, flag mask changed to
  0xFF because the 8080 defines all eight flag bits) together with a port of
  Cringle's preliminary test (`8080PRE.MAC`), and published them at
  `http://www.idb.me.uk/sunhillow/8080.html` with a request for results from
  real CP/M 2.2 systems. That page is gone (the domain is parked); the Wayback
  Machine holds it, and Mike Douglas printed it to PDF on 2019-04-09:
  <https://web.archive.org/web/20151108135453/http://www.idb.me.uk:80/sunhillow/8080.html>,
  <https://altairclone.com/downloads/cpu_tests/8080_8085%20CPU%20Exerciser.pdf>.
- The results table on that page lists, for the 8080, thirteen submissions
  across these chips: KR580VM80A (Soviet clone), Intel P8080A, National
  INS8080A, TI TMS8080AJL, AMD 9080A (3 chips), AMD 8080A, National 8080AN
  (2), Intel 8080A (4), KR580 (4), NEC 8080A (2), Samsung 8080, Tesla 8080A
  (Czechoslovak clone), TI 8080A. All agree on every CRC **except the two AMD
  entries**, which differ on `aluop nn` and `aluop <b,c,d,e,h,l,m,a>`; the
  submitter traced it to AMD's `ANA`/`ANI` clearing AC like `ORA`. The
  non-AMD column is the 8080A behavior this core targets.
- Mike Douglas (altairclone.com) compiled those CRCs into the program in May
  2013 as `8080EXM.MAC`/`.COM`, which prints `PASS! crc is:XXXXXXXX` per
  group instead of `ERROR`, and published the set with `TST8080` and
  `CPUTEST` at <https://altairclone.com/downloads/cpu_tests/> (directory
  dated 2013-05-20). His `8080EXER.PNG` in that directory is a screenshot of
  `8080EXER` on a real 8080 under 64K CP/M 2.2, dated 20/09/2009, showing the
  same 25 CRCs.
- superzazu/8080 (<https://github.com/superzazu/8080>, MIT, Nicolas
  Allemand) mirrors that directory byte-for-byte under `cpu_tests/`; commit
  `274ffd700b81baabea99b0963bc1260b67132185` (2020-10-14) is the pinned
  revision. The hashes below were computed from both sources on 2026-09-11
  and are identical.

### The 25 expected CRCs

In program order, as `db` bytes in `8080EXM.MAC` and as printed:

| Group | CRC | Group | CRC |
| --- | --- | --- | --- |
| `dad <b,d,h,sp>` | 14474BA6 | `<inx,dcx> sp` | D5702FAB |
| `aluop nn` | 9E922F9E | `lhld nnnn` | A9C3D5CB |
| `aluop <b,c,d,e,h,l,m,a>` | CF762C86 | `shld nnnn` | E8864F26 |
| `<daa,cma,stc,cmc>` | BB3F030C | `lxi <b,d,h,sp>,nnnn` | FCF46E12 |
| `<inr,dcr> a` | ADB6460E | `ldax <b,d>` | 2B821D5F |
| `<inr,dcr> b` | 83ED1345 | `mvi <b,c,d,e,h,l,m,a>,nn` | EAA72044 |
| `<inx,dcx> b` | F79287CD | `mov <bcdehla>,<bcdehla>` | 10B58CEE |
| `<inr,dcr> c` | E5F6721B | `sta nnnn / lda nnnn` | ED57AF72 |
| `<inr,dcr> d` | 15B5579A | `<rlc,rrc,ral,rar>` | E0D89235 |
| `<inx,dcx> d` | 7F4E2501 | `stax <b,d>` | 2B0471E9 |
| `<inr,dcr> e` | CF2AB396 | | |
| `<inr,dcr> h` | 12B2952C | | |
| `<inx,dcx> h` | 9F2B23C0 | | |
| `<inr,dcr> l` | FF57D356 | | |
| `<inr,dcr> m` | 92E963BD | | |

AMD 9080A/8080A: `aluop nn` 7799EA9D, `aluop <...>` B3491C2A; not targeted.

### What it proves and what it cannot

Each group runs its instructions over a generated sweep of operand and flag
values (the `aluop <...>` group alone is 753,664 iterations) and folds every
resulting machine state, flags included with mask 0xFF, into one CRC. A
matching CRC means the core produced the same registers and flags as real
chips on every iteration; a mismatch says only which group. It does not
check state counts, branches, stack instructions beyond their use by the
framework, `IN`/`OUT`, `EI`/`DI`/`HLT`, interrupts, or the twelve undocumented
opcodes. Expect the full run to take about 3 h 20 min at 2 MHz
(Bartholomew), 23,803,381,171 states by superzazu's count; a Python core
will need PyPy or patience.

## The other CP/M programs

- **`8080PRE.COM`** prints `8080 Preliminary tests complete` on success and
  jumps to 0 (warm boot) or prints an address on failure. 7,817 states
  (superzazu). Run it first; it is the cheapest gate.
- **`TST8080.COM`** prints the Microcosm banner then `CPU IS OPERATIONAL`,
  or `CPU HAS FAILED! ERROR EXIT=xxxx` with the address of the failing check
  (look it up in `TST8080.ASM`). 4,924 states. Its 2012 update by Douglas
  added the missing `MOV C,M`, `MOV M,C`, `ANA B` tests and fixed the exit
  message.
- **`CPUTEST.COM`** prints `DIAGNOSTICS II V1.2 - CPU TEST`, the letters
  `ABCDEFGHIJKLMNOPQRSTUVWXYZ` as each test group passes, `CPU IS 8080/8085`,
  `BEGIN TIMING TEST` / `END TIMING TEST`, and `CPU TESTS OK`. On failure it
  prints the instruction sequence, the register, and the expected and actual
  values. 255,653,383 states (superzazu). Copyright SuperSoft Associates
  1981 with no license grant; the fetch script skips it unless asked, and it
  must never be committed.

All three are self-checking: their expected values are what their authors
believed the 8080 does. They found real bugs in many emulators, which is the
proper use of a detector.

## Pinned artifacts

`python scripts/fetch_exercisers.py` (add `--include-cputest` for the
proprietary program) installs these into the gitignored `tests/exercisers/`,
trying the immutable GitHub URL first and altairclone.com second, and refuses
any byte stream whose SHA-256 differs. Run on 2026-09-12: all nine fetched from
`raw.githubusercontent.com/superzazu/8080/274ffd700b81baabea99b0963bc1260b67132185/cpu_tests/`
and verified.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `8080PRE.COM` | 1,024 | `18eb3c79cba42c0718f160be6a1853cb64cdce7aa47d65780189a57bdd98c4e0` |
| `8080PRE.MAC` | 4,818 | `ca1507444929978038ad4f83d18e13bcce72072df2b850932b3982c31cfc1ccc` |
| `8080EXER.COM` | 4,608 | `8e1736b667c088ac63b69f20768a9a237f3cd739b4cb0ebea99b9e39d3ab1da4` |
| `8080EXER.MAC` | 29,079 | `ddf30299b87e7e244251f96f495d6e2946545a296af25675a8cdebc6478dbf9c` |
| `8080EXM.COM` | 4,608 | `6e3286e11bb1a8f47b8ee1280b4a067be813193363e3223c99b0d21912f44aeb` |
| `8080EXM.MAC` | 29,411 | `806d3a069b0021e9925c0b7c26fd74a3c397ca7f618a599ab4a8396ebcd1f3f3` |
| `TST8080.COM` | 1,536 | `9561c6fb6c99efe3de00eb77e4044fd102151058b39ac2d7bce10483838a08e7` |
| `TST8080.ASM` | 14,657 | `d9f405470a0ec9bb9368bcbef015b0bbb326c3d673ce7ddfc48ba2d978e44940` |
| `CPUTEST.COM` (opt-in) | 19,200 | `e61a9a75348c774486c2207080ea4effbf6c2367fdace31b0731081a4144030b` |

## MAME 0.285 as the emulator-derived oracle

[mame-oracle.md](mame-oracle.md) records a working headless command line, the
Lua trace script, and the output formats. It yields one line per executed
instruction with PC, all registers, SP, the running state count, the beam
line, and the frame number, for the real Space Invaders program. It is the
only oracle here that exercises interrupts, `IN`/`OUT`, `RST`, and the state
counter over a long real program, and it is the lowest tier: MAME's 8080 is
another emulator (its `F` omits the fixed bit 1 internally, for one). A
divergence from MAME is a lead to chase against the datasheet and the CRCs,
not a bug by definition.

## Harness

Built as planned before the core existed, in z80-python's shape:

- **`cpm-minimal` host** (`validation/cpm.py`): 64 KiB RAM; the `.COM` at
  0x0100, PC = 0x0100, SP = 0xF000, and the word at 0x0006 = 0xF000 (the
  exercisers run `LHLD 6; SPHL` before their first BDOS call). Two traps are
  checked before every step, outside the CPU: PC == 0x0000 ends the run, and
  PC == 0x0005 performs BDOS function C (0 ends the run, 2 prints E, 9 prints
  from DE up to `$`) and then pops the return address. Any `IN` or `OUT` is
  an error.
- **Pass criteria**: `8080PRE`: `8080 Preliminary tests complete`;
  `TST8080`: `CPU IS OPERATIONAL` and no `CPU HAS FAILED`; `8080EXM`: the 25
  printed CRCs equal the hardware table in order, `Tests complete`, no
  `ERROR`; `CPUTEST`: `CPU TESTS OK`.
- **Budgets**: 10^5 instructions for PRE and TST8080, 10^9 for CPUTEST,
  10^11 for EXM. An overrun reports the last PC and the output so far.
- **Trace**: `python -m validation.cpm PROGRAM --trace FILE` writes the
  JSON Lines conformance trace in [trace-schema.md](trace-schema.md), with
  the traps running between records.
- **MAME lockstep** (`validation/mame_lockstep.py`,
  `scripts/mame_trace.py`): the `invaders` host restates MAME 0.285's Midway
  board. The ROM is read from the zip in place. The board's interrupt
  generator triggers at lines 96 and 224 and asserts INT only if its copy of
  the INTE pin is high; that copy starts high and follows INTE edges. The
  vector comes from 64V at acknowledge time, and board time is kept in
  MAME's attoseconds. Two MAME runs produced the same `error.log` (SHA-256
  `5096a63f49030e87f9db94fcf1095c5a38af37d26e9d30cb9abf2d2b2084e330`).
  [mame-oracle.md](mame-oracle.md) has the recipe.

## Sources and licenses

- Ian Bartholomew, "8080/8085 CPU Exerciser", archived page and Douglas's
  2019 PDF (URLs above). Programs GPL-2.0-or-later (from Cringle's zexall).
- Mike Douglas, altairclone.com `downloads/cpu_tests/` and its
  `+README.TXT` (May 2013).
- superzazu/8080, MIT, Copyright (c) 2018 Nicolas Allemand; `i8080_tests.c`
  for the cycle totals; commit `274ffd700b81baabea99b0963bc1260b67132185`.
- Microcosm Associates, `TST8080.ASM` header (1980, donated to SIG/M).
- SuperSoft Associates, `CPUTEST.COM` embedded copyright string (1981).
- MAME 0.285, BSD-3-Clause: <https://github.com/mamedev/mame/tree/mame0285>.
- SingleStepTests organization listing, 2026-09-11.
- Intel manuals: URLs and order numbers in [start-here.md](start-here.md).
- Background on 8080 vs 8080A (not an oracle): comp.os.cpm thread "A Trivia
  Item re: Intel 8080 vs. 8080A" and the cctalk September 2001 "8080 vs.
  8080A" thread.
