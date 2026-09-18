"""CPU state, fetch, stack, register selection, and the lifecycle boundaries."""

from i8080_python._flags import Flags


class CoreMixin:
    """Private implementation of CPU state and core helpers."""

    def __init__(self) -> None:
        self.a = 0
        self.f = Flags()
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.sp = 0
        self.pc = 0
        self.inte = False
        self.halted = False
        self._ei_delay = 0
        self._reset_pending = False
        self._pending_interrupt: int | None = None

    def _fetch_byte(self) -> int:
        value = self.read_byte(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def _read_operand_word(self) -> int:
        # Operands are little-endian: low byte first [UM ch. 4].
        low = self._fetch_byte()
        high = self._fetch_byte()
        return (high << 8) | low

    def _push_word(self, value: int) -> None:
        # High byte to SP-1, then low byte to SP-2 [UM ch. 4, PUSH rp].
        self.sp = (self.sp - 1) & 0xFFFF
        self.write_byte(self.sp, (value >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self.write_byte(self.sp, value & 0xFF)

    def _pop_word(self) -> int:
        low = self.read_byte(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        high = self.read_byte(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        return (high << 8) | low

    def _hl(self) -> int:
        return (self.h << 8) | self.l

    def _bc(self) -> int:
        return (self.b << 8) | self.c

    def _de(self) -> int:
        return (self.d << 8) | self.e

    def _read_pair(self, index: int) -> int:
        """Read register pair RP: 0 = B (BC), 1 = D (DE), 2 = H (HL), 3 = SP."""
        if index == 0:
            return self._bc()
        if index == 1:
            return self._de()
        if index == 2:
            return self._hl()
        return self.sp

    def _write_pair(self, index: int, value: int) -> None:
        value &= 0xFFFF
        if index == 0:
            self.b = value >> 8
            self.c = value & 0xFF
        elif index == 1:
            self.d = value >> 8
            self.e = value & 0xFF
        elif index == 2:
            self.h = value >> 8
            self.l = value & 0xFF
        else:
            self.sp = value

    def _read_reg(self, index: int) -> int:
        """Read register DDD/SSS: B C D E H L M A, where 6 (M) is the byte at HL."""
        if index == 0:
            return self.b
        if index == 1:
            return self.c
        if index == 2:
            return self.d
        if index == 3:
            return self.e
        if index == 4:
            return self.h
        if index == 5:
            return self.l
        if index == 6:
            return self.read_byte(self._hl())
        return self.a

    def _write_reg(self, index: int, value: int) -> None:
        value &= 0xFF
        if index == 0:
            self.b = value
        elif index == 1:
            self.c = value
        elif index == 2:
            self.d = value
        elif index == 3:
            self.e = value
        elif index == 4:
            self.h = value
        elif index == 5:
            self.l = value
        elif index == 6:
            self.write_byte(self._hl(), value)
        else:
            self.a = value

    def _condition(self, code: int) -> bool:
        """Evaluate condition CCC: NZ Z NC C PO PE P M."""
        if code == 0:
            return self.f.z == 0
        if code == 1:
            return self.f.z == 1
        if code == 2:
            return self.f.cy == 0
        if code == 3:
            return self.f.cy == 1
        if code == 4:
            return self.f.p == 0  # PO: parity odd
        if code == 5:
            return self.f.p == 1  # PE: parity even
        if code == 6:
            return self.f.s == 0  # P: plus
        return self.f.s == 1  # M: minus

    def _can_accept_interrupt(self) -> bool:
        # INT is sampled at the end of each instruction and honoured only with
        # INTE set [UM ch. 2]; the EI delay holds it off for one instruction.
        return self.inte and self._ei_delay == 0 and self._pending_interrupt is not None

    def _accept_reset(self) -> int:
        """Apply RESET while the host holds it asserted.

        RESET clears PC, INTE, and the halt state and defines nothing else
        [UM ch. 2, "Start-up"], so every other register is left as it was. The
        3 states are the minimum RESET pulse the manual requires, a modeling
        choice: RESET is not an instruction and has no state count of its own.
        """
        self.pc = 0
        self.inte = False
        self.halted = False
        self._ei_delay = 0
        return 3

    def _accept_interrupt(self) -> int:
        """Execute the device-supplied instruction as an interrupt acknowledge.

        The acknowledge is an instruction-fetch cycle whose byte comes from the
        device, not memory, and PC is not incremented for it, so an RST pushes the
        address of the instruction that would have run next [UM ch. 2,
        "Interrupt Sequences"]. INTE is cleared on acceptance. A halted CPU leaves
        the halt state with PC already past the HLT [ALP, HLT]. The acknowledge
        costs exactly what the instruction costs: 11 states for RST n.
        """
        instruction = self._pending_interrupt
        self._pending_interrupt = None
        self.inte = False
        self.halted = False
        return self._execute(instruction)
