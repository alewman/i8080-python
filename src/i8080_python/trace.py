"""Conformance traces: the core's observable behavior, one boundary per JSON line.

The shape is z80-python's version-1 trace (its docs/trace-schema.md) with an
8080 state object; this package's docs/trace-schema.md is the contract. Two
cores that produce equal traces for the same program and host are, as far as
software can tell, the same CPU.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, fields
from enum import Enum
from typing import Protocol, TextIO

from i8080_python.disasm import ByteReader, Instruction, disassemble, disassemble_bytes
from i8080_python.state import CPUState

TRACE_SCHEMA_VERSION = 1
STATE_FIELDS = tuple(field.name for field in fields(CPUState))
_RECORD_KEYS = {"version", "sequence", "kind", "states", "instruction", "before", "after"}


class BoundaryKind(Enum):
    """What one step() did."""

    INSTRUCTION = "instruction"
    HALT_IDLE = "halt_idle"
    RESET = "reset"
    INTERRUPT = "interrupt"


def boundary_kind(state: CPUState) -> BoundaryKind:
    """The kind of the next boundary, decided from the state before it, as step() decides it."""
    if state.reset_pending:
        return BoundaryKind.RESET
    if state.interrupt_vector is not None and state.inte and state.ei_delay == 0:
        return BoundaryKind.INTERRUPT
    if state.halted:
        return BoundaryKind.HALT_IDLE
    return BoundaryKind.INSTRUCTION


@dataclass(frozen=True, slots=True)
class StepRecord:
    """Before/after evidence for one boundary."""

    sequence: int
    kind: BoundaryKind
    states: int
    instruction: Instruction | None
    before: CPUState
    after: CPUState


class Traceable(Protocol):
    """What :func:`trace_steps` needs; an :class:`~i8080_python.I8080CPU` has both."""

    def step(self) -> int: ...

    def capture_state(self) -> CPUState: ...


def trace_steps(
    cpu: Traceable,
    peek: ByteReader,
    *,
    max_steps: int,
    between: Callable[[], bool] | None = None,
) -> Iterator[StepRecord]:
    """Run ``cpu`` for up to ``max_steps`` boundaries, yielding one record per boundary.

    ``peek`` must read memory without side effects; it is used only to
    disassemble the instruction at PC before it executes. ``between``, if
    given, runs host behavior before each boundary (a trap, a device) and
    returns False to end the trace; what it does to the CPU appears only as
    the difference between one record's ``after`` and the next one's ``before``.
    """
    for sequence in range(max_steps):
        if between is not None and not between():
            return
        before = cpu.capture_state()
        kind = boundary_kind(before)
        instruction = disassemble(peek, before.pc) if kind is BoundaryKind.INSTRUCTION else None
        states = cpu.step()
        yield StepRecord(sequence, kind, states, instruction, before, cpu.capture_state())


def record_to_dict(record: StepRecord) -> dict[str, object]:
    """The JSON-compatible form of one record."""
    instruction = record.instruction
    return {
        "version": TRACE_SCHEMA_VERSION,
        "sequence": record.sequence,
        "kind": record.kind.value,
        "states": record.states,
        "instruction": None
        if instruction is None
        else {
            "address": instruction.address,
            "data": instruction.data.hex(),
            "mnemonic": instruction.mnemonic,
            "operands": list(instruction.operands),
        },
        "before": {name: getattr(record.before, name) for name in STATE_FIELDS},
        "after": {name: getattr(record.after, name) for name in STATE_FIELDS},
    }


def record_from_dict(value: object) -> StepRecord:
    """Rebuild and validate one record.

    A producer in another language may omit ``mnemonic`` and ``operands``; they
    are then decoded from ``data`` with this package's disassembler.
    """
    if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
        raise ValueError(f"a record must be an object with exactly the keys {sorted(_RECORD_KEYS)}")
    if value["version"] != TRACE_SCHEMA_VERSION:
        raise ValueError(f"unsupported trace schema version: {value['version']!r}")
    for name in ("before", "after"):
        state = value[name]
        if not isinstance(state, dict) or set(state) != set(STATE_FIELDS):
            raise ValueError(f"{name} must have exactly the keys {list(STATE_FIELDS)}")
    before = CPUState(**value["before"])
    after = CPUState(**value["after"])
    kind = BoundaryKind(value["kind"])
    if kind is not boundary_kind(before):
        raise ValueError(f"kind {kind.value!r} contradicts the before state")
    states = value["states"]
    if type(states) is not int or states <= 0:
        raise ValueError("states must be a positive integer")
    instruction = None
    raw = value["instruction"]
    if raw is not None:
        decoded = disassemble_bytes(bytes.fromhex(raw["data"]), raw["address"])
        if decoded.size != len(raw["data"]) // 2:
            raise ValueError("instruction data is not exactly one instruction")
        if "mnemonic" in raw and (raw["mnemonic"], tuple(raw["operands"])) != (
            decoded.mnemonic,
            decoded.operands,
        ):
            raise ValueError("instruction mnemonic and operands do not match its data")
        instruction = decoded
    return StepRecord(value["sequence"], kind, states, instruction, before, after)


def write_trace(records: Iterable[StepRecord], stream: TextIO) -> int:
    """Write records as JSON Lines (sorted keys, no spaces); return how many."""
    count = 0
    for record in records:
        stream.write(json.dumps(record_to_dict(record), separators=(",", ":"), sort_keys=True))
        stream.write("\n")
        count += 1
    return count


def read_trace(stream: TextIO) -> Iterator[StepRecord]:
    """Yield validated records lazily from JSON Lines, skipping blank lines."""
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            continue
        try:
            yield record_from_dict(json.loads(line))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"invalid trace record at line {line_number}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class TraceDivergence:
    """The first place two traces differ: record index, field path, and both values."""

    index: int
    path: str
    left: object
    right: object


def _flatten(record: StepRecord) -> dict[str, object]:
    instruction = record.instruction
    flat: dict[str, object] = {
        "kind": record.kind.value,
        "states": record.states,
        "instruction.address": None if instruction is None else instruction.address,
        "instruction.data": None if instruction is None else instruction.data.hex(),
    }
    for side in ("before", "after"):
        state = getattr(record, side)
        flat.update({f"{side}.{name}": getattr(state, name) for name in STATE_FIELDS})
    return flat


def first_trace_divergence(
    left: Iterable[StepRecord], right: Iterable[StepRecord]
) -> TraceDivergence | None:
    """Compare two traces record by record and return the first difference, or None."""
    left_records, right_records = iter(left), iter(right)
    index = 0
    while True:
        a = next(left_records, None)
        b = next(right_records, None)
        if a is None and b is None:
            return None
        if a is None or b is None:
            return TraceDivergence(index, "record", a and "present", b and "present")
        flat_a, flat_b = _flatten(a), _flatten(b)
        for path, value in flat_a.items():
            if flat_b[path] != value:
                return TraceDivergence(index, path, value, flat_b[path])
        index += 1


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "BoundaryKind",
    "StepRecord",
    "TraceDivergence",
    "boundary_kind",
    "first_trace_divergence",
    "read_trace",
    "record_from_dict",
    "record_to_dict",
    "trace_steps",
    "write_trace",
]
