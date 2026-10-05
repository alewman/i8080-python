#!/usr/bin/env python3
"""Produce MAME 0.285's per-instruction trace of ``invaders`` for rung 5.

Runs the recipe in docs/mame-oracle.md in a fresh directory (default
``tests/mame_traces/run60``, gitignored) and leaves ``error.log`` there. The
ROM set is read in place through ``-rompath``; nothing is copied.

    python scripts/mame_trace.py [--seconds 1] [--out DIR]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAME = os.environ.get("MAME", "mame")
#: MAME's ROM search path; the set is read in place, never copied here.
ROMPATH = os.environ.get("MAME_ROMPATH", ".")
TRACE_LUA = """\
local dbg = manager.machine.debugger
dbg.visible_cpu = manager.machine.devices[":maincpu"]
dbg:command('trace invaders.trace,,noloop,{logerror "%X %X %X %X %X %X %X %X %X %X %d %d %d\\n",\
pc,a,f,b,c,d,e,h,l,sp,totalcycles,beamy,frame}')
dbg:command("go")
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seconds", type=int, default=1, help="emulated seconds (60 frames each)")
    parser.add_argument("--out", type=Path, default=ROOT / "tests" / "mame_traces" / "run60")
    parser.add_argument("--mame", default=MAME)
    parser.add_argument("--rompath", default=ROMPATH)
    args = parser.parse_args()

    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "trace.lua").write_text(TRACE_LUA, encoding="utf-8")
    version = subprocess.run(
        [args.mame, "-version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # error.log lands in the working directory, not under -homepath.
    subprocess.run(
        [args.mame, "invaders", "-rompath", args.rompath, "-homepath", str(out),
         "-video", "none", "-sound", "none", "-nothrottle", "-noreadconfig",
         "-skip_gameinfo", "-debug", "-debugger", "none", "-log",
         "-seconds_to_run", str(args.seconds), "-autoboot_script", str(out / "trace.lua")],
        cwd=out, check=True, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    lines = sum(1 for _ in (out / "error.log").open(encoding="utf-8-sig"))
    print(f"MAME {version}: {out / 'error.log'} ({lines:,} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
