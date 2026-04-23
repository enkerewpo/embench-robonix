"""Env adapter — owns ONE EB-Habitat env, serves skill RPCs over UNIX socket.

Skill MCP servers (eb_navigate / eb_manipulate / eb_observe) are stateless
clients that talk to this adapter via :class:`embench_robonix.env_client.EnvClient`.

Wire format: newline-delimited JSON.
Request:  {"method": "<name>", "params": {...}}
Response: {"success": bool, "step": int, ...method-specific extras}

Skill-name → discrete action-index mapping
------------------------------------------
EB-Habitat has 70 discrete actions (as of the `base` eval_set), each encoding
a (skill, arg) pair: e.g. `nav_table_0` with arg `table_0_0`, `pick_apple_0`
with arg `apple_0`, `open_fridge`, etc. The high-level MCP tools translate
to these by picking the first action whose string form contains the given
target. See :meth:`EBHabitatAdapter._skill_index_for`.
"""
from __future__ import annotations

import json
import logging
import os
import socketserver
import threading
from typing import Any, Callable

log = logging.getLogger("embench.env")


class EBHabitatAdapter:
    """Wraps `embodiedbench.envs.eb_habitat.EBHabEnv`."""

    def __init__(self, eval_set: str = "base", resolution: int = 256) -> None:
        from embodiedbench.envs.eb_habitat.EBHabEnv import EBHabEnv
        self._env = EBHabEnv(eval_set=eval_set,
                             exp_name=os.environ.get("EMBENCH_EXP_NAME", "embench_robonix"),
                             resolution=resolution,
                             recording=False)
        self._reset_needed = True
        self._task_success = False
        self._holding: str | None = None
        self._near: str | None = None
        self._n_episodes = int(self._env.number_of_episodes)
        # cache skill table for lookup
        self._skills: list[tuple[str, list]] = list(self._env.skill_set)
        self._language_skills: list[str] = list(self._env.language_skill_set)
        log.info("EBHabEnv ready — %d episodes, %d skills",
                 self._n_episodes, len(self._skills))

    # ── episode lifecycle ─────────────────────────────────────────────────
    def reset(self, episode_id: int | None = None) -> dict:
        """Advance to the next episode (or the requested one by skipping forward).

        EBHabEnv iterates its dataset sequentially; we do NOT re-initialize on
        backwards jumps (that requires tearing down the Habitat sim and
        crashes the shared EGL context). Caller should run tasks in
        monotonically increasing episode_id.
        """
        if episode_id is not None:
            if episode_id < self._env._current_episode_num:
                log.warning("requested episode %d < current %d — skipping "
                            "(backwards reset not supported)",
                            episode_id, self._env._current_episode_num)
            while self._env._current_episode_num < episode_id:
                self._env.reset()
        self._env.reset()
        self._reset_needed = False
        self._task_success = False
        self._holding = None
        self._near = None
        return {
            "success": True,
            "episode_id": int(self._env._current_episode_num) - 1,
            "instruction": self._env.episode_language_instruction,
            "n_skills": len(self._skills),
            "skills": self._language_skills,
        }

    # ── action lookup helpers ─────────────────────────────────────────────
    def _skill_index_for(self, op: str, target: str) -> int | None:
        """Match (op, VLM-natural-language-target) against EB-Habitat's 70 skills.

        VLM emits free-form args like "table 1", "kitchen counter", "refrigerator".
        Each Habitat skill has (internal_name, [object_handle]) plus a
        human-readable entry in ``language_skill_set`` — we match on that.

        op: "nav" | "pick" | "place" | "open" | "close"
        """
        op_verb = {"nav": "navigate to", "pick": "pick up",
                   "place": "place at", "open": "open the",
                   "close": "close the"}.get(op, op)
        t = target.lower().strip()
        # normalise target: "left counter" / "counter left" both ok
        t_tokens = [w for w in t.replace("_", " ").split() if w]

        def score(phrase: str) -> int:
            p = phrase.lower()
            if op_verb not in p:
                return -1
            # partial: every token from target must appear
            return sum(1 for w in t_tokens if w in p)

        best_i, best_s = None, 0
        for i, phrase in enumerate(self._language_skills):
            s = score(phrase)
            if s > best_s:
                best_s, best_i = s, i
        return best_i if best_s >= max(1, len(t_tokens) - 1) else None

    def _step(self, op: str, target: str) -> dict:
        if self._reset_needed:
            self._env.reset()
            self._reset_needed = False
        idx = self._skill_index_for(op, target)
        if idx is None:
            return {"success": False, "step": self._env._current_step,
                    "error": f"no skill matching {op!r} target={target!r}"}
        obs, reward, done, info = self._env.step(idx)
        success = bool(info.get("task_success", False) or reward >= 1.0)
        self._task_success = self._task_success or success
        return {
            "success": not info.get("was_prev_action_invalid", False),
            "step": int(self._env._current_step),
            "reward": float(reward),
            "done": bool(done),
            "task_success": bool(self._task_success),
            "env_feedback": info.get("env_feedback") or info.get("action"),
        }

    # ── RPC methods ──────────────────────────────────────────────────────
    def describe_scene(self) -> dict:
        """Return a world-model snapshot: receptacles, pickables, state,
        and the exact natural-language phrases accepted by each skill so
        the planner can choose grounded targets.

        Free call — no env step consumed.
        """
        # Derive sets from the skill table (names like "nav_table_0", args
        # like ["table_0_0"]). language_skill_set gives the planner-facing
        # phrase ("navigate to the table 1" etc.).
        receptacles: list[str] = []
        pickables: list[str] = []
        nav_targets: set[str] = set()
        pick_targets: set[str] = set()
        place_targets: set[str] = set()
        open_targets: set[str] = set()
        close_targets: set[str] = set()
        for (name, _args), phrase in zip(self._skills, self._language_skills):
            if name.startswith("nav"):
                rec = phrase.replace("navigate to the ", "").strip()
                nav_targets.add(rec)
                receptacles.append(rec)
            elif name.startswith("pick"):
                obj = phrase.replace("pick up the ", "").strip()
                pick_targets.add(obj)
                pickables.append(obj)
            elif name.startswith("place"):
                place_targets.add(phrase.replace("place at the ", "").strip())
            elif name.startswith("open"):
                open_targets.add(phrase.replace("open the ", "").strip())
            elif name.startswith("close"):
                close_targets.add(phrase.replace("close the ", "").strip())

        return {
            "success": True,
            "step": int(self._env._current_step),
            "instruction": self._env.episode_language_instruction,
            "holding": self._holding,
            "agent_near": self._near,
            "receptacles": sorted(set(receptacles)),
            "pickable_objects": sorted(set(pickables)),
            "valid_targets": {
                "navigate": sorted(nav_targets),
                "pick": sorted(pick_targets),
                "place": sorted(place_targets),
                "open": sorted(open_targets),
                "close": sorted(close_targets),
            },
        }

    def navigate(self, target: str) -> dict:
        out = self._step("nav", target)
        if out["success"]:
            self._near = target
        return out

    def pick(self, obj: str) -> dict:
        out = self._step("pick", obj)
        if out["success"]:
            self._holding = obj
        return out

    def place(self, obj: str, receptacle: str) -> dict:
        out = self._step("place", receptacle)
        if out["success"]:
            self._holding = None
        return out

    def open(self, receptacle: str) -> dict:
        return self._step("open", receptacle)

    def close(self, receptacle: str) -> dict:
        return self._step("close", receptacle)


