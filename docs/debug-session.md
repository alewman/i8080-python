# Debugging: sessions, the console, and the CLI

Three layers, each usable on its own, all outside the core: `DebugSession`
drives a CPU one boundary at a time and records what happened;
`CommandDebugger` is a text frontend over a session; `python -m i8080_python`
loads a program into a flat machine and starts one. None of them changes what
the core does. The shape and the command names are z80-python's and
m6800-python's, so a session written for one core reads like a session
written for another.

## DebugSession

```python
from i8080_python import DebugSession, I8080CPU

memory = bytearray(0x10000)
memory[0x0100:0x0103] = bytes((0x3E, 0x2A, 0x76))  # MVI A,2AH; HLT
cpu = I8080CPU(memory.__getitem__, memory.__setitem__)
cpu.pc = 0x0100

session = DebugSession(cpu, peek_byte=memory.__getitem__, track_accesses=True)
record = session.step()
record.instruction.text  # 'MVI A,2AH'
record.states  # 7
record.accesses  # (('r', 256, 62), ('r', 257, 42))
```

- **`step()`** returns a `StepRecord`: `sequence`, `kind`, `before`, `after`,
  `states`, `instruction` (`None` on a lifecycle boundary, or when no
  `peek_byte` was given), and `accesses`.
- **`run(max_steps=..., max_states=None, stop_on_halt=True)`** returns a
  `RunResult` whose `reason` is one of `breakpoint`, `watchpoint`, `halted`,
  `step_limit`, `state_limit`. The step budget is mandatory and finite. A
  state limit is checked after each boundary, so it can be exceeded by that
  boundary's cost.
- **Breakpoints** (`add_breakpoint`, `remove_breakpoint`) stop *before* the
  instruction at an address; `run()` therefore returns without moving when it
  is already there, and the console's `continue` steps off first.
- **Watchpoints** (`add_watchpoint(address, "r" | "w" | "rw")`) stop *after*
  the step that touched the byte, and the hits are in `RunResult.hits`. They
  need `track_accesses=True`.
- **`peek_byte`** must be side-effect-free: the host's memory, not its bus.
- **History** is a bounded ring (`history_limit`, default 256), read with
  `history` or `iter_history(newest_first=...)`.

### Access tracking

`track_accesses=True` replaces the CPU's four bus callables with wrappers that
append to a list, which is why 0.2.0 made the bus callables ordinary
attributes. Each access is `("r" | "w", address, value)` for memory and
`("in" | "out", port, value)` for I/O, in the order the step made them.
`close()` puts the original callables back; until then the wrappers stay, so a
session that tracks should be closed when the program is done with it.

The target may be a **board** rather than a bare CPU: any object with `step()`
and `capture_state()`. If it has a `cpu` attribute, that is the processor
whose bus is tracked, so a board whose `step()` also runs its devices can be
debugged as one unit.

## The console

`CommandDebugger(session).execute(line)` returns printable lines;
`interact(stdin, stdout)` is a loop with no terminal dependencies. `help`
lists the commands:

| Command | What it does |
| --- | --- |
| `registers` / `regs` / `r` | Registers, the flag letters `S Z 0 AC 0 P 1 CY`, and INTE/INT/EI_DELAY/HALT/RESET |
| `step [COUNT]` / `s` | Execute boundaries, ignoring breakpoints |
| `over` / `o` | Step, running a `CALL`, `Ccc` or `RST` through to its return |
| `run STEPS [STATES]`, `continue` / `c` | Bounded run; `continue` is 1,000,000 steps and steps off a breakpoint first |
| `break` / `delete` / `breakpoints` | Execute breakpoints; the listing includes watchpoints |
| `watch ADDRESS [r\|w\|rw]`, `unwatch` | Memory watchpoints |
| `disassemble [ADDRESS] [COUNT]` / `d`, `memory ADDRESS [LENGTH]` / `m` | Read without side effects |
| `history [COUNT]` | Retained step records |
| `set REGISTER VALUE` | `A F B C D E H L PSW B16 D16 H16 SP PC`; `F` and `PSW` keep the flag byte's fixed bits |
| `int BYTE`, `int off` | Assert INT with the byte a device supplies (`int CF` is `RST 1`), or drop it |
| `reset` | Pulse RESET: assert, run the one boundary that services it, release |

Numbers are decimal; `0x1234` or `$1234` is hexadecimal.

## The CLI

```text
python -m i8080_python --load 8080pre.com@0x100 --pc 0x100
python -m i8080_python --zip "ROMs/invaders.zip:9316b-0869_m739h.h1@0" -c "d 0 20" --batch
```

The machine is flat 64 KiB RAM holding every image loaded, with nothing on the
I/O bus (`IN` reads 0xFF, `OUT` goes nowhere), and accesses tracked so `watch`
works. It is for reading and stepping through code, not for running a
machine: a real board is a host of its own, as `validation/mame_lockstep.py`
is. `-c` commands run first; `--batch` exits after them instead of reading
stdin.

## Traces

`iter_session_steps(session, max_steps=N)` yields the same records for
[write_trace](trace-schema.md), so a trace taken through a tracking session
carries its `accesses` array. `trace_steps(cpu, peek, max_steps=N)` is the
lighter path when the bus does not matter.
