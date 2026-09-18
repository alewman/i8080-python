"""Arithmetic group, worked examples [UM ch. 4; ALP ch. 3] and the AC rules."""

from __future__ import annotations

import pytest
from conftest import machine_with

from i8080_python import FLAG_AC, FLAG_CY, FLAG_P, FLAG_S, FLAG_Z


def test_add_sets_ac_on_carry_out_of_bit_3_and_cy_on_carry_out_of_bit_7() -> None:
    cpu = machine_with([0x80], a=0x2E, b=0x74)  # ADD B: 0x2E + 0x74 = 0xA2 [ALP ch. 3]
    assert cpu.step() == 4
    assert cpu.a == 0xA2
    assert cpu.f.byte == FLAG_S | FLAG_AC | 0x02  # 0xA2 has three bits set: parity odd


def test_adc_adds_the_carry() -> None:
    cpu = machine_with([0x88], a=0xFF, b=0x00, f=FLAG_CY)  # ADC B
    cpu.step()
    assert cpu.a == 0x00
    assert cpu.f.byte == FLAG_Z | FLAG_AC | FLAG_P | FLAG_CY | 0x02


def test_sub_a_clears_a_and_carry_and_sets_ac() -> None:
    # "SUB A": Z = 1, P = 1, CY = 0, and AC = 1 because the ALU's complement
    # addition carries out of bit 3 (docs/undocumented-behavior.md).
    cpu = machine_with([0x97], a=0x3E, f=FLAG_CY)
    assert cpu.step() == 4
    assert cpu.a == 0
    assert cpu.f.byte == FLAG_Z | FLAG_AC | FLAG_P | 0x02


def test_sub_borrow_sets_cy_and_clears_ac() -> None:
    cpu = machine_with([0xD6, 0x01], a=0x00)  # SUI 1: 0x00 - 0x01 borrows through every nibble
    assert cpu.step() == 7
    assert cpu.a == 0xFF
    assert cpu.f.byte == FLAG_S | FLAG_P | FLAG_CY | 0x02


def test_sbb_subtracts_the_borrow() -> None:
    cpu = machine_with([0x9A], a=0x04, d=0x02, f=FLAG_CY)  # SBB D [ALP ch. 3]
    cpu.step()
    assert cpu.a == 0x01
    assert cpu.f.cy == 0
    assert cpu.f.ac == 1


@pytest.mark.parametrize(("opcode", "a", "cy", "result"), [
    (0xC6, 0x10, 0, 0x30),  # ADI 20H
    (0xCE, 0x10, 1, 0x31),  # ACI 20H
    (0xD6, 0x30, 0, 0x10),  # SUI 20H
    (0xDE, 0x30, 1, 0x0F),  # SBI 20H
])  # fmt: skip
def test_arithmetic_immediates(opcode: int, a: int, cy: int, result: int) -> None:
    cpu = machine_with([opcode, 0x20], a=a, f=cy)
    assert cpu.step() == 7
    assert cpu.a == result
    assert cpu.pc == 0x0102


def test_inr_sets_ac_when_the_low_nibble_wraps() -> None:
    cpu = machine_with([0x0C], c=0x0F)  # INR C
    assert cpu.step() == 5
    assert cpu.c == 0x10
    assert cpu.f.ac == 1


def test_dcr_sets_ac_unless_the_low_nibble_borrows() -> None:
    cpu = machine_with([0x15, 0x15], d=0x11)  # DCR D twice
    cpu.step()
    assert (cpu.d, cpu.f.ac) == (0x10, 1)  # 0x11 -> 0x10: no borrow, AC set
    cpu.step()
    assert (cpu.d, cpu.f.ac) == (0x0F, 0)  # 0x10 -> 0x0F: borrow, AC clear


def test_inr_dcr_m_operate_on_memory_in_10_states() -> None:
    cpu = machine_with([0x34, 0x35, 0x35], h=0x20, l=0x00)
    cpu.memory[0x2000] = 0xFF
    assert cpu.step() == 10
    assert cpu.memory[0x2000] == 0x00
    assert cpu.f.z == 1
    assert cpu.step() == 10
    assert cpu.memory[0x2000] == 0xFF
    assert cpu.f.s == 1


def test_inx_dcx_wrap_and_leave_flags() -> None:
    cpu = machine_with([0x33, 0x0B], sp=0xFFFF, b=0x00, c=0x00, f=0xFF)
    assert cpu.step() == 5
    assert cpu.sp == 0x0000
    assert cpu.step() == 5
    assert (cpu.b, cpu.c) == (0xFF, 0xFF)
    assert cpu.f.byte == 0xD7


@pytest.mark.parametrize(
    ("opcode", "pair"), [(0x09, "bc"), (0x19, "de"), (0x29, "hl"), (0x39, "sp")]
)
def test_dad_sets_only_carry(opcode: int, pair: str) -> None:
    cpu = machine_with([opcode], h=0xA1, l=0x7B, f=FLAG_Z | FLAG_S)
    if pair == "sp":
        cpu.sp = 0x8000
    elif pair != "hl":
        setattr(cpu, pair[0], 0x80)
        setattr(cpu, pair[1], 0x00)
    assert cpu.step() == 10
    expected = 0xA17B * 2 if pair == "hl" else 0xA17B + 0x8000
    assert (cpu.h << 8) | cpu.l == expected & 0xFFFF
    assert cpu.f.cy == 1
    assert cpu.f.byte & (FLAG_S | FLAG_Z) == FLAG_S | FLAG_Z


@pytest.mark.parametrize(("a", "flags", "result", "result_flags"), [
    # The manual's example: A = 9BH, AC = CY = 0 -> 01H with CY and AC set [ALP ch. 3, DAA].
    (0x9B, 0x00, 0x01, FLAG_AC | FLAG_CY),
    (0x15, FLAG_AC, 0x1B, FLAG_P),                # AC forces the +6 even for a digit <= 9
    (0x99, 0x00, 0x99, FLAG_S | FLAG_P),          # already BCD: unchanged
    (0x00, FLAG_CY, 0x60, FLAG_P | FLAG_CY),      # CY forces +60H and stays set
    (0x9A, 0x00, 0x00, FLAG_Z | FLAG_AC | FLAG_P | FLAG_CY),
])  # fmt: skip
def test_daa(a: int, flags: int, result: int, result_flags: int) -> None:
    cpu = machine_with([0x27], a=a, f=flags)
    assert cpu.step() == 4
    assert cpu.a == result
    assert cpu.f.byte == result_flags | 0x02


def test_daa_never_clears_carry() -> None:
    for a in range(256):
        cpu = machine_with([0x27], a=a, f=FLAG_CY)
        cpu.step()
        assert cpu.f.cy == 1, f"A={a:02X}"
