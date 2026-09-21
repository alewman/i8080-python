"""Rung 5: lockstep against MAME 0.285's trace of ``invaders`` (the detector).

Runs the real Space Invaders program on an ``invaders`` host and compares the
core, instruction by instruction, with the ``error.log`` that the recipe in
docs/mame-oracle.md produces: ``pc a b c d e h l sp`` exactly, ``f`` masked
to the five real flags (MAME's internal F omits the fixed bit 1), and the
cumulative state count against ``totalcycles``. MAME is emulator-derived: a
divergence is a lead to settle against the datasheet and the hardware CRCs,
never a bug by definition.

The host restates the Midway board as MAME 0.285 models it
(``src/mame/midw8080/mw8080bw.cpp``, BSD-3-Clause; numbers and rules restated,
no code copied), because lockstep needs the same interrupt timing as MAME:

- 128 CPU states per line, 262 lines per frame, and the beam on line 224 at
  state 0 (MAME's first trace line reads ``beamy`` 224). Time is kept in
  attoseconds exactly as MAME computes it, because MAME's truncated periods
  make a 128-state line 128 as longer than a scanline: a timer at time T is
  seen at the first boundary at or after ``T // CYCLE_AS`` states, which is
  one state before the whole-number position (``emu/schedule.cpp`` hands the
  CPU ``floor(delta / attoseconds_per_cycle)`` cycles per timeslice).
- Interrupt triggers at the start of line 96 (counter 0x80) and line 224
  (counter 0xDA), the first at line 96. At a trigger the board asserts INT if
  its copy of the CPU's INTE pin is high, and clears it otherwise. That copy
  starts high and follows only *changes* of INTE, so before the program's
  first INTE edge the board asserts INT while the CPU ignores it.
- The acknowledge forms the vector from the vertical counter's 64V bit at
  acknowledge time, ``0xC7 | 64V << 4 | !64V << 3`` (RST 1 or RST 2), and
  clears INT.
- ROM 0x0000-0x1FFF, RAM 0x2000-0x3FFF mirrored at 0x6000-0x7FFF, an
  unpopulated ROM hole at 0x4000-0x5FFF that reads 0, a 15-bit address bus;
  ports masked to 3 bits: IN 0/1/2 idle switches, IN 3 the MB14241 shifter,
  OUT 2 shift count, OUT 4 shift data, OUT 3/5 sound, OUT 6 watchdog.

Usage::

    python -m validation.mame_lockstep tests/mame_traces/run60/error.log
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from i8080_python import FLAG_MASK, I8080CPU

DEFAULT_ROM_ZIP = Path(
    "/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)/invaders.zip"
)
#: (file in invaders.zip, load address), per MAME 0.285's ROM_LOAD lines.
ROMS = (
    ("9316b-0869_m739h.h1", 0x0000),
    ("9316b-0856_m739g.g1", 0x0800),
    ("9316b-0855_m739f.f1", 0x1000),
    ("9316b-0854_m739e.e1", 0x1800),
)

LINES_PER_FRAME = 262
VBLANK_START_LINE = 224
FIRST_LINE = 224  # the beam's line at state 0
TRIGGER_LINES = (96, 224)  # vertical counter 0x80 and 0xDA

# MAME's periods: HZ_TO_ATTOSECONDS truncates 1e18 / clock.
CYCLE_AS = 10**18 // 1_996_800  # CPU clock, 19.968 MHz / 10
PIXEL_AS = 10**18 // 4_992_000  # pixel clock, 19.968 MHz / 4
SCANLINE_AS = PIXEL_AS * 320

#: IN 0, 1, 2 with MAME 0.285's default switches and no input: IN 0 bit 3 and
#: IN 1 bits 0 (coin, active low) and 3 are the only bits that read 1.
IDLE_INPUTS = (0x08, 0x09, 0x00)


def line_at(attoseconds: int) -> int:
    """The beam line at a time measured from the start of the first VBLANK."""
    return (FIRST_LINE + attoseconds // SCANLINE_AS) % LINES_PER_FRAME


def vertical_counter(line: int) -> int:
    """The board's sync-chain counter: 0x20-0xFF over the visible lines, then 0xDA-0xFF."""
    if line >= VBLANK_START_LINE:
        return line - VBLANK_START_LINE + 0xDA
    return line + 0x20


