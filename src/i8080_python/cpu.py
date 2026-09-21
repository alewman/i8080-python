"""Public 8080 CPU API.

The instruction groups live in private mixins named after the five groups of
Intel's instruction-set chapter [UM ch. 4]: data transfer, arithmetic,
logical, branch, and stack/I/O/machine control. This module is the stable
import surface for ``I8080CPU`` and the flag masks.
"""

from collections.abc import Callable

from i8080_python._arithmetic import ArithmeticMixin
from i8080_python._branch import BranchMixin
from i8080_python._core import CoreMixin
from i8080_python._dispatch import DispatchMixin
from i8080_python._flags import FLAG_AC, FLAG_CY, FLAG_MASK, FLAG_P, FLAG_S, FLAG_Z, Flags
from i8080_python._logical import LogicalMixin
from i8080_python._machine import MachineMixin
from i8080_python._transfer import TransferMixin
from i8080_python.disasm import instruction_length
from i8080_python.state import CPUState

ReadByte = Callable[[int], int]
WriteByte = Callable[[int, int], None]

_BUS = ("read_byte", "write_byte", "read_port", "write_port")

Flags.__module__ = __name__

__all__ = [
    "FLAG_AC",
    "FLAG_CY",
    "FLAG_MASK",
    "FLAG_P",
    "FLAG_S",
    "FLAG_Z",
    "HALT_IDLE_STATES",
    "I8080CPU",
    "CPUState",
    "Flags",
    "ReadByte",
    "WriteByte",
]


def _undriven_port(port: int) -> int:
    """The default ``read_port``: no device drives the data bus, so it reads 0xFF."""
    return 0xFF


def _unconnected_port(port: int, value: int) -> None:
    """The default ``write_port``: no device is listening, so the write goes nowhere."""


#: States a halted CPU's step() consumes. The chip sits in its halt wait state
#: and samples INT every clock, so any positive constant is a modeling choice;
#: 7 is what one HLT costs, which is what MAME charges for each halted slice
#: (it re-executes the HLT), keeping lockstep comparisons aligned.
HALT_IDLE_STATES = 7


