"""The JSON Lines conformance trace."""

from __future__ import annotations

import io
import json

import pytest
from conftest import machine_with

from i8080_python.trace import (
    BoundaryKind,
    first_trace_divergence,
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
