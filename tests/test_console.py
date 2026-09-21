"""The command debugger and the ``python -m i8080_python`` front end."""

from __future__ import annotations

import io

import pytest
from conftest import machine_with

from i8080_python.console import CommandDebugger, CommandError, format_flags
from i8080_python.debug import DebugSession

# MVI A,2AH; CALL 0110H; HLT ... at 0x0110: INR A; RET
PROGRAM = [0x3E, 0x2A, 0xCD, 0x10, 0x01, 0x76]


def debugger_for(program=PROGRAM, *, track=True, **kwargs):
    cpu = machine_with(program, sp=0x8000, **kwargs)
    cpu.load(0x0110, 0x3C, 0xC9)
    session = DebugSession(cpu, peek_byte=cpu.memory.__getitem__, track_accesses=track)
    return CommandDebugger(session), cpu


def run(debugger, command: str) -> str:
    return "\n".join(debugger.execute(command).lines)


def test_registers_and_flag_letters() -> None:
    debugger, _ = debugger_for()
    lines = run(debugger, "r")
    assert "A=00 F=02" in lines
    assert "INTE=0 INT=-- EI_DELAY=0 HALT=0 RESET=0" in lines
    # F reads S Z 0 AC 0 P 1 CY, so a cleared byte still shows the fixed bit 1.
    assert format_flags(0x02) == "------1-"
    assert format_flags(0xD7) == "SZ-A-P1C"


def test_step_and_history() -> None:
    debugger, _ = debugger_for()
    assert "MVI A,2AH" in run(debugger, "step")
    assert run(debugger, "s 1").endswith("-> PC=0110 +17")  # into the CALL
    assert len(run(debugger, "history").splitlines()) == 2
    assert run(debugger, "history 1").count("#") == 1


def test_over_runs_a_call_through_to_its_return() -> None:
    debugger, cpu = debugger_for()
    debugger.execute("step")  # MVI
    lines = run(debugger, "over")
    assert cpu.pc == 0x0105  # back after the CALL
    assert cpu.a == 0x2B  # the INR A inside ran
    assert "CALL 0110H" in lines


def test_breakpoints_and_continue() -> None:
    debugger, cpu = debugger_for()
    assert run(debugger, "break 0x0110") == "breakpoint at 0110"
    assert "breakpoint" in run(debugger, "continue")
    assert cpu.pc == 0x0110
    assert run(debugger, "breakpoints") == "break 0110"
    # continue steps off the breakpoint it is sitting on, then runs to the HLT.
    assert "halted" in run(debugger, "c")
    assert run(debugger, "delete 0x0110").endswith("removed")
    assert run(debugger, "breakpoints") == "no breakpoints or watchpoints"


def test_watch_stops_the_run_and_lists_with_breakpoints() -> None:
    debugger, _ = debugger_for([0x3E, 0x2A, 0x32, 0x00, 0x20, 0x76])
    assert run(debugger, "watch 0x2000 w") == "watch 2000 w"
    assert run(debugger, "breakpoints") == "watch 2000 w"
    output = run(debugger, "run 100")
    assert "watchpoint" in output
    assert "w 2000 = 2A" in output
    assert run(debugger, "unwatch 0x2000").endswith("removed")


def test_watch_without_tracking_is_a_command_error() -> None:
    debugger, _ = debugger_for(track=False)
    with pytest.raises(CommandError, match="track_accesses"):
        debugger.execute("watch 0x2000")


def test_disassemble_and_memory() -> None:
    debugger, _ = debugger_for()
    lines = run(debugger, "d 0x0100 3").splitlines()
    assert lines[0].endswith("MVI A,2AH")
    assert lines[1].endswith("CALL 0110H")
    assert run(debugger, "m 0x0100 4") == "0100  3E 2A CD 10"


def test_set_registers_and_pairs() -> None:
    debugger, cpu = debugger_for()
    run(debugger, "set a 0x7F")
    run(debugger, "set h16 0x1234")
    run(debugger, "set psw 0xAAFF")
    run(debugger, "set pc 0x0200")
    assert (cpu.a, cpu.h, cpu.l, cpu.pc) == (0xAA, 0x12, 0x34, 0x0200)
    assert cpu.f.byte == 0xD7  # the flag byte keeps its fixed bits
    with pytest.raises(CommandError, match="no register IX"):
        debugger.execute("set ix 1")


def test_int_and_reset() -> None:
    debugger, cpu = debugger_for()
    assert run(debugger, "int 0xCF") == "INT asserted, device supplies CF"
    assert cpu.interrupt_pending
    assert run(debugger, "int off") == "INT deasserted"
    with pytest.raises(CommandError):
        debugger.execute("int 0xCD")  # multi-byte injection is refused
    cpu.a = 0x55
    lines = run(debugger, "reset")
    assert "<reset>" in lines
    assert (cpu.pc, cpu.a, cpu.reset_pending) == (0, 0x55, False)


def test_errors_and_help() -> None:
    debugger, _ = debugger_for()
    assert run(debugger, "help").startswith("help | ?")
    assert debugger.execute("").lines == ()
    with pytest.raises(CommandError, match="unknown command"):
        debugger.execute("frobnicate")
    with pytest.raises(CommandError, match="expects"):
        debugger.execute("break")
    with pytest.raises(CommandError, match="must be an integer"):
        debugger.execute("break zz")


def test_interact_loop_reads_until_quit() -> None:
    debugger, _ = debugger_for()
    output = io.StringIO()
    debugger.interact(io.StringIO("step\nbogus\nquit\nstep\n"), output)
    text = output.getvalue()
    assert "MVI A,2AH" in text
    assert "error: unknown command: bogus" in text
    assert text.count("8080> ") == 3  # the loop ended at quit


def test_cli_batch_run(tmp_path, capsys) -> None:
    from i8080_python.__main__ import main

    image = tmp_path / "program.bin"
    image.write_bytes(bytes(PROGRAM))
    main(["--load", f"{image}@0x100", "--pc", "0x100", "--batch", "-c", "step 2", "-c", "r"])
    out = capsys.readouterr().out
    assert "MVI A,2AH" in out
    assert "CALL 0110H" in out
    assert "A=2A" in out


def test_over_also_runs_rst_through_and_leaves_an_untaken_call_alone() -> None:
    # RST 1 at 0x0100, then CZ 0120H with Z clear (not taken).
    debugger, cpu = debugger_for([0xCF, 0xCC, 0x20, 0x01, 0x00])
    cpu.load(0x0008, 0x3C, 0xC9)  # INR A; RET
    assert "RST 1" in run(debugger, "over")
    assert (cpu.pc, cpu.a, cpu.sp) == (0x0101, 0x01, 0x8000)
    assert "CZ 0120H" in run(debugger, "over")
    assert (cpu.pc, cpu.sp) == (0x0104, 0x8000)  # one step, nothing pushed
