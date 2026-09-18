"""Rungs 2 and 3: the CP/M exercisers under the ``cpm-minimal`` host.

The programs are fetched, hash-pinned, into the gitignored tests/exercisers/
by ``python scripts/fetch_exercisers.py``; without them these tests skip.
8080PRE and TST8080 take a fraction of a second and run by default. 8080EXM
(the hardware-captured CRCs) is ~2.9 billion instructions: minutes under PyPy,
hours under CPython, so it runs only with ``-m slow``. CPUTEST is proprietary
and fetched only on request; it is also ``slow``.

Each run is also checked against superzazu/8080's published state totals,
converted to its accounting (``CPMResult.superzazu_states``). Those totals are
emulator-derived: they are a detector, and they agree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from validation.cpm import PROGRAMS, SUPERZAZU_STATES, failures, run_com

EXERCISERS = Path(__file__).resolve().parent / "exercisers"


def _run(name: str) -> None:
    path = EXERCISERS / name
    if not path.exists():
        pytest.skip(f"{name} not fetched; run python scripts/fetch_exercisers.py")
    result = run_com(path.read_bytes(), max_instructions=PROGRAMS[name][0])
    assert failures(name, result.output) == [], result.output
    assert result.superzazu_states == SUPERZAZU_STATES[name]


def test_8080pre() -> None:
    _run("8080PRE.COM")


def test_tst8080() -> None:
    _run("TST8080.COM")


@pytest.mark.slow
def test_8080exm_hardware_crcs() -> None:
    _run("8080EXM.COM")


@pytest.mark.slow
def test_cputest() -> None:
    _run("CPUTEST.COM")
