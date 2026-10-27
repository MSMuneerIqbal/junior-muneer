"""Local print worker: fixed HTML, no network, bounded lifetime, no Google writes."""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from junior.computer.terminal import clean_env

MAX_PDF_BYTES = 20 * 1024 * 1024
PDF_SECONDS = 45


async def render_pdf(doc, sources, output_format, count):
    from junior.documents.schema import validate_document
    validate_document(doc, sources, output_format, count)
    tree = proc = None
    with tempfile.TemporaryDirectory(prefix="junior-pdf-") as folder:
        root = Path(folder)
        (root / "input.json").write_text(json.dumps({"document": doc.model_dump(), "sources": sources,
            "format": output_format, "count": count}, ensure_ascii=False), encoding="utf-8")
        try:
            if os.name == "nt":
                from junior.computer.owned_process import OwnedTree
                tree = OwnedTree()
            env = clean_env()
            if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
                env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
            proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "junior.documents.pdf_worker", folder,
                cwd=Path(__file__).resolve().parents[2], env=env, stdin=asyncio.subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
            if tree:
                tree.assign(proc.pid)
            proc.stdin.write(b"junior-go\n")
            await proc.stdin.drain()
            proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), PDF_SECONDS)
            except TimeoutError:
                raise ValueError("PDF generation exceeded 45 seconds. No unfinished PDF was saved.") from None
            target = root / "output.pdf"
            if proc.returncode or not target.is_file():
                raise ValueError("PDF rendering failed. Check Chromium is installed (python -m playwright install chromium), or request Word/PowerPoint.")
            if target.stat().st_size > MAX_PDF_BYTES:
                raise ValueError("The PDF exceeds the 20 MB limit. Request a shorter document.")
            data = target.read_bytes()
            if not data.startswith(b"%PDF-"):
                raise ValueError("The renderer did not return a valid PDF.")
            return data
        finally:
            if tree:
                tree.close()
            if proc is not None:
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                await proc.wait()
