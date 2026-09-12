# Timing: state counts and what the arcade host needs

## Machine cycles and states

The 8080 executes an instruction as one to five **machine cycles**, each of
three to five **states** (T-states), one state per clock period
`[UM ch. 2, "Processor Cycle"]`. The building blocks:

| Machine cycle | States | Used for |
| --- | --- | --- |
| Instruction fetch (M1) | 4, or 5 when the instruction needs an extra decode/transfer state | Every instruction's first cycle: T1-T3 read the opcode, T4 decodes, T5 exists only for instructions such as `MOV r1,r2`, `INX`, `DCX`, `PCHL`, `SPHL`, `PUSH`, `CALL`, `RST`, conditional `RET` |
| Memory read | 3 | Operand bytes, `LDA`, `MOV r,M`, `POP`, `RET` |
| Memory write | 3 | `STA`, `MOV M,r`, `PUSH`, `CALL` |
| Stack read / write | 3 | Same as memory, with the stack status word |
| Input / output | 3 | `IN`, `OUT` |
| Interrupt acknowledge | 4 (5 for `RST`) | The injected instruction's M1 |

So every documented total on [start-here.md](start-here.md) is a sum of these.
Worked examples, each matching the summary table on `[UM p. 4-15]`:

| Instruction | Decomposition | Total |
| --- | --- | --- |
| `NOP`, `ADD r`, `RLC`, `EI` | M1 4 | 4 |
| `MOV r1,r2`, `INX`, `PCHL`, `SPHL`, `INR r` | M1 5 | 5 |
| `MOV r,M`, `ADD M`, `ADI` | M1 4 + read 3 | 7 |
| `MOV M,r`, `STAX` | M1 4 + write 3 | 7 |
| `HLT` | M1 4 + halt-entry cycle 3 | 7 |
| `INR M`, `MVI M`, `JMP`, `Jcc`, `RET`, `POP`, `IN`, `OUT`, `LXI`, `DAD` | M1 4 + 3 + 3 | 10 |
| `PUSH`, `RST`, `Ccc` not taken, `Rcc` taken | M1 5 + 3 + 3 | 11 |
| `Rcc` not taken | M1 5 | 5 |
| `LDA`, `STA` | 4 + 3 + 3 + 3 | 13 |
| `LHLD`, `SHLD` | 4 + 3 + 3 + 3 + 3 | 16 |
| `CALL`, `Ccc` taken | M1 5 + 3 + 3 + 3 + 3 | 17 |
| `XTHL` | 4 + 3 + 3 + 3 + 5 | 18 |

The totals are the ones the core must return and the ones every oracle
checks; they were read from the summary page. The decomposition column is one
consistent reading of the machine-cycle rules in `[UM ch. 2]` and the
per-instruction "Cycles/States" lines in `[ALP ch. 3]`; it was not re-derived
cycle by cycle from the manual's state-transition table here, so treat it as
an aid to memory, not as a claim the core must reproduce. A core returns totals, not per-state bus positions,
exactly as z80-python does; per-state bus placement is out of scope.

Two consequences worth knowing before writing handlers:

- **Conditional jumps cost 10 either way** on the 8080. The 8085 aborts an
  untaken `Jcc` after 7; any table that shows `7/10` is an 8085 table.
- **`Ccc` not taken is 11, not 10**, because the M1 already spent its T5 on
  the stack-pointer decrement before the condition was evaluated; likewise
  `Rcc` not taken is 5, not 4.

### Cross-check against MAME 0.285

MAME's `src/devices/cpu/i8085/i8085.cpp` carries two 256-entry tables,
`lut_cycles_8080` and `lut_cycles_8085`, plus `+6` for a taken conditional
`RET`/`CALL`. Every entry of the 8080 table was compared against the summary
page above on 2026-09-11 and none differs; the 12 undocumented aliases carry
the counts of the instructions they alias (4 for the NOPs, 10 for `JMP`/`RET`,
11 + 6 for `CALL`). superzazu/8080's table is the same except that it charges
`CALL` and the three `CALL` aliases 17 outright. These are emulator tables and
confirm only that the community agrees with the datasheet.

### Interrupt acceptance

Accepting an interrupt costs exactly what the injected instruction costs: 11
states for `RST n` (the interrupt-acknowledge M1 is 5 states like a normal
`RST` M1, then two stack writes). No extra states are charged and PC is not
incremented for the acknowledge fetch `[UM ch. 2, "Interrupt Sequences"]`.
MAME agrees: `check_for_interrupts()` runs `execute_one(vector)` and charges
its table entry; the trace in [mame-oracle.md](mame-oracle.md) shows a
`totalcycles` delta of 11 across each acceptance.

## What the Space Invaders host needs

