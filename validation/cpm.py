"""The ``cpm-minimal`` host: just enough CP/M to run the 8080 exercisers.

Loads a ``.COM`` at 0x0100 and supplies two traps checked before every step,
outside the CPU: PC == 0x0000 (warm boot) ends the run; PC == 0x0005 is BDOS
function C: 0 ends the run, 2 prints E, 9 prints from DE up to ``$``; then the
trap pops the return address. The word at 0x0006 is set to 0xF000 because the
exercisers execute ``LHLD 6; SPHL`` before their first BDOS call.
(docs/validation.md, "Harness plan".)

Usage::

    python -m validation.cpm tests/exercisers/8080PRE.COM
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from i8080_python import I8080CPU, trace_steps, write_trace

_COM_LOAD_ADDRESS = 0x0100
_BDOS_ENTRY = 0x0005
_WARM_BOOT = 0x0000
_TOP_OF_TPA = 0xF000

#: superzazu/8080@274ffd7's published state totals: emulator-derived, so a
#: mismatch is a lead to chase, not a failure (docs/validation.md).
SUPERZAZU_STATES = {
    "8080PRE.COM": 7_817,
    "TST8080.COM": 4_924,
    "CPUTEST.COM": 255_653_383,
    "8080EXM.COM": 23_803_381_171,
}

#: Per-program pass criteria and instruction budgets (docs/validation.md).
PROGRAMS: dict[str, tuple[int, tuple[str, ...], tuple[str, ...]]] = {
    # name: (instruction budget, required substrings, forbidden substrings)
    "8080PRE.COM": (100_000, ("8080 Preliminary tests complete",), ()),
    "TST8080.COM": (100_000, ("CPU IS OPERATIONAL",), ("CPU HAS FAILED",)),
    "8080EXM.COM": (100_000_000_000, ("Tests complete",), ("ERROR",)),
    "CPUTEST.COM": (1_000_000_000, ("CPU TESTS OK",), ()),
}

#: The 25 CRCs 8080EXM.COM prints, in program order, as captured on real
#: non-AMD 8080A chips (docs/validation.md, "The 25 expected CRCs").
EXM_HARDWARE_CRCS = (
    ("dad <b,d,h,sp>", "14474BA6"),
    ("aluop nn", "9E922F9E"),
    ("aluop <b,c,d,e,h,l,m,a>", "CF762C86"),
    ("<daa,cma,stc,cmc>", "BB3F030C"),
    ("<inr,dcr> a", "ADB6460E"),
    ("<inr,dcr> b", "83ED1345"),
    ("<inx,dcx> b", "F79287CD"),
    ("<inr,dcr> c", "E5F6721B"),
    ("<inr,dcr> d", "15B5579A"),
    ("<inx,dcx> d", "7F4E2501"),
    ("<inr,dcr> e", "CF2AB396"),
    ("<inr,dcr> h", "12B2952C"),
    ("<inx,dcx> h", "9F2B23C0"),
    ("<inr,dcr> l", "FF57D356"),
    ("<inr,dcr> m", "92E963BD"),
    ("<inx,dcx> sp", "D5702FAB"),
    ("lhld nnnn", "A9C3D5CB"),
    ("shld nnnn", "E8864F26"),
    ("lxi <b,d,h,sp>,nnnn", "FCF46E12"),
    ("ldax <b,d>", "2B821D5F"),
    ("mvi <b,c,d,e,h,l,m,a>,nn", "EAA72044"),
    ("mov <bcdehla>,<bcdehla>", "10B58CEE"),
    ("sta nnnn / lda nnnn", "ED57AF72"),
    ("<rlc,rrc,ral,rar>", "E0D89235"),
    ("stax <b,d>", "2B0471E9"),
)


class CPMRunError(RuntimeError):
    """The program exceeded its budget, halted, or used a BDOS call we do not supply."""


class CPMHost(I8080CPU):
    """``flat`` host (64 KiB RAM, no ports) that the CP/M traps drive."""

    def __init__(self) -> None:
        self.memory = bytearray(0x10000)
        super().__init__(
            self.memory.__getitem__,
            self.memory.__setitem__,
            read_port=self._refuse_in,
            write_port=self._refuse_out,
        )

    def _refuse_in(self, port: int) -> int:
        raise CPMRunError(f"unexpected IN from port 0x{port:02X} at PC 0x{self.pc:04X}")

    def _refuse_out(self, port: int, value: int) -> None:
        raise CPMRunError(f"unexpected OUT to port 0x{port:02X} at PC 0x{self.pc:04X}")


@dataclass(frozen=True)
class CPMResult:
    """A completed run: the console transcript and its accounting."""

    output: str
    instructions: int
    states: int
    bdos_calls: int
    seconds: float

    @property
    def superzazu_states(self) -> int:
        """This run's total in superzazu/8080's accounting, for its published totals.

        superzazu traps BDOS with real code at 0x0005 (``OUT 1,A; RET``: 10 + 10
        states per call) and warm boot with ``OUT 0,A`` at 0x0000 (10 states,
        counted once); this host traps both outside the CPU for free
        (superzazu/8080@274ffd7, ``i8080_tests.c``).
        """
        return self.states + 20 * self.bdos_calls + 10


def load_com(program: bytes) -> CPMHost:
    """A ``cpm-minimal`` machine with ``program`` loaded and PC at 0x0100."""
    if len(program) > _TOP_OF_TPA - _COM_LOAD_ADDRESS:
        raise ValueError(f"program too large: {len(program)} bytes")
    cpu = CPMHost()
    cpu.memory[_COM_LOAD_ADDRESS : _COM_LOAD_ADDRESS + len(program)] = program
    cpu.memory[0x0006] = _TOP_OF_TPA & 0xFF
    cpu.memory[0x0007] = _TOP_OF_TPA >> 8
    cpu.pc = _COM_LOAD_ADDRESS
    cpu.sp = _TOP_OF_TPA
    return cpu


def bdos(cpu: CPMHost, emit: Callable[[bytes], None]) -> bool:
    """Perform the BDOS call at 0x0005 and return from it; False means the program exited."""
    function = cpu.c
    if function == 0:
        return False
    if function == 2:
        emit(bytes((cpu.e,)))
    elif function == 9:
        address = cpu._de()
        end = cpu.memory.index(ord("$"), address)
        emit(bytes(cpu.memory[address:end]))
    else:
        raise CPMRunError(f"unsupported BDOS function {function}")
    cpu.pc = cpu._pop_word()
    return True


def trace_com(program: bytes, stream: TextIO, *, max_steps: int) -> int:
    """Write the first ``max_steps`` boundaries of ``program`` as a conformance trace.

    The traps are host behavior: they run between records and produce none.
    """
    cpu = load_com(program)

    def between() -> bool:
        while cpu.pc == _BDOS_ENTRY:
            if not bdos(cpu, lambda data: None):
                return False
        return cpu.pc != _WARM_BOOT

    return write_trace(
        trace_steps(cpu, cpu.memory.__getitem__, max_steps=max_steps, between=between), stream
    )


def run_com(
    program: bytes,
    *,
    max_instructions: int,
    echo: bool = False,
) -> CPMResult:
    """Run ``program`` under ``cpm-minimal`` until warm boot or BDOS function 0."""
    cpu = load_com(program)
    output = bytearray()

    def emit(data: bytes) -> None:
        output.extend(data)
        if echo:
            sys.stdout.write(data.decode("latin-1"))
            sys.stdout.flush()

    step = cpu.step
    instructions = 0
    states = 0
    bdos_calls = 0
    started = time.perf_counter()
    while instructions < max_instructions:
        pc = cpu.pc
        if pc == _WARM_BOOT:
            break
        if pc == _BDOS_ENTRY:
            bdos_calls += 1
            if not bdos(cpu, emit):
                break
            continue
        if cpu.halted:
            raise CPMRunError(f"halted at PC 0x{pc:04X}")
        states += step()
        instructions += 1
    else:
        raise CPMRunError(
            f"no exit within {max_instructions:,} instructions; last PC 0x{cpu.pc:04X}; "
            f"output so far: {output.decode('latin-1')!r}"
        )
    return CPMResult(
        output.decode("latin-1"), instructions, states, bdos_calls, time.perf_counter() - started
    )


def failures(name: str, output: str) -> list[str]:
    """Return every way ``output`` misses ``name``'s pass criteria (empty means pass)."""
    _, required, forbidden = PROGRAMS[name]
    problems = [f"missing {text!r}" for text in required if text not in output]
    problems += [f"contains {text!r}" for text in forbidden if text in output]
    if name == "8080EXM.COM":
        # Check each printed CRC against the hardware table ourselves rather than
        # trusting the program's own PASS!/ERROR verdict.
        printed = re.findall(
            r"^(.*?)\.*\s+(?:PASS!|ERROR \*+) crc is:([0-9a-fA-F]{8})", output, re.M
        )
        for index, (group, expected) in enumerate(EXM_HARDWARE_CRCS):
            if index >= len(printed):
                problems.append(f"{group}: no CRC printed")
                continue
            got_group, got_crc = printed[index]
            if got_group.strip() != group or got_crc.upper() != expected:
                problems.append(
                    f"{group}: expected {expected}, got {got_group.strip()!r} {got_crc.upper()}"
                )
        if len(printed) > len(EXM_HARDWARE_CRCS):
            problems.append(f"{len(printed)} CRCs printed, expected {len(EXM_HARDWARE_CRCS)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("program", type=Path, help="a .COM file from tests/exercisers/")
    parser.add_argument("--max-instructions", type=int, default=None)
    parser.add_argument(
        "--trace",
        type=Path,
        help="instead of running to completion, write the first --trace-steps boundaries "
        "as a JSON Lines conformance trace (docs/trace-schema.md) and exit",
    )
    parser.add_argument("--trace-steps", type=int, default=10_000)
    args = parser.parse_args(argv)
    name = args.program.name.upper()
    if args.trace:
        with args.trace.open("w", encoding="utf-8") as stream:
            count = trace_com(args.program.read_bytes(), stream, max_steps=args.trace_steps)
        print(f"wrote {count:,} records to {args.trace}")
        return 0
    budget = args.max_instructions or PROGRAMS.get(name, (10**9,))[0]
    result = run_com(args.program.read_bytes(), max_instructions=budget, echo=True)
    print(
        f"\n--- {name}: {result.instructions:,} instructions, {result.states:,} states "
        f"({result.superzazu_states:,} in superzazu's accounting, which publishes "
        f"{SUPERZAZU_STATES.get(name, 0):,}), {result.seconds:.1f} s on "
        f"{sys.implementation.name} {sys.version.split()[0]}"
    )
    if name not in PROGRAMS:
        return 0
    problems = failures(name, result.output)
    for problem in problems:
        print(f"FAIL: {problem}")
    print("PASS" if not problems else "FAIL")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
