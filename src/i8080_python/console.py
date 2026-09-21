"""Portable command debugger: a thin text frontend over :class:`DebugSession`.

``CommandDebugger.execute(line)`` runs one command and returns printable lines;
``interact(input, output)`` is a line-oriented loop with no terminal
dependencies. ``python -m i8080_python`` starts one on a binary or a ROM set.
The command set matches m6800-python's and z80-python's, with 8080 registers
and the one interrupt input.
"""

import shlex
from dataclasses import dataclass
from typing import TextIO

from i8080_python.debug import DebugSession, RunResult, StepRecord, StopReason
from i8080_python.disasm import ByteReader, Instruction, disassemble
from i8080_python.state import CPUState


class CommandError(ValueError):
    """A malformed or unsupported debugger command."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Rendered lines and whether the loop should end."""

    lines: tuple[str, ...] = ()
    quit: bool = False


_HELP = (
    "help | ?                     Show this command summary",
    "registers | regs | r         Show registers, flags and lifecycle state",
    "step [COUNT] | s             Execute one or more boundaries (ignores breakpoints)",
    "over | o                     Step, running a CALL or RST through to its return",
    "run STEPS [STATES]           Run with finite step and optional timing limits",
    "continue | c                 Run up to 1,000,000 steps, off a breakpoint if on one",
    "break ADDRESS | b            Add an execute breakpoint",
    "delete ADDRESS               Remove an execute breakpoint",
    "breakpoints                  List breakpoints and watchpoints",
    "watch ADDRESS [r|w|rw]       Stop after a step that touches the byte at ADDRESS",
    "unwatch ADDRESS              Remove a watchpoint",
    "disassemble [ADDRESS] [COUNT] | d  Decode instructions without side effects",
    "memory ADDRESS [LENGTH] | m  Display up to 256 bytes",
    "history [COUNT]              Show retained step records",
    "set REGISTER VALUE           Set A F B C D E H L PSW B16 D16 H16 SP PC",
    "int BYTE | int off           Assert INT with the byte a device supplies, or drop it",
    "reset                        Pulse RESET for one step",
    "quit | exit | q              Leave the command loop",
    "Numbers are decimal; 0x1234 or $1234 is hexadecimal.",
)

#: Registers ``set`` accepts, with their widths. ``PSW`` is A and F together,
#: as ``PUSH PSW`` stacks them; ``B16``/``D16``/``H16`` are the pairs.
_REGISTERS = {
    "A": 0xFF,
    "F": 0xFF,
    "B": 0xFF,
    "C": 0xFF,
    "D": 0xFF,
    "E": 0xFF,
    "H": 0xFF,
    "L": 0xFF,
    "PSW": 0xFFFF,
    "B16": 0xFFFF,
    "D16": 0xFFFF,
    "H16": 0xFFFF,
    "SP": 0xFFFF,
    "PC": 0xFFFF,
}
_PAIRS = {"PSW": ("a", "f"), "B16": ("b", "c"), "D16": ("d", "e"), "H16": ("h", "l")}

#: What ``over`` runs through to its return: every form that pushes a return
#: address. ``*CALL`` is the undocumented DD/ED/FD alias.
_CALLS = frozenset(
    "CALL *CALL CNZ CZ CNC CC CPO CPE CP CM RST".split()  # noqa: SIM905 - a table reads better
)


def _number(text: str, name: str, *, maximum: int | None = None) -> int:
    try:
        value = int(text[1:], 16) if text.startswith("$") else int(text, 0)
    except ValueError as exc:
        raise CommandError(f"{name} must be an integer") from exc
    if value < 0 or (maximum is not None and value > maximum):
        suffix = f" in range 0..{maximum}" if maximum is not None else " non-negative"
        raise CommandError(f"{name} must be{suffix}")
    return value


def parse_number(text: str, name: str = "value", *, maximum: int | None = None) -> int:
    """Parse a debugger number: decimal, or hexadecimal written ``0x1234`` or ``$1234``."""
    return _number(text, name, maximum=maximum)


