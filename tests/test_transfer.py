"""Data transfer group, worked examples [UM ch. 4]."""

from __future__ import annotations

import pytest
from conftest import machine_with

REGISTERS = ("b", "c", "d", "e", "h", "l", None, "a")  # index 6 is M


@pytest.mark.parametrize("dest", range(8))
@pytest.mark.parametrize("src", range(8))
def test_mov_every_pair(dest: int, src: int) -> None:
    opcode = 0x40 | (dest << 3) | src
    if opcode == 0x76:
        pytest.skip("MOV M,M is HLT (test_machine.py)")
    cpu = machine_with([opcode], b=0x11, c=0x22, d=0x33, e=0x44, h=0x20, l=0x10, a=0x77)
    cpu.memory[0x2010] = 0x99
    source_value = 0x99 if src == 6 else getattr(cpu, REGISTERS[src])
    assert cpu.step() == (7 if 6 in (src, dest) else 5)
    if dest == 6:
        assert cpu.memory[0x2010] == source_value
    else:
        assert getattr(cpu, REGISTERS[dest]) == source_value
    assert cpu.pc == 0x0101


def test_mvi_register_and_memory() -> None:
    cpu = machine_with([0x3E, 0x2A, 0x36, 0x5C], h=0x30, l=0x00)  # MVI A,2AH; MVI M,5CH
    assert cpu.step() == 7
    assert cpu.a == 0x2A
    assert cpu.step() == 10
    assert cpu.memory[0x3000] == 0x5C
    assert cpu.pc == 0x0104


@pytest.mark.parametrize(
    ("opcode", "pair"), [(0x01, "bc"), (0x11, "de"), (0x21, "hl"), (0x31, "sp")]
)
def test_lxi_is_little_endian(opcode: int, pair: str) -> None:
    cpu = machine_with([opcode, 0x34, 0x12])
    assert cpu.step() == 10
    value = cpu.sp if pair == "sp" else (getattr(cpu, pair[0]) << 8) | getattr(cpu, pair[1])
    assert value == 0x1234
    assert cpu.pc == 0x0103


def test_lda_sta() -> None:
    cpu = machine_with([0x3A, 0x00, 0x20, 0x32, 0x01, 0x20])
    cpu.memory[0x2000] = 0xAB
    assert cpu.step() == 13
    assert cpu.a == 0xAB
    assert cpu.step() == 13
    assert cpu.memory[0x2001] == 0xAB


def test_lhld_loads_l_from_the_address_and_h_from_the_next() -> None:
    cpu = machine_with([0x2A, 0x00, 0x20])
    cpu.load(0x2000, 0xCD, 0xAB)
    assert cpu.step() == 16
    assert (cpu.h, cpu.l) == (0xAB, 0xCD)


def test_shld_stores_l_then_h() -> None:
    cpu = machine_with([0x22, 0xFF, 0xFF], h=0x12, l=0x34)
    assert cpu.step() == 16
    assert (cpu.memory[0xFFFF], cpu.memory[0x0000]) == (0x34, 0x12)  # address wraps


def test_ldax_stax_use_bc_and_de() -> None:
    cpu = machine_with([0x0A, 0x1A, 0x02, 0x12], b=0x20, c=0x00, d=0x30, e=0x00)
    cpu.memory[0x2000] = 0x11
    cpu.memory[0x3000] = 0x22
    assert cpu.step() == 7
    assert cpu.a == 0x11
    assert cpu.step() == 7
    assert cpu.a == 0x22
    cpu.memory[0x2000] = cpu.memory[0x3000] = 0
    assert cpu.step() == 7
    assert cpu.memory[0x2000] == 0x22
    assert cpu.step() == 7
    assert cpu.memory[0x3000] == 0x22


def test_xchg_swaps_hl_and_de() -> None:
    cpu = machine_with([0xEB], d=0x12, e=0x34, h=0x56, l=0x78)
    assert cpu.step() == 4
    assert (cpu.d, cpu.e, cpu.h, cpu.l) == (0x56, 0x78, 0x12, 0x34)
