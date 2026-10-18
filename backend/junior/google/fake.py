"""A pretend Google (FAKE_AI with GOOGLE_CLIENT_ID=fake, and the tests): sign-in, Docs, Sheets, Drive export and
Calendar, kept in memory. Nothing leaves the PC."""

import json
import re
from datetime import UTC, datetime
from functools import lru_cache

import httpx

SCOPES = (
    "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/drive.file "
    "https://www.googleapis.com/auth/documents.readonly https://www.googleapis.com/auth/spreadsheets.readonly "
    "https://www.googleapis.com/auth/calendar.events"
)


class FakeGoogle:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {
            "doc-plan": {"title": "Research plan", "text": "Goal: an AI tutor for Urdu speakers.\nStep 1: survey."}
        }
        self.sheets: dict[str, dict] = {
            "sheet-income": {"title": "Income", "tabs": {"Sheet1": [["Month", "USD"], ["Sep", "900"], ["Oct", "1200"]]}}
        }
        self.events: list[dict] = []
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

        # Drive: a doc as a Word file
        m = re.match(r"^/drive/v3/files/([^/]+)/export$", path)
        if host == "www.googleapis.com" and m:
            if m.group(1) not in self.docs:
                return httpx.Response(404, json={"error": {"message": "File not found."}})
            return httpx.Response(200, content=b"PK fake docx: " + self.docs[m.group(1)]["text"].encode())

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
