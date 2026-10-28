"""Terminal commands on your PC: rule-controlled PowerShell in an allowed folder, 2 minutes at most.

`refusal(command)` says why a command is never run, whatever the rule: it's checked before the card is made and again
right before it runs (you can edit a card's command). The command runs without your keys in its environment.
"""

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass

RUN_SECONDS = 120
OUTPUT_CHARS = 8_000

# Never run, in plain words. Checked on the command with quotes and carets removed, case ignored.
NEVER = [
    # "format D:" and Format-Volume; not Format-Table / Format-List, which only lay out text
    (r"\bformat(\.com)?\s+/?[a-z]:|\b(format-volume|diskpart|clear-disk|initialize-disk|remove-partition|cipher\s+/w)\b",
     "formatting or wiping a disk"),
    (r"\b(bcdedit|bootrec|reagentc)\b", "changing how Windows starts"),
    (r"\b(shutdown|restart-computer|stop-computer|logoff)\b", "shutting down or restarting the PC"),
    (r"\b(reg(\.exe)?\s+(add|delete|import|load|restore)|set-itemproperty\s+.*hk(lm|cu):|new-itemproperty|remove-itemproperty)\b|\bhk(lm|cu):",
     "changing the Windows registry"),
    (r"\b(net\s+(user|localgroup|accounts)|new-localuser|set-localuser|remove-localuser|add-localgroupmember)\b", "changing user accounts"),
    (r"\b(netsh\s+(advfirewall|firewall)|set-netfirewall\w*|new-netfirewallrule|disable-netfirewall\w*)\b", "changing the firewall"),
    (r"\b(set-mppreference|add-mppreference|disable-windowsoptionalfeature|uninstall-windowsfeature)\b", "turning off protection or Windows features"),
    (r"\b(vssadmin|wbadmin|wmic\s+shadowcopy)\b", "touching backups and restore points"),
    (r"\b(takeown|icacls|cacls|set-acl)\b", "changing who may open files"),
    (r"\b(set-executionpolicy|schtasks|register-scheduledtask|new-service|sc(\.exe)?\s+(create|config|delete))\b",
     "changing security settings, services or scheduled tasks"),
    (r"\b(iex|invoke-expression|downloadstring|downloadfile|start-bitstransfer)\b|\|\s*(iex|powershell|pwsh|cmd)\b|-e(nc|ncodedcommand)?\s+[a-z0-9+/=]{16,}",
     "running downloaded or hidden code"),
    (r"-verb\s+runas|\brunas\b|\bsudo\b", "running as administrator"),
    (r"\b(remove-item|rm|rmdir|rd|del|erase|ri)\b|\bclear-recyclebin\b", "deleting (use pc_delete: it goes to the Recycle Bin)"),
    (r"(^|[\\/\s\"'])\.env\b|\.ssh\b|\bappdata\b|\$env:\w*(key|token|secret|pass)\w*|\bget-childitem\s+env:|\bset\s*$|\bprintenv\b|\bdpapi\b|credential",
     "reading secrets (.env, keys, AppData, passwords)"),
]
_NEVER = [(re.compile(p, re.IGNORECASE), why) for p, why in NEVER]
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.IGNORECASE)


def refusal(command: str) -> str | None:
    """Why this command is never run, or None."""
    flat = re.sub(r"[`^\"']", "", command or "")  # cmd's ^ and PowerShell's ` can split a word; quotes too
    if not flat.strip():
        return "the command is empty"
    if len(flat) > 2000:
        return "the command is over 2,000 characters"
    for pattern, why in _NEVER:
        if pattern.search(flat):
            return why
    return None


def clean_env() -> dict[str, str]:
    """Your PC's environment without anything that looks like a key, token or password."""
    return {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}


@dataclass
class Ran:
    code: int | None  # None: stopped at the time limit
    output: str


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)  # noqa: S603, S607


async def run_powershell(command: str, folder: str, seconds: float = RUN_SECONDS) -> Ran:
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; $ProgressPreference = 'SilentlyContinue'; " + command
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script,
        cwd=folder, env=clean_env(), stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), seconds)
        code: int | None = proc.returncode
    except TimeoutError:
        _kill_tree(proc.pid)
        out, _ = await proc.communicate()
        code = None
    text = (out or b"").decode("utf-8", errors="replace").replace("\r\n", "\n").strip()
    if len(text) > OUTPUT_CHARS:
        text = text[:OUTPUT_CHARS // 2] + f"\n... ({len(text) - OUTPUT_CHARS:,} characters cut) ...\n" + text[-OUTPUT_CHARS // 2:]
    return Ran(code, text)
