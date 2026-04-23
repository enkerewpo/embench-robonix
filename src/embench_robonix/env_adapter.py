"""Env adapter — owns one EB-Habitat env instance and exposes its skill RPCs
over a UNIX socket. Skill MCP servers talk to this adapter via EnvClient.

Design invariant: exactly ONE env process for the whole Phase A run.
Skill servers are stateless clients; they never instantiate Habitat.

Wire format: newline-delimited JSON. One request per line, one response
per line. Request schema:

    {"method": "<name>", "params": {...}}

Response schema:

    {"success": bool, "step": int, ...per-method extras}

This module is intentionally thin — the actual EB-Habitat binding (scene
loading, action dispatch, success evaluation) goes into
:class:`EBHabitatEnv` below. At Phase A start, the concrete hook-up to
EmbodiedBench's ``eb_habitat`` package is TODO until that package is
installed on rtx — see scripts/run_phase_a.sh for the startup sequence.
"""
from __future__ import annotations

import json
import logging
import os
import socketserver
import threading
from typing import Any, Callable

log = logging.getLogger("embench.env")


class EBHabitatEnv:
    """Wrapper around EmbodiedBench's EB-Habitat env.

    TODO (2026-04-23): bind to EmbodiedBench's actual API once their
    package is pip-installed on the rtx server. EmbodiedBench exposes an
    env object with ``reset(task)``, ``step(action)``, ``get_obs()``, and
    ``check_success()`` — mirror those here.
    """

    def __init__(self) -> None:
        self._task = None
        self._step = 0
        self._held: str | None = None
        self._near: str | None = None
        self._success = False

    def reset(self, task_id: str) -> dict:
        self._task = task_id
        self._step = 0
        self._held = None
        self._near = None
        self._success = False
        # TODO: call EmbodiedBench env.reset(task_id=task_id)
        return self._snapshot()

    def describe_scene(self) -> dict:
        # TODO: fetch receptacles / pickables / door states from habitat env
        return self._snapshot()

    def navigate(self, target: str) -> dict:
        # TODO: env.step({"action": "navigation", "target": target})
        self._near = target
        self._step += 1
        return self._snapshot()

    def pick(self, obj: str) -> dict:
        # TODO: env.step({"action": "pick", "obj": obj})
        self._held = obj
        self._step += 1
        return self._snapshot()

    def place(self, obj: str, receptacle: str) -> dict:
        # TODO: env.step(...)
        self._held = None
        self._step += 1
        return self._snapshot()

    def open(self, receptacle: str) -> dict:
        self._step += 1
        return self._snapshot()

    def close(self, receptacle: str) -> dict:
        self._step += 1
        return self._snapshot()

    def _snapshot(self) -> dict:
        return {
            "success": True,
            "step": self._step,
            "holding": self._held,
            "agent_near": self._near,
            "task_success": self._success,
        }


class _Handler(socketserver.StreamRequestHandler):
    dispatch: dict[str, Callable[..., dict]]

    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        req = json.loads(line.decode())
        method = req.get("method", "")
        params: dict[str, Any] = req.get("params", {}) or {}
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

    env = EBHabitatEnv()
    dispatch: dict[str, Callable[..., dict]] = {
        "describe_scene": env.describe_scene,
        "navigate": env.navigate,
        "pick": env.pick,
        "place": env.place,
        "open": env.open,
        "close": env.close,
        "reset": env.reset,
    }

    if os.path.exists(sock_path):
        os.remove(sock_path)

    class Handler(_Handler):
        pass

    Handler.dispatch = dispatch

    with socketserver.ThreadingUnixStreamServer(sock_path, Handler) as srv:
        os.chmod(sock_path, 0o600)
        log.info("env adapter serving at %s", sock_path)
        srv.serve_forever()


if __name__ == "__main__":
    serve(os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock"))
