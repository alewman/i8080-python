"""Opcode dispatch: one explicit if-chain over all 256 byte values.

The chain is ordered as the 8080's decoder splits an opcode, ``xx yyy zzz``:
the MOV block (x = 01), the ALU block (x = 10), then everything else. Every
byte value reaches a handler; the twelve undocumented ones reach the handler of
the documented instruction they alias (docs/undocumented-behavior.md).
"""


class DispatchMixin:
    """Private instruction fetch and dispatch implementation."""

    def decode_and_execute(self) -> int:
        """Fetch one opcode at PC, execute it, and return its state count."""
        return self._execute(self._fetch_byte())

    def _execute(self, opcode: int) -> int:
        # 01 DDD SSS: MOV, except that MOV M,M is HLT.
        if opcode == 0x76:
            return self._op_hlt()
        if 0x40 <= opcode <= 0x7F:
            return self._op_mov(opcode)

        # 10 ALU SSS: the eight accumulator operations on a register or M.
        if 0x80 <= opcode <= 0x87:
            return self._op_add(opcode)
        if 0x88 <= opcode <= 0x8F:
            return self._op_adc(opcode)
        if 0x90 <= opcode <= 0x97:
            return self._op_sub(opcode)
        if 0x98 <= opcode <= 0x9F:
            return self._op_sbb(opcode)
        if 0xA0 <= opcode <= 0xA7:
            return self._op_ana(opcode)
        if 0xA8 <= opcode <= 0xAF:
            return self._op_xra(opcode)
        if 0xB0 <= opcode <= 0xB7:
            return self._op_ora(opcode)
        if 0xB8 <= opcode <= 0xBF:
            return self._op_cmp(opcode)

        # 00 yyy zzz
        if opcode in (0x00, 0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38):
            return self._op_nop()
        if opcode in (0x01, 0x11, 0x21, 0x31):
            return self._op_lxi(opcode)
        if opcode in (0x09, 0x19, 0x29, 0x39):
            return self._op_dad(opcode)
        if opcode in (0x02, 0x12):
            return self._op_stax(opcode)
        if opcode in (0x0A, 0x1A):
            return self._op_ldax(opcode)
        if opcode == 0x22:
            return self._op_shld()
        if opcode == 0x2A:
            return self._op_lhld()
        if opcode == 0x32:
            return self._op_sta()
        if opcode == 0x3A:
            return self._op_lda()
        if opcode in (0x03, 0x13, 0x23, 0x33):
            return self._op_inx(opcode)
        if opcode in (0x0B, 0x1B, 0x2B, 0x3B):
            return self._op_dcx(opcode)
        if opcode in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C):
            return self._op_inr(opcode)
        if opcode in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
            return self._op_dcr(opcode)
        if opcode in (0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E):
            return self._op_mvi(opcode)
        if opcode == 0x07:
            return self._op_rlc()
        if opcode == 0x0F:
            return self._op_rrc()
        if opcode == 0x17:
            return self._op_ral()
        if opcode == 0x1F:
            return self._op_rar()
        if opcode == 0x27:
            return self._op_daa()
        if opcode == 0x2F:
            return self._op_cma()
        if opcode == 0x37:
            return self._op_stc()
        if opcode == 0x3F:
            return self._op_cmc()

        # 11 yyy zzz
        if opcode in (0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8):
            return self._op_rcc(opcode)
        if opcode in (0xC1, 0xD1, 0xE1, 0xF1):
            return self._op_pop(opcode)
        if opcode in (0xC9, 0xD9):
            return self._op_ret()
        if opcode == 0xE9:
            return self._op_pchl()
        if opcode == 0xF9:
            return self._op_sphl()
        if opcode in (0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA):
            return self._op_jcc(opcode)
        if opcode in (0xC3, 0xCB):
            return self._op_jmp()
        if opcode == 0xD3:
            return self._op_out()
        if opcode == 0xDB:
            return self._op_in()
        if opcode == 0xE3:
            return self._op_xthl()
        if opcode == 0xEB:
            return self._op_xchg()
        if opcode == 0xF3:
            return self._op_di()
        if opcode == 0xFB:
            return self._op_ei()
        if opcode in (0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC):
            return self._op_ccc(opcode)
        if opcode in (0xC5, 0xD5, 0xE5, 0xF5):
            return self._op_push(opcode)
        if opcode in (0xCD, 0xDD, 0xED, 0xFD):
            return self._op_call()
        if opcode == 0xC6:
            return self._op_adi()
        if opcode == 0xCE:
            return self._op_aci()
        if opcode == 0xD6:
            return self._op_sui()
        if opcode == 0xDE:
            return self._op_sbi()
        if opcode == 0xE6:
            return self._op_ani()
        if opcode == 0xEE:
            return self._op_xri()
        if opcode == 0xF6:
            return self._op_ori()
        if opcode == 0xFE:
            return self._op_cpi()
        # 11 NNN 111 is all that is left.
        return self._op_rst(opcode)
