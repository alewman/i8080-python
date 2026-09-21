"""DebugSession: records, breakpoints, bounded runs, access tracking, watchpoints."""

from __future__ import annotations

import pytest
from conftest import machine_with

from i8080_python import I8080CPU
from i8080_python.debug import BoundaryKind, DebugSession, StopReason, next_boundary

# MVI A,2AH; STA 2000H; EI; HLT
PROGRAM = [0x3E, 0x2A, 0x32, 0x00, 0x20, 0xFB, 0x76]


def session_for(program=PROGRAM, **kwargs):
    cpu = machine_with(program, sp=0x8000)
    return DebugSession(cpu, peek_byte=cpu.memory.__getitem__, **kwargs), cpu


def test_step_records_carry_the_instruction_and_both_states() -> None:
    session, _ = session_for()
    record = session.step()
    assert record.sequence == 0
    assert record.kind is BoundaryKind.INSTRUCTION
    assert record.instruction.text == "MVI A,2AH"
    assert (record.before.a, record.after.a) == (0, 0x2A)
    assert record.states == 7
    assert record.accesses is None  # not tracking
    assert (session.total_steps, session.total_instructions, session.total_states) == (1, 1, 7)


def test_lifecycle_boundaries_have_no_instruction() -> None:
    session, cpu = session_for()
    session.run(max_steps=10)  # runs into the HLT
    assert cpu.halted
    record = session.step()
    assert record.kind is BoundaryKind.HALT_IDLE
    assert record.instruction is None

    cpu.request_interrupt(0xCF)
    record = session.step()
    assert record.kind is BoundaryKind.INTERRUPT
    assert record.after.pc == 0x0008
    assert record.states == 11


def test_next_boundary_agrees_with_what_step_does() -> None:
    session, cpu = session_for()
    cpu.request_reset()
    assert next_boundary(cpu.capture_state()) is BoundaryKind.RESET
    assert session.step().kind is BoundaryKind.RESET


def test_run_stops_before_a_breakpoint_and_continue_steps_off_it() -> None:
    session, _ = session_for()
    session.add_breakpoint(0x0102)  # the STA
    result = session.run(max_steps=100)
    assert result.reason is StopReason.BREAKPOINT
    assert (result.steps, result.state.pc) == (1, 0x0102)
    # run() again without moving would stop again; a step gets past it.
    session.step()
    assert session.run(max_steps=100).reason is StopReason.HALTED


def test_run_limits() -> None:
    session, _ = session_for()
    assert session.run(max_steps=2).reason is StopReason.STEP_LIMIT
    session, _ = session_for()
    result = session.run(max_steps=100, max_states=10)
    assert result.reason is StopReason.STATE_LIMIT
    assert result.states >= 10  # the boundary that crossed the limit still ran
    with pytest.raises(ValueError):
        session.run(max_steps=0)


def test_halt_stops_a_run_unless_asked_not_to() -> None:
    session, _ = session_for()
    assert session.run(max_steps=100).reason is StopReason.HALTED
    assert session.run(max_steps=3, stop_on_halt=False).reason is StopReason.STEP_LIMIT


def test_tracking_records_every_access_in_order() -> None:
    session, _ = session_for(track_accesses=True)
    assert session.tracking
    assert session.step().accesses == (("r", 0x0100, 0x3E), ("r", 0x0101, 0x2A))
    assert session.step().accesses == (
        ("r", 0x0102, 0x32),
        ("r", 0x0103, 0x00),
        ("r", 0x0104, 0x20),
        ("w", 0x2000, 0x2A),
    )


def test_tracking_records_port_accesses() -> None:
    cpu = machine_with([0xDB, 0x03, 0xD3, 0x05], a=0x11)
    cpu.port_values[0x03] = 0x5A
    session = DebugSession(cpu, track_accesses=True)
    assert session.step().accesses[-1] == ("in", 0x03, 0x5A)
    assert session.step().accesses[-1] == ("out", 0x05, 0x5A)


def test_close_puts_the_original_bus_back() -> None:
    session, cpu = session_for(track_accesses=True)
    wrapped = cpu.read_byte
    session.close()
    assert not session.tracking
    assert cpu.read_byte is not wrapped
    assert cpu.read_byte(0x0100) == 0x3E
    assert session.step().accesses is None


def test_watchpoints_stop_after_the_step_that_touched_the_byte() -> None:
    session, _ = session_for(track_accesses=True)
    session.add_watchpoint(0x2000, "w")
    result = session.run(max_steps=100)
    assert result.reason is StopReason.WATCHPOINT
    assert result.hits == (("w", 0x2000, 0x2A),)
    assert result.last_record.instruction.text == "STA 2000H"


def test_a_read_watchpoint_ignores_writes() -> None:
    session, _ = session_for(track_accesses=True)
    session.add_watchpoint(0x2000, "r")
    assert session.run(max_steps=100).reason is StopReason.HALTED


def test_watchpoints_need_tracking() -> None:
    session, _ = session_for()
    with pytest.raises(ValueError, match="track_accesses=True"):
        session.add_watchpoint(0x2000)


def test_history_is_bounded_and_ordered() -> None:
    session, _ = session_for(history_limit=2)
    session.run(max_steps=4)
    assert len(session.history) == 2
    assert [record.sequence for record in session.iter_history()] == [2, 3]
    assert [record.sequence for record in session.iter_history(newest_first=True)] == [3, 2]
    session.clear_history()
    assert session.history == ()


def test_a_board_target_is_driven_and_its_cpu_is_the_tracked_one() -> None:
    class Board:
        """A target whose step() runs a device around one CPU step."""

        def __init__(self) -> None:
            self.memory = bytearray(0x10000)
            self.memory[0:2] = bytes((0x3E, 0x2A))
            self.cpu = I8080CPU(self.memory.__getitem__, self.memory.__setitem__)
            self.ticks = 0

        def step(self) -> int:
            states = self.cpu.step()
            self.ticks += states
            return states

        def capture_state(self):
            return self.cpu.capture_state()

    board = Board()
    session = DebugSession(board, peek_byte=board.memory.__getitem__, track_accesses=True)
    record = session.step()
    assert session.cpu is board.cpu
    assert board.ticks == 7
    assert record.accesses == (("r", 0, 0x3E), ("r", 1, 0x2A))


def test_a_target_without_the_protocol_is_refused() -> None:
    with pytest.raises(TypeError):
        DebugSession(object())
