# Provenance

Audited 2026-11-13 (provenance audit, wave 1) at `9c08d80` on `main`, all branches and
history included. No GPL source was opened for this audit.

## Summary

| Verdict | Count |
| --- | --- |
| clean | 8 |
| cite | 0 |
| rewrite | 0 |
| unclear | 0 |

## The code

| Part | Where its behaviour came from | Licence of the source | Verdict |
| --- | --- | --- | --- |
| Instruction handlers, flags, DAA, state counts (`_arithmetic.py`, `_logical.py`, `_transfer.py`, `_branch.py`, `_machine.py`, `_flags.py`, `_core.py`, `cpu.py`) | Intel *8080 Microcomputer Systems User's Manual* (1975) and *8080/8085 Assembly Language Programming Manual* (1981); undocumented opcodes from emulator consensus (MAME, superzazu/8080) settled by the hardware 8080EXM CRCs | Intel manuals (copyright Intel; facts); MAME `i8085.cpp` BSD-3-Clause; superzazu/8080 MIT | clean |
| EI delay across repeated EIs (`_machine.py`: "as MAME's `m_after_ei` does"), HLT slice of 7 (`cpu.py`) | Behaviour matched to MAME 0.285 | `i8085.cpp`: `license:BSD-3-Clause`, copyright-holders Juergen Buchmueller, Roberto Fresca, Grull Osgo (header confirmed 2026-11-13) | clean (behaviour, named; no code taken) |
| State-count table | Intel UM p. 4-15; cross-checked against MAME's `lut_cycles_8080` and superzazu's table (`docs/timing.md`) | facts; BSD-3 / MIT | clean |
| `validation/cpm.py` `EXM_HARDWARE_CRCS` (25 CRCs and their group labels) | The CRCs 8080EXM prints on real non-AMD 8080A chips, documented as hardware captures (Mike Douglas's 2013 build, his 2009 screenshot of a real 8080) | 8080EXM is GPL-2.0-or-later; the values are hardware-measured facts stated in prose (middle rule) | clean (the labels are the program's short output strings, used to parse its output) |
| `validation/mame_lockstep.py`, `scripts/mame_trace.py` | MAME 0.285 `invaders` run as a closed-box detector | MAME (run only) | clean |
| `scripts/fetch_exercisers.py` | Fetches 8080PRE/8080EXER/8080EXM (GPL-2.0-or-later), TST8080 (Microcosm 1980, no formal licence), CPUTEST (SuperSoft 1981, no licence, opt-in) by SHA-256; nothing committed | as stated | clean |
| Tests (`tests/*.py`) | Own, from the manuals; `test_alu_reference.py` an independent restatement; exerciser state totals compared with superzazu/8080's published numbers | superzazu MIT (numbers, credited in `docs/validation.md`) | clean |
| `disasm.py`, `debug.py`, `trace.py`, `console.py`, `state.py`, `__main__.py` | Own | n/a | clean |

## provenance_check.py run

`provenance_check.py --repo i8080-python --reference <superzazu/8080 @ 274ffd7>` (MIT,
cloned into a scratch directory; the tree also holds the GPL exerciser sources under
`cpu_tests/`, which produced no hits): 4 pairs, all against `i8080.c`: mnemonic lists
(`jnz jz jnc ...`) and runs of the datasheet state counts. Facts; nothing copied.

## History

No file was ever deleted; no binary, exerciser or ROM was ever committed; no removed line
cites a GPL source. Not provenance but recorded for a history clean-up: commits `ba0b21a`
and `54eadf0` (2026-09-12/18) wrote a machine path naming a ROM mirror into
`docs/mame-oracle.md`, `scripts/mame_trace.py`, `validation/mame_lockstep.py`; `c9cc11c`
removed it; the repository is public. 15 commits carry the author name "the owner's full name".
`docs/handoff-brief.md` still holds machine paths.

## Owed

- SPDX headers: 0 of 38 source files.
