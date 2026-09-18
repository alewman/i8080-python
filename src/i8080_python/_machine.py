"""Stack, I/O, and machine control group [UM ch. 4]: PUSH POP XTHL SPHL IN OUT EI DI HLT NOP."""


class MachineMixin:
    """Private stack, port, and machine-control implementation."""

    def _op_push(self, opcode: int) -> int:
        """PUSH rp -- B, D, H, or PSW (A, then the flag byte with its fixed bits)."""
        pair = (opcode >> 4) & 0x03
        if pair == 3:
            self._push_word((self.a << 8) | self.f.byte)
        else:
            self._push_word(self._read_pair(pair))
        return 11

    def _op_pop(self, opcode: int) -> int:
        """POP rp -- B, D, H, or PSW; POP PSW forces bits 5 and 3 to 0 and bit 1 to 1."""
        pair = (opcode >> 4) & 0x03
        value = self._pop_word()
        if pair == 3:
            self.a = value >> 8
            self.f.byte = value & 0xFF  # Flags strips the filler bits [ALP 1-14].
        else:
            self._write_pair(pair, value)
        return 10

    def _op_xthl(self) -> int:
        """XTHL -- swap HL with the word at SP."""
        low = self.read_byte(self.sp)
        high = self.read_byte((self.sp + 1) & 0xFFFF)
        # The two stack writes run high byte first, (SP+1) then (SP), the reverse
        # of the reads. No 8080 oracle observes bus order; this is the order the
        # Z80's hardware-generated pin traces certify for EX (SP),HL in z80-python.
        self.write_byte((self.sp + 1) & 0xFFFF, self.h)
        self.write_byte(self.sp, self.l)
        self.h = high
        self.l = low
        return 18

    def _op_sphl(self) -> int:
        """SPHL -- SP = HL."""
        self.sp = self._hl()
        return 5

    def _op_in(self) -> int:
        """IN p8 -- A from port p8."""
        # The chip drives the port number on both halves of the address bus
        # [ALP 1-14]; the 8080 has 256 ports, so the host is given the number.
        self.a = self.read_port(self._fetch_byte())
        return 10

    def _op_out(self) -> int:
        """OUT p8 -- A to port p8."""
        self.write_port(self._fetch_byte(), self.a)
        return 10

    def _op_ei(self) -> int:
        """EI -- set INTE; no interrupt is accepted until the next instruction completes.

        "The interrupt system is enabled following the execution of the next
        instruction" [UM ch. 4, EI]. The delay counts this EI and the one
        instruction after it; step() counts it down after every boundary, so a
        run of EIs keeps holding interrupts off, as MAME's ``m_after_ei`` does.
        """
        self.inte = True
        self._ei_delay = 2
        return 4

    def _op_di(self) -> int:
        """DI -- clear INTE, effective immediately."""
        self.inte = False
        self._ei_delay = 0
        return 4

    def _op_hlt(self) -> int:
        """HLT -- 76, the byte MOV M,M would have; enter the halt state with PC past the HLT.

        Only RESET, or INT while INTE is set, leaves the halt state [UM ch. 2,
        "Halt Sequences"; ALP, HLT].
        """
        self.halted = True
        return 7

    def _op_nop(self) -> int:
        """NOP -- also 08 10 18 20 28 30 38, the undocumented aliases (undocumented-behavior.md)."""
        return 4
