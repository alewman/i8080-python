"""Logical group [UM ch. 4]: ANA XRA ORA CMP and their immediates, RLC RRC RAL RAR, CMA CMC STC."""


class LogicalMixin:
    """Private logical, compare, rotate, and carry implementation."""

    def _and_with_a(self, value: int) -> None:
        result = self.a & value
        self.f.cy = 0
        # AC is the OR of bit 3 of the two operands [ALP 1-12]. AMD's 9080A
        # clears it instead, and fails the hardware CRC the Intel chips produce
        # (docs/undocumented-behavior.md); this core models Intel.
        self.f.ac = ((self.a | value) >> 3) & 1
        self.f.set_szp(result)
        self.a = result

    def _xor_with_a(self, value: int) -> None:
        self.a ^= value
        self.f.cy = 0
        self.f.ac = 0
        self.f.set_szp(self.a)

    def _or_with_a(self, value: int) -> None:
        self.a |= value
        self.f.cy = 0
        self.f.ac = 0
        self.f.set_szp(self.a)

    def _op_ana(self, opcode: int) -> int:
        """ANA r -- A = A & r; CY = 0, AC = bit 3 of A | bit 3 of r. 4 states, ANA M 7."""
        value, states = self._register_operand(opcode)
        self._and_with_a(value)
        return states

    def _op_xra(self, opcode: int) -> int:
        """XRA r -- A = A ^ r; CY = AC = 0. 4 states, XRA M 7."""
        value, states = self._register_operand(opcode)
        self._xor_with_a(value)
        return states

    def _op_ora(self, opcode: int) -> int:
        """ORA r -- A = A | r; CY = AC = 0. 4 states, ORA M 7."""
        value, states = self._register_operand(opcode)
        self._or_with_a(value)
        return states

    def _op_cmp(self, opcode: int) -> int:
        """CMP r -- flags of A - r, result discarded. 4 states, CMP M 7."""
        value, states = self._register_operand(opcode)
        self._subtract(value, 0)
        return states

    def _op_ani(self) -> int:
        """ANI d8"""
        self._and_with_a(self._fetch_byte())
        return 7

    def _op_xri(self) -> int:
        """XRI d8"""
        self._xor_with_a(self._fetch_byte())
        return 7

    def _op_ori(self) -> int:
        """ORI d8"""
        self._or_with_a(self._fetch_byte())
        return 7

    def _op_cpi(self) -> int:
        """CPI d8"""
        self._subtract(self._fetch_byte(), 0)
        return 7

    def _op_rlc(self) -> int:
        """RLC -- rotate A left; bit 7 goes to both bit 0 and CY."""
        bit7 = self.a >> 7
        self.a = ((self.a << 1) | bit7) & 0xFF
        self.f.cy = bit7
        return 4

    def _op_rrc(self) -> int:
        """RRC -- rotate A right; bit 0 goes to both bit 7 and CY."""
        bit0 = self.a & 1
        self.a = (self.a >> 1) | (bit0 << 7)
        self.f.cy = bit0
        return 4

    def _op_ral(self) -> int:
        """RAL -- rotate A left through CY."""
        bit7 = self.a >> 7
        self.a = ((self.a << 1) | self.f.cy) & 0xFF
        self.f.cy = bit7
        return 4

    def _op_rar(self) -> int:
        """RAR -- rotate A right through CY."""
        bit0 = self.a & 1
        self.a = (self.a >> 1) | (self.f.cy << 7)
        self.f.cy = bit0
        return 4

    def _op_cma(self) -> int:
        """CMA -- A = ~A; no flags."""
        self.a ^= 0xFF
        return 4

    def _op_cmc(self) -> int:
        """CMC -- complement CY."""
        self.f.cy ^= 1
        return 4

    def _op_stc(self) -> int:
        """STC -- set CY."""
        self.f.cy = 1
        return 4