# ── socket server glue ───────────────────────────────────────────────────
class _Handler(socketserver.StreamRequestHandler):
    dispatch: dict[str, Callable[..., dict]] = {}

    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        req = json.loads(line.decode())
        method = req.get("method", "")
        params: dict[str, Any] = req.get("params") or {}
        fn = self.dispatch.get(method)
        if fn is None:
            res = {"success": False, "error": f"unknown method: {method}"}
        else:
            try:
                res = fn(**params)
            except TypeError as e:
                res = {"success": False, "error": f"bad params: {e}"}
            except Exception as e:
                log.exception("env handler crash")
                res = {"success": False, "error": str(e)}
        self.wfile.write((json.dumps(res) + "\n").encode())


def serve(sock_path: str) -> None:
    logging.basicConfig(level=os.environ.get("LOG", "INFO"),
                        format="[env %(asctime)s] %(message)s")

    eval_set = os.environ.get("EMBENCH_EVAL_SET", "base")
    adapter = EBHabitatAdapter(eval_set=eval_set)
    _Handler.dispatch = {
        "reset": adapter.reset,
        "describe_scene": adapter.describe_scene,
        "navigate": adapter.navigate,
        "pick": adapter.pick,
        "place": adapter.place,
        "open": adapter.open,
        "close": adapter.close,
    }

    if os.path.exists(sock_path):
        os.remove(sock_path)
    # Non-threading: Habitat-sim's OpenGL/EGL context is bound to the thread
    # that created the env, so all env.step calls MUST run on that thread.
    # Sequential handling is fine — skill calls are low-frequency anyway.
    with socketserver.UnixStreamServer(sock_path, _Handler) as srv:
        os.chmod(sock_path, 0o600)
        log.info("env adapter serving at %s (eval_set=%s)", sock_path, eval_set)
        srv.serve_forever()


if __name__ == "__main__":
    serve(os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock"))