def interrupt_vector(line: int) -> int:
    """RST 1 (0xCF) or RST 2 (0xD7), chosen by the counter's 64V bit."""
    v64 = (vertical_counter(line) >> 6) & 1
    return 0xC7 | (v64 << 4) | ((v64 ^ 1) << 3)


class InvadersHost(I8080CPU):
    """The Midway ``invaders`` board as far as the CPU can observe it."""

    def __init__(self, rom: bytes) -> None:
        if len(rom) != 0x2000:
            raise ValueError("invaders needs 8 KiB of ROM")
        self.rom = rom
        self.ram = bytearray(0x2000)
        self.states = 0
        self.shift_data = 0
        self.shift_count = 0
        super().__init__(
            self._read_memory,
            self._write_memory,
            read_port=self._read_device,
            write_port=self._write_device,
        )
        # The board's copy of the INTE pin starts high and follows edges only.
        self.board_int_enable = True
        self._last_inte = self.inte
        self._int_line = False
        # Attosecond times of the next and the last interrupt trigger.
        self._next_trigger = (TRIGGER_LINES[0] - FIRST_LINE) % LINES_PER_FRAME * SCANLINE_AS
        self._last_trigger = 0

    @classmethod
    def from_zip(cls, path: Path) -> InvadersHost:
        rom = bytearray(0x2000)
        with zipfile.ZipFile(path) as archive:
            for name, address in ROMS:
                rom[address : address + 0x800] = archive.read(name)
        return cls(bytes(rom))

    def _read_memory(self, addr: int) -> int:
        addr &= 0x7FFF
        if addr < 0x2000:
            return self.rom[addr]
        if addr < 0x4000:
            return self.ram[addr - 0x2000]
        if addr < 0x6000:
            return 0
        return self.ram[addr - 0x6000]

    def _write_memory(self, addr: int, value: int) -> None:
        addr &= 0x7FFF
        if 0x2000 <= addr < 0x4000:
            self.ram[addr - 0x2000] = value
        elif addr >= 0x6000:
            self.ram[addr - 0x6000] = value

    def _read_device(self, port: int) -> int:
        port &= 0x07
        if port & 0x03 == 3:
            return (self.shift_data >> self.shift_count) & 0xFF
        return IDLE_INPUTS[port & 0x03]

    def _write_device(self, port: int, value: int) -> None:
        port &= 0x07
        if port == 2:
            self.shift_count = ~value & 0x07
        elif port == 4:
            self.shift_data = (self.shift_data >> 8) | (value << 7)
        # 3 and 5 are sound latches, 6 the watchdog: nothing the CPU can read back.

    def run_board(self) -> None:
        """Advance the interrupt generator to the current state count."""
        while self.states >= self._next_trigger // CYCLE_AS:
            if self.board_int_enable:
                self._int_line = True
            else:
                self._int_line = False
                self.clear_interrupt()
            trigger_line = line_at(self._next_trigger)
            following = TRIGGER_LINES[1] if trigger_line == TRIGGER_LINES[0] else TRIGGER_LINES[0]
            gap = (following - trigger_line) % LINES_PER_FRAME
            self._last_trigger = self._next_trigger
            self._next_trigger += gap * SCANLINE_AS
        if self._int_line:
            # The vector is formed when the CPU acknowledges, from the counter
            # at that moment. MAME reads the beam at the scheduler's time, which
            # is never earlier than the trigger that raised INT.
            now = max(self.states * CYCLE_AS, self._last_trigger)
            self.request_interrupt(interrupt_vector(line_at(now)))

    def accepts_interrupt_next(self) -> bool:
        """Whether the next step() is an interrupt acceptance rather than an instruction."""
        return self.inte and self.interrupt_pending and self.capture_state().ei_delay == 0

    def board_step(self) -> tuple[int, bool]:
        """Run one CPU boundary; return (states, whether it was an interrupt acceptance)."""
        self.run_board()
        accepting = self.accepts_interrupt_next()
        states = self.step()
        self.states += states
        if accepting:
            self._int_line = False  # the acknowledge clears INT
        if self.inte != self._last_inte:
            self.board_int_enable = self.inte
            self._last_inte = self.inte
        return states, accepting


