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
from typing import Protocol, TextIO

from i8080_python.debug import BoundaryKind, DebugSession, StepRecord, next_boundary
from i8080_python.disasm import ByteReader, disassemble, disassemble_bytes
from i8080_python.state import CPUState

TRACE_SCHEMA_VERSION = 1
STATE_FIELDS = tuple(field.name for field in fields(CPUState))
_RECORD_KEYS = {"version", "sequence", "kind", "states", "instruction", "before", "after"}
#: ``accesses`` is optional: a record that carries it came from a session that
#: tracked the bus, and two records are compared on it only when both have it.
_OPTIONAL_KEYS = {"accesses"}


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
        kind = next_boundary(before)
        instruction = disassemble(peek, before.pc) if kind is BoundaryKind.INSTRUCTION else None
        states = cpu.step()
        yield StepRecord(sequence, kind, before, cpu.capture_state(), states, instruction)


def iter_session_steps(session: DebugSession, *, max_steps: int) -> Iterator[StepRecord]:
    """Yield records from a :class:`~i8080_python.debug.DebugSession`, one per boundary.

    Use this instead of :func:`trace_steps` when the trace should carry the bus
    accesses each step made: a session created with ``track_accesses=True``
    records them, and :func:`write_trace` then writes the optional ``accesses``
    array.
    """
    if type(max_steps) is not int or max_steps <= 0:
        raise ValueError("max_steps must be a positive integer")
    for _ in range(max_steps):
        yield session.step()


def record_to_dict(record: StepRecord) -> dict[str, object]:
    """The JSON-compatible form of one record."""
    instruction = record.instruction
    value: dict[str, object] = {
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
    if record.accesses is not None:
        value["accesses"] = [[kind, address, data] for kind, address, data in record.accesses]
    return value


def record_from_dict(value: object) -> StepRecord:
    """Rebuild and validate one record.

    A producer in another language may omit ``mnemonic`` and ``operands``; they
    are then decoded from ``data`` with this package's disassembler.
    """
    if (
        not isinstance(value, dict)
        or not _RECORD_KEYS <= set(value) <= _RECORD_KEYS | _OPTIONAL_KEYS
    ):
        raise ValueError(
            f"a record must be an object with the keys {sorted(_RECORD_KEYS)} "
            f"and optionally {sorted(_OPTIONAL_KEYS)}"
        )
    if value["version"] != TRACE_SCHEMA_VERSION:
        raise ValueError(f"unsupported trace schema version: {value['version']!r}")
    for name in ("before", "after"):
        state = value[name]
        if not isinstance(state, dict) or set(state) != set(STATE_FIELDS):
            raise ValueError(f"{name} must have exactly the keys {list(STATE_FIELDS)}")
    before = CPUState(**value["before"])
    after = CPUState(**value["after"])
    kind = BoundaryKind(value["kind"])
    if kind is not next_boundary(before):
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
    accesses = value.get("accesses")
    if accesses is not None:
        accesses = tuple(tuple(access) for access in accesses)
    return StepRecord(value["sequence"], kind, before, after, states, instruction, accesses)


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
        # Accesses are compared only when both producers recorded them; a trace
        # written without tracking says nothing about the bus either way.
        if a.accesses is not None and b.accesses is not None:
            flat_a["accesses"] = a.accesses
            flat_b["accesses"] = b.accesses
        for path, value in flat_a.items():
            if flat_b[path] != value:
                return TraceDivergence(index, path, value, flat_b[path])
        index += 1


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "TraceDivergence",
    "first_trace_divergence",
    "iter_session_steps",
    "read_trace",
    "record_from_dict",
    "record_to_dict",
    "trace_steps",
    "write_trace",
]
