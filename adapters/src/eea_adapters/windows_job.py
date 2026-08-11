"""Windows-only Job Object enforcement for the structured-command sandbox.

This module is imported lazily by :mod:`eea_adapters.sandbox` only on Windows.
Keeping the ctypes binding here prevents Linux runtime imports and type checking of
Windows-only attributes from crossing the portable sandbox boundary.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from collections.abc import Callable
from typing import Any, cast

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import SandboxPolicy


class _LargeInteger(ctypes.Structure):
    _fields_ = [("QuadPart", ctypes.c_longlong)]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", _LargeInteger),
        ("PerJobUserTimeLimit", _LargeInteger),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _last_error() -> int:
    getter = getattr(ctypes, "get_last_error", None)
    if getter is None:
        return 0
    return cast(Callable[[], int], getter)()


def _windll(name: str) -> Any:
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError("Windows ctypes loader is unavailable")
    return cast(Callable[..., Any], loader)(name, use_last_error=True)


class WindowsJob:
    """Windows Job Object adapter for process-tree and resource enforcement."""

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    _JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    @staticmethod
    def supported() -> bool:
        return os.name == "nt" and getattr(ctypes, "WinDLL", None) is not None

    def __init__(self, policy: SandboxPolicy) -> None:
        if not self.supported():
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Windows Job Object sandboxing is unavailable on this platform",
            )
        try:
            self._kernel32: Any = _windll("kernel32")
            self._handle = self._kernel32.CreateJobObjectW(None, None)
            if not self._handle:
                raise OSError(_last_error())
            self._configure(policy)
        except (AttributeError, OSError, TypeError) as exc:
            self.close()
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Windows Job Object limits could not be configured",
                details={"reason": type(exc).__name__},
            ) from None

    def _configure(self, policy: SandboxPolicy) -> None:
        info = _JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = (
            self._JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | self._JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | self._JOB_OBJECT_LIMIT_JOB_MEMORY
            | self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.BasicLimitInformation.ActiveProcessLimit = policy.max_processes
        info.ProcessMemoryLimit = policy.max_memory_bytes
        info.JobMemoryLimit = policy.max_memory_bytes
        if not self._kernel32.SetInformationJobObject(
            self._handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            raise OSError(_last_error())

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        process_handle = cast(Any, process)._handle
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise OSError(_last_error())

    @staticmethod
    def resume(process: subprocess.Popen[bytes]) -> None:
        """Resume a process only after it has been attached to the Job Object."""
        try:
            ntdll = _windll("ntdll")
            resume_process = ntdll.NtResumeProcess
            resume_process.argtypes = [ctypes.c_void_p]
            resume_process.restype = ctypes.c_long
            status = resume_process(cast(Any, process)._handle)
        except (AttributeError, OSError, TypeError) as exc:
            raise OSError("NtResumeProcess is unavailable") from exc
        if status != 0:
            raise OSError(f"NtResumeProcess failed with NTSTATUS {status}")

    def terminate(self) -> None:
        self._kernel32.TerminateJobObject(self._handle, 1)

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle:
            self._kernel32.CloseHandle(handle)
            self._handle = None


__all__ = ["WindowsJob"]
