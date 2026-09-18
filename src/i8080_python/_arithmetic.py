"""Arithmetic group [UM ch. 4]: ADD ADC SUB SBB and their immediates, INR DCR INX DCX DAD DAA.

The auxiliary-carry rules are the ones the hardware-captured 8080EXM CRCs pin
down (docs/undocumented-behavior.md). The one a Z80 programmer gets wrong: in
the subtract family AC is set when there is *no* borrow from bit 4, because the
8080 ALU subtracts by adding the complement and AC is that addition's carry
out of bit 3.
"""


class ArithmeticMixin:
    """Private arithmetic implementation."""

    def _add_to_a(self, value: int, carry_in: int) -> None:
        total = self.a + value + carry_in
        result = total & 0xFF
        self.f.cy = total >> 8
        # Carry out of bit 3: bit 4 of the sum differs from bit 4 of the addends'
        # XOR exactly when a carry came in from below [ALP 1-11].
        self.f.ac = ((self.a ^ value ^ result) >> 4) & 1
        self.f.set_szp(result)
        self.a = result

    def _subtract(self, value: int, borrow_in: int) -> int:
        """Compute A - value - borrow_in, set all five flags, and return the result.

        CY is the borrow. AC is the carry out of bit 3 of A + ~value + !borrow_in,
        which is the inverse of a borrow into bit 4.
        """
        total = self.a - value - borrow_in
        result = total & 0xFF
        self.f.cy = 1 if total < 0 else 0
        self.f.ac = (((self.a ^ value ^ result) >> 4) & 1) ^ 1
        self.f.set_szp(result)
        return result

    def _register_operand(self, opcode: int) -> tuple[int, int]:
        """Return (value, states) for the SSS operand of an ALU instruction: 4, or 7 for M."""
        src = opcode & 0x07
        return self._read_reg(src), (7 if src == 6 else 4)

    def _op_add(self, opcode: int) -> int:
        """ADD r -- A = A + r; all five flags. 4 states, ADD M 7."""
        value, states = self._register_operand(opcode)
        self._add_to_a(value, 0)
        return states

    def _op_adc(self, opcode: int) -> int:
        """ADC r -- A = A + r + CY; all five flags. 4 states, ADC M 7."""
        value, states = self._register_operand(opcode)
        self._add_to_a(value, self.f.cy)
        return states

    def _op_sub(self, opcode: int) -> int:
        """SUB r -- A = A - r; all five flags, CY = borrow. 4 states, SUB M 7."""
        value, states = self._register_operand(opcode)
        self.a = self._subtract(value, 0)
        return states

    def _op_sbb(self, opcode: int) -> int:
        """SBB r -- A = A - r - CY; all five flags, CY = borrow. 4 states, SBB M 7."""
        value, states = self._register_operand(opcode)
        self.a = self._subtract(value, self.f.cy)
        return states

    def _op_adi(self) -> int:
        """ADI d8"""
        self._add_to_a(self._fetch_byte(), 0)
        return 7

    def _op_aci(self) -> int:
        """ACI d8"""
        self._add_to_a(self._fetch_byte(), self.f.cy)
        return 7

    def _op_sui(self) -> int:
        """SUI d8"""
        self.a = self._subtract(self._fetch_byte(), 0)
        return 7

    def _op_sbi(self) -> int:
        """SBI d8"""
        self.a = self._subtract(self._fetch_byte(), self.f.cy)
        return 7

    def _op_inr(self, opcode: int) -> int:
        """INR r -- r + 1; S Z P AC, CY untouched. 5 states, INR M 10."""
        reg = (opcode >> 3) & 0x07
        result = (self._read_reg(reg) + 1) & 0xFF
        self._write_reg(reg, result)
        # Carry out of bit 3 happens exactly when the low nibble wraps to 0.
        self.f.ac = 1 if (result & 0x0F) == 0 else 0
        self.f.set_szp(result)
        return 10 if reg == 6 else 5

    def _op_dcr(self, opcode: int) -> int:
        """DCR r -- r - 1; S Z P AC, CY untouched. 5 states, DCR M 10."""
        reg = (opcode >> 3) & 0x07
        result = (self._read_reg(reg) - 1) & 0xFF
        self._write_reg(reg, result)
        # Subtract-family polarity: AC is set unless the low nibble borrowed,
        # i.e. unless it wrapped to 0xF.
        self.f.ac = 0 if (result & 0x0F) == 0x0F else 1
        self.f.set_szp(result)
        return 10 if reg == 6 else 5

    def _op_inx(self, opcode: int) -> int:
        """INX rp -- 16-bit increment; no flags."""
        pair = (opcode >> 4) & 0x03
        self._write_pair(pair, self._read_pair(pair) + 1)
        return 5

    def _op_dcx(self, opcode: int) -> int:
        """DCX rp -- 16-bit decrement; no flags."""
        pair = (opcode >> 4) & 0x03
        self._write_pair(pair, self._read_pair(pair) - 1)
        return 5

    def _op_dad(self, opcode: int) -> int:
        """DAD rp -- HL = HL + rp; CY only."""
        total = self._hl() + self._read_pair((opcode >> 4) & 0x03)
        self.f.cy = total >> 16
        self._write_pair(2, total)
        return 10

    def _op_daa(self) -> int:
        """DAA -- decimal-adjust A after a BCD addition [ALP ch. 3, DAA].

        Add 6 if the low nibble is above 9 or AC is set; add 0x60 if A is above
        0x99 or CY is set. CY is then set if the high correction applied and is
        never cleared. AC is the carry out of bit 3 of the correction. There is
        no N flag, so there is no subtraction mode. This formulation reproduces
        the hardware CRC over all 65,536 A/F inputs (docs/undocumented-behavior.md).
        """
        correction = 0
        carry = self.f.cy
        if (self.a & 0x0F) > 9 or self.f.ac:
            correction |= 0x06
        if self.a > 0x99 or carry:
            correction |= 0x60
            carry = 1
        result = (self.a + correction) & 0xFF
        self.f.ac = ((self.a ^ correction ^ result) >> 4) & 1
        self.f.cy = carry
        self.f.set_szp(result)
        self.a = result
        return 4
