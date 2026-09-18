"""Stack, I/O, and machine control group; and the twelve undocumented opcodes."""

from __future__ import annotations

import pytest
from conftest import machine_with


@pytest.mark.parametrize(
    ("opcode", "high", "low"), [(0xC5, "b", "c"), (0xD5, "d", "e"), (0xE5, "h", "l")]
)
def test_push_pop_register_pairs(opcode: int, high: str, low: str) -> None:
    cpu = machine_with([opcode, opcode - 4], sp=0x8000)  # PUSH rp; POP rp
    setattr(cpu, high, 0x8F)
    setattr(cpu, low, 0x9D)
    assert cpu.step() == 11
    assert cpu.sp == 0x7FFE
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x8F, 0x9D)
    setattr(cpu, high, 0)
    setattr(cpu, low, 0)
    assert cpu.step() == 10
    assert (getattr(cpu, high), getattr(cpu, low), cpu.sp) == (0x8F, 0x9D, 0x8000)


def test_push_psw_writes_a_then_the_flag_byte_with_fixed_bits() -> None:
    cpu = machine_with([0xF5], a=0x1F, f=0x00, sp=0x8000)
    assert cpu.step() == 11
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x1F, 0x02)


@pytest.mark.parametrize(("stacked", "loaded"), [(0xFF, 0xD7), (0x00, 0x02), (0x28, 0x02)])
def test_pop_psw_forces_bits_5_3_1(stacked: int, loaded: int) -> None:
    # [ALP 1-14]; hardware-captured by every 8080EXM group (docs/undocumented-behavior.md).
    cpu = machine_with([0xF1], sp=0x7FFE)
    cpu.load(0x7FFE, stacked, 0x3C)
    assert cpu.step() == 10
    assert (cpu.a, cpu.f.byte, cpu.sp) == (0x3C, loaded, 0x8000)


def test_xthl_swaps_hl_with_the_top_of_stack() -> None:
    cpu = machine_with([0xE3], sp=0x10AD, h=0x0B, l=0x3C)  # [ALP ch. 3, XTHL]
    cpu.load(0x10AD, 0xF0, 0x0D)
    assert cpu.step() == 18
    assert (cpu.h, cpu.l) == (0x0D, 0xF0)
    assert (cpu.memory[0x10AD], cpu.memory[0x10AE]) == (0x3C, 0x0B)
    assert cpu.sp == 0x10AD


def test_sphl() -> None:
    cpu = machine_with([0xF9], h=0x50, l=0x6C)
    assert cpu.step() == 5
    assert cpu.sp == 0x506C


def test_in_reads_the_port_named_by_its_operand() -> None:
    cpu = machine_with([0xDB, 0x03])
    cpu.port_values[0x03] = 0x5A
    assert cpu.step() == 10
    assert cpu.a == 0x5A
    assert cpu.port_reads == [0x03]


def test_out_writes_a_to_the_port_named_by_its_operand() -> None:
    cpu = machine_with([0xD3, 0x06], a=0x77)
    assert cpu.step() == 10
    assert cpu.port_writes == [(0x06, 0x77)]


def test_ei_di() -> None:
    cpu = machine_with([0xFB, 0xF3])
    assert cpu.step() == 4
    assert cpu.inte
    assert cpu.step() == 4
    assert not cpu.inte


def test_hlt_is_76_takes_7_and_leaves_pc_past_it() -> None:
    cpu = machine_with([0x76])
    assert cpu.step() == 7
    assert cpu.halted
    assert cpu.pc == 0x0101


def test_nop() -> None:
    cpu = machine_with([0x00])
    before = cpu.capture_state()
    assert cpu.step() == 4
    assert cpu.capture_state() == before.__class__(**{**_fields(before), "pc": 0x0101})


def _fields(state: object) -> dict[str, object]:
    return {name: getattr(state, name) for name in state.__slots__}


# The undocumented aliases: emulator consensus and decoder inference, unverified
# on hardware (docs/undocumented-behavior.md). They are pinned here so a change
# to them is deliberate.


@pytest.mark.parametrize("opcode", [0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38])
def test_undocumented_nops(opcode: int) -> None:
    cpu = machine_with([opcode], a=0x12, f=0xFF, sp=0x8000)
    before = _fields(cpu.capture_state())
    assert cpu.step() == 4
    assert _fields(cpu.capture_state()) == {**before, "pc": 0x0101}


def test_undocumented_cb_is_jmp() -> None:
    cpu = machine_with([0xCB, 0x00, 0x30])
    assert cpu.step() == 10
    assert cpu.pc == 0x3000


def test_undocumented_d9_is_ret() -> None:
    cpu = machine_with([0xD9], sp=0x7FFE)
    cpu.load(0x7FFE, 0x34, 0x12)
    assert cpu.step() == 10
    assert (cpu.pc, cpu.sp) == (0x1234, 0x8000)


@pytest.mark.parametrize("opcode", [0xDD, 0xED, 0xFD])
def test_undocumented_call_aliases(opcode: int) -> None:
    cpu = machine_with([opcode, 0x00, 0x30], sp=0x8000)
    assert cpu.step() == 17
    assert (cpu.pc, cpu.sp) == (0x3000, 0x7FFE)
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x03)
