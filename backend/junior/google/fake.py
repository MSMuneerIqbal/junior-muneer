"""A pretend Google (FAKE_AI with GOOGLE_CLIENT_ID=fake, and the tests): sign-in, Docs, Sheets, Drive export and
Calendar, kept in memory. Nothing leaves the PC."""

import base64
import json
import re
from datetime import UTC, datetime
from functools import lru_cache

import httpx

SCOPES = (
    "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/drive.file "
    "https://www.googleapis.com/auth/drive.readonly "
    "https://www.googleapis.com/auth/documents.readonly https://www.googleapis.com/auth/spreadsheets.readonly "
    "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.compose"
)


class FakeGoogle:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {
            "doc-plan": {"title": "Research plan", "text": "Goal: an AI tutor for Urdu speakers.\nStep 1: survey."}
        }
        self.sheets: dict[str, dict] = {
            "sheet-income": {"title": "Income", "tabs": {"Sheet1": [["Month", "USD"], ["Sep", "900"], ["Oct", "1200"]]}}
        }
        self.presentations: dict[str, dict] = {}
        self.files: dict[str, dict] = {
            "file-cv-2026": {"name": "Muneer Iqbal CV.pdf", "mimeType": "application/pdf", "size": "52000",
                             "data": tiny_pdf("Muneer Iqbal - Agentic AI Engineer, Lahore")},
            "file-invoice": {"name": "Invoice September.pdf", "mimeType": "application/pdf", "size": "900",
                             "parents": ["folder-work"], "data": tiny_pdf("Invoice 42: total Rs 5,000")},
            "file-old-cv": {"name": "Muneer Iqbal CV 2024.docx", "size": "40000",
                            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "data": b"PK old"},
            "folder-work": {"name": "Work", "mimeType": "application/vnd.google-apps.folder", "data": b""},  # yours
        }
        self.events: list[dict] = []
        now = int(datetime.now(UTC).timestamp())
        self.mail: list[dict] = [
            {"id": "msg0001client", "threadId": "thr0001", "labels": ["INBOX", "UNREAD"], "at": now - 3600,
             "from": "Ali Khan <ali@acme.com>", "to": "you@example.com", "subject": "Quote for a chatbot",
             "message_id": "<ali-1@acme.com>", "body": "Hi Muneer, can you send a quote for a support chatbot by Friday? Thanks, Ali"},
            {"id": "msg0002promo", "threadId": "thr0002", "labels": ["INBOX", "CATEGORY_PROMOTIONS"], "at": now - 1800,
             "from": "Shop <deals@shop.example>", "to": "you@example.com", "subject": "50% off today",
             "message_id": "<deal@shop.example>", "html": "<p>Big <b>sale</b> today</p>"},
        ]
        self.drafts: dict[str, dict] = {}
        self.sent: list[dict] = []
        self.revoked: list[str] = []
        self.scopes = SCOPES
        self.n = 0

    def _id(self, kind: str) -> str:
        self.n += 1
        return f"{kind}-{self.n}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path, method = request.url.host, request.url.path, request.method
        body = json.loads(request.content) if request.content and request.headers.get("content-type", "").startswith("application/json") else {}
        if host == "oauth2.googleapis.com" and path == "/token":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form.get("refresh_token") == "revoked":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "fake-access", "expires_in": 3600,
                                             "refresh_token": "fake-refresh", "scope": self.scopes})
        if host == "oauth2.googleapis.com" and path == "/revoke":
            self.revoked.append(request.content.decode())
            return httpx.Response(200, json={})
        if host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "you@example.com"})

        # Docs
        if host == "docs.googleapis.com":
            if method == "POST" and path == "/v1/documents":
                doc_id = self._id("doc")
                self.docs[doc_id] = {"title": body.get("title", "Untitled"), "text": ""}
                return httpx.Response(200, json={"documentId": doc_id, "title": self.docs[doc_id]["title"]})
            m = re.match(r"^/v1/documents/([^/:]+)(:batchUpdate)?$", path)
            if m and m.group(1) in self.docs:
                doc = self.docs[m.group(1)]
                if m.group(2):
                    for r in body.get("requests", []):
                        if "insertText" in r:
                            doc["text"] += r["insertText"]["text"]
                        else:
                            doc.setdefault("styles", []).append(r)
                    return httpx.Response(200, json={"documentId": m.group(1)})
                content = [{"paragraph": {"elements": [{"textRun": {"content": line + "\n"}}]}} for line in doc["text"].split("\n")]
                return httpx.Response(200, json={"documentId": m.group(1), "title": doc["title"], "body": {"content": content}})
            return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})

        # Slides: emulate API structure, including real note shape IDs and immutable object IDs.
        if host == "slides.googleapis.com":
            if method == "POST" and path == "/v1/presentations":
                fid = self._id("presentation")
                self.presentations[fid] = {"title": body["title"], "slides": [], "requests": []}
                return httpx.Response(200, json={"presentationId": fid, "pageSize": {
                    "width": {"magnitude": 9144000, "unit": "EMU"}, "height": {"magnitude": 5143500, "unit": "EMU"}}})
            match = re.fullmatch(r"/v1/presentations/([^/:]+)(:batchUpdate)?", path)
            if match and match[1] in self.presentations:
                deck = self.presentations[match[1]]
                if match[2]:
                    for request in body["requests"]:
                        if "createSlide" in request:
                            oid = request["createSlide"]["objectId"]
                            deck["slides"].append({"objectId": oid, "slideProperties": {
                                "notesPage": {"notesProperties": {"speakerNotesObjectId": oid + "_notes"}}}})
                    deck["requests"].extend(body["requests"])
                    return httpx.Response(200, json={"presentationId": match[1]})
                return httpx.Response(200, json={"presentationId": match[1], **deck})
            return httpx.Response(404, json={"error": {"message": "Presentation not found."}})

        # Sheets
        if host == "sheets.googleapis.com":
            if method == "POST" and path == "/v4/spreadsheets":
                sheet_id = self._id("sheet")
                tab = body.get("sheets", [{}])[0].get("properties", {}).get("title", "Sheet1")
                self.sheets[sheet_id] = {"title": body["properties"]["title"], "tabs": {tab: []}, "value_input": None}
                return httpx.Response(200, json={"spreadsheetId": sheet_id,
                                                 "spreadsheetUrl": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"})
            m = re.match(r"^/v4/spreadsheets/([^/:]+)(?:(:batchUpdate)|/values/(.+))?$", path)
            if m and m.group(1) in self.sheets:
                sheet = self.sheets[m.group(1)]
                if m.group(2):
                    sheet.setdefault("formatting", []).extend(body.get("requests", []))
                    return httpx.Response(200, json={"spreadsheetId": m.group(1)})
                if m.group(3) is None:
                    return httpx.Response(200, json={"properties": {"title": sheet["title"]},
                                                     "sheets": [{"properties": {"title": t}} for t in sheet["tabs"]]})
                tab = m.group(3).split("!")[0].strip("'")
                if method == "PUT":
                    sheet["tabs"][tab] = body["values"]
                    sheet["value_input"] = request.url.params.get("valueInputOption")
                    return httpx.Response(200, json={"updatedRows": len(body["values"])})
                return httpx.Response(200, json={"values": sheet["tabs"].get(tab, [])})
            return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})

        # Drive: search, file details, download, Google's own files exported, new folders and uploads
        if host == "www.googleapis.com" and (permission_match := re.match(r"^/drive/v3/files/([^/]+)/permissions(?:/([^/]+))?$", path)):
            fid, pid = permission_match.groups()
            permissions = self.__dict__.setdefault("permissions", {}).setdefault(fid, [])
            if method == "GET":
                return httpx.Response(200, json={"permissions": permissions})
            if method == "POST":
                entry = {"id": self._id("permission"), **body}
                permissions.append(entry)
                return httpx.Response(200, json=entry)
            if method == "PATCH":
                entry = next((p for p in permissions if p["id"] == pid), None)
                if entry is not None:
                    entry.update(body)
                    return httpx.Response(200, json=entry)
            return httpx.Response(404)
        if host == "www.googleapis.com" and path == "/upload/drive/v3/files":
            return self._upload(request)
        if host == "www.googleapis.com" and path == "/drive/v3/files" and method == "POST":
            fid = self._id("folder")
            self.files[fid] = {"name": body["name"], "mimeType": body["mimeType"], "parents": body.get("parents", ["root"]),
                               "app": True, "data": b""}
            return httpx.Response(200, json={"id": fid, "name": body["name"], "webViewLink": f"https://drive.google.com/drive/folders/{fid}"})
        if host == "www.googleapis.com" and path.startswith("/drive/v3/files"):
            return self._drive(request, path)

        if host == "gmail.googleapis.com":
            return self._gmail(request, path.removeprefix("/gmail/v1/users/me"), body)

        # Calendar
        if host == "www.googleapis.com" and path == "/calendar/v3/calendars/primary/events":
            if method == "POST":
                event = {**body, "id": self._id("event"), "status": "confirmed"}
                event["htmlLink"] = f"https://www.google.com/calendar/event?eid={event['id']}"
                self.events.append(event)
                return httpx.Response(200, json=event)
            lo, hi = (_when(request.url.params.get(k)) for k in ("timeMin", "timeMax"))
            found = [e for e in self.events if lo <= _when(e["start"].get("dateTime") or e["start"].get("date")) < hi]
            q = request.url.params.get("q", "").casefold()
            found = [e for e in found if q in e.get("summary", "").casefold()]
            found.sort(key=lambda e: _when(e["start"].get("dateTime") or e["start"].get("date")))
            return httpx.Response(200, json={"items": found})
        return httpx.Response(404, json={"error": {"message": f"Fake Google doesn't know {method} {host}{path}"}})

    def add_mail(self, **mail) -> None:
        """A new email arrives (tests)."""
        self.mail.append({"labels": ["INBOX", "UNREAD"], "at": int(datetime.now(UTC).timestamp()), "threadId": mail["id"],
                          "to": "you@example.com", "message_id": f"<{mail['id']}@x>", **mail})

    def _message(self, m: dict) -> dict:
        from email.utils import formatdate

        headers = [{"name": k, "value": v} for k, v in (("From", m["from"]), ("To", m["to"]), ("Subject", m["subject"]),
                                                        ("Date", formatdate(m["at"])), ("Message-ID", m["message_id"]))]
        part = ("text/html", m["html"]) if "html" in m else ("text/plain", m.get("body", ""))
        data = base64.urlsafe_b64encode(part[1].encode()).decode().rstrip("=")
        return {"id": m["id"], "threadId": m["threadId"], "labelIds": m["labels"], "snippet": re.sub("<[^>]+>", "", part[1])[:100],
                "internalDate": str(m["at"] * 1000),
                "payload": {"mimeType": "multipart/alternative", "headers": headers,
                            "parts": [{"mimeType": part[0], "body": {"data": data}}]}}

    def _gmail(self, request: httpx.Request, path: str, body: dict) -> httpx.Response:
        method = request.method
        if path == "/profile":
            return httpx.Response(200, json={"emailAddress": "you@example.com"})
        if path == "/messages" and method == "GET":
            q = request.url.params.get("q", "")
            after = int(m.group(1)) if (m := re.search(r"after:(\d+)", q)) else 0
            sender = m.group(1).lower() if (m := re.search(r"from:(\S+)", q)) else ""
            words = [w for w in q.split() if ":" not in w]
            found = [m for m in sorted(self.mail, key=lambda m: -m["at"])
                     if m["at"] > after and sender in m["from"].lower()
                     and all(w.lower() in (m["subject"] + m.get("body", "")).lower() for w in words)]
            limit = int(request.url.params.get("maxResults", "10"))
            return httpx.Response(200, json={"messages": [{"id": m["id"], "threadId": m["threadId"]} for m in found[:limit]]})
        if (m := re.match(r"^/messages/([A-Za-z0-9]+)$", path)) and method == "GET":
            mail = next((x for x in self.mail if x["id"] == m.group(1)), None)
            if mail is None:
                return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})
            return httpx.Response(200, json=self._message(mail))
        if path == "/drafts" and method == "POST":
            draft_id = self._id("draft")
            self.drafts[draft_id] = body["message"]
            return httpx.Response(200, json={"id": draft_id, "message": {"id": f"m-{draft_id}"}})
        if (m := re.match(r"^/drafts/([\w-]+)$", path)) and method == "PUT":
            if m.group(1) not in self.drafts:
                return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})
            self.drafts[m.group(1)] = body["message"]
            return httpx.Response(200, json={"id": m.group(1)})
        if path == "/drafts/send":
            message = self.drafts.pop(body["id"], None)
            if message is None:
                return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})
            self.sent.append(message)
            return httpx.Response(200, json={"id": f"sent{len(self.sent)}", "threadId": message.get("threadId", "")})
        if path == "/messages/send":
            self.sent.append(body)
            return httpx.Response(200, json={"id": f"sent{len(self.sent)}", "threadId": body.get("threadId", "")})
        return httpx.Response(404, json={"error": {"message": f"Fake Gmail doesn't know {method} {path}"}})

    def _all_files(self) -> dict[str, dict]:
        files = {fid: {"name": d["title"], "mimeType": "application/vnd.google-apps.document"} for fid, d in self.docs.items()}
        files |= {fid: {"name": s["title"], "mimeType": "application/vnd.google-apps.spreadsheet"} for fid, s in self.sheets.items()}
        files |= {fid: {"name": s["title"], "mimeType": "application/vnd.google-apps.presentation"} for fid, s in self.presentations.items()}
        return files | {fid: {k: v for k, v in f.items() if k != "data"} for fid, f in self.files.items()}

    def _drive(self, request: httpx.Request, path: str) -> httpx.Response:
        files = self._all_files()
        if path == "/drive/v3/files":
            q = request.url.params.get("q", "")
            words = re.findall(r"name contains '((?:[^'\\]|\\.)*)'", q)
            exact = re.findall(r"name = '((?:[^'\\]|\\.)*)'", q)
            mime = re.findall(r"mimeType = '([^']*)'", q)
            parent = re.findall(r"'([^']*)' in parents", q)
            found = [
                {"id": fid, **{k: v for k, v in f.items() if k not in ("parents", "app")},
                 "modifiedTime": "2026-10-01T09:00:00Z", "webViewLink": f"https://drive.google.com/file/d/{fid}/view"}
                for fid, f in files.items()
                if all(w.casefold() in f["name"].casefold() for w in words)
                and all(f["name"] == e.replace("\\'", "'") for e in exact)
                and all(f["mimeType"] == m for m in mime)
                and all(p in f.get("parents", ["root"]) for p in parent)
            ]
            offset = int(request.url.params.get("pageToken", "0"))
            count = int(request.url.params.get("pageSize", "100"))
            result = {"files": found[offset:offset + count]}
            if offset + count < len(found):
                result["nextPageToken"] = str(offset + count)
            return httpx.Response(200, json=result)
        m = re.match(r"^/drive/v3/files/([^/]+)(/export)?$", path)
        if not m or m.group(1) not in files:
            return httpx.Response(404, json={"error": {"message": "File not found."}})
        fid, info = m.group(1), files[m.group(1)]
        if m.group(2):
            text = self.docs.get(fid, {}).get("text", "")
            return httpx.Response(200, content=f"exported as {request.url.params.get('mimeType')}: {text}".encode())
        if request.url.params.get("alt") == "media":
            if info["mimeType"].startswith("application/vnd.google-apps."):
                return httpx.Response(403, json={"error": {"message": "Only files with binary content can be downloaded."}})
            return httpx.Response(200, content=self.files[fid]["data"])
        return httpx.Response(200, json={"id": fid, **{k: v for k, v in info.items() if k not in ("parents", "app")}})

    def _upload(self, request: httpx.Request) -> httpx.Response:
        boundary = request.headers["content-type"].split("boundary=")[1]
        parts = request.content.split(f"--{boundary}".encode())
        meta = json.loads(parts[1].split(b"\r\n\r\n", 1)[1].strip())
        head, data = parts[2].split(b"\r\n\r\n", 1)
        parent = meta.get("parents", ["root"])[0]
        folder = self.files.get(parent)
        from junior.google.auth import has_scope
        if parent != "root" and not (folder and (folder.get("app") or has_scope("drive"))):
            # The app may only add to folders it made (drive.file); Google answers as if it can't see yours.
            return httpx.Response(404, json={"error": {"message": f"File not found: {parent}."}})
        fid = self._id("upload")
        mime = head.decode().split("Content-Type:")[1].strip()
        self.files[fid] = {"name": meta["name"], "mimeType": mime, "parents": [parent], "app": True, "data": data[: -len(b"\r\n")]}
        return httpx.Response(200, json={"id": fid, "name": meta["name"], "webViewLink": f"https://drive.google.com/file/d/{fid}/view"})


def tiny_pdf(text: str) -> bytes:
    """A real one-page PDF with this text (for reading tests)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def _when(text: str | None) -> datetime:
    """A time from Google's formats (2026-11-05T10:00:00+05:00, ...Z, or a date) as UTC."""
    if not text:
        return datetime.max.replace(tzinfo=UTC)
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


@lru_cache
def fake_store() -> FakeGoogle:
    return FakeGoogle()


def fake_google() -> httpx.MockTransport:
    return httpx.MockTransport(fake_store())
