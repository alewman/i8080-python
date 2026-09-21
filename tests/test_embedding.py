"""The embedding contract: the bus is four callables the host passes in.

Same shape as z80-python 0.4.0 and m6800-python, so a host written for one
core reads like a host written for another.
"""

from __future__ import annotations

import pytest

from i8080_python import I8080CPU


def test_a_flat_host_is_two_arguments() -> None:
    memory = bytearray(0x10000)
    memory[0:2] = bytes((0x3E, 0x2A))  # MVI A,2AH
    cpu = I8080CPU(memory.__getitem__, memory.__setitem__)
    assert cpu.step() == 7
    assert cpu.a == 0x2A


def test_the_io_bus_defaults_to_nothing_connected() -> None:
    memory = bytearray(0x10000)
    memory[0:4] = bytes((0xDB, 0x03, 0xD3, 0x05))  # IN 03H; OUT 05H
    cpu = I8080CPU(memory.__getitem__, memory.__setitem__)
    cpu.step()
    assert cpu.a == 0xFF  # no device drives the bus
    assert cpu.step() == 10  # and the write goes nowhere


def test_ports_are_supplied_by_keyword() -> None:
    memory = bytearray(0x10000)
    memory[0:4] = bytes((0xDB, 0x03, 0xD3, 0x05))
    written: list[tuple[int, int]] = []
    cpu = I8080CPU(
        memory.__getitem__,
        memory.__setitem__,
        read_port=lambda port: port * 2,
        write_port=lambda port, value: written.append((port, value)),
    )
    cpu.step()
    assert cpu.a == 0x06
    cpu.step()
    assert written == [(0x05, 0x06)]


@pytest.mark.parametrize("position", range(4))
def test_a_bus_that_is_not_callable_is_refused(position: int) -> None:
    buses: list[object] = [lambda addr: 0, lambda addr, value: None] * 2
    buses[position] = 0x42
    with pytest.raises(TypeError, match="must be callable"):
        I8080CPU(buses[0], buses[1], read_port=buses[2], write_port=buses[3])


def test_defining_the_bus_as_methods_is_refused_with_the_new_form() -> None:
    # The pre-0.2.0 form: the instance attributes would silently shadow these,
    # so the class definition itself fails and names the replacement.
    with pytest.raises(TypeError, match=r"defines read_byte, write_port as methods"):

        class Legacy(I8080CPU):
            def read_byte(self, addr: int) -> int:
                return 0

            def write_port(self, port: int, value: int) -> None:
                pass


def test_a_host_may_still_subclass_for_its_own_state() -> None:
    class Board(I8080CPU):
        def __init__(self) -> None:
            self.memory = bytearray(0x10000)
            self.log: list[int] = []
            super().__init__(self.memory.__getitem__, self.memory.__setitem__, write_port=self._out)

        def _out(self, port: int, value: int) -> None:
            self.log.append(port)

    board = Board()
    board.memory[0:2] = bytes((0xD3, 0x02))
    board.step()
    assert board.log == [0x02]


def test_the_bus_callables_can_be_replaced_after_construction() -> None:
    # What DebugSession(track_accesses=True) relies on.
    memory = bytearray(0x10000)
    cpu = I8080CPU(memory.__getitem__, memory.__setitem__)
    reads: list[int] = []
    inner = cpu.read_byte

    def tracked(address: int) -> int:
        reads.append(address)
        return inner(address)

    cpu.read_byte = tracked
    memory[0:3] = bytes((0x21, 0x34, 0x12))  # LXI H,1234H
    cpu.step()
    assert reads == [0, 1, 2]