The numbers below are restated from MAME 0.285's
`src/mame/midw8080/mw8080bw.h` and `mw8080bw.cpp` (BSD-3-Clause), which
document the Midway board's sync chain from the schematics; they are not
copied and no MAME code is reproduced. The Taito board (`8080bw.cpp`) uses
the same 19.968 MHz crystal and the same interrupt scheme for `invaders`'
parent-set relatives.

| Quantity | Value | Derivation |
| --- | --- | --- |
| Master clock | 19.968 MHz | crystal |
| CPU clock | 1.9968 MHz | master / 10 |
| Pixel clock | 4.992 MHz | master / 4 |
| Line | 320 pixel clocks | HTOTAL 0x140; 256 visible |
| Frame | 262 lines | VTOTAL 0x106; 224 visible, VBLANK from line 224 |
| Frame rate | 59.541 Hz | 4,992,000 / 320 / 262 |
| CPU states per line | 128 | 320 / (4.992 / 1.9968) = 320 / 2.5 |
| CPU states per frame | 33,536 | 128 x 262 |

Two interrupts per frame, from a flip-flop clocked by the vertical counter:

| Event | Vertical counter | Displayed line | State offset within the frame | Instruction placed on the bus |
| --- | --- | --- | --- | --- |
| Mid-screen | 0x80, VBLANK low | 96 | 12,288 | 0xCF = `RST 1`, handler at 0x0008 |
| Start of VBLANK | 0xDA, VBLANK high | 224 | 28,672 | 0xD7 = `RST 2`, handler at 0x0010 |

The vector is built from the counter's 64V bit (`0xC7 | 64V << 4 | !64V << 3`),
and the INT line stays asserted until the CPU acknowledges it, at which point
the vector is formed from the counter **at acknowledge time**. Two facts follow
for a host:

- If the program has interrupts disabled when the flip-flop sets, the request
  waits; it is accepted after the next `EI` (plus one instruction). The MAME
  trace shows the game's very first interrupt being accepted on line 63 of
  frame 9 with vector `RST 2`, because a request from line 224 of an earlier
  frame was still pending when the boot code executed `EI`, and 64V was set at
  line 63 (counter 0x5F).
- After that, acceptances alternate at lines 96 and 224 as long as the
  handlers re-enable interrupts before the next trigger, which the game's do.

A host therefore needs: a state counter it advances by each `step()`'s return
value, a comparison against 12,288 and 28,672 within the 33,536-state frame,
`request_interrupt(0xCF)` / `request_interrupt(0xD7)` at those points, and
the level semantics above (a pending request is not lost if INTE is clear).
The MAME run in [mame-oracle.md](mame-oracle.md) confirmed, over 60 frames,
handler entry at PC 0x0008 on beam line 96 and PC 0x0010 on beam line 224,
with consecutive same-vector acceptances 33,536 or 33,537 `totalcycles` apart
(the odd state is instruction-boundary rounding).

### The rest of the board, for the harness only

Restated from `mw8080bw.cpp` (`main_map`, `invaders_state::io_map`); the core
does not model any of it, but the MAME lockstep host in
[handoff-brief.md](handoff-brief.md) must:

- Memory: 8 KiB ROM at 0x0000-0x1FFF (`invaders.h`, `.g`, `.f`, `.e`, 2 KiB
  each, in that order), 8 KiB RAM at 0x2000-0x3FFF (0x2000-0x23FF work RAM,
  0x2400-0x3FFF the 256x224 one-bit frame buffer), address bus masked to 15
  bits so 0x4000-0x7FFF mirrors 0x0000-0x3FFF. Writes to ROM are ignored.
- Ports: `IN 0`, `IN 1`, `IN 2` are switches and controls; `IN 3` reads the
  MB14241 shift register; `OUT 2` sets the shift count, `OUT 4` loads shift
  data, `OUT 3` and `OUT 5` drive sound latches, `OUT 6` kicks a watchdog that
  MAME sets to 255 frames. Port numbers are masked to 3 bits.
- A pristine machine with all inputs idle is deterministic, which is what
  makes lockstep against MAME possible without input replay.

## Sources

- `[UM]` Intel 8080 Microcomputer Systems User's Manual, September 1975,
  chapter 2 (processor cycle, interrupt, halt) and page 4-15 (summary table).
  URL and license in [start-here.md](start-here.md).
- `[ALP]` Intel 8080/8085 Assembly Language Programming Manual, May 1981,
  chapter 3 (per-instruction cycles and states).
- MAME 0.285, `src/mame/midw8080/mw8080bw.h`, `mw8080bw.cpp`, `8080bw.cpp`,
  `src/devices/cpu/i8085/i8085.cpp`; BSD-3-Clause;
  <https://github.com/mamedev/mame/tree/mame0285>. Numbers restated, code
  not copied.
