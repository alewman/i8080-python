"""Rung 4: interrupt, HLT, and RESET behavior at instruction boundaries.

No hardware oracle covers any of this (docs/validation.md); each test cites
the manual section it rests on. Where the manual leaves a choice, the test
names the choice and MAME 0.285's matching behavior, which rung 5 compares
against over a real program.
"""

from __future__ import annotations

import pytest
from conftest import machine_with

from i8080_python import HALT_IDLE_STATES

NOP, EI, DI, HLT = 0x00, 0xFB, 0xF3, 0x76
RST_1, RST_2 = 0xCF, 0xD7


def interruptible(program: list[int], **registers: int):
    cpu = machine_with(program, sp=0x8000, **registers)
    return cpu


def test_accepted_interrupt_runs_rst_in_11_states_and_pushes_the_interrupted_pc() -> None:
    # [UM ch. 2, "Interrupt Sequences"]: PC is not incremented for the
    # acknowledge fetch, so the pushed address is the next instruction's.
    cpu = interruptible([NOP, NOP])
    cpu.inte = True
    cpu.step()  # NOP at 0x0100
    cpu.request_interrupt(RST_1)
    assert cpu.step() == 11
    assert cpu.pc == 0x0008
    assert cpu.sp == 0x7FFE
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x01)


def test_acceptance_clears_inte_and_the_request() -> None:
    # [UM ch. 2]: INTE is reset when an interrupt is accepted; the service
    # routine must EI again. The acknowledge also drops the board's INT.
    cpu = interruptible([NOP])
    cpu.inte = True
    cpu.request_interrupt(RST_2)
    cpu.step()
    assert not cpu.inte
    assert not cpu.interrupt_pending
    assert cpu.pc == 0x0010


def test_ei_delay_holds_off_an_interrupt_for_one_instruction() -> None:
    # "The interrupt system is enabled following the execution of the next
    # instruction" [UM ch. 4, EI]: a request already pending before EI is
    # accepted only after the instruction that follows EI.
    cpu = interruptible([EI, NOP, NOP])
    cpu.request_interrupt(RST_1)
    assert cpu.step() == 4  # EI
    assert cpu.inte
    assert cpu.pc == 0x0101
    assert cpu.step() == 4  # the NOP after EI runs; no acceptance before it
    assert cpu.pc == 0x0102
    assert cpu.step() == 11  # accepted now
    assert cpu.pc == 0x0008
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x02)


def test_ei_then_ret_returns_before_the_interrupt() -> None:
    # The idiom the EI delay exists for: EI; RET leaves the service routine
    # before a pending interrupt can nest [UM ch. 4, EI].
    cpu = interruptible([EI, 0xC9])
    cpu.load(0x7FFE, 0x00, 0x20)
    cpu.sp = 0x7FFE
    cpu.request_interrupt(RST_1)
    cpu.step()
    cpu.step()  # RET
    assert cpu.pc == 0x2000
    assert cpu.step() == 11
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x20, 0x00)


def test_consecutive_eis_each_hold_off_the_next_boundary() -> None:
    # Each EI inhibits acceptance at its own end, so EI; EI; NOP accepts only
    # after the NOP. The manual states the rule per EI; MAME 0.285 implements
    # it by re-arming m_after_ei = 2 on every EI.
    cpu = interruptible([EI, EI, NOP, NOP])
    cpu.request_interrupt(RST_1)
    assert [cpu.step() for _ in range(3)] == [4, 4, 4]
    assert cpu.pc == 0x0103
    assert cpu.step() == 11


def test_di_takes_effect_immediately() -> None:
    cpu = interruptible([DI, NOP])
    cpu.inte = True
    cpu.step()
    cpu.request_interrupt(RST_1)
    assert cpu.step() == 4
    assert cpu.pc == 0x0102


def test_request_with_inte_clear_is_held_until_ei() -> None:
    # The arcade boards hold INT until acknowledged (docs/timing.md), so a
    # request made with interrupts disabled is delivered after EI plus one.
    cpu = interruptible([NOP, NOP, EI, NOP, NOP])
    cpu.request_interrupt(RST_2)
    for _ in range(4):
        cpu.step()
    assert cpu.interrupt_pending
    assert cpu.pc == 0x0104
    assert cpu.step() == 11
    assert cpu.pc == 0x0010


