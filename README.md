# embench-robonix

Phase A validation: can Robonix's two-layer agent (Pilot planner + Executor) plug into the EmbodiedBench EB-Habitat benchmark via its skill/capability layer?

## Goal

Drive 20 EB-Habitat tasks through Robonix, logging success rate and per-task traces. The point is to prove the architecture composes with an existing embodied-agent benchmark — not to claim a win. Baseline comparison (vs. ReAct / ReAct+Reflection) is deferred until Robonix integrates RTDL, since today's Pilot planner is effectively ReAct.

## How integration works

EB-Habitat exposes five high-level skills: `navigation`, `pick`, `place`, `open`, `close`, each parameterized by an object argument. Robonix reflects the same five as packages under `skills/`. Each package exports its capability via `CAPABILITY.md` (per the new Robonix packaging spec) and a Python MCP server that forwards the call into the shared EB-Habitat environment.

Concretely, the three top-level skill packages here are:

- `skills/eb_navigate/` — wraps `navigation(object)`
- `skills/eb_manipulate/` — wraps `pick`, `place`, `open`, `close`
- `skills/eb_observe/` — (optional) scene-description hooks for the planner

`CAPABILITY.md` is the planner-facing description Pilot reads during plan generation. No `capabilities/*.toml` until the Robonix toolchain for contracts lands — this tracks the `dev-packaging` branch.

The EB-Habitat env lives in one long-running process owned by `env_adapter.py`; all skill MCP handlers talk to it over a local socket.

## Layout

```
embench-robonix/
├── README.md
├── pyproject.toml
├── robonix_manifest.yaml       # points Pilot/Executor at the local skill packages
├── skills/
│   ├── eb_navigate/
│   │   ├── package_manifest.yaml
│   │   ├── CAPABILITY.md
│   │   ├── bin/start.sh
│   │   └── src/skill.py        # @mcp.tool navigate(obj)
│   ├── eb_manipulate/
│   │   ├── package_manifest.yaml
│   │   ├── CAPABILITY.md
│   │   ├── bin/start.sh
│   │   └── src/skill.py        # @mcp.tool pick / place / open / close
│   └── eb_observe/
│       ├── package_manifest.yaml
│       ├── CAPABILITY.md
│       ├── bin/start.sh
│       └── src/skill.py        # @mcp.tool describe_scene
├── src/embench_robonix/
│   ├── env_adapter.py          # holds EB-Habitat env, serves skill RPCs
│   └── runner.py               # task loop: load task → start stack → record result
├── configs/
│   ├── robonix_manifest.yaml
│   └── tasks_phase_a.yaml      # 20 EB-Habitat tasks
├── results/                    # per-task JSONL + SR summary
└── scripts/run_phase_a.sh
```

## Running

```bash
# rtx server (5090), python 3.10 venv
uv venv --python 3.10
source .venv/bin/activate
uv pip install -e .
# EmbodiedBench + habitat-sim prerequisites — see docs/habitat_setup.md
bash scripts/run_phase_a.sh
```

## Status

- [ ] scaffold + `CAPABILITY.md` for all three skill packages
- [ ] `env_adapter.py` holds an EB-Habitat env, exposes skill RPC handlers
- [ ] `runner.py` iterates 20 tasks through Robonix stack
- [ ] results CSV + one summary figure

Deadline: Monday 2026-04-27. Robonix itself gets packaging fixes on the `dev-packaging` branch in `syswonder/robonix`; those are orthogonal to this repo.
