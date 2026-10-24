"""Never silently omit a file: refuse secrets, links, oversized batches or changed source material."""
import asyncio
import fnmatch
import io
import os
from pathlib import Path
import stat
import time
import zipfile

from junior.computer.paths import BLOCKED_DIRS, BLOCKED_FILES, blocked_reason, recheck
from junior.pause import is_paused
from junior.permissions import get_mode
from junior.transfers.sources import pc_path

MAX_ENTRIES = 500
MAX_INPUT = 100 * 1024 * 1024
MAX_ZIP = 20 * 1024 * 1024
MAX_SECONDS = 120


def tick(started):
    if is_paused() or get_mode() == "plan":
        raise ValueError("Junior was paused or switched to Plan; archive preparation stopped.")
    if time.monotonic() - started > MAX_SECONDS:
        raise ValueError("Archive preparation exceeded two minutes. Choose a smaller folder.")


def blocked_name(name):
    low = name.casefold()
    return low in BLOCKED_DIRS or low.endswith((".lnk", ".url")) or any(fnmatch.fnmatch(low, p) for p in BLOCKED_FILES)


def linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def local_manifest(root, started):
    entries, size = [], 0
    def unreadable(error):
        raise ValueError(f"Couldn't read a folder while packaging ({error}). No incomplete archive was saved.") from error
    for here, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        tick(started)
        for name in sorted(dirs + files):
            path = Path(here) / name
            if linked(path) or blocked_reason(path) or path.suffix.casefold() in (".lnk", ".url"):
                raise ValueError(f"Cannot archive {path.name}: it is a link, system location or secret. Choose a cleaned folder.")
            recheck(str(path))
            info = path.stat()
            folder = path.is_dir()
            if not folder and not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Cannot archive the special file {path.name}.")
            size += 0 if folder else info.st_size
            entries.append((path.relative_to(root).as_posix(), folder, info.st_size, info.st_mtime_ns))
            if len(entries) > MAX_ENTRIES or size > MAX_INPUT:
                raise ValueError("Archive limit: 500 entries and 100 MB of source files. Choose a smaller folder.")
    return sorted(entries)


def _local_zip(root):
    started = time.monotonic()
    manifest = local_manifest(root, started)
    if not manifest:
        raise ValueError("That folder is empty.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for relative, folder, size, mtime in manifest:
            tick(started)
            path = recheck(str(root / relative))
            if linked(path):
                raise ValueError("A source became a link. Nothing was packaged.")
            member = root.name + "/" + relative
            if folder:
                z.writestr(member + "/", b"")
            else:
                info = path.stat()
                if (info.st_size, info.st_mtime_ns) != (size, mtime):
                    raise ValueError("A source file changed during preparation. Ask again when it is saved.")
                with path.open("rb") as src, z.open(member, "w") as target:
                    copied = 0
                    while chunk := src.read(65536):
                        tick(started)
                        copied += len(chunk)
                        if copied > size:
                            raise ValueError("A source file grew during preparation. Ask again.")
                        target.write(chunk)
                        if output.tell() > MAX_ZIP:
                            raise ValueError("The ZIP is over 20 MB. Choose a smaller folder.")
            if output.tell() > MAX_ZIP:
                raise ValueError("The ZIP is over 20 MB. Choose a smaller folder.")
    if manifest != local_manifest(root, started):
        raise ValueError("Folder contents changed during preparation. Ask again when files are saved.")
    if len(output.getvalue()) > MAX_ZIP:
        raise ValueError("The ZIP is over 20 MB. Choose a smaller folder.")
    return root.name + ".zip", output.getvalue(), manifest


async def local_zip(context, folder):
    root = pc_path(context, folder)
    if not root.is_dir() or root == Path(root.anchor):
        raise ValueError("Choose a specific existing folder, not an entire drive.")
    if linked(root):
        raise ValueError("A linked folder cannot be archived.")
    return await asyncio.to_thread(_local_zip, root)


async def cloud_manifest(root, started):
    from junior.google.auth import call
    from junior.google.drive import FILES, FOLDER, _quoted
    entries, total = [], 0

    async def walk(fid, prefix, depth):
        nonlocal total
        if depth > 12:
            raise ValueError("Drive folder is more than 12 levels deep. Choose a smaller folder.")
        token = ""
        while True:
            tick(started)
            params = {"q": f"{_quoted(fid)} in parents and trashed = false", "pageSize": "100",
                      "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,version)", "supportsAllDrives": "true",
                      "includeItemsFromAllDrives": "true"}
            if token:
                params["pageToken"] = token
            got = await call("GET", FILES, params=params)
            for row in got.get("files", []):
                name = row["name"]
                if blocked_name(name) or "/" in name or "\\" in name or name in (".", ".."):
                    raise ValueError(f"Cannot archive Drive entry {name!r}: secret or unsafe archive name.")
                if row["mimeType"] == "application/vnd.google-apps.shortcut":
                    raise ValueError(f"Drive shortcut {name!r} cannot be archived. Choose its actual folder.")
                path = prefix + "/" + name
                entries.append((path, row))
                total += int(row.get("size") or 0)
                if len(entries) > MAX_ENTRIES or total > MAX_INPUT:
                    raise ValueError("Archive limit: 500 entries and 100 MB of source files.")
                if row["mimeType"] == FOLDER:
                    await walk(row["id"], path, depth + 1)
            token = got.get("nextPageToken", "")
            if not token:
                break
    await walk(root["id"], root["name"], 0)
    return sorted(entries, key=lambda r: (r[0], r[1]["id"]))


async def cloud_zip(folder):
    from junior.google.drive import FOLDER, fetch, resolve_folder
    async with asyncio.timeout(MAX_SECONDS):
        root = await resolve_folder(folder, create=False)
        if root["id"] == "root" or "/" in root["name"] or "\\" in root["name"] or blocked_name(root["name"]):
            raise ValueError("Choose a specific Drive folder with a safe name, not the whole drive.")
        started = time.monotonic()
        entries = await cloud_manifest(root, started)
        if not entries:
            raise ValueError("That Drive folder is empty.")
        output, names, total = io.BytesIO(), set(), 0
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path, row in entries:
                tick(started)
                if row["mimeType"] == FOLDER:
                    name, data = path + "/", b""
                else:
                    filename, data, _ = await fetch(row["id"])
                    name = path.rsplit("/", 1)[0] + "/" + filename
                if name.casefold() in names:
                    raise ValueError("Drive contains duplicate archive filenames. Rename them before packaging.")
                names.add(name.casefold())
                total += len(data)
                if total > MAX_INPUT:
                    raise ValueError("Exported Drive material exceeds 100 MB. Choose a smaller folder.")
                await asyncio.to_thread(z.writestr, name, data)
                if output.tell() > MAX_ZIP:
                    raise ValueError("The ZIP is over 20 MB. Choose a smaller folder.")
        if entries != await cloud_manifest(root, started):
            raise ValueError("Drive folder contents changed during preparation. Ask again.")
        return root["name"] + ".zip", output.getvalue(), entries
