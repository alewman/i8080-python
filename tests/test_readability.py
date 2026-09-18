"""Readability contract for the instruction core, enforced the way correctness is.

Carried over from z80-python's contract. Every opcode handler must be findable
by the mnemonic an 8080 programmer would grep for, and must live in the module
for its group in Intel's instruction-set chapter [UM ch. 4]. Checked from the
source with :mod:`ast`, without importing or executing it:

1. Every ``_op_*`` method has a docstring whose first line starts with one or
   more Intel mnemonics (``LHLD a16``, ``JNZ/JZ/... a16``).
2. Every handler lives in the module that owns its mnemonic group.
3. Every Intel mnemonic is claimed by at least one handler, and no handler name
   is defined twice across the mixins (the MRO would silently shadow one).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "i8080_python"

#: Intel's instruction groups [UM ch. 4], one private module each.
OWNERS: dict[str, frozenset[str]] = {
    module: frozenset(mnemonics.split())
    for module, mnemonics in {
        "_transfer.py": "MOV MVI LXI LDA STA LHLD SHLD LDAX STAX XCHG",
        "_arithmetic.py": "ADD ADC SUB SBB ADI ACI SUI SBI INR DCR INX DCX DAD DAA",
        "_logical.py": "ANA XRA ORA CMP ANI XRI ORI CPI RLC RRC RAL RAR CMA CMC STC",
        "_branch.py": "JMP JNZ JZ JNC JC JPO JPE JP JM CALL CNZ CZ CNC CC CPO CPE CP CM "
        "RET RNZ RZ RNC RC RPO RPE RP RM RST PCHL",
        "_machine.py": "PUSH POP XTHL SPHL IN OUT EI DI HLT NOP",
    }.items()
}
INTEL_MNEMONICS = frozenset().union(*OWNERS.values())

_HEADLINE = re.compile(r"^(?P<mnemonics>[A-Z]+(?:/[A-Z]+)*)(?P<rest>(?:\s.*)?)$")


class Handler:
    """One ``_op_*`` method as found in the source."""

    def __init__(self, module: str, node: ast.FunctionDef) -> None:
        self.module = module
        self.name = node.name
        self.lineno = node.lineno
        self.docstring = ast.get_docstring(node, clean=True)

    @property
    def location(self) -> str:
        return f"{self.module}:{self.lineno} {self.name}"

    def mnemonics(self) -> list[str]:
        headline = (self.docstring or "").splitlines()[0] if self.docstring else ""
        match = _HEADLINE.match(headline.split(" -- ", 1)[0].strip())
        if match is None:
            raise AssertionError(
                f"{self.location}: docstring must start with an Intel mnemonic (got {headline!r})"
            )
        return match.group("mnemonics").split("/")


def _handlers() -> list[Handler]:
    found: list[Handler] = []
    for path in sorted(SRC.glob("_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            found.extend(
                Handler(path.name, node)
                for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name.startswith("_op_")
            )
    assert found, f"no _op_* handlers found under {SRC}"
    return found


HANDLERS = _handlers()


def test_the_vocabulary_is_intels_78_mnemonics() -> None:
    assert sum(len(owned) for owned in OWNERS.values()) == len(INTEL_MNEMONICS) == 78


@pytest.mark.parametrize("handler", HANDLERS, ids=lambda h: f"{h.module}::{h.name}")
def test_handler_docstring_starts_with_intel_mnemonic(handler: Handler) -> None:
    assert handler.docstring, f"{handler.location}: opcode handler has no docstring"
    unknown = [m for m in handler.mnemonics() if m not in INTEL_MNEMONICS]
    assert not unknown, f"{handler.location}: not Intel mnemonics: {unknown}"


@pytest.mark.parametrize("handler", HANDLERS, ids=lambda h: f"{h.module}::{h.name}")
def test_handler_lives_in_owning_module(handler: Handler) -> None:
    owned = OWNERS.get(handler.module)
    assert owned is not None, f"{handler.location}: {handler.module} is not a handler module"
    strays = [m for m in handler.mnemonics() if m not in owned]
    assert not strays, f"{handler.location}: {strays} do not belong in {handler.module}"


def test_every_intel_mnemonic_has_a_greppable_handler() -> None:
    claimed = {m for handler in HANDLERS for m in handler.mnemonics()}
    missing = sorted(INTEL_MNEMONICS - claimed)
    assert not missing, f"no handler docstring names these mnemonics: {missing}"


def test_handler_names_are_unique_across_mixins() -> None:
    seen: dict[str, str] = {}
    duplicates = []
    for handler in HANDLERS:
        if handler.name in seen:
            duplicates.append(f"{handler.name} in {seen[handler.name]} and {handler.module}")
        seen[handler.name] = handler.module
    assert not duplicates, "handlers shadowed by the mixin MRO: " + "; ".join(duplicates)
