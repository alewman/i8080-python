# Undocumented and under-documented behavior

The 8080 has far less of this than the Z80: no X/Y flags that copy an internal
bus, no MEMPTR leak, no refresh counter. What remains is (a) three fixed bits
in F, (b) a handful of auxiliary-carry rules the manuals state only by
example, (c) twelve opcode aliases, and (d) a few lifecycle corners. Each rule
below carries its evidence and the tier of that evidence:

- **hardware-captured**: the `8080EXM.COM` CRCs, which were produced by real
  8080A chips and cover the rule's whole input space (see
  [validation.md](validation.md) for the chips and provenance);
- **documented**: stated in Intel's manuals `[UM]`/`[ALP]` (URLs in
  [start-here.md](start-here.md));
- **emulator consensus**: MAME 0.285 `i8085.cpp` and superzazu/8080 agree and
  the latter reports the hardware CRCs passing;
- `[unverified]`: inferred; no hardware oracle covers it.

A rule marked hardware-captured is "verified" only in the sense that the CRC
test that includes it passes on real chips and fails on any core that gets it
wrong; the CRC does not say which formulation is right, only that the
formulation below is one that produces the hardware value.

## Status in this core (certified at `6c08ccd`)

The core implements every rule on this page as written. At `6c08ccd`, all 25
8080EXM groups print the hardware CRCs ([validation.md](validation.md)). So
every **hardware-captured** row below, including the fixed flag bits, all AC
rules, and the DAA formulation, now holds for this code, not only for the
emulators the page first cited. Nothing that was `[unverified]` has gained a
hardware oracle. The undocumented opcodes, RESET's effect on the other
registers, and multi-byte INTA injection stay marked. The core's choices for
them are stated in the rows, and unit tests pin them so that any change is
deliberate. The two lifecycle modeling choices the manuals leave open, the EI
delay's handling of consecutive EIs and the halt idle count, follow MAME
0.285 and are named in `src/i8080_python/_machine.py` and `cpu.py`.

## The flag byte

**Bits 5 and 3 read 0, bit 1 reads 1, always.** Documented (`[ALP 1-14]`:
`PUSH PSW` adds filler bits, `POP PSW` strips them) and hardware-captured:
every exerciser test snapshots the machine state through `PUSH PSW` after
loading it through `POP PSW` with all 256 flag-byte values, with an all-ones
flag mask, and the CRCs match on every non-AMD chip. So `POP PSW` with 0xFF
in memory leaves F = 0xD7, and `POP PSW` with 0x00 leaves F = 0x02.

**MAME's `F` is not the PSW byte.** MAME's 8080 core keeps bit 1 clear
internally and forces it only inside `PUSH PSW`, so the `f` value in a MAME
trace can be even. When diffing against MAME compare `(f | 0x02) & 0xD7`, or
mask to the five real flags. This is a modeling choice on MAME's side, not a
hardware fact.

## Auxiliary carry (AC) rules

| Instruction family | AC result | Evidence |
| --- | --- | --- |
| `ADD`, `ADC`, `ADI`, `ACI` | carry out of bit 3 of the 8-bit addition (including the carry-in for `ADC`) | documented (`[ALP 1-11]`); hardware-captured (`aluop` tests) |
| `SUB`, `SBB`, `SUI`, `SBI`, `CMP`, `CPI` | **set when there is no borrow from bit 4**, i.e. `AC = NOT ((A ^ operand ^ result) & 0x10)`; equivalently the carry out of bit 3 of the two's-complement addition the ALU performs | documented by example (`[ALP ch. 3, SUB]`: "the auxiliary carry flag is set because ... causes a carry out of bit 3" while CY, shown as the borrow, is clear); hardware-captured (`aluop` tests); emulator consensus |
| `INR` | set when the low nibble of the result is 0 (carry out of bit 3) | hardware-captured (`<inr,dcr>` tests over all 256 values); emulator consensus |
| `DCR` | set when the low nibble of the result is **not** 0xF (no borrow from bit 4) | same |
| `ANA`, `ANI` | **OR of bit 3 of A and bit 3 of the operand** (before the AND) | documented (`[ALP 1-12]`, the sentence that also states the 8085 always sets it); hardware-captured: Intel, NS, TI, NEC, Samsung, Tesla, and KR580 chips produce the `aluop` CRCs 9E922F9E / CF762C86, while AMD 9080A/8080A produce 7799EA9D / B3491C2A because they clear AC "as Intel originally intended" |
| `ORA`, `ORI`, `XRA`, `XRI` | cleared, with CY | documented (`[ALP ch. 3]`); hardware-captured |
| `DAA` | set when the low-nibble correction (+6) carried out of bit 3, otherwise cleared | hardware-captured (`<daa,cma,stc,cmc>`, all 65,536 A/F combinations); emulator consensus on the formulation |
| `INX`, `DCX`, `DAD` | unchanged | documented (`DAD` affects only CY) |
| rotates, `CMA`, `STC`, `CMC` | unchanged | documented |

