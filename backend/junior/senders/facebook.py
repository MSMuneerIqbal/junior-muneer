"""Facebook Page posting through Meta's Graph API (P3-02).

Plain code: it posts exactly the approved text (and your images) to your Facebook Page.
    text only     POST /{page-id}/feed    message
    one image     POST /{page-id}/photos  caption + the image file
    more images   each image unpublished on /{page-id}/photos, then /{page-id}/feed with attached_media
The Page access token comes from backend/.env (set by `connect.bat meta`); every call also sends an
appsecret_proof when the app secret is known, so a leaked token alone can't be used.
"""

import hashlib
import hmac
import json
import mimetypes
from collections.abc import Callable

import httpx

from junior.senders.base import Outgoing, SendResult, result_from_http_error

GRAPH = "https://graph.facebook.com"
TIMEOUT_SECONDS = 45


def appsecret_proof(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


class GraphError(Exception):
    """Meta answered with an error: its message and code, in plain words."""

    def __init__(self, status: int, code: int | None, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class FacebookPageSender:
    label = "Facebook"
    action_types = ("facebook.page.post",)

    def __init__(
        self,
        page_id: str,
        token: str,
        app_secret: str = "",
        version: str = "v26.0",
        transport: httpx.AsyncBaseTransport | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.page_id, self.token, self.app_secret, self.version = page_id, token, app_secret, version
        self._transport = transport
        self._client_factory = client_factory

    def is_connected(self) -> bool:
        return bool(self.page_id and self.token)

    def _client(self) -> httpx.AsyncClient:
        if self._client_factory:
            return self._client_factory()
        return httpx.AsyncClient(base_url=f"{GRAPH}/{self.version}/", timeout=TIMEOUT_SECONDS, transport=self._transport)

    def _auth(self) -> dict[str, str]:
        params = {"access_token": self.token}
        if self.app_secret:
            params["appsecret_proof"] = appsecret_proof(self.token, self.app_secret)
        return params

    async def _call(self, client: httpx.AsyncClient, method: str, path: str, **kw) -> dict:
        r = await client.request(method, path, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code >= 500:
            r.raise_for_status()  # a server problem: it may or may not have happened (unclear)
        if r.status_code >= 400 or (isinstance(body, dict) and "error" in body):
            err = body.get("error", {}) if isinstance(body, dict) else {}
            message = str(err.get("message") or r.text[:200])
            if err.get("is_transient"):
                message = f"a temporary problem at Facebook ({message}). Nothing was posted; try again later."
            raise GraphError(r.status_code, err.get("code"), message)
        return body

    async def check(self) -> str:
        """Whether the token still works, in plain words."""
        async with self._client() as client:
            try:
                page = await self._call(client, "GET", self.page_id, params={**self._auth(), "fields": "name"})
            except GraphError as e:
                return f"Facebook refused the connection: {_plain(e)}"
            except httpx.HTTPError:
                return "Couldn't reach Facebook right now."
        return f"Connected to the Page “{page.get('name', self.page_id)}”."

    async def send(self, out: Outgoing) -> SendResult:
        try:
            async with self._client() as client:
                if not out.images:
                    body = await self._call(client, "POST", f"{self.page_id}/feed", data={**self._auth(), "message": out.text})
                    post_id = body.get("id", "")
                elif len(out.images) == 1:
                    body = await self._photo(client, out.images[0], caption=out.text, published=True)
                    post_id = body.get("post_id") or body.get("id", "")
                else:
                    media = [(await self._photo(client, p, published=False))["id"] for p in out.images]
                    data = {**self._auth(), "message": out.text}
                    for n, media_id in enumerate(media):
                        data[f"attached_media[{n}]"] = json.dumps({"media_fbid": media_id})
                    body = await self._call(client, "POST", f"{self.page_id}/feed", data=data)
                    post_id = body.get("id", "")
                url = await self._permalink(client, post_id)
        except GraphError as e:
            return SendResult("failed", f"Facebook refused it: {_plain(e)}")
        except httpx.HTTPError as e:
            return result_from_http_error(e, "Facebook")
        return SendResult("sent", "Posted on your Facebook Page.", remote_id=post_id, url=url)

    async def _photo(self, client: httpx.AsyncClient, path, caption: str = "", published: bool = True) -> dict:
        content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = {**self._auth(), "published": "true" if published else "false"}
        if caption:
            data["caption"] = caption
        with open(path, "rb") as f:
            return await self._call(client, "POST", f"{self.page_id}/photos", data=data, files={"source": (path.name, f.read(), content_type)})

    async def _permalink(self, client: httpx.AsyncClient, post_id: str) -> str:
        if not post_id:
            return ""
        try:
            body = await self._call(client, "GET", post_id, params={**self._auth(), "fields": "permalink_url"})
            return str(body.get("permalink_url") or "")
        except (GraphError, httpx.HTTPError):  # posted fine; only the link is missing
            return f"https://www.facebook.com/{post_id}"


def _plain(e: GraphError) -> str:
    if e.code == 190:
        return "the connection has expired or was removed. Run connect.bat meta again."
    if e.code in (10, 200) or (e.code and 200 <= e.code < 300):
        return f"a permission is missing ({e.message}). Check the app's permissions, then run connect.bat meta again."
    if e.code == 368:
        return "Facebook blocked it as possibly abusive. Nothing was posted."
    return e.message
