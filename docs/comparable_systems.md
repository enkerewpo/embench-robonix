# Comparable Systems for Robonix on EB-Habitat

Candidates to benchmark against Robonix (Pilot → Executor → MCP skills) on the
EB-Habitat subset of EmbodiedBench. Ranked by how easily they plug into the
same harness.

## Tier 1 — Native to EmbodiedBench (lowest effort)

These run on the same `EBHabEnv` with the same action space and episode set.
No adapter work, just a different Hydra config.

- **EB `VLMPlanner` (chat_history=True)** — closest apples-to-apples baseline.
  Single-shot LLM per step with env feedback appended to history. This is
  functionally ReAct: Robonix's Pilot does the same thing, just routing
  tool-calls through Executor + MCP instead of returning action_ids directly.
  Invocation:
  ```bash
  python -m embodiedbench.main env=eb-hab model_name=gpt-4o-mini \
         exp_name=baseline_chat chat_history=True down_sample_ratio=0.4
  ```
- **EB `VLMPlanner` (multistep=True)** — plans multiple actions per turn.
  Tests whether "longer horizon in one LLM call" buys anything. Mutually
  exclusive with chat_history.
- **EB `VLMPlanner` (default, chat_history=False, n_shot=10)** — pure
  few-shot zero-context planner. Ablation to show the value of history.
- **EB `VLMPlanner` (language_only=True)** — no image. Ablation showing how
  much of the SR is driven by vision.

All four above + Robonix = 5-way comparison with one backbone (gpt-4o-mini).
Paper's Table 2 reports the first three modes across models — our numbers
can be triangulated against their published 50-episode SRs.

## Tier 2 — Published papers with open code on embodied planning

Non-trivial to adapt to EB-Habitat's action space but plausible.

- **Inner Monologue** (Huang et al., CoRL 2022). Loop of LLM proposals +
  success-detector feedback. Closest conceptual match to Robonix's Executor
  reflecting env outcomes back to Pilot. Google didn't release the original
  code; community reimplementation exists (e.g. `YeonSoo/inner-monologue`).
- **ReAct** (Yao et al., 2023). The canonical Reason-Act paradigm. EB's
  `chat_history=True` is already a ReAct instantiation on their action API.
  Porting Yao's original prompt template as a drop-in planner would take a
  few hours.
- **Reflexion** (Shinn et al., NeurIPS 2023). Adds an episode-level verbal
  reflection that's prepended to the next attempt. Not directly implemented
  by EB; would be a ~200-line wrapper around `VLMPlanner`.
- **RoboMatrix** (Mao et al., SIGKDD 2024). Hierarchical task decomposition
  tree for multi-agent robot control. Different benchmark (their own), so
  porting isn't a drop-in. Probably a hackweek project.
- **SayCan / PaLM-E class** (Google). Not open-source; unable to benchmark.
- **EMMA** (Ma et al., ICML 2025). Embodied reasoning model; if the weights
  and EB-Alfred/EB-Habitat scaffolding are released, tier 1.

## Tier 3 — Same space but different domain

Comparison is aspirational; would need cross-benchmark meta-analysis rather
than direct runs.

- **Voyager** (NVIDIA, 2023) — Minecraft long-horizon agent. Shares the
  "LLM proposes, env executes, reflect on failure" structure but targets a
  different environment with open-ended tasks. Cite as conceptual neighbor,
  not a baseline.
- **AutoGPT / LangGraph workflows** — tool-calling agents in the web/code
  domain. Robonix's Pilot effectively generalizes this to embodied skills.
- **OpenVLA / RT-2 / pi-0** — end-to-end VLAs, not LLM-agent frameworks.
  Different category: they *replace* the planner+skill stack with a single
  network. We compare Robonix against them in the VLA-as-skill direction
  (Phase B: load a VLA as a Robonix skill).

## What we will run overnight (when GPU clears)

1. **Robonix × 5 subsets × 20 eps** — both `claude-opus-4-7` (extends
   existing base runs to full 5-subset profile) and `gpt-4o-mini` (same
   backbone as EB baseline).
2. **EB `VLMPlanner` × 5 subsets × 20 eps** at `gpt-4o-mini` with
   `chat_history=True` — the head-to-head baseline for "does Robonix's
   architecture cost anything".
3. **EB `VLMPlanner` × base × 20 eps** at `gpt-4o-mini` with
   `chat_history=False` and `multistep=True` — two ablation points on base
   to characterize the planner dimension independent of Robonix.

`scripts/overnight_compare.sh` orchestrates batches 1+2; batch 3 is a
one-liner off the same entrypoint.

## Current blocker

Two EB native smoke runs started with `resolution=500` (EB default) hit the
habitat-sim `CubeMap.cpp:315` framebuffer assertion on the rtx 5090. The
crashes left the processes in uninterruptible D state holding a GPU driver
rwlock — subsequent habitat init (including Robonix's env_adapter) now
hangs on `os_acquire_rwlock_write`. `kill -9` does not release them;
`nvidia-smi` itself hangs. Needs either a server reboot or a long GPU
driver timeout to clear.

The smoke test with `resolution=256` (Robonix's default, which has been
working all evening) did NOT hit CubeMap. So the overnight plan should:
- Always pass `resolution=256` to EB native, not leave at 500.
- Clean up the D-state zombies by rebooting rtx before next attempt.
