"""Logical group, worked examples [UM ch. 4; ALP ch. 3]."""

from __future__ import annotations

from conftest import machine_with

from i8080_python import FLAG_AC, FLAG_CY, FLAG_P, FLAG_S, FLAG_Z


def test_ana_clears_carry_and_sets_ac_from_bit_3_of_either_operand() -> None:
    # AC = bit 3 of A OR bit 3 of the operand [ALP 1-12]; the Intel behavior the
    # hardware CRCs pin, which AMD's 9080A does not share.
    cpu = machine_with([0xA0], a=0x08, b=0x00, f=FLAG_CY)  # ANA B
    assert cpu.step() == 4
    assert cpu.a == 0
    assert cpu.f.byte == FLAG_Z | FLAG_AC | FLAG_P | 0x02

    cpu = machine_with([0xE6, 0x0F], a=0xF0)  # ANI 0FH: bit 3 of the operand set
    assert cpu.step() == 7
    assert cpu.a == 0
    assert cpu.f.ac == 1

    cpu = machine_with([0xE6, 0xF7], a=0xF7)  # neither operand has bit 3
    cpu.step()
    assert cpu.f.ac == 0


def test_xra_ora_clear_carry_and_ac() -> None:
    cpu = machine_with([0xAF], a=0x5C, f=FLAG_CY | FLAG_AC)  # XRA A
    assert cpu.step() == 4
    assert cpu.a == 0
    assert cpu.f.byte == FLAG_Z | FLAG_P | 0x02

    cpu = machine_with([0xB1], a=0x33, c=0x0F, f=FLAG_CY | FLAG_AC)  # ORA C [ALP ch. 3]
    cpu.step()
    assert cpu.a == 0x3F
    assert cpu.f.byte == FLAG_P | 0x02


def test_xri_ori() -> None:
    cpu = machine_with([0xEE, 0x81, 0xF6, 0x01], a=0x3B)
    assert cpu.step() == 7
    assert cpu.a == 0xBA
    assert cpu.step() == 7
    assert cpu.a == 0xBB


def test_cmp_sets_flags_like_sub_and_keeps_a() -> None:
    cpu = machine_with([0xBB], a=0x0A, e=0x05)  # CMP E [ALP ch. 3]: A > E
    assert cpu.step() == 4
    assert cpu.a == 0x0A
    assert (cpu.f.z, cpu.f.cy) == (0, 0)

    cpu = machine_with([0xBB], a=0x02, e=0x05)  # A < E: borrow
    cpu.step()
    assert (cpu.f.z, cpu.f.cy) == (0, 1)

    cpu = machine_with([0xFE, 0x40], a=0x40)  # CPI 40H: equal
    assert cpu.step() == 7
    assert (cpu.a, cpu.f.z, cpu.f.cy, cpu.f.ac) == (0x40, 1, 0, 1)


def test_rotates() -> None:
    cpu = machine_with([0x07], a=0xF2)  # RLC [ALP ch. 3]
    assert cpu.step() == 4
    assert (cpu.a, cpu.f.cy) == (0xE5, 1)

    cpu = machine_with([0x0F], a=0xF2)  # RRC
    cpu.step()
    assert (cpu.a, cpu.f.cy) == (0x79, 0)

    cpu = machine_with([0x17], a=0xB5, f=0)  # RAL: CY into bit 0, bit 7 into CY
    cpu.step()
    assert (cpu.a, cpu.f.cy) == (0x6A, 1)

    cpu = machine_with([0x1F], a=0x6A, f=FLAG_CY)  # RAR: CY into bit 7, bit 0 into CY
    cpu.step()
    assert (cpu.a, cpu.f.cy) == (0xB5, 0)


def test_rotates_touch_only_carry() -> None:
    for opcode in (0x07, 0x0F, 0x17, 0x1F):
        cpu = machine_with([opcode], a=0x81, f=FLAG_S | FLAG_Z | FLAG_AC | FLAG_P)
        cpu.step()
        assert cpu.f.byte & ~FLAG_CY == FLAG_S | FLAG_Z | FLAG_AC | FLAG_P | 0x02


def test_cma_stc_cmc() -> None:
    cpu = machine_with([0x2F, 0x37, 0x3F, 0x3F], a=0x51, f=0xFF)
    assert cpu.step() == 4
    assert (cpu.a, cpu.f.byte) == (0xAE, 0xD7)  # CMA: no flags
    cpu.f.cy = 0
    assert cpu.step() == 4
    assert cpu.f.cy == 1  # STC
    assert cpu.step() == 4
    assert cpu.f.cy == 0  # CMC
    cpu.step()
    assert cpu.f.cy == 1