def _positive(text: str, name: str, *, maximum: int | None = None) -> int:
    value = _number(text, name, maximum=maximum)
    if value == 0:
        raise CommandError(f"{name} must be positive")
    return value


def format_flags(f: int) -> str:
    """F as ``S Z 0 AC 0 P 1 CY``, a letter for each bit set; the fixed bits print as 0 and 1."""
    labels = ("S", "Z", "0", "A", "0", "P", "1", "C")
    return "".join(label if f & (0x80 >> index) else "-" for index, label in enumerate(labels))


def format_state(state: CPUState) -> tuple[str, ...]:
    """The registers and lifecycle state, two lines."""
    vector = state.interrupt_vector
    return (
        f"A={state.a:02X} F={state.f:02X} {format_flags(state.f)} "
        f"B={state.b:02X}{state.c:02X} D={state.d:02X}{state.e:02X} "
        f"H={state.h:02X}{state.l:02X} SP={state.sp:04X} PC={state.pc:04X}",
        f"INTE={int(state.inte)} INT={'--' if vector is None else f'{vector:02X}'} "
        f"EI_DELAY={state.ei_delay} HALT={int(state.halted)} "
        f"RESET={int(state.reset_pending)}",
    )


def format_instruction(instruction: Instruction) -> str:
    encoded = " ".join(f"{value:02X}" for value in instruction.data)
    return f"{instruction.address:04X}  {encoded:<9} {instruction.text}"


def format_record(record: StepRecord) -> str:
    if record.instruction is not None:
        work = format_instruction(record.instruction)
    else:
        work = f"{record.before.pc:04X}  <{record.kind.value}>"
    return f"#{record.sequence} {work:<34} -> PC={record.after.pc:04X} +{record.states}"


def format_run(result: RunResult) -> tuple[str, ...]:
    lines = [
        f"stopped: {result.reason.value}, {result.steps} steps, {result.instructions} "
        f"instructions, {result.states} states, PC={result.state.pc:04X}"
    ]
    if result.reason is StopReason.WATCHPOINT:
        lines += [f"  {kind} {address:04X} = {value:02X}" for kind, address, value in result.hits]
    return tuple(lines)


