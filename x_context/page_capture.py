"""Issue #64 AC-2: one explicitly selected external HTML page; no crawler.

No X calls, credentials, browser cookies, JavaScript execution, image download
or implicit link traversal. Network operations are opt-in via the CLI. The
fetcher pins DNS-vetted public IPs through the TCP/TLS boundary, without proxies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import http.client
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
import time
from typing import Callable, Mapping
from urllib.parse import urljoin, urlsplit

from .bookmark_enrichment import Snapshot as EnrichmentSnapshot, _unique as unique_json
from .bookmark_store import StoreSnapshot, _timestamp

MAX_HTML_BYTES = 512 * 1024
MAX_PAGE_TEXT = 4096
MAX_REDIRECTS = 2
MAX_URL_CHARS = 4096
TIMEOUT_SECONDS = 8
MAX_STORE_BYTES = 16 * 1024 * 1024

_STATES = frozenset({
    "captured", "blocked_target", "connection_error", "http_error",
    "authentication_required", "not_html", "too_large", "no_extractable_text",
    "redirect_limit", "invalid_response", "timeout",
})


class PageTimeout(TimeoutError):
    """The shared monotonic request/redirect/extraction deadline elapsed."""


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise PageTimeout()
    return left


class PageCaptureError(ValueError):
    def __init__(self, category="storage_error", *, may_have_occurred=False):
        super().__init__(category)
        self.category = category
        self.may_have_occurred = may_have_occurred


@dataclass(frozen=True, slots=True)
class PageResponse:
    status: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    path: Path = field(repr=False)
    raw: bytes | None = field(repr=False)
    value: dict | None = field(repr=False)


Resolver = Callable[[str, int], tuple[str, ...]]
Transport = Callable[[str, tuple[str, ...], float], PageResponse]


def _valid_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # Explicitly disallow mapped IPv4 forms to avoid inconsistent reachability.
    # Well-known and local-use NAT64 prefixes can translate to private IPv4.
    if isinstance(address, ipaddress.IPv6Address) and any(address in network for network in (
        ipaddress.IPv6Network("64:ff9b::/96"), ipaddress.IPv6Network("64:ff9b:1::/48"),
    )):
        return False
    return address.is_global and getattr(address, "ipv4_mapped", None) is None


def _url_parts(url: str):
    if not isinstance(url, str) or not 1 <= len(url) <= MAX_URL_CHARS or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ValueError("invalid URL")
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username is not None or p.password is not None:
        raise ValueError("invalid URL")
    port = 443 if p.scheme == "https" else 80
    if p.port is not None and p.port != port:
        raise ValueError("nonstandard port blocked")
    host = p.hostname
    if len(host) > 253 or host.endswith(".") or not host.isascii() or any(ord(c) < 33 for c in host):
        raise ValueError("bad host")
    if host.lower() in ("localhost",) or host.lower().endswith((".localhost", ".local", ".internal")):
        raise ValueError("nonpublic host")
    # Reject obviously malformed host names; do not accept IPv4 octal shortcuts.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", host):
            raise ValueError("invalid hostname") from None
        if any(not 1 <= len(label) <= 63 or label.startswith("-") or label.endswith("-")
               for label in host.split(".")):
            raise ValueError("invalid hostname")
    else:
        if not _valid_public_ip(str(addr)):
            raise ValueError("private IP")
    return p, host, port


def _resolver(host: str, port: int) -> tuple[str, ...]:
    # Resolver failures remain connection errors, not access-policy rejections.
    return tuple(sorted({row[4][0] for row in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM)}))


class _DeadlineSocket:
    """Socket file-adapter enforcing one absolute budget on every TCP/TLS read.

    http.client reads headers and chunk metadata via buffered readline(), which
    may perform many socket reads inside a single getresponse/read1 call. Set
    remaining time before *each* low-level recv, not merely per HTTP operation.
    Keep the socket alive while HTTPResponse's makefile reference is open.
    """
    def __init__(self, sock: socket.socket, deadline: float):
        self._sock = sock
        self._deadline = deadline
        self._files = 0
        self._closed = False

    def settimeout(self, seconds: float):
        self._sock.settimeout(min(seconds, _remaining(self._deadline)))

    def recv_into(self, buffer):
        self._sock.settimeout(_remaining(self._deadline))
        return self._sock.recv_into(buffer)

    def sendall(self, data):
        self._sock.settimeout(_remaining(self._deadline))
        return self._sock.sendall(data)

    def makefile(self, mode="rb"):
        if mode != "rb":
            raise ValueError("unexpected socket file mode")
        self._files += 1
        return io.BufferedReader(socket.SocketIO(self, "rb"))

    def fileno(self):
        return self._sock.fileno()

    def _decref_socketios(self):
        self._files -= 1
        if self._closed and self._files == 0:
            self._sock.close()

    def close(self):
        self._closed = True
        if self._files == 0:
            self._sock.close()


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, *, secure: bool,
                 deadline: float):
        super().__init__(host, port, timeout=_remaining(deadline))
        self._selected_ip = ip
        self._secure = secure
        self._deadline = deadline

    def connect(self):
        # Connect to a numeric IP using a numeric address-family socket;
        # no second hostname resolution can occur during the TCP connection.
        family = socket.AF_INET6 if ":" in self._selected_ip else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(_remaining(self._deadline))
            sock.connect((self._selected_ip, self.port))
            if self._secure:
                sock.settimeout(_remaining(self._deadline))
                sock = ssl.create_default_context().wrap_socket(
                    sock, server_hostname=self.host)
            sock.settimeout(_remaining(self._deadline))
        except BaseException:
            sock.close()
            raise
        self.sock = _DeadlineSocket(sock, self._deadline)


def _transport(url: str, vetted_ips: tuple[str, ...],
               deadline: float) -> PageResponse:
    p, host, port = _url_parts(url)
    if not vetted_ips or not all(_valid_public_ip(ip) for ip in vetted_ips):
        raise OSError("no public addresses")
    conn = _PinnedHTTP(host, port, vetted_ips[0], secure=p.scheme == "https",
                       deadline=deadline)
    response = None
    try:
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        _remaining(deadline)
        conn.request("GET", path, headers={
            "Host": p.netloc, "Accept": "text/html", "Accept-Encoding": "identity",
            "User-Agent": "x-context/AC2", "Connection": "close",
        })
        # Connection: close may disown conn.sock after getresponse(). Retain
        # the actual socket to refresh the remaining timeout for each read.
        wire = conn.sock
        wire.settimeout(_remaining(deadline))
        response = conn.getresponse()
        body = bytearray()
        # read1() returns after at most one socket read, unlike read(n) which
        # may wait for all n bytes during a slow-trickle response.
        while len(body) <= MAX_HTML_BYTES:
            wire.settimeout(_remaining(deadline))
            part = response.read1(min(8192, MAX_HTML_BYTES + 1 - len(body)))
            if not part:
                break
            body.extend(part)
            # A known Content-Length can close the HTTPResponse immediately
            # after the last data chunk; do not touch its closed socket again.
            if response.isclosed():
                break
        _remaining(deadline)
        return PageResponse(response.status,
                            {k.lower(): v for k, v in response.getheaders()},
                            bytes(body))
    finally:
        if response is not None:
            response.close()
        conn.close()


class _PageHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.title = []
        self.description = None
        self.body = []
        self.in_body = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header"):
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "body":
            self.in_body = True
        if tag == "meta" and self.description is None:
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in ("description", "og:description") and isinstance(attrs.get("content"), str):
                self.description = attrs["content"]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header") and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        if self.in_body:
            self.body.append(data)


def _normalize_text(value: str, limit: int) -> str | None:
    result = re.sub(r"\s+", " ", value).strip()
    return result[:limit] if result else None


def _extract_html(body: bytes, *, deadline: float | None = None) -> tuple[str | None, str | None, str | None]:
    # Incremental feed avoids a single long, non-interruptible malformed-HTML
    # parse. Check the same monotonic deadline between small parse slices.
    page = _PageHTML()
    decoded = body.decode("utf-8", errors="replace")
    for start in range(0, len(decoded), 1024):
        if deadline is not None:
            _remaining(deadline)
        page.feed(decoded[start:start + 1024])
        if deadline is not None:
            _remaining(deadline)
        # Invalid, never-ending tag fragments can cause quadratic rescanning.
        if len(page.rawdata) > 16384:
            raise ValueError("malformed HTML pending buffer")
    page.close()
    if deadline is not None:
        _remaining(deadline)
    return (_normalize_text(" ".join(page.title), 512),
            _normalize_text(page.description or "", 1024),
            _normalize_text(" ".join(page.body), MAX_PAGE_TEXT))


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name and isinstance(value, str):
            return value
    return None


def capture_one(url: str, *, at: str, resolver: Resolver | None = None,
                transport: Transport | None = None) -> dict:
    """Returns a bounded result for a single explicitly selected HTTP(S) URL."""
    if not _timestamp(at):
        raise PageCaptureError("invalid_input")
    selected_resolver = _resolver if resolver is None else resolver
    selected_transport = _transport if transport is None else transport
    original = url
    current = url
    deadline = time.monotonic() + TIMEOUT_SECONDS
    final_url = None
    code = None
    state = "invalid_response"
    title = description = excerpt = None
    try:
        for redirect in range(MAX_REDIRECTS + 1):
            _remaining(deadline)
            try:
                p, host, port = _url_parts(current)
                # Fragments are client-side anchors, never HTTP request bytes.
                current = p._replace(fragment="").geturl()
                ips = selected_resolver(host, port)
                _remaining(deadline)
                if not isinstance(ips, tuple) or not ips:
                    state = "connection_error"
                    break
                if not all(_valid_public_ip(ip) for ip in ips):
                    state = "blocked_target"
                    break
            except PageTimeout:
                state = "timeout"
                break
            except ValueError:
                state = "blocked_target"
                break
            except Exception:
                state = "connection_error"
                break
            try:
                reply = selected_transport(current, ips, deadline)
                _remaining(deadline)
            except (PageTimeout, TimeoutError, socket.timeout):
                state = "timeout"
                break
            except Exception:
                state = "connection_error"
                break
            if not isinstance(reply, PageResponse) or type(reply.status) is not int or not 100 <= reply.status <= 599:
                state = "invalid_response"
                break
            if not isinstance(reply.headers, Mapping) or not isinstance(reply.body, bytes):
                state = "invalid_response"
                break
            final_url, code = current, reply.status
            if code in (301, 302, 303, 307, 308):
                location = _get_header(reply.headers, "location")
                if not location:
                    state = "invalid_response"
                    break
                if redirect == MAX_REDIRECTS:
                    state = "redirect_limit"
                    break
                current = urljoin(current, location)
                continue
            if code in (401, 403):
                state = "authentication_required"
            elif code != 200:
                state = "http_error"
            elif len(reply.body) > MAX_HTML_BYTES:
                state = "too_large"
            elif "text/html" not in (_get_header(reply.headers, "content-type") or "").lower():
                state = "not_html"
            elif (_get_header(reply.headers, "content-encoding") or "identity").lower() != "identity":
                state = "invalid_response"
            else:
                try:
                    title, description, excerpt = _extract_html(reply.body, deadline=deadline)
                except PageTimeout:
                    state = "timeout"
                    break
                state = "captured" if excerpt else "no_extractable_text"
            break
    except PageTimeout:
        state = "timeout"
    except Exception:
        state = "invalid_response"
    if state == "timeout":
        title = description = excerpt = None
    return {
        "requested_url": original, "final_url": final_url,
        "http_status": code, "retrieved_at": at, "state": state,
        "title": title, "description": description, "excerpt": excerpt,
    }


def _valid_record(record: object) -> bool:
    if not isinstance(record, dict) or set(record) != {
        "post_id", "url_index", "requested_url", "final_url", "http_status",
        "retrieved_at", "state", "title", "description", "excerpt",
    }:
        return False
    if not isinstance(record["post_id"], str) or not record["post_id"].isascii() or not record["post_id"].isdigit():
        return False
    if type(record["url_index"]) is not int or not 0 <= record["url_index"] <= 19:
        return False
    if not isinstance(record["requested_url"], str) or len(record["requested_url"]) > MAX_URL_CHARS:
        return False
    if record["final_url"] is not None and (not isinstance(record["final_url"], str) or len(record["final_url"]) > MAX_URL_CHARS):
        return False
    if record["http_status"] is not None and (type(record["http_status"]) is not int or not 100 <= record["http_status"] <= 599):
        return False
    if not _timestamp(record["retrieved_at"]) or record["state"] not in _STATES:
        return False
    for k, maximum in (("title", 512), ("description", 1024), ("excerpt", MAX_PAGE_TEXT)):
        if record[k] is not None and (not isinstance(record[k], str) or len(record[k]) > maximum):
            return False
    if record["state"] == "captured" and not record["excerpt"]:
        return False
    return True


def select_url(bookmarks: StoreSnapshot, enrichment: EnrichmentSnapshot,
               post_id: str, url_index: int) -> tuple[str, str]:
    if not isinstance(bookmarks, StoreSnapshot) or not isinstance(enrichment, EnrichmentSnapshot):
        raise PageCaptureError()
    if not isinstance(post_id, str) or not post_id.isascii() or not post_id.isdigit() or not 1 <= len(post_id) <= 19:
        raise PageCaptureError("invalid_input")
    if type(url_index) is not int or not 0 <= url_index <= 19:
        raise PageCaptureError("invalid_input")
    try:
        if bookmarks.value is None or enrichment.value is None:
            raise ValueError("no bookmarks")
        subject = bookmarks.value["subject"]["id"]
        if enrichment.value["subject_id"] != subject:
            raise ValueError("subject mismatch")
        if post_id not in {row["id"] for row in bookmarks.value["items"]}:
            raise ValueError("unknown Post")
        item = enrichment.value["items"][post_id]
        urls = item["fields"]["entities.urls"]
        if urls["state"] != "present" or url_index >= len(urls["value"]):
            raise ValueError("unknown URL index")
        link = urls["value"][url_index]
        for key in ("unwound_url", "expanded_url", "url"):
            if isinstance(link.get(key), str) and link[key]:
                return subject, link[key]
    except Exception:
        pass
    raise PageCaptureError("invalid_input") from None


def preflight(bookmarks: StoreSnapshot, enrichment: EnrichmentSnapshot) -> PageSnapshot:
    try:
        if bookmarks.value is None or enrichment.value is None:
            raise ValueError("missing inputs")
        subject = bookmarks.value["subject"]["id"]
        if enrichment.value["subject_id"] != subject:
            raise ValueError("subject mismatch")
        path = bookmarks.path.with_name("bookmark-pages-v1.json")
        with path.open("rb") as stream:
            raw = stream.read(MAX_STORE_BYTES + 1)
        if len(raw) > MAX_STORE_BYTES:
            raise ValueError("store too large")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json)
        if not isinstance(value, dict) or set(value) != {"schema_version", "subject_id", "items"}:
            raise ValueError("bad store")
        if value["schema_version"] != "1" or value["subject_id"] != subject or not isinstance(value["items"], dict):
            raise ValueError("bad store")
        if any(not _valid_record(r) or k != f'{r["post_id"]}:{r["url_index"]}' for k, r in value["items"].items()):
            raise ValueError("bad record")
        return PageSnapshot(path, raw, value)
    except FileNotFoundError:
        return PageSnapshot(bookmarks.path.with_name("bookmark-pages-v1.json"), None, None)
    except Exception:
        raise PageCaptureError() from None


def save(snapshot: PageSnapshot, *, subject_id: str, post_id: str, url_index: int,
         result: dict) -> None:
    tmp = None
    fd = None
    replaced = False
    try:
        record = {"post_id": post_id, "url_index": url_index, **result}
        if not _valid_record(record):
            raise ValueError("invalid record")
        data = json.loads(json.dumps(snapshot.value)) if snapshot.value is not None else {
            "schema_version": "1", "subject_id": subject_id, "items": {},
        }
        if data["subject_id"] != subject_id:
            raise ValueError("subject mismatch")
        data["items"][f"{post_id}:{url_index}"] = record
        raw = (json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        if len(raw) > MAX_STORE_BYTES:
            raise ValueError("store too large")
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".bookmark-pages-", suffix=".tmp", dir=snapshot.path.parent)
        tmp = Path(name)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            if stream.write(raw) != len(raw):
                raise OSError("short write")
            stream.flush()
            os.fsync(stream.fileno())
        if tmp.read_bytes() != raw:
            raise ValueError("temp mismatch")
        if (snapshot.path.read_bytes() if snapshot.path.exists() else None) != snapshot.raw:
            raise ValueError("changed store")
        os.replace(tmp, snapshot.path)
        replaced = True
        if snapshot.path.read_bytes() != raw:
            raise OSError("post-write mismatch")
    except Exception:
        raise PageCaptureError(may_have_occurred=replaced) from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
