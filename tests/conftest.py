"""A flat 64 KiB test machine with recorded port traffic."""

from __future__ import annotations

import pytest

from i8080_python import I8080CPU


class Machine(I8080CPU):
    """64 KiB RAM; IN returns ``port_values[port]`` (default 0xFF); OUT is recorded.

    The bus is passed to the core, as every host does since 0.2.0; subclassing
    is just a convenient place to keep the memory and the port log.
    """

    def __init__(self) -> None:
        self.memory = bytearray(0x10000)
        self.port_values: dict[int, int] = {}
        self.port_reads: list[int] = []
        self.port_writes: list[tuple[int, int]] = []
        super().__init__(
            self.memory.__getitem__,
            self.memory.__setitem__,
            read_port=self._in,
            write_port=self._out,
        )

    def _in(self, port: int) -> int:
        self.port_reads.append(port)
        return self.port_values.get(port, 0xFF)

    def _out(self, port: int, value: int) -> None:
        self.port_writes.append((port, value))

    def load(self, address: int, *data: int) -> None:
        for offset, value in enumerate(data):
            self.memory[(address + offset) & 0xFFFF] = value


def machine_with(program: bytes | list[int], *, at: int = 0x0100, **registers: int) -> Machine:
    """A machine with ``program`` at ``at``, PC there, and the given registers set.

    ``f`` goes through the Flags byte setter, so its fixed bits are forced.
    """
    cpu = Machine()
    cpu.load(at, *program)
    cpu.pc = at
    for name, value in registers.items():
        if name == "f":
            cpu.f.byte = value
        else:
            setattr(cpu, name, value)
    return cpu


@pytest.fixture
def machine() -> Machine:
    return Machine()
