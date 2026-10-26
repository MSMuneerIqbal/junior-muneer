"""Windows process-tree ownership. Kill-on-close also applies when the backend crashes.

The shell waits on stdin until assigned, so the approved command cannot spawn children before ownership.
Job objects are lifetime controls, NOT a file/network sandbox. Terminal commands still require approval.
See https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects .
"""

import asyncio
import ctypes
import os
import subprocess
from ctypes import wintypes

from junior.computer.terminal import clean_env


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD),
    ]


class _Limits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits), ("io", ctypes.c_ulonglong * 6),
        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
    ]


class OwnedTree:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Managed PC jobs require the local Windows backend; a VPS needs the PC Helper.")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)  # unnamed, non-inheritable
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid: int):
        process = self.api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(process)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


async def spawn(command: str, folder: str) -> tuple[asyncio.subprocess.Process, OwnedTree]:
    tree = OwnedTree()
    proc = None
    try:
        # Keep the gate outside the command's script block; input is disabled after this one handshake.
        script = (
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
            "$ProgressPreference = 'SilentlyContinue'; "
            "if ([Console]::In.ReadLine() -ne 'junior-go') { exit 125 }; "
            "$ErrorActionPreference = 'Stop'; $global:LASTEXITCODE = 0; "
            "try { & { " + command + "\n}; if (-not $?) { exit 1 }; exit $global:LASTEXITCODE } "
            "catch { [Console]::Error.WriteLine($_.ToString()); exit 1 }"
        )
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script,
            cwd=folder, env=clean_env(), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        tree.assign(proc.pid)
        proc.stdin.write(b"junior-go\n")
        await proc.stdin.drain()
        proc.stdin.close()
        return proc, tree
    except BaseException:
        tree.close()
        if proc is not None:
            if proc.returncode is None:
                proc.kill()  # only this live handle, never a saved PID
            await proc.communicate()
        raise
