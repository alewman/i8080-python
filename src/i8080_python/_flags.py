"""The 8080 flag byte (the low byte of the PSW) and its bit masks.

    bit:   7   6   5   4   3   2   1   0
    flag:  S   Z   0   AC  0   P   1   CY

Bits 5 and 3 always read 0 and bit 1 always reads 1 [ALP 1-14]; the
hardware-captured 8080EXM CRCs were taken with an all-ones flag mask, so real
8080As produce exactly these values (docs/undocumented-behavior.md).
"""

FLAG_S = 0b1000_0000
FLAG_Z = 0b0100_0000
FLAG_AC = 0b0001_0000
FLAG_P = 0b0000_0100
FLAG_CY = 0b0000_0001

#: The five real flags. Everything outside this mask is fixed.
FLAG_MASK = FLAG_S | FLAG_Z | FLAG_AC | FLAG_P | FLAG_CY
#: Bit 1 is wired to 1; bits 5 and 3 are wired to 0.
FIXED_ONES = 0b0000_0010


def _szp(value: int) -> int:
    bits_set = bin(value).count("1")
    return (
        (value & FLAG_S)
        | (FLAG_Z if value == 0 else 0)
        | (FLAG_P if bits_set % 2 == 0 else 0)  # P = 1 for even parity [ALP 1-11]
    )


#: S, Z, and P for every 8-bit result, the three flags every ALU result sets
#: the same way. A table, not a loop, because the ALU consults it on nearly
#: every instruction.
SZP_FLAGS = bytes(_szp(value) for value in range(256))


class Flags:
    """The 8080 F register: five flags and three bits that cannot change.

    Every write, whole-byte or single-flag, leaves bits 5 and 3 clear and bit 1
    set, which is what ``POP PSW`` does on the chip ("strips out these filler
    bits" [ALP 1-14]).
    """

    __slots__ = ("_byte",)

    def __init__(self, value: int = FIXED_ONES) -> None:
        self._byte = (value & FLAG_MASK) | FIXED_ONES

    def __int__(self) -> int:
        return self._byte

    def __repr__(self) -> str:
        return f"Flags(0x{self._byte:02X})"

    @property
    def byte(self) -> int:
        return self._byte

    @byte.setter
    def byte(self, value: int) -> None:
        self._byte = (value & FLAG_MASK) | FIXED_ONES

    @property
    def s(self) -> int:
        return (self._byte >> 7) & 1

    @s.setter
    def s(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_S) | ((value & 1) << 7)

    @property
    def z(self) -> int:
        return (self._byte >> 6) & 1

    @z.setter
    def z(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_Z) | ((value & 1) << 6)

    @property
    def ac(self) -> int:
        return (self._byte >> 4) & 1

    @ac.setter
    def ac(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_AC) | ((value & 1) << 4)

    @property
    def p(self) -> int:
        return (self._byte >> 2) & 1

    @p.setter
    def p(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_P) | ((value & 1) << 2)

    @property
    def cy(self) -> int:
        return self._byte & 1

    @cy.setter
    def cy(self, value: int) -> None:
        self._byte = (self._byte & ~FLAG_CY) | (value & 1)

    def set_szp(self, value: int) -> None:
        """Set S, Z, and P from an 8-bit result, leaving AC and CY alone."""
        self._byte = (self._byte & (FLAG_AC | FLAG_CY)) | SZP_FLAGS[value] | FIXED_ONES