@dataclass(frozen=True, slots=True)
class MameLine:
    number: int
    pc: int
    a: int
    f: int
    b: int
    c: int
    d: int
    e: int
    h: int
    l: int  # noqa: E741
    sp: int
    totalcycles: int
    beamy: int
    frame: int

    @property
    def registers(self) -> tuple[int, ...]:
        return (self.pc, self.a, self.f & FLAG_MASK, self.b, self.c, self.d, self.e,
                self.h, self.l, self.sp, self.totalcycles)  # fmt: skip


def read_error_log(path: Path) -> Iterator[MameLine]:
    """Yield each instruction line of MAME's ``error.log``, skipping the header."""
    with path.open(encoding="utf-8-sig") as stream:
        for number, text in enumerate(stream, start=1):
            fields = text.split()
            if len(fields) != 13:
                continue  # "Soft reset" and any other non-trace line
            hexes = [int(field, 16) for field in fields[:10]]
            decimals = [int(field) for field in fields[10:]]
            yield MameLine(number, *hexes, *decimals)


FIELDS = ("pc", "a", "f&D5", "b", "c", "d", "e", "h", "l", "sp", "states")


def _ours(host: InvadersHost) -> tuple[int, ...]:
    return (host.pc, host.a, host.f.byte & FLAG_MASK, host.b, host.c, host.d, host.e,
            host.h, host.l, host.sp, host.states)  # fmt: skip


def _format(values: tuple[int, ...]) -> str:
    return " ".join(
        f"{name}={value:X}" for name, value in zip(FIELDS[:-1], values[:-1], strict=True)
    ) + (f" states={values[-1]}")


@dataclass
class LockstepResult:
    lines: int
    interrupts: int
    seconds: float
    divergence: str | None


def lockstep(log: Path, rom_zip: Path = DEFAULT_ROM_ZIP, *, context: int = 10) -> LockstepResult:
    """Compare the core with every line of ``log``; stop at the first divergence."""
    host = InvadersHost.from_zip(rom_zip)
    ours: deque[str] = deque(maxlen=context)
    theirs: deque[str] = deque(maxlen=context)
    lines = interrupts = 0
    started = time.perf_counter()
    for line in read_error_log(log):
        # MAME accepts an interrupt without a debugger hook, so an acceptance
        # has no line of its own: run it, then compare the handler's entry.
        while True:
            host.run_board()
            if not host.accepts_interrupt_next():
                break
            states, _ = host.board_step()
            interrupts += 1
            ours.append(f"  interrupt accepted: {states} states, now pc={host.pc:04X}")
        mine = _ours(host)
        if mine != line.registers:
            differing = [
                name for name, x, y in zip(FIELDS, mine, line.registers, strict=True) if x != y
            ]
            report = [
                f"first divergence at error.log line {line.number} "
                f"(beamy {line.beamy}, frame {line.frame}); differs in: {', '.join(differing)}",
                "MAME, the lines before and this one:",
                *theirs,
                f"> {line.number}: {_format(line.registers)}",
                "core, the boundaries before and this one:",
                *ours,
                f"> {_format(mine)}",
            ]
            return LockstepResult(
                lines, interrupts, time.perf_counter() - started, "\n".join(report)
            )
        theirs.append(f"  {line.number}: {_format(line.registers)}")
        ours.append(f"  {_format(mine)}")
        host.board_step()
        lines += 1
    return LockstepResult(lines, interrupts, time.perf_counter() - started, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("error_log", type=Path)
    parser.add_argument("--rom-zip", type=Path, default=DEFAULT_ROM_ZIP)
    args = parser.parse_args(argv)
    result = lockstep(args.error_log, args.rom_zip)
    interpreter = f"{sys.implementation.name} {sys.version.split()[0]}"
    print(
        f"{result.lines:,} MAME lines matched, {result.interrupts} interrupts accepted, "
        f"{result.seconds:.1f} s on {interpreter}"
    )
    if result.divergence:
        print(result.divergence)
        return 1
    print("PASS: identical registers, masked flags, and cumulative states on every line")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