class CommandDebugger:
    """Parse and execute debugger commands against a :class:`DebugSession`."""

    def __init__(self, session: DebugSession) -> None:
        if type(session) is not DebugSession:
            raise TypeError("session must be a DebugSession")
        self.session = session

    def execute(self, command: str) -> CommandResult:
        """Execute one command and return deterministic printable lines."""
        try:
            words = shlex.split(command)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if not words:
            return CommandResult()
        name, *arguments = words
        name = name.lower()
        if name in ("quit", "exit", "q"):
            self._arity(name, arguments, 0)
            return CommandResult(quit=True)
        if name in ("help", "?"):
            self._arity(name, arguments, 0)
            return CommandResult(_HELP)
        if name in ("registers", "regs", "r"):
            self._arity(name, arguments, 0)
            return CommandResult(format_state(self.session.target.capture_state()))
        if name in ("step", "s"):
            return self._step(arguments)
        if name in ("over", "o"):
            return self._over(arguments)
        if name == "run":
            return self._run(arguments)
        if name in ("continue", "c"):
            return self._continue(arguments)
        if name in ("break", "b"):
            self._arity(name, arguments, 1)
            address = _number(arguments[0], "address", maximum=0xFFFF)
            self.session.add_breakpoint(address)
            return CommandResult((f"breakpoint at {address:04X}",))
        if name == "delete":
            self._arity(name, arguments, 1)
            address = _number(arguments[0], "address", maximum=0xFFFF)
            self.session.remove_breakpoint(address)
            return CommandResult((f"breakpoint at {address:04X} removed",))
        if name == "breakpoints":
            self._arity(name, arguments, 0)
            lines = [f"break {address:04X}" for address in sorted(self.session.breakpoints)]
            lines += [
                f"watch {address:04X} {kind}"
                for address, kind in sorted(self.session.watchpoints.items())
            ]
            return CommandResult(tuple(lines) or ("no breakpoints or watchpoints",))
        if name == "watch":
            return self._watch(arguments)
        if name == "unwatch":
            self._arity(name, arguments, 1)
            address = _number(arguments[0], "address", maximum=0xFFFF)
            self.session.remove_watchpoint(address)
            return CommandResult((f"watchpoint at {address:04X} removed",))
        if name in ("disassemble", "disasm", "d"):
            return self._disassemble(arguments)
        if name in ("memory", "m"):
            return self._memory(arguments)
        if name == "history":
            return self._history(arguments)
        if name == "set":
            return self._set(arguments)
        if name == "int":
            return self._interrupt(arguments)
        if name == "reset":
            return self._reset(arguments)
        raise CommandError(f"unknown command: {name} (try help)")

    def interact(
        self, input_stream: TextIO, output_stream: TextIO, *, prompt: str = "8080> "
    ) -> None:
        """Run a line-oriented loop over the given streams until quit or end of input."""
        while True:
            output_stream.write(prompt)
            output_stream.flush()
            line = input_stream.readline()
            if line == "":
                return
            try:
                result = self.execute(line)
            except (CommandError, ValueError) as exc:
                output_stream.write(f"error: {exc}\n")
                continue
            for rendered in result.lines:
                output_stream.write(f"{rendered}\n")
            if result.quit:
                return

    # -- commands ----------------------------------------------------------

    def _step(self, arguments: list[str]) -> CommandResult:
        self._arity("step", arguments, 0, 1)
        count = _positive(arguments[0], "count", maximum=10_000) if arguments else 1
        return CommandResult(tuple(format_record(self.session.step()) for _ in range(count)))

    def _over(self, arguments: list[str]) -> CommandResult:
        self._arity("over", arguments, 0)
        state = self.session.target.capture_state()
        instruction = disassemble(self._require_peek(), state.pc)
        if instruction.mnemonic not in _CALLS:
            return self._step([])
        # Run the call through: stop when control is back at the instruction
        # after it with the stack where it was (a Ccc not taken gets there in
        # one step).
        lines = [format_record(self.session.step())]
        for _ in range(1_000_000):
            now = self.session.target.capture_state()
            if now.pc == instruction.next_address and now.sp == state.sp:
                break
            if now.pc in self.session.breakpoints:
                lines.append(f"breakpoint at {now.pc:04X}")
                break
            result = self.session.run(max_steps=1, stop_on_halt=False)
            if result.reason is not StopReason.STEP_LIMIT:
                lines += format_run(result)
                break
        else:
            lines.append("gave up after 1,000,000 steps")
        return CommandResult((*lines, *format_state(self.session.target.capture_state())))

    def _run(self, arguments: list[str]) -> CommandResult:
        self._arity("run", arguments, 1, 2)
        steps = _positive(arguments[0], "steps")
        states = _positive(arguments[1], "states") if len(arguments) == 2 else None
        return CommandResult(format_run(self.session.run(max_steps=steps, max_states=states)))

    def _continue(self, arguments: list[str]) -> CommandResult:
        self._arity("continue", arguments, 0)
        steps = 1_000_000
        lines = []
        # run() stops before a breakpoint without moving, so step off one first.
        if self.session.target.capture_state().pc in self.session.breakpoints:
            lines.append(format_record(self.session.step()))
            steps -= 1
        lines += format_run(self.session.run(max_steps=steps))
        return CommandResult(tuple(lines))

    def _watch(self, arguments: list[str]) -> CommandResult:
        self._arity("watch", arguments, 1, 2)
        address = _number(arguments[0], "address", maximum=0xFFFF)
        kind = arguments[1].lower() if len(arguments) == 2 else "rw"
        try:
            self.session.add_watchpoint(address, kind)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        return CommandResult((f"watch {address:04X} {kind}",))

    def _set(self, arguments: list[str]) -> CommandResult:
        self._arity("set", arguments, 2)
        register = arguments[0].upper()
        if register not in _REGISTERS:
            raise CommandError(f"no register {register}; set takes {' '.join(_REGISTERS)}")
        value = _number(arguments[1], register, maximum=_REGISTERS[register])
        cpu = self.session.cpu
        if register in _PAIRS:
            high, low = _PAIRS[register]
            if register == "PSW":
                cpu.a = value >> 8
                cpu.f.byte = value & 0xFF
            else:
                setattr(cpu, high, value >> 8)
                setattr(cpu, low, value & 0xFF)
        elif register == "F":
            cpu.f.byte = value
        else:
            setattr(cpu, register.lower(), value)
        return CommandResult(format_state(cpu.capture_state()))

    def _interrupt(self, arguments: list[str]) -> CommandResult:
        self._arity("int", arguments, 1)
        cpu = self.session.cpu
        if arguments[0].lower() == "off":
            cpu.clear_interrupt()
            return CommandResult(("INT deasserted",))
        byte = _number(arguments[0], "byte", maximum=0xFF)
        try:
            cpu.request_interrupt(byte)
        except (NotImplementedError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        return CommandResult((f"INT asserted, device supplies {byte:02X}",))

    def _reset(self, arguments: list[str]) -> CommandResult:
        self._arity("reset", arguments, 0)
        # RESET is a level input: assert it, run the one boundary that services
        # it, then release, so the CPU is left ready to fetch from 0x0000.
        cpu = self.session.cpu
        cpu.request_reset()
        record = self.session.step()
        cpu.clear_reset()
        return CommandResult((format_record(record), *format_state(cpu.capture_state())))

    def _disassemble(self, arguments: list[str]) -> CommandResult:
        self._arity("disassemble", arguments, 0, 2)
        peek = self._require_peek()
        state = self.session.target.capture_state()
        address = _number(arguments[0], "address", maximum=0xFFFF) if arguments else state.pc
        count = _positive(arguments[1], "count", maximum=256) if len(arguments) == 2 else 8
        lines = []
        for _ in range(count):
            instruction = disassemble(peek, address)
            lines.append(format_instruction(instruction))
            address = instruction.next_address
        return CommandResult(tuple(lines))

    def _memory(self, arguments: list[str]) -> CommandResult:
        self._arity("memory", arguments, 1, 2)
        peek = self._require_peek()
        address = _number(arguments[0], "address", maximum=0xFFFF)
        length = _positive(arguments[1], "length", maximum=256) if len(arguments) == 2 else 16
        lines = []
        for offset in range(0, length, 16):
            row = (address + offset) & 0xFFFF
            values = [
                self._read_peek(peek, (row + column) & 0xFFFF)
                for column in range(min(16, length - offset))
            ]
            lines.append(f"{row:04X}  {' '.join(f'{value:02X}' for value in values)}")
        return CommandResult(tuple(lines))

    def _history(self, arguments: list[str]) -> CommandResult:
        self._arity("history", arguments, 0, 1)
        count = _positive(arguments[0], "count", maximum=10_000) if arguments else 16
        records = self.session.history[-count:]
        return CommandResult(
            tuple(format_record(record) for record in records) or ("history empty",)
        )

    def _require_peek(self) -> ByteReader:
        if self.session.peek_byte is None:
            raise CommandError("this session has no side-effect-free peek capability")
        return self.session.peek_byte

    @staticmethod
    def _read_peek(peek: ByteReader, address: int) -> int:
        value = peek(address)
        if type(value) is not int or not 0 <= value <= 0xFF:
            raise CommandError(f"peek returned a non-byte value at {address:04X}")
        return value

    @staticmethod
    def _arity(name: str, arguments: list[str], minimum: int, maximum: int | None = None) -> None:
        maximum = minimum if maximum is None else maximum
        if not minimum <= len(arguments) <= maximum:
            expected = str(minimum) if minimum == maximum else f"{minimum}..{maximum}"
            raise CommandError(f"{name} expects {expected} argument(s)")


__all__ = [
    "CommandDebugger",
    "CommandError",
    "CommandResult",
    "format_flags",
    "format_state",
    "parse_number",
]