Note the asymmetry the Z80 later removed: on the 8080 the subtract family's
AC is the inverse of what a Z80 programmer expects (Z80 H = borrow from bit
4; 8080 AC = no borrow from bit 4), and `DCR` follows the same polarity.

## Carry and DAA

- **`DAA` never clears CY.** If CY was set before `DAA`, the +0x60 correction
  is applied and CY stays set; if CY was clear, CY becomes set only when the
  high-nibble test (`A > 0x99` after the low correction, equivalently high
  nibble > 9) fires. Hardware-captured by the same test as above; emulator
  consensus (MAME: `F = (F & keep) | (A > 0x99)`).
- The low correction is applied when the low nibble > 9 **or AC is set**; the
  high correction when the high nibble > 9 **or CY is set**; both tests use
  A as it was before the low correction for the CY decision (`A > 0x99`) and
  A after the low correction for the nibble comparison in MAME's and
  superzazu's implementations, which agree with each other and with the CRC.
  `[unverified]` whether an alternative formulation that differs only on
  inputs the exerciser cannot produce exists; none is known.
- `SUB A` / `CMP A` clear CY and set AC (no borrow), Z = 1, P = 1: a
  consequence of the rules above, checked by the `aluop` CRCs.

## Undocumented opcodes

| Bytes | Behavior | Evidence |
| --- | --- | --- |
| 08, 10, 18, 20, 28, 30, 38 | `NOP`, 4 states | emulator consensus; decoder inference (`00 yyy 000`, y != 0, has no row in the decode table, and nothing is enabled) `[unverified on hardware]` |
| CB | `JMP a16`, 10 states | emulator consensus; decoder inference (bit 3 ignored in the `JMP` row) `[unverified on hardware]` |
| D9 | `RET`, 10 states | same `[unverified on hardware]` |
| DD, ED, FD | `CALL a16`, 17 states | same `[unverified on hardware]` |

No exerciser emits these bytes (Cringle's design and Bartholomew's port only
test documented instructions; CPUTEST and TST8080 are documented-instruction
diagnostics). MAME's `I8080`/`I8080A` devices implement exactly this table,
and its `I8085A` device implements the 8085's real instructions at the same
bytes, so a MAME trace of `invaders` would expose a game that used them; the
Space Invaders code does not. **Treat the table as the best available rule
and say so in the handler docstrings.** If a hardware run of a program that
executes these bytes is ever published, its result outranks every line of
this section.

`MOV M,M` (0x76) is `HLT`: documented, not undocumented, but easy to get
wrong in a table-driven decoder.

## Lifecycle corners

| Behavior | Rule | Evidence |
| --- | --- | --- |
| PC during interrupt acknowledge | not incremented; the pushed return address is the interrupted instruction's address | documented (`[UM ch. 2]`); MAME implements it by fetching the vector outside `read_op` |
| INTE on acceptance | cleared | documented |
| `EI` delay | enabled after the next instruction completes; each `EI` re-arms it, so `EI; EI; X` accepts only after X | documented (`[UM ch. 4, EI]`); MAME `m_after_ei = 2`; this core agrees with MAME over 103 `EI`s and 102 acceptances in the `invaders` lockstep (emulator-derived) |
| `HLT` then interrupt | pushed return address is the instruction after `HLT` | documented (`[ALP, HLT]`: PC holds the next sequential instruction); MAME models it by rewinding PC on `HLT` and advancing on wake, which is observably the same. `invaders` never executes `HLT`, so the lockstep does not cover this; `tests/test_lifecycle.py` does, from the manual |
| `HLT` with INTE clear | only RESET exits | documented (`[UM ch. 2, "Halt Sequences"]`) |
| RESET | PC = 0, INTE = 0, halt cleared; other registers unspecified | documented (`[UM ch. 2, "Start-up"]`); `[unverified]` what real chips leave in A..L, SP. This core preserves them (`tests/test_lifecycle.py`) |
| Multi-byte instruction supplied on INTA | supported by the 8228 for `CALL`; each operand byte is fetched with INTA and PC is not advanced | documented (`[UM ch. 5, 8228]`); out of scope for the arcade boards; no oracle `[unverified]`. This core refuses it (`request_interrupt` raises `NotImplementedError`) |
| `IN`/`OUT` address bus | port number on A0-A7 and A8-A15 | documented (`[ALP 1-14]`). This core hands the host the 8-bit port number; a host that decodes the full bus rebuilds `(port << 8) \| port` |

## Where the truth lives

1. The `8080EXM.COM` CRCs, captured on real chips, for every documented ALU,
   load, store, and rotate instruction's flag and register results. If this
   page and a CRC disagree, the CRC wins; fix the page.
2. Intel's manuals for state counts and the lifecycle rules.
3. MAME 0.285 and superzazu/8080 for the undocumented opcodes and for
   cross-checking the formulations, as detectors only.

Sources are listed with URLs and licenses in [start-here.md](start-here.md)
and [validation.md](validation.md).
