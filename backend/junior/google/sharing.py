"""Explicit link sharing via Drive permissions; separate from upload and its permission rule."""
import re
from junior.google.auth import GoogleError, call
from junior.google.drive import FILES
from junior.settings_store import get_setting


def sharing_meta(role="", request=""):
    if not role:
        words = re.sub(r"\[file \d+:[^\]]*\]", "", request, flags=re.I).casefold()
        if re.search(r"\bprivate\b|don't share|do not share|not public", words):
            role = "private"
        elif re.search(r"view.only|read.only|not editable", words):
            role = "reader"
        elif re.search(r"public.{0,25}edit|anyone.{0,30}edit|edit(?:able|ing)?.{0,30}(?:anyone|public)", words):
            role = "writer"
        elif re.search(r"\bpublic\b|anyone.{0,30}view", words):
            role = "reader"
        else:
            role = get_setting("drive_share_default")
    if role not in ("private", "reader", "writer"):
        raise ValueError("Sharing must be private, reader or writer.")
    return {"sharing_role": role, "required_actions": ["google.drive.share"] if role != "private" else []}


def sharing_label(role):
    return "Private" if role == "private" else "Anyone with the link can " + ("edit" if role == "writer" else "view")


async def set_link_access(fid, role):
    if role not in ("reader", "writer"):
        raise GoogleError("Choose reader (public view) or writer (public edit).")
    url = f"{FILES}/{fid}/permissions"
    params = {"fields": "permissions(id,type,role,allowFileDiscovery),nextPageToken", "supportsAllDrives": "true", "pageSize": "100"}
    anyone = []
    while True:
        got = await call("GET", url, params=params)
        anyone += [p for p in got.get("permissions", []) if p.get("type") == "anyone"]
        if not got.get("nextPageToken"):
            break
        params["pageToken"] = got["nextPageToken"]
    if anyone:
        result = await call("PATCH", f"{url}/{anyone[0]['id']}", params={"supportsAllDrives": "true", "fields": "id,type,role,allowFileDiscovery"},
                            json={"role": role, "allowFileDiscovery": False})
    else:
        result = await call("POST", url, params={"supportsAllDrives": "true", "fields": "id,type,role,allowFileDiscovery"},
                            json={"type": "anyone", "role": role, "allowFileDiscovery": False})
    if result.get("role") != role:
        raise GoogleError("Google did not confirm the requested sharing role.")
    return result


def allowed_after_creation(out):
    from junior.db import ApprovalItem, session_scope
    from junior.senders.guard import check
    with session_scope() as s:
        problems = check(s.get(ApprovalItem, out.item_id), out.text)
    if problems:
        raise GoogleError("Sharing was held: " + problems[0])


async def apply_prepared_sharing(out, fid):
    role = out.meta.get("sharing_role", "private")
    if role != "private":
        allowed_after_creation(out)
        await set_link_access(fid, role)
