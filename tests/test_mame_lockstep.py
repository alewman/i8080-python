"""Rung 5: lockstep against MAME 0.285 on ``invaders`` (emulator-derived detector).

The full comparison needs MAME's trace (``python scripts/mame_trace.py``) and
the ``invaders`` ROM set in place; without them it skips. The board-timing
helpers are checked unconditionally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validation.mame_lockstep import (
    CYCLE_AS,
    DEFAULT_ROM_ZIP,
    SCANLINE_AS,
    interrupt_vector,
    line_at,
    lockstep,
    vertical_counter,
)

TRACE = Path(__file__).resolve().parent / "mame_traces" / "run60" / "error.log"


def test_vectors_follow_64v() -> None:
    assert vertical_counter(96) == 0x80
    assert vertical_counter(224) == 0xDA
    assert interrupt_vector(96) == 0xCF  # RST 1, mid-screen
    assert interrupt_vector(224) == 0xD7  # RST 2, start of VBLANK
    assert interrupt_vector(63) == 0xD7  # counter 0x5F: the game's first acceptance


def test_mame_periods_put_each_trigger_one_state_early() -> None:
    # A 128-state line is 128 as longer than a scanline in MAME's truncated
    # periods, so a trigger is seen one state before the whole-number position.
    assert 128 * CYCLE_AS - SCANLINE_AS == 128
    frame = 262 * SCANLINE_AS
    assert (13 * frame) // CYCLE_AS == 13 * 33_536 - 1
    assert line_at(134 * SCANLINE_AS) == 96


def test_lockstep_60_frames() -> None:
    if not TRACE.exists() or not DEFAULT_ROM_ZIP.exists():
        pytest.skip("needs the MAME trace (python scripts/mame_trace.py) and invaders.zip")
    result = lockstep(TRACE)
    assert result.divergence is None, result.divergence
    assert result.lines == 230_313
