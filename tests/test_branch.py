"""Branch group [UM ch. 4]: every condition both ways, with the 8080's state counts."""

from __future__ import annotations

import pytest
from conftest import machine_with

from i8080_python import FLAG_CY, FLAG_P, FLAG_S, FLAG_Z

#: CCC -> (flags that make it true, flags that make it false).
CONDITIONS = {
    0: ("NZ", 0x00, FLAG_Z),
    1: ("Z", FLAG_Z, 0x00),
    2: ("NC", 0x00, FLAG_CY),
    3: ("C", FLAG_CY, 0x00),
    4: ("PO", 0x00, FLAG_P),
    5: ("PE", FLAG_P, 0x00),
    6: ("P", 0x00, FLAG_S),
    7: ("M", FLAG_S, 0x00),
}


def test_jmp() -> None:
    cpu = machine_with([0xC3, 0x00, 0x30])
    assert cpu.step() == 10
    assert cpu.pc == 0x3000


@pytest.mark.parametrize("code", range(8), ids=lambda c: "J" + CONDITIONS[c][0])
def test_jcc_costs_10_taken_or_not(code: int) -> None:
    _, true_flags, false_flags = CONDITIONS[code]
    opcode = 0xC2 | (code << 3)
    cpu = machine_with([opcode, 0x00, 0x30], f=true_flags)
    assert cpu.step() == 10
    assert cpu.pc == 0x3000
    cpu = machine_with([opcode, 0x00, 0x30], f=false_flags)
    assert cpu.step() == 10
    assert cpu.pc == 0x0103


def test_call_pushes_the_next_address_high_byte_first() -> None:
    cpu = machine_with([0xCD, 0x00, 0x30], sp=0x8000)
    assert cpu.step() == 17
    assert cpu.pc == 0x3000
    assert cpu.sp == 0x7FFE
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x03)


@pytest.mark.parametrize("code", range(8), ids=lambda c: "C" + CONDITIONS[c][0])
def test_ccc_costs_17_taken_and_11_not(code: int) -> None:
    _, true_flags, false_flags = CONDITIONS[code]
    opcode = 0xC4 | (code << 3)
    cpu = machine_with([opcode, 0x00, 0x30], f=true_flags, sp=0x8000)
    assert cpu.step() == 17
    assert (cpu.pc, cpu.sp) == (0x3000, 0x7FFE)
    cpu = machine_with([opcode, 0x00, 0x30], f=false_flags, sp=0x8000)
    assert cpu.step() == 11
    assert (cpu.pc, cpu.sp) == (0x0103, 0x8000)


def test_ret() -> None:
    cpu = machine_with([0xC9], sp=0x7FFE)
    cpu.load(0x7FFE, 0x34, 0x12)
    assert cpu.step() == 10
    assert (cpu.pc, cpu.sp) == (0x1234, 0x8000)


@pytest.mark.parametrize("code", range(8), ids=lambda c: "R" + CONDITIONS[c][0])
def test_rcc_costs_11_taken_and_5_not(code: int) -> None:
    _, true_flags, false_flags = CONDITIONS[code]
    opcode = 0xC0 | (code << 3)
    cpu = machine_with([opcode], f=true_flags, sp=0x7FFE)
    cpu.load(0x7FFE, 0x34, 0x12)
    assert cpu.step() == 11
    assert (cpu.pc, cpu.sp) == (0x1234, 0x8000)
    cpu = machine_with([opcode], f=false_flags, sp=0x7FFE)
    assert cpu.step() == 5
    assert (cpu.pc, cpu.sp) == (0x0101, 0x7FFE)


@pytest.mark.parametrize("n", range(8))
def test_rst_pushes_pc_and_jumps_to_8n(n: int) -> None:
    cpu = machine_with([0xC7 | (n << 3)], sp=0x8000)
    assert cpu.step() == 11
    assert cpu.pc == 8 * n
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x01)


def test_pchl() -> None:
    cpu = machine_with([0xE9], h=0x41, l=0x3E)
    assert cpu.step() == 5
    assert cpu.pc == 0x413E


def test_stack_wraps_at_zero() -> None:
    cpu = machine_with([0xCD, 0x00, 0x30], sp=0x0001)
    cpu.step()
    assert cpu.sp == 0xFFFF
    assert (cpu.memory[0x0000], cpu.memory[0xFFFF]) == (0x01, 0x03)
