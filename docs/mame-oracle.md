# MAME 0.285 as an emulator-derived oracle for `invaders`

MAME's 8080 core (`src/devices/cpu/i8085/i8085.cpp`, device `I8080`) running
the real Space Invaders program is the one oracle here that exercises
interrupts, ports, and the state counter over a long real workload. It is
**tier 3, emulator-derived**: use it to find where a Python core first
disagrees, then settle the disagreement with the datasheet and the
hardware-captured CRCs in [validation.md](validation.md).

Everything on this page was run on 2026-09-11 and again on 2026-09-12 on this
machine with MAME 0.285 at `/usr/games/mame` and the non-merged ROM set at
`/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)/invaders.zip`,
used in place via `-rompath` and never copied. No ROM bytes, and no trace
log, are in this repository (`*.trace` and `error.log` are gitignored).

## The recipe

Write this Lua script (path `trace.lua` in a throwaway working directory):

```lua
local dbg = manager.machine.debugger
dbg.visible_cpu = manager.machine.devices[":maincpu"]
dbg:command('trace invaders.trace,,noloop,{logerror "%X %X %X %X %X %X %X %X %X %X %d %d %d\n",pc,a,f,b,c,d,e,h,l,sp,totalcycles,beamy,frame}')
dbg:command("go")
```

Run, from that same directory:

```text
/usr/games/mame invaders \
  -rompath "/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)" \
  -homepath "$PWD" -video none -sound none -nothrottle -noreadconfig \
  -skip_gameinfo -debug -debugger none -log -seconds_to_run 1 \
  -autoboot_script "$PWD/trace.lua"
```

It exits by itself after one emulated second (60 frames) with exit status 0,
having written two files:

| File | Where | What |
| --- | --- | --- |
| `error.log` | the **current working directory** (`-log` writes there, not next to `-homepath`; verified by running with the two different) | one line per executed instruction from the `logerror` action, after a first line `Soft reset` that begins with a UTF-8 byte-order mark |
| `invaders.trace` | the path given to `trace`, relative to the working directory | MAME's own disassembly trace: `PC: mnemonic operands`, with `(interrupted at XXXX, IRQ 0)` markers |

Also created under `-homepath`: `cfg/` and `snap/`. Use a fresh directory per
run; a second run overwrites `error.log`.

Facts confirmed by these runs that another session had established:

- `-debugger none` is required; without it MAME wants a debugger window.
- `logerror` inside the trace action is the channel that works; the
  `tracelog` command is silent in this configuration; `focus` breaks actions;
  the Lua `device.debug:bpset` API segfaults. These three negatives were not
  re-tested here; the positive recipe above was.
- The ALSA `open /dev/snd/seq failed` message on stderr is harmless.
- `-seconds_to_run N` bounds the run; 1 s produced 230,314 `error.log` lines
  (one per instruction plus the header, 10.0 MB) ending at `totalcycles`
  2,012,152; 2 s produced about 447 k. Expect about 230 k instructions and
  2.0 M states per emulated second, i.e. the 1.9968 MHz clock.

## Output formats

`error.log`, first lines (the BOM is invisible here):

```text
Soft reset
0 0 0 0 0 0 0 0 0 0 0 224 0
1 0 0 0 0 0 0 0 0 0 4 224 0
2 0 0 0 0 0 0 0 0 0 8 224 0
3 0 0 0 0 0 0 0 0 0 12 224 0
18D4 0 0 0 0 0 0 0 0 0 22 224 0
18D7 0 0 0 0 0 0 0 0 2400 32 224 0
18D9 0 0 0 0 0 0 0 0 2400 39 224 0
```

Columns, space separated: `pc a f b c d e h l sp` in uppercase hex **without
leading zeros** (`%X`), then `totalcycles beamy frame` in decimal. Each line
is the state **before** the instruction at `pc` executes (the debugger hook
fires before `execute_one`), so `totalcycles` on a line minus the previous
line's is the previous instruction's state count: above, `jmp` 10, `lxi sp`
10, `mvi b` 7, then `call` 17 (the next line reads `1E6 ... 56`).

The same moment in `invaders.trace`:

```text
0000: nop
0001: nop
0002: nop
0003: jmp  $18d4
18D4: lxi  sp,$2400
18D7: mvi  b,$00
```

Interrupt acceptance, from `error.log` (line before, line after):

```text
ADA 40 0 0 0 1F B0 3E 1 23FE 318966 95 9
8 40 0 0 0 1F B0 3E 1 23FC 318990 96 9
...
ADA 40 0 0 0 1F B0 3E 1 23FE 335356 223 9
10 40 0 0 0 1F B0 3E 1 23FC 335380 224 9
```

There is **no line for the injected `RST`**: MAME executes the vector inside
`check_for_interrupts()` without a debugger hook. The next line is the
handler entry (`0x0008` for `RST 1`, `0x0010` for `RST 2`) with SP already
decremented by 2 and the return address pushed, and its `totalcycles` is the
interrupted instruction's states plus 11. `invaders.trace` marks the same
event explicitly:

```text
   (interrupted at 0ADD, IRQ 0)

0008: push psw
```

Over the 60-frame run, every `0x0008` entry was on `beamy` 96 and every
`0x0010` entry on 224, except the game's first acceptance (frame 9, line 63,
vector `RST 2`), explained in [timing.md](timing.md). Consecutive
same-vector acceptances were 33,536 or 33,537 states apart.

## Diffing a Python core against it

1. Build the `invaders` host described in [timing.md](timing.md): the four
   2 KiB ROMs read straight out of `invaders.zip` (`9316b-0869_m739h.h1` at
   0x0000, `9316b-0856_m739g.g1` at 0x0800, `9316b-0855_m739f.f1` at 0x1000,
   `9316b-0854_m739e.e1` at 0x1800, per MAME's `ROM_LOAD` lines), 8 KiB RAM,
   a 15-bit address mask, the MB14241 shifter on ports 2/3/4, inputs idle
   (`IN 0`, `IN 1`, `IN 2` return the values MAME's default DIP/switch
   settings produce; capture them from the trace's first `IN` results rather
   than guessing), and the two interrupts at state offsets 12,288 and 28,672
   of a 33,536-state frame with a level-held request.
2. Start from RESET: PC 0, all registers 0, SP 0 (MAME's first line).
3. For each `error.log` line after `Soft reset`: compare `pc`, `a`, `b`, `c`,
   `d`, `e`, `h`, `l`, `sp` exactly; compare `f` as `(f | 0x02) & 0xD7`
   because MAME's internal F omits the fixed bit 1; compare the cumulative
   state count to `totalcycles`. On an interrupt acceptance the Python core
   emits its own `interrupt` boundary; skip it when aligning, then check the
   handler-entry line as usual.
4. Stop at the first mismatch and print the ten lines before it from both
   sides. The tenth line before a divergence is usually the cause.

`beamy` and `frame` are MAME's own screen timing and are informational; the
host's frame model should reproduce them, but only `totalcycles` is compared.

## Sources

- MAME 0.285, `src/devices/cpu/i8085/i8085.cpp`, `src/mame/midw8080/mw8080bw.cpp`,
  `mw8080bw.h`; BSD-3-Clause; <https://github.com/mamedev/mame/tree/mame0285>.
- MAME debugger expression symbols `totalcycles`, `beamy`, `frame`, and the
  `trace` command's action syntax: MAME documentation,
  <https://docs.mamedev.org/debugger/>.
