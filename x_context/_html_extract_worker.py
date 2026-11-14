"""Private one-page HTML extraction subprocess; no imports from the product.

Invoked only by the bounded parent after explicit link capture. This worker
has no credentials/network logic. It receives at most 512 KiB via stdin,
returns only bounded normalized text, and can be terminated by the parent.
"""
from html.parser import HTMLParser
import json
import re
import sys

MAX_HTML_BYTES = 512 * 1024
MAX_PAGE_TEXT = 4096

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



def _extract(body: bytes) -> tuple[str | None, str | None, str | None]:
    page = _PageHTML()
    decoded = body.decode("utf-8", errors="replace")
    for start in range(0, len(decoded), 1024):
        page.feed(decoded[start:start + 1024])
    # CPython HTMLParser.close() can take unbounded CPU on malformed HTML.
    # The parent process imposes the shared deadline and kills this worker.
    page.close()
    return (_normalize_text(" ".join(page.title), 512),
            _normalize_text(page.description or "", 1024),
            _normalize_text(" ".join(page.body), MAX_PAGE_TEXT))


def main() -> int:
    data = sys.stdin.buffer.read(MAX_HTML_BYTES + 1)
    if len(data) > MAX_HTML_BYTES:
        return 2
    try:
        result = _extract(data)
        raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > 32768:
            return 2
    except Exception:
        return 2
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
