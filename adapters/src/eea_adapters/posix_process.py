"""POSIX process resource controller for the M5 structured-command sandbox.

The controller deliberately contains the POSIX-specific enforcement hooks so
that the public sandbox adapter remains platform-neutral.  Resource limits are
installed in the child immediately before ``exec`` and process groups are
created by the parent ``Popen`` call.  A capability is advertised only when
the current POSIX runtime exposes the corresponding kernel resource boundary.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable
from importlib import import_module
from typing import Any

try:
    _resource: Any = import_module("resource")
except ImportError:  # pragma: no cover - exercised by Windows runtime
    _resource = None

from eea_core.sandbox import SandboxCapabilities, SandboxPolicy


class PosixProcessController:
    """Apply POSIX address-space and process-spawn limits to one process tree."""

    def __init__(self, policy: SandboxPolicy) -> None:
        self._policy = policy
        self._process: subprocess.Popen[bytes] | None = None

    @classmethod
    def capabilities(cls) -> SandboxCapabilities:
        """Return only limits that this host can actually install."""

        resource_module = _resource
        posix = os.name == "posix" and resource_module is not None
        memory_limit = bool(
            posix
            and hasattr(resource_module, "RLIMIT_AS")
            and hasattr(resource_module, "setrlimit")
        )
        # RLIMIT_NPROC is bypassed for UID 0 on Linux.  Do not claim a process
        # boundary for that runtime; trusted execution then fails closed.
        process_limit = bool(
            posix
            and hasattr(resource_module, "RLIMIT_NPROC")
            and hasattr(resource_module, "setrlimit")
            and getattr(os, "geteuid", lambda: 1)() != 0
        )
        return SandboxCapabilities(
            network_isolation=False,
            memory_limit=memory_limit,
            process_limit=process_limit,
            process_tree_kill=bool(posix and hasattr(os, "killpg")),
            streaming_output_limit=True,
            filesystem_isolation=False,
            strong_isolation=False,
        )

    def preexec_fn(self) -> Callable[[], None]:
        """Build the child hook that installs all advertised POSIX limits."""

        def apply_limits() -> None:
            resource_module = _resource
            if resource_module is None:
                raise RuntimeError("POSIX resource module is unavailable")
            capabilities = self.capabilities()
            if capabilities.memory_limit:
                self._set_limit(resource_module.RLIMIT_AS, self._policy.max_memory_bytes)
            if capabilities.process_limit:
                self._set_limit(resource_module.RLIMIT_NPROC, self._policy.max_processes)

        return apply_limits

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process

    def resume(self, process: subprocess.Popen[bytes]) -> None:
        del process

    def terminate(self) -> None:
        process = self._process
        if process is None:
            return
        killpg = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", None)
        try:
            if not callable(killpg) or sigkill is None:
                raise OSError("POSIX process-group termination is unavailable")
            killpg(process.pid, sigkill)
        except (OSError, AttributeError):
            process.kill()

    def close(self) -> None:
        self._process = None

    @staticmethod
    def _set_limit(resource_id: int, requested: int) -> None:
        resource_module = _resource
        if resource_module is None:
            raise RuntimeError("POSIX resource module is unavailable")
        soft, hard = resource_module.getrlimit(resource_id)
        del soft
        target = requested if hard == resource_module.RLIM_INFINITY else min(requested, hard)
        resource_module.setrlimit(resource_id, (target, target))


__all__ = ["PosixProcessController"]

