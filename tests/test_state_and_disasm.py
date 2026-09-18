"""CPUState, the Flags type, and the disassembler."""

from __future__ import annotations

import pytest
from conftest import Machine, machine_with

from i8080_python import CPUState, Flags, disassemble, disassemble_bytes, instruction_length


def test_new_cpu_state() -> None:
    assert Machine().capture_state() == CPUState()
    assert CPUState().f == 0x02


def test_capture_restore_round_trip() -> None:
    cpu = machine_with([0x00], a=1, b=2, c=3, d=4, e=5, h=6, l=7, sp=0x1234, f=0xFF)
    cpu.inte = True
    cpu.request_interrupt(0xCF)
    state = cpu.capture_state()
    other = Machine()
    other.restore_state(state)
    assert other.capture_state() == state
    assert state.f == 0xD7
    assert state.interrupt_vector == 0xCF


@pytest.mark.parametrize(
    ("field", "value"),
    [("a", 256), ("pc", -1), ("f", 0x00), ("f", 0x2A), ("ei_delay", 2), ("inte", 1)],
)
def test_state_validation(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        CPUState(**{field: value})


def test_flags_force_the_fixed_bits() -> None:
    flags = Flags(0xFF)
    assert flags.byte == 0xD7
    flags.byte = 0x00
    assert flags.byte == 0x02
    flags.cy = 1
    flags.ac = 1
    assert flags.byte == 0x13


@pytest.mark.parametrize(
    ("data", "text"),
    [
        ([0x00], "NOP"),
        ([0x08], "*NOP"),
        ([0x01, 0x34, 0x12], "LXI B,1234H"),
        ([0x31, 0x00, 0xF0], "LXI SP,0F000H"),
        ([0x3E, 0x2A], "MVI A,2AH"),
        ([0x36, 0xFF], "MVI M,0FFH"),
        ([0x78], "MOV A,B"),
        ([0x76], "HLT"),
        ([0x86], "ADD M"),
        ([0xBF], "CMP A"),
        ([0x2A, 0x06, 0x00], "LHLD 0006H"),
        ([0x27], "DAA"),
        ([0xC2, 0x00, 0x30], "JNZ 3000H"),
        ([0xCB, 0x00, 0x30], "*JMP 3000H"),
        ([0xD9], "*RET"),
        ([0xDD, 0x00, 0x30], "*CALL 3000H"),
        ([0xF5], "PUSH PSW"),
        ([0xF1], "POP PSW"),
        ([0xDB, 0x01], "IN 01H"),
        ([0xD3, 0xAB], "OUT 0ABH"),
        ([0xCF], "RST 1"),
        ([0xFE, 0x00], "CPI 00H"),
        ([0xE9], "PCHL"),
        ([0xF8], "RM"),
    ],
)
def test_disassembly_text(data: list[int], text: str) -> None:
    instruction = disassemble_bytes(data, 0x0100)
    assert instruction.text == text
    assert instruction.data == bytes(data)
    assert instruction.next_address == 0x0100 + len(data)


@pytest.mark.parametrize("opcode", range(256), ids=lambda op: f"{op:02X}")
def test_length_matches_how_far_execution_advances_pc(opcode: int) -> None:
    # For every opcode that does not branch, PC after one step is its length.
    cpu = machine_with([opcode, 0x00, 0x00], sp=0x8000, h=0x20)
    cpu.step()
    moved = (cpu.pc - 0x0100) & 0xFFFF
    if moved < 4:  # the instruction did not transfer control elsewhere
        assert moved == instruction_length(opcode)
    assert disassemble_bytes([opcode, 0, 0]).size == instruction_length(opcode)


def test_disassemble_reads_each_byte_once() -> None:
    reads: list[int] = []
    memory = {0x10: 0xCD, 0x11: 0x34, 0x12: 0x12}

    def reader(address: int) -> int:
        reads.append(address)
        return memory[address]

    assert disassemble(reader, 0x10).text == "CALL 1234H"
    assert reads == [0x10, 0x11, 0x12]