class I8080CPU(
    DispatchMixin,
    TransferMixin,
    ArithmeticMixin,
    LogicalMixin,
    BranchMixin,
    MachineMixin,
    CoreMixin,
):
    """An 8080A instruction core whose memory and I/O are callables from a host.

    ``read_byte(address)`` and ``write_byte(address, value)`` are the memory
    bus; ``read_port(port)`` and ``write_port(port, value)`` the I/O bus, which
    defaults to nothing connected: reads return 0xFF, writes are discarded.
    The core passes a 16-bit address and an 8-bit value on the memory bus, and
    the 8-bit port number on the I/O bus, so a flat host is two arguments::

        memory = bytearray(0x10000)
        cpu = I8080CPU(memory.__getitem__, memory.__setitem__)

    The four callables are ordinary attributes and may be replaced later (the
    debugger's access tracking does exactly that). A new CPU has every
    register 0, F = 0x02 (its fixed bits), INTE clear, and is not halted.
    """

    def __init__(
        self,
        read_byte: ReadByte,
        write_byte: WriteByte,
        *,
        read_port: ReadByte | None = None,
        write_port: WriteByte | None = None,
    ) -> None:
        if read_port is None:
            read_port = _undriven_port
        if write_port is None:
            write_port = _unconnected_port
        for name, bus in zip(_BUS, (read_byte, write_byte, read_port, write_port), strict=True):
            if not callable(bus):
                raise TypeError(f"{name} must be callable, not {type(bus).__name__}")
        self.read_byte = read_byte
        self.write_byte = write_byte
        self.read_port = read_port
        self.write_port = write_port
        super().__init__()

    def __init_subclass__(cls, **kwargs: object) -> None:
        # Until 0.2.0 a host subclassed I8080CPU and defined the bus as methods.
        # The instance attributes set in __init__ would silently shadow them, so
        # refuse the old form when the class is defined, naming the new one.
        super().__init_subclass__(**kwargs)
        legacy = [name for name in _BUS if name in cls.__dict__]
        if legacy:
            raise TypeError(
                f"{cls.__name__} defines {', '.join(legacy)} as methods; since 0.2.0 the "
                "bus is passed in: I8080CPU(read_byte, write_byte, *, read_port=None, "
                "write_port=None)"
            )

    def step(self) -> int:
        """Advance one instruction or lifecycle boundary and return its state count.

        In priority order: an asserted RESET is serviced (3 states); else a
        pending interrupt is accepted if INTE is set and no EI delay is running
        (the injected instruction's own count, 11 for RST n); else a halted CPU
        idles for :data:`HALT_IDLE_STATES`; else one instruction runs and returns
        the count from Intel's summary table [UM p. 4-15].
        """
        if self._reset_pending:
            return self._accept_reset()
        if self._can_accept_interrupt():
            states = self._accept_interrupt()
        elif self.halted:
            states = HALT_IDLE_STATES
        else:
            states = self.decode_and_execute()
        if self._ei_delay:
            self._ei_delay -= 1
        return states

    def capture_state(self) -> CPUState:
        """Return an immutable snapshot of all CPU-owned state, with no host access."""
        return CPUState(
            a=self.a,
            f=self.f.byte,
            b=self.b,
            c=self.c,
            d=self.d,
            e=self.e,
            h=self.h,
            l=self.l,
            sp=self.sp,
            pc=self.pc,
            inte=self.inte,
            halted=self.halted,
            ei_delay=self._ei_delay,
            reset_pending=self._reset_pending,
            interrupt_vector=self._pending_interrupt,
        )

    def restore_state(self, state: CPUState) -> None:
        """Restore a captured CPU state without touching the host."""
        if type(state) is not CPUState:
            raise TypeError("state must be a CPUState")
        self.a = state.a
        self.f.byte = state.f
        self.b = state.b
        self.c = state.c
        self.d = state.d
        self.e = state.e
        self.h = state.h
        self.l = state.l
        self.sp = state.sp
        self.pc = state.pc
        self.inte = state.inte
        self.halted = state.halted
        self._ei_delay = state.ei_delay
        self._reset_pending = state.reset_pending
        self._pending_interrupt = state.interrupt_vector

    @property
    def reset_pending(self) -> bool:
        """Whether the host holds RESET asserted."""
        return self._reset_pending

    def request_reset(self) -> None:
        """Assert RESET. Each step() services it until :meth:`clear_reset`."""
        self._reset_pending = True

    def clear_reset(self) -> None:
        """Release RESET."""
        self._reset_pending = False

    @property
    def interrupt_pending(self) -> bool:
        """Whether INT is asserted and not yet acknowledged."""
        return self._pending_interrupt is not None

    def request_interrupt(self, instruction_byte: int) -> None:
        """Assert INT with ``instruction_byte`` as the byte the device will supply.

        The request is level-held: it survives DI and the EI delay and is
        accepted at the first boundary where INTE permits, which is how the
        arcade boards hold INT until acknowledged. On acceptance the CPU executes
        the byte as an instruction without advancing PC [UM ch. 2]. Only
        one-byte instructions are supported (RST n is the one boards use); the
        8228's three-byte CALL injection is out of scope.
        """
        if type(instruction_byte) is not int or not 0 <= instruction_byte <= 0xFF:
            raise ValueError("instruction_byte must be an integer in range 0x00..0xFF")
        if instruction_length(instruction_byte) != 1:
            raise NotImplementedError(
                "only one-byte instructions can be supplied on interrupt acknowledge "
                f"(got 0x{instruction_byte:02X})"
            )
        self._pending_interrupt = instruction_byte

    def clear_interrupt(self) -> None:
        """Deassert INT before it has been acknowledged."""
        self._pending_interrupt = None