def test_clear_interrupt_withdraws_a_request() -> None:
    cpu = interruptible([NOP, NOP])
    cpu.request_interrupt(RST_1)
    cpu.clear_interrupt()
    cpu.inte = True
    assert cpu.step() == 4
    assert cpu.pc == 0x0101


def test_hlt_then_interrupt_pushes_the_address_after_hlt() -> None:
    # [ALP, HLT]: PC holds the address of the next sequential instruction, and
    # an accepted interrupt leaves the halt state [UM ch. 2, "Halt Sequences"].
    cpu = interruptible([EI, HLT, NOP])
    cpu.step()  # EI
    assert cpu.step() == 7  # HLT; the EI delay expires with it
    assert cpu.halted
    assert cpu.step() == HALT_IDLE_STATES
    cpu.request_interrupt(RST_1)
    assert cpu.step() == 11
    assert not cpu.halted
    assert cpu.pc == 0x0008
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x02)


def test_ei_hlt_with_a_pending_request_wakes_on_the_next_boundary() -> None:
    cpu = interruptible([EI, HLT])
    cpu.request_interrupt(RST_1)
    cpu.step()
    cpu.step()  # HLT executes: it is the instruction after EI
    assert cpu.halted
    assert cpu.step() == 11
    assert (cpu.memory[0x7FFF], cpu.memory[0x7FFE]) == (0x01, 0x02)


def test_hlt_with_inte_clear_never_wakes_on_int() -> None:
    # [UM ch. 2, "Halt Sequences"; ALP, HLT]: with INTE clear only RESET
    # restarts the CPU.
    cpu = interruptible([HLT])
    cpu.step()
    cpu.request_interrupt(RST_1)
    for _ in range(100):
        assert cpu.step() == HALT_IDLE_STATES
    assert cpu.halted
    assert cpu.pc == 0x0101
    assert cpu.interrupt_pending


def test_reset_clears_pc_inte_and_halt_and_nothing_else() -> None:
    # [UM ch. 2, "Start-up"]: RESET clears PC, INTE, and the halt state; the
    # other registers are not defined by RESET, so the core leaves them alone.
    cpu = interruptible([EI, HLT], a=0x11, b=0x22, c=0x33, d=0x44, e=0x55, h=0x66, l=0x77, f=0xFF)
    cpu.step()
    cpu.step()
    assert cpu.halted and cpu.inte
    before = cpu.capture_state()
    cpu.request_reset()
    assert cpu.step() == 3
    after = cpu.capture_state()
    assert (after.pc, after.inte, after.halted, after.ei_delay) == (0, False, False, 0)
    for name in ("a", "f", "b", "c", "d", "e", "h", "l", "sp"):
        assert getattr(after, name) == getattr(before, name), name


def test_reset_is_level_held_and_outranks_a_pending_interrupt() -> None:
    cpu = interruptible([NOP], at=0x0000)
    cpu.inte = True
    cpu.request_interrupt(RST_1)
    cpu.request_reset()
    assert [cpu.step() for _ in range(3)] == [3, 3, 3]
    assert cpu.pc == 0
    cpu.clear_reset()
    assert cpu.step() == 4  # INTE was cleared by RESET, so the NOP at 0 runs
    assert cpu.pc == 1


def test_a_one_byte_non_rst_instruction_can_be_injected() -> None:
    # Any byte on the bus is executed as if fetched [UM ch. 2]; with PC not
    # advanced, an injected NOP simply costs its 4 states.
    cpu = interruptible([NOP])
    cpu.inte = True
    cpu.request_interrupt(NOP)
    assert cpu.step() == 4
    assert cpu.pc == 0x0100
    assert not cpu.inte


@pytest.mark.parametrize("vector", [0xCD, 0xC3, 0x3E])
def test_multi_byte_injection_is_refused(vector: int) -> None:
    # The 8228's three-byte CALL injection [UM ch. 5] is a stated limitation.
    cpu = interruptible([NOP])
    with pytest.raises(NotImplementedError):
        cpu.request_interrupt(vector)


def test_capture_state_reports_the_ei_delay_window() -> None:
    cpu = interruptible([EI, NOP])
    cpu.step()
    assert cpu.capture_state().ei_delay == 1
    cpu.step()
    assert cpu.capture_state().ei_delay == 0
