"""Every one of the 256 opcodes: its state count and which flags it may touch.

The grid below is transcribed by hand from Intel's "Summary of Processor
Instructions" [UM p. 4-15] (docs/start-here.md), not generated from the core
or its disassembler, so it is an independent statement of the datasheet. For
conditional calls and returns it holds the not-taken count; the taken counts
are 17 (Ccc) and 11 (Rcc). The twelve undocumented bytes carry the counts of
the instructions they alias (docs/undocumented-behavior.md).
"""

from __future__ import annotations

import pytest
from conftest import machine_with

from i8080_python import FLAG_AC, FLAG_CY, FLAG_MASK, FLAG_P, FLAG_S, FLAG_Z

# fmt: off
STATES = (
    #  0   1   2   3   4   5   6   7   8   9   A   B   C   D   E   F
       4, 10,  7,  5,  5,  5,  7,  4,  4, 10,  7,  5,  5,  5,  7,  4,  # 0x
       4, 10,  7,  5,  5,  5,  7,  4,  4, 10,  7,  5,  5,  5,  7,  4,  # 1x
       4, 10, 16,  5,  5,  5,  7,  4,  4, 10, 16,  5,  5,  5,  7,  4,  # 2x
       4, 10, 13,  5, 10, 10, 10,  4,  4, 10, 13,  5,  5,  5,  7,  4,  # 3x
       5,  5,  5,  5,  5,  5,  7,  5,  5,  5,  5,  5,  5,  5,  7,  5,  # 4x
       5,  5,  5,  5,  5,  5,  7,  5,  5,  5,  5,  5,  5,  5,  7,  5,  # 5x
       5,  5,  5,  5,  5,  5,  7,  5,  5,  5,  5,  5,  5,  5,  7,  5,  # 6x
       7,  7,  7,  7,  7,  7,  7,  7,  5,  5,  5,  5,  5,  5,  7,  5,  # 7x
       4,  4,  4,  4,  4,  4,  7,  4,  4,  4,  4,  4,  4,  4,  7,  4,  # 8x
       4,  4,  4,  4,  4,  4,  7,  4,  4,  4,  4,  4,  4,  4,  7,  4,  # 9x
       4,  4,  4,  4,  4,  4,  7,  4,  4,  4,  4,  4,  4,  4,  7,  4,  # Ax
       4,  4,  4,  4,  4,  4,  7,  4,  4,  4,  4,  4,  4,  4,  7,  4,  # Bx
       5, 10, 10, 10, 11, 11,  7, 11,  5, 10, 10, 10, 11, 17,  7, 11,  # Cx
       5, 10, 10, 10, 11, 11,  7, 11,  5, 10, 10, 10, 11, 17,  7, 11,  # Dx
       5, 10, 10, 18, 11, 11,  7, 11,  5,  5, 10,  4, 11, 17,  7, 11,  # Ex
       5, 10, 10,  4, 11, 11,  7, 11,  5,  5, 10,  4, 11, 17,  7, 11,  # Fx
)
# fmt: on

CONDITIONAL_RETURNS = frozenset(range(0xC0, 0x100, 8))
CONDITIONAL_CALLS = frozenset(range(0xC4, 0x100, 8))

#: Opcodes documented to change only CY: DAD, the four rotates, STC, CMC.
CARRY_ONLY = frozenset({0x09, 0x19, 0x29, 0x39, 0x07, 0x0F, 0x17, 0x1F, 0x37, 0x3F})
#: INR and DCR: S Z P AC, never CY.
ALL_BUT_CARRY = frozenset(range(0x04, 0x40, 8)) | frozenset(range(0x05, 0x40, 8))
#: The ALU block, the ALU immediates, and DAA may change all five flags.
ALL_FLAGS = frozenset(range(0x80, 0xC0)) | frozenset(range(0xC6, 0x100, 8)) | {0x27}
POP_PSW = 0xF1
NO_FLAGS = frozenset(range(256)) - CARRY_ONLY - ALL_BUT_CARRY - ALL_FLAGS - {POP_PSW}


def _flag_bits_satisfy(flags: int, code: int) -> bool:
    """Condition CCC evaluated from the table in docs/start-here.md."""
    return (
        not flags & FLAG_Z,
        bool(flags & FLAG_Z),
        not flags & FLAG_CY,
        bool(flags & FLAG_CY),
        not flags & FLAG_P,
        bool(flags & FLAG_P),
        not flags & FLAG_S,
        bool(flags & FLAG_S),
    )[code]


def _run_one(opcode: int, flags: int) -> tuple[int, int]:
    """Execute ``opcode`` (operands 0x34 0x12) with ``flags``; return (states, F after)."""
    cpu = machine_with([opcode, 0x34, 0x12], f=flags, sp=0x8000, h=0x40, l=0x00)
    states = cpu.step()
    return states, cpu.f.byte


def test_grid_is_complete() -> None:
    assert len(STATES) == 256


@pytest.mark.parametrize("opcode", range(256), ids=lambda op: f"{op:02X}")
def test_state_count_matches_intel_summary(opcode: int) -> None:
    code = (opcode >> 3) & 0x07
    for flags in (0x00, 0xFF):
        states, _ = _run_one(opcode, flags)
        taken = _flag_bits_satisfy(flags & FLAG_MASK, code)
        if opcode in CONDITIONAL_RETURNS and taken:
            assert states == 11, f"{opcode:02X} taken"
        elif opcode in CONDITIONAL_CALLS and taken:
            assert states == 17, f"{opcode:02X} taken"
        else:
            assert states == STATES[opcode], f"{opcode:02X} with F={flags:02X}"


@pytest.mark.parametrize("opcode", sorted(NO_FLAGS), ids=lambda op: f"{op:02X}")
def test_documented_flagless_instruction_leaves_f_alone(opcode: int) -> None:
    for flags in (0x02, 0xD7):
        assert _run_one(opcode, flags)[1] == flags


@pytest.mark.parametrize("opcode", sorted(CARRY_ONLY), ids=lambda op: f"{op:02X}")
def test_carry_only_instruction_leaves_s_z_ac_p_alone(opcode: int) -> None:
    others = FLAG_S | FLAG_Z | FLAG_AC | FLAG_P
    for flags in (0x02, 0xD7):
        assert _run_one(opcode, flags)[1] & others == flags & others


@pytest.mark.parametrize("opcode", sorted(ALL_BUT_CARRY), ids=lambda op: f"{op:02X}")
def test_inr_dcr_leave_carry_alone(opcode: int) -> None:
    for flags in (0x02, 0xD7):
        assert _run_one(opcode, flags)[1] & FLAG_CY == flags & FLAG_CY


@pytest.mark.parametrize("opcode", range(256), ids=lambda op: f"{op:02X}")
def test_fixed_flag_bits_hold_after_every_opcode(opcode: int) -> None:
    for flags in (0x00, 0xFF):
        assert _run_one(opcode, flags)[1] & ~FLAG_MASK == 0x02
