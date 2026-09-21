"""The JSON Lines conformance trace."""

from __future__ import annotations

import io
import json
from dataclasses import replace

import pytest
from conftest import machine_with

from i8080_python.debug import BoundaryKind, DebugSession
from i8080_python.trace import (
    first_trace_divergence,
    iter_session_steps,
    read_trace,
    trace_steps,
    write_trace,
)

# MVI A,2AH; EI; NOP; HLT; then an interrupt wakes it into RST 1.
PROGRAM = [0x3E, 0x2A, 0xFB, 0x00, 0x76]


def _records(steps: int = 6):
    cpu = machine_with(PROGRAM, sp=0x8000)
    records = []
    for record in trace_steps(cpu, cpu.memory.__getitem__, max_steps=steps):
        records.append(record)
        if record.kind is BoundaryKind.HALT_IDLE:
            cpu.request_interrupt(0xCF)
    return records


def test_kinds_and_instructions() -> None:
    records = _records()
    assert [r.kind for r in records] == [
        BoundaryKind.INSTRUCTION,
        BoundaryKind.INSTRUCTION,
        BoundaryKind.INSTRUCTION,
        BoundaryKind.INSTRUCTION,
        BoundaryKind.HALT_IDLE,
        BoundaryKind.INTERRUPT,
    ]
    assert [r.instruction.text for r in records[:4]] == ["MVI A,2AH", "EI", "NOP", "HLT"]
    assert [r.states for r in records] == [7, 4, 4, 7, 7, 11]
    assert records[-1].after.pc == 0x0008


def test_round_trip_through_json_lines() -> None:
    records = _records()
    stream = io.StringIO()
    assert write_trace(records, stream) == 6
    stream.seek(0)
    assert list(read_trace(stream)) == records
    assert first_trace_divergence(records, records) is None


def test_external_producer_may_omit_the_mnemonic() -> None:
    stream = io.StringIO()
    write_trace(_records(1), stream)
    value = json.loads(stream.getvalue())
    del value["instruction"]["mnemonic"], value["instruction"]["operands"]
    (record,) = read_trace(io.StringIO(json.dumps(value)))
    assert record.instruction.text == "MVI A,2AH"


def test_divergence_names_the_field() -> None:
    records = _records()
    stream = io.StringIO()
    write_trace(records, stream)
    lines = stream.getvalue().splitlines()
    changed = json.loads(lines[2])
    changed["after"]["f"] = 0x03
    lines[2] = json.dumps(changed)
    divergence = first_trace_divergence(records, read_trace(io.StringIO("\n".join(lines))))
    assert (divergence.index, divergence.path) == (2, "after.f")


def test_reader_rejects_a_kind_that_contradicts_its_state() -> None:
    stream = io.StringIO()
    write_trace(_records(1), stream)
    value = json.loads(stream.getvalue())
    value["kind"] = "halt_idle"
    with pytest.raises(ValueError, match="contradicts"):
        list(read_trace(io.StringIO(json.dumps(value))))


def test_a_session_trace_carries_the_bus_accesses() -> None:
    cpu = machine_with(PROGRAM, sp=0x8000)
    session = DebugSession(cpu, peek_byte=cpu.memory.__getitem__, track_accesses=True)
    records = list(iter_session_steps(session, max_steps=2))
    assert records[0].accesses == (("r", 0x0100, 0x3E), ("r", 0x0101, 0x2A))

    stream = io.StringIO()
    write_trace(records, stream)
    assert json.loads(stream.getvalue().splitlines()[0])["accesses"] == [
        ["r", 256, 62],
        ["r", 257, 42],
    ]
    stream.seek(0)
    assert list(read_trace(stream)) == records


def test_accesses_are_compared_only_when_both_traces_have_them() -> None:
    cpu = machine_with(PROGRAM, sp=0x8000)
    session = DebugSession(cpu, peek_byte=cpu.memory.__getitem__, track_accesses=True)
    tracked = list(iter_session_steps(session, max_steps=3))
    untracked = _records(3)
    # Same execution, one trace without bus records: no divergence.
    assert first_trace_divergence(tracked, untracked) is None

    wrong = [
        replace(tracked[0], accesses=(("r", 0x0100, 0x00),)),
        *tracked[1:],
    ]
    divergence = first_trace_divergence(tracked, wrong)
    assert (divergence.index, divergence.path) == (0, "accesses")
