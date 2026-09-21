# Documents

Reading order for someone who wants to understand, check, or port the core:

1. [start-here.md](start-here.md): the 8080A as the core models it.
   Register file, the PSW byte and its three fixed bits, opcode bit fields,
   the full instruction table with encodings and state counts, the interrupt
   model, DAA and the auxiliary carry, and the undocumented opcodes.
2. [timing.md](timing.md): where each state count comes from (machine cycles
   and T-states), and what a Space Invaders host needs: 1.9968 MHz, 33,536
   states per frame, `RST 1` on line 96 and `RST 2` on line 224.
3. [undocumented-behavior.md](undocumented-behavior.md): the undocumented
   opcodes and every flag result the manuals do not fully specify, each with
   its evidence and tier, and `[unverified]` where only inferred.
4. [validation.md](validation.md): the claim and the certification record
   (commit, hashes, interpreters, timings), then every oracle found for the
   8080 with its tier, license, URL, pinned revision and SHA-256, what it
   covers and cannot, and the harness that runs them.
5. [mame-oracle.md](mame-oracle.md): a verified MAME 0.285 command line and
   Lua script that log registers per instruction for `invaders`, the output
   formats, and how to diff a Python core against it.
6. [trace-schema.md](trace-schema.md): the JSON Lines conformance trace, the
   contract a port in another language produces to be compared with this
   core.
7. [debug-session.md](debug-session.md): stepping, breakpoints, watchpoints,
   bus-access tracking, the console commands and `python -m i8080_python`.
8. [handoff-brief.md](handoff-brief.md): the brief the core was built from,
   kept as written: milestones with acceptance tests in oracle-tier order.

The oracle-tier rule used throughout: rank oracles by where their expected
values came from, hardware-captured above hardware-corrected above
emulator-derived; a low-tier oracle is a detector, never a judge.
