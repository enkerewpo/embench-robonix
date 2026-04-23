# eb_navigate

High-level navigation skill for EB-Habitat (Language Rearrangement / Habitat 2.0).

## What this skill exposes

A single MCP tool, `navigate(target: str) -> bool`.

`target` must be the name of a **receptacle object** currently in the scene — e.g. `"counter"`, `"kitchen_counter"`, `"fridge"`, `"bathroom_cabinet"`. EB-Habitat restricts navigation to receptacles, not arbitrary pickable items, so call `describe_scene` from `eb_observe` first if unsure which names are valid.

Returns `True` once the agent is positioned such that the receptacle is reachable for a subsequent `pick`/`place`/`open`/`close`. Returns `False` on name lookup failure or unreachable goal.

## Preconditions

- Robonix env bridge (`env_adapter.py`) is running and connected to an initialized EB-Habitat scene.
- `target` is a receptacle-type name returned by `describe_scene()`.

## Post-conditions

- Robot end-effector / base is positioned adjacent to `target`.
- Episode step counter advanced.
- On success, subsequent manipulation skills can act on `target`.

## Failure modes

- Unknown receptacle name → return `False`, no step consumed.
- Path blocked → return `False`, step(s) consumed.
- Pilot should plan an alternate receptacle or re-observe the scene.

## Notes for planners

This is **high-level** navigation — no low-level velocity / heading commands. Each call is one atomic action in the benchmark's action space.
