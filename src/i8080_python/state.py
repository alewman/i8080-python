"""Immutable values for capturing and restoring 8080 processor state."""

from dataclasses import dataclass

from i8080_python._flags import FIXED_ONES, FLAG_MASK


def _require_int(name: str, value: object, maximum: int) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        width = 2 if maximum == 0xFF else 4
        message = f"{name} must be an integer in range 0x{'0' * width}..0x{maximum:0{width}X}"
        raise ValueError(message)


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")


@dataclass(frozen=True, slots=True)
class CPUState:
    """Complete CPU-owned state at an instruction boundary.

    The 8080 has no architecturally visible latch beyond these (its W and Z
    temporaries never leak into a result; docs/start-here.md). ``interrupt_vector``
    is the instruction byte a device has placed on the bus with INT asserted, or
    ``None`` when INT is not asserted. Host memory, ports, devices, and counters
    are not included, so restoring this restores the processor, not a machine.
    """

    a: int = 0
    f: int = FIXED_ONES
    b: int = 0
    c: int = 0
    d: int = 0
    e: int = 0
    h: int = 0
    l: int = 0  # noqa: E741 - canonical 8080 register name
    sp: int = 0
    pc: int = 0
    inte: bool = False
    halted: bool = False
    ei_delay: int = 0
    reset_pending: bool = False
    interrupt_vector: int | None = None

    def __post_init__(self) -> None:
        for name in ("a", "f", "b", "c", "d", "e", "h", "l"):
            _require_int(name, getattr(self, name), 0xFF)
        for name in ("sp", "pc"):
            _require_int(name, getattr(self, name), 0xFFFF)
        for name in ("inte", "halted", "reset_pending"):
            _require_bool(name, getattr(self, name))
        if (self.f & ~FLAG_MASK) != FIXED_ONES:
            raise ValueError("f must have bits 5 and 3 clear and bit 1 set")
        if type(self.ei_delay) is not int or self.ei_delay not in (0, 1):
            raise ValueError("ei_delay must be 0 or 1")
        if self.interrupt_vector is not None:
            _require_int("interrupt_vector", self.interrupt_vector, 0xFF)


__all__ = ["CPUState"]
