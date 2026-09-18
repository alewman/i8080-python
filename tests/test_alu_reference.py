"""The ALU against a second, independently written statement of the flag rules.

The core computes AC with the XOR trick (bit 4 of a ^ b ^ result). This file
restates each rule from docs/undocumented-behavior.md the way the 8080's ALU
does it, as a 4-bit addition, and sweeps every A against a spread of operands
with CY clear and set. The hardware-captured 8080EXM CRCs cover the full input
space; this is the quick detector that runs on every push.
"""

from __future__ import annotations

import pytest
from conftest import machine_with

OPERANDS = (0x00, 0x01, 0x07, 0x08, 0x09, 0x0F, 0x10, 0x3C, 0x7F, 0x80, 0x81, 0x99, 0xF0, 0xFF)


def _szp(result: int) -> int:
    parity_even = bin(result).count("1") % 2 == 0
    return (0x80 if result & 0x80 else 0) | (0x40 if result == 0 else 0) | (4 if parity_even else 0)


def reference(op: str, a: int, value: int, carry: int) -> tuple[int, int]:
    """Return (A after, F after) for an ALU op, from the documented rules."""
    if op in ("ADD", "ADC"):
        carry_in = carry if op == "ADC" else 0
        total = a + value + carry_in
        ac = (a & 0x0F) + (value & 0x0F) + carry_in > 0x0F
        result, cy = total & 0xFF, total > 0xFF
    elif op in ("SUB", "SBB", "CMP"):
        borrow_in = carry if op == "SBB" else 0
        # The ALU adds the complement with an inverted borrow as carry-in; AC is
        # that addition's nibble carry, CY is the inverted final carry (borrow).
        ac = (a & 0x0F) + (~value & 0x0F) + (1 - borrow_in) > 0x0F
        total = a - value - borrow_in
        result, cy = total & 0xFF, total < 0
        if op == "CMP":
            return a, _szp(result) | (0x10 if ac else 0) | 0x02 | (1 if cy else 0)
    elif op == "ANA":
        result, cy, ac = a & value, False, bool((a | value) & 0x08)
    elif op == "XRA":
        result, cy, ac = a ^ value, False, False
    else:  # ORA
        result, cy, ac = a | value, False, False
    return result, _szp(result) | (0x10 if ac else 0) | 0x02 | (1 if cy else 0)


REGISTER_FORMS = {"ADD": 0x80, "ADC": 0x88, "SUB": 0x90, "SBB": 0x98,
                  "ANA": 0xA0, "XRA": 0xA8, "ORA": 0xB0, "CMP": 0xB8}  # fmt: skip
IMMEDIATE_FORMS = {"ADD": 0xC6, "ADC": 0xCE, "SUB": 0xD6, "SBB": 0xDE,
                   "ANA": 0xE6, "XRA": 0xEE, "ORA": 0xF6, "CMP": 0xFE}  # fmt: skip


@pytest.mark.parametrize("op", REGISTER_FORMS)
def test_register_form_matches_reference(op: str) -> None:
    for a in range(256):
        for value in OPERANDS:
            for carry in (0, 1):
                # Operand in B (SSS = 000).
                cpu = machine_with([REGISTER_FORMS[op]], a=a, b=value, f=carry)
                cpu.step()
                assert (cpu.a, cpu.f.byte) == reference(op, a, value, carry), (
                    f"{op} A={a:02X} B={value:02X} CY={carry}"
                )


@pytest.mark.parametrize("op", IMMEDIATE_FORMS)
def test_immediate_form_matches_reference(op: str) -> None:
    for a in range(0, 256, 3):
        for value in OPERANDS:
            for carry in (0, 1):
                cpu = machine_with([IMMEDIATE_FORMS[op], value], a=a, f=carry)
                cpu.step()
                assert (cpu.a, cpu.f.byte) == reference(op, a, value, carry)


def test_memory_operand_matches_reference() -> None:
    for a in range(256):
        cpu = machine_with([0x96], a=a, h=0x20, l=0x00)  # SUB M
        cpu.memory[0x2000] = 0x5A
        cpu.step()
        assert (cpu.a, cpu.f.byte) == reference("SUB", a, 0x5A, 0)


def test_inr_dcr_match_reference_for_every_value() -> None:
    for value in range(256):
        for carry in (0, 1):
            cpu = machine_with([0x04], b=value, f=carry)  # INR B
            cpu.step()
            result = (value + 1) & 0xFF
            ac = (value & 0x0F) + 1 > 0x0F
            assert cpu.b == result
            assert cpu.f.byte == _szp(result) | (0x10 if ac else 0) | 0x02 | carry

            cpu = machine_with([0x05], b=value, f=carry)  # DCR B
            cpu.step()
            result = (value - 1) & 0xFF
            # DCR adds 0xFF (the complement of 1, carry-in 1 absorbed): nibble carry
            # out happens unless the low nibble was 0.
            ac = (value & 0x0F) + 0x0F > 0x0F
            assert cpu.b == result
            assert cpu.f.byte == _szp(result) | (0x10 if ac else 0) | 0x02 | carry
