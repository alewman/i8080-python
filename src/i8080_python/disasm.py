"""Side-effect-free structured disassembly of all 256 8080 opcodes, in Intel syntax.

Operands print as Intel's assembler writes them: registers by name (``M`` for
the byte at HL), pairs by their first register (``B``, ``D``, ``H``, ``SP``,
``PSW``), numbers in hex with an ``H`` suffix and a leading 0 when the first
digit is a letter (``0FFH``). The twelve undocumented bytes print as the
instruction they execute as, prefixed with ``*`` (``*NOP``, ``*JMP``,
``*RET``, ``*CALL``), so a listing shows where a program used one.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

ByteReader = Callable[[int], int]

_REGISTERS = ("B", "C", "D", "E", "H", "L", "M", "A")
_PAIRS = ("B", "D", "H", "SP")
_STACK_PAIRS = ("B", "D", "H", "PSW")
_CONDITIONS = ("NZ", "Z", "NC", "C", "PO", "PE", "P", "M")
_ALU_REGISTER = ("ADD", "ADC", "SUB", "SBB", "ANA", "XRA", "ORA", "CMP")
_ALU_IMMEDIATE = ("ADI", "ACI", "SUI", "SBI", "ANI", "XRI", "ORI", "CPI")
_ACCUMULATOR_OPS = ("RLC", "RRC", "RAL", "RAR", "DAA", "CMA", "STC", "CMC")


@dataclass(frozen=True, slots=True)
class Instruction:
    """One decoded instruction and the exact bytes consumed from memory."""

    address: int
    data: bytes
    mnemonic: str
    operands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.address) is not int or not 0 <= self.address <= 0xFFFF:
            raise ValueError("address must be an integer in range 0x0000..0xFFFF")
        if type(self.data) is not bytes or not self.data:
            raise ValueError("data must contain at least one byte")
        if type(self.mnemonic) is not str or not self.mnemonic:
            raise ValueError("mnemonic must not be empty")
        if type(self.operands) is not tuple or not all(
            type(operand) is str for operand in self.operands
        ):
            raise ValueError("operands must be a tuple of strings")

    @property
    def size(self) -> int:
        """Number of encoded bytes consumed by this instruction."""
        return len(self.data)

    @property
    def next_address(self) -> int:
        """16-bit address immediately following the encoded instruction."""
        return (self.address + self.size) & 0xFFFF

    @property
    def text(self) -> str:
        """Canonical human-readable assembly text, e.g. ``MVI A,2AH``."""
        return self.mnemonic if not self.operands else f"{self.mnemonic} {','.join(self.operands)}"


def _hex(value: int, digits: int) -> str:
    text = f"{value:0{digits}X}"
    return f"0{text}H" if text[0] in "ABCDEF" else f"{text}H"


def instruction_length(opcode: int) -> int:
    """Return how many bytes the instruction starting with ``opcode`` occupies (1, 2, or 3)."""
    x, y, z = opcode >> 6, (opcode >> 3) & 0x07, opcode & 0x07
    if x in (1, 2):  # MOV and the register ALU block
        return 1
    if x == 0:
        if z == 1 and y % 2 == 0:  # LXI
            return 3
        if opcode in (0x22, 0x2A, 0x32, 0x3A):  # SHLD LHLD STA LDA
            return 3
        return 2 if z == 6 else 1  # MVI
    if z in (2, 4) or opcode in (0xC3, 0xCB, 0xCD, 0xDD, 0xED, 0xFD):  # jumps and calls
        return 3
    if z == 6 or opcode in (0xD3, 0xDB):  # immediate ALU, OUT, IN
        return 2
    return 1


def _decode(opcode: int, operand: int) -> tuple[str, tuple[str, ...]]:
    """Return (mnemonic, operands) for ``opcode`` whose operand bytes form ``operand``."""
    x, y, z = opcode >> 6, (opcode >> 3) & 0x07, opcode & 0x07
    byte, word = _hex(operand & 0xFF, 2), _hex(operand, 4)

    if x == 1:
        if opcode == 0x76:
            return "HLT", ()
        return "MOV", (_REGISTERS[y], _REGISTERS[z])
    if x == 2:
        return _ALU_REGISTER[y], (_REGISTERS[z],)

    if x == 0:
        pair = _PAIRS[y >> 1]
        if z == 0:
            return ("NOP", ()) if y == 0 else ("*NOP", ())
        if z == 1:
            return ("DAD", (pair,)) if y & 1 else ("LXI", (pair, word))
        if z == 2:
            return {
                0x02: ("STAX", ("B",)),
                0x0A: ("LDAX", ("B",)),
                0x12: ("STAX", ("D",)),
                0x1A: ("LDAX", ("D",)),
                0x22: ("SHLD", (word,)),
                0x2A: ("LHLD", (word,)),
                0x32: ("STA", (word,)),
                0x3A: ("LDA", (word,)),
            }[opcode]
        if z == 3:
            return ("DCX" if y & 1 else "INX"), (pair,)
        if z == 4:
            return "INR", (_REGISTERS[y],)
        if z == 5:
            return "DCR", (_REGISTERS[y],)
        if z == 6:
            return "MVI", (_REGISTERS[y], byte)
        return _ACCUMULATOR_OPS[y], ()

    # x == 3
    if z == 0:
        return f"R{_CONDITIONS[y]}", ()
    if z == 1:
        if y & 1 == 0:
            return "POP", (_STACK_PAIRS[y >> 1],)
        return {0xC9: ("RET", ()), 0xD9: ("*RET", ()), 0xE9: ("PCHL", ()), 0xF9: ("SPHL", ())}[
            opcode
        ]
    if z == 2:
        return f"J{_CONDITIONS[y]}", (word,)
    if z == 3:
        return {
            0xC3: ("JMP", (word,)),
            0xCB: ("*JMP", (word,)),
            0xD3: ("OUT", (byte,)),
            0xDB: ("IN", (byte,)),
            0xE3: ("XTHL", ()),
            0xEB: ("XCHG", ()),
            0xF3: ("DI", ()),
            0xFB: ("EI", ()),
        }[opcode]
    if z == 4:
        return f"C{_CONDITIONS[y]}", (word,)
    if z == 5:
        if y & 1 == 0:
            return "PUSH", (_STACK_PAIRS[y >> 1],)
        return ("CALL" if opcode == 0xCD else "*CALL"), (word,)
    if z == 6:
        return _ALU_IMMEDIATE[y], (byte,)
    return "RST", (str(y),)


def disassemble(reader: ByteReader, address: int = 0) -> Instruction:
    """Decode the instruction at ``address``, reading bytes only through ``reader``.

    ``reader`` must be side-effect free (a memory peek, not a bus read); the
    disassembler calls it once per byte the instruction occupies.
    """
    if type(address) is not int or not 0 <= address <= 0xFFFF:
        raise ValueError("address must be an integer in range 0x0000..0xFFFF")
    data = bytearray()
    size = 1
    while len(data) < size:
        target = (address + len(data)) & 0xFFFF
        value = reader(target)
        if type(value) is not int or not 0 <= value <= 0xFF:
            raise ValueError(f"byte reader returned a non-byte value at 0x{target:04X}")
        data.append(value)
        size = instruction_length(data[0])
    operand = int.from_bytes(data[1:], "little")
    mnemonic, operands = _decode(data[0], operand)
    return Instruction(address, bytes(data), mnemonic, operands)


def disassemble_bytes(data: Sequence[int], address: int = 0) -> Instruction:
    """Decode one instruction from the start of ``data``, as if it were at ``address``."""

    def reader(target: int) -> int:
        offset = (target - address) & 0xFFFF
        if offset >= len(data):
            raise ValueError("data ends inside the instruction")
        return data[offset]

    return disassemble(reader, address)


__all__ = ["ByteReader", "Instruction", "disassemble", "disassemble_bytes", "instruction_length"]
