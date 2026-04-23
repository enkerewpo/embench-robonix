# eb_manipulate

High-level manipulation skills for EB-Habitat: `pick`, `place`, `open`, `close`.

## MCP tools

- `pick(object: str) -> bool` — grasp the named pickable item from the currently-active receptacle. Requires the agent to have navigated to the right receptacle first.
- `place(object: str, receptacle: str) -> bool` — put a currently-held object on/in a receptacle the agent is next to.
- `open(receptacle: str) -> bool` — open a door / drawer / fridge. Receptacle must be reachable (agent navigated to it).
- `close(receptacle: str) -> bool` — inverse of `open`.

All four are parameterized by scene object names. Use `describe_scene` from `eb_observe` for the authoritative list.

## Preconditions

- Env bridge running.
- `navigate` has placed the agent at the relevant receptacle before `pick`/`open`/`close`.
- For `pick`: the object name is currently in a reachable receptacle. For `place`: the robot is holding an object and the target receptacle is reachable.

## Post-conditions

- Robot state updated: held object set/cleared, receptacle open/close state flipped, etc.
- Episode step counter advanced.
- Task success flag is re-evaluated by the env; Pilot should check after each step.

## Failure modes

- Wrong receptacle currently active → `False`, planner should re-`navigate`.
- Object not present or already held → `False`.
- `open`/`close` on a non-articulated receptacle → `False`.

## Notes for planners

Typical task decomposition: `navigate(src)` → `pick(obj)` → `navigate(dst)` → `place(obj, dst)`. For tasks requiring container access, insert `open` / `close` around the pick.
