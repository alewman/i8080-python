"""Branch group [UM ch. 4]: JMP, Jcc, CALL, Ccc, RET, Rcc, RST, PCHL.

Conditions are CCC = NZ Z NC C PO PE P M. The 8080's costs differ from the
8085's: Jcc is 10 whether or not it jumps, and Ccc/Rcc not taken are 11/5
because the first machine cycle has already spent a fifth state before the
condition is evaluated (docs/timing.md).
"""


class BranchMixin:
    """Private jump, call, return, and restart implementation."""

    def _op_jmp(self) -> int:
        """JMP a16 -- also byte CB, an undocumented alias (docs/undocumented-behavior.md)."""
        self.pc = self._read_operand_word()
        return 10

    def _op_jcc(self, opcode: int) -> int:
        """JNZ/JZ/JNC/JC/JPO/JPE/JP/JM a16 -- 11 CCC 010; 10 states taken or not."""
        target = self._read_operand_word()
        if self._condition((opcode >> 3) & 0x07):
            self.pc = target
        return 10

    def _op_call(self) -> int:
        """CALL a16 -- push the next address and jump; also DD, ED, FD (undocumented aliases)."""
        target = self._read_operand_word()
        self._push_word(self.pc)
        self.pc = target
        return 17

    def _op_ccc(self, opcode: int) -> int:
        """CNZ/CZ/CNC/CC/CPO/CPE/CP/CM a16 -- 11 CCC 100; 17 states taken, 11 not."""
        target = self._read_operand_word()
        if not self._condition((opcode >> 3) & 0x07):
            return 11
        self._push_word(self.pc)
        self.pc = target
        return 17

    def _op_ret(self) -> int:
        """RET -- also byte D9, an undocumented alias (docs/undocumented-behavior.md)."""
        self.pc = self._pop_word()
        return 10

    def _op_rcc(self, opcode: int) -> int:
        """RNZ/RZ/RNC/RC/RPO/RPE/RP/RM -- 11 CCC 000; 11 states taken, 5 not."""
        if not self._condition((opcode >> 3) & 0x07):
            return 5
        self.pc = self._pop_word()
        return 11

    def _op_rst(self, opcode: int) -> int:
        """RST n -- 11 NNN 111; push PC and jump to 8 * NNN."""
        self._push_word(self.pc)
        self.pc = opcode & 0x38
        return 11

    def _op_pchl(self) -> int:
        """PCHL -- PC = HL."""
        self.pc = self._hl()
        return 5
