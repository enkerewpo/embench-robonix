# eb_observe

Scene inspection for the planner. Not an action skill — calling it doesn't advance the episode.

## MCP tools

- `describe_scene() -> dict` — returns:
  ```json
  {
    "receptacles": ["counter", "fridge", "kitchen_counter", ...],
    "pickable_objects": ["apple_0", "bowl_0", ...],
    "agent_holding": "apple_0" | null,
    "agent_near": "fridge" | null,
    "open_state": {"fridge": false, "cabinet_1": true}
  }
  ```

Use this at the start of each task and whenever the planner needs to ground an object name before dispatching a manipulation skill.

## Preconditions

- Env bridge running, task reset.

## Post-conditions

- **None**. This call is free: no env step consumed, no state changed.

## Notes for planners

Prefer calling this once at task start + after major state changes (e.g. after opening a container that revealed new pickables). Don't spam it.
