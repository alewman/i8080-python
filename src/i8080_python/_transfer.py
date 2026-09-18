"""Data transfer group [UM ch. 4]: MOV, MVI, LXI, LDA, STA, LHLD, SHLD, LDAX, STAX, XCHG.

No instruction in this group touches the flags.
"""


class TransferMixin:
    """Private data-transfer implementation."""

    def _op_mov(self, opcode: int) -> int:
        """MOV r1,r2 -- 01 DDD SSS; 5 states, or 7 when either side is M."""
        dest = (opcode >> 3) & 0x07
        src = opcode & 0x07
        self._write_reg(dest, self._read_reg(src))
        # MOV r1,r2 spends a fifth M1 state moving the byte; MOV r,M and MOV M,r
        # instead add a 3-state memory cycle to a 4-state M1. MOV M,M is HLT and
        # never reaches here.
        return 7 if src == 6 or dest == 6 else 5

    def _op_mvi(self, opcode: int) -> int:
        """MVI r,d8 -- 7 states; MVI M,d8 is 10."""
        value = self._fetch_byte()
        dest = (opcode >> 3) & 0x07
        self._write_reg(dest, value)
        return 10 if dest == 6 else 7

    def _op_lxi(self, opcode: int) -> int:
        """LXI rp,d16 -- load B, D, H, or SP with a 16-bit immediate."""
        self._write_pair((opcode >> 4) & 0x03, self._read_operand_word())
        return 10

    def _op_lda(self) -> int:
        """LDA a16"""
        self.a = self.read_byte(self._read_operand_word())
        return 13

    def _op_sta(self) -> int:
        """STA a16"""
        self.write_byte(self._read_operand_word(), self.a)
        return 13

    def _op_lhld(self) -> int:
        """LHLD a16 -- L from a16, then H from a16+1."""
        address = self._read_operand_word()
        self.l = self.read_byte(address)
        self.h = self.read_byte((address + 1) & 0xFFFF)
        return 16

    def _op_shld(self) -> int:
        """SHLD a16 -- L to a16, then H to a16+1."""
        address = self._read_operand_word()
        self.write_byte(address, self.l)
        self.write_byte((address + 1) & 0xFFFF, self.h)
        return 16

    def _op_ldax(self, opcode: int) -> int:
        """LDAX rp -- A from the byte at BC (0A) or DE (1A)."""
        self.a = self.read_byte(self._bc() if opcode == 0x0A else self._de())
        return 7

    def _op_stax(self, opcode: int) -> int:
        """STAX rp -- A to the byte at BC (02) or DE (12)."""
        self.write_byte(self._bc() if opcode == 0x02 else self._de(), self.a)
        return 7

    def _op_xchg(self) -> int:
        """XCHG -- swap HL and DE."""
        self.h, self.d = self.d, self.h
        self.l, self.e = self.e, self.l
        return 4
