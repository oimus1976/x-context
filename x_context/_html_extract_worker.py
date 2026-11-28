"""Private one-page HTML extraction subprocess; no imports from the product.

``--technical`` (Issue #77 stage 3, thread reference pages only) keeps code
line breaks/indentation, prefers main/article text and reports truncation.
Without arguments the original AC-2 extraction is unchanged.

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


_SKIP_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header")
_BLOCK_TAGS = frozenset((
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li",
    "main", "ol", "p", "pre", "section", "table", "tbody", "td", "th", "thead",
    "tr", "ul",
))
# Inline-preformatted code cells as rendered by GitHub Gist (synthetic shape).
_PRE_CLASSES = frozenset(("blob-code", "blob-code-inner"))
_VOID_TAGS = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input",
                        "link", "meta", "source", "track", "wbr"))


class _TechnicalHTML(HTMLParser):
    """Issue #77 stage 3: keep code layout and prefer main/article content.

    Text is collected as (preformatted, text) runs separated by block breaks
    (None), once for the whole body and once for main/article subtrees.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.title = []
        self.description = None
        self.in_body = False
        self.main_depth = 0
        self.pre_stack = []
        self.data_count = 0
        self.body_runs = []
        self.main_runs = []

    def _break(self):
        targets = [self.body_runs] + ([self.main_runs] if self.main_depth else [])
        for runs in targets:
            if runs and runs[-1] is not None:
                runs.append(None)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _SKIP_TAGS:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "body":
            self.in_body = True
        if tag == "meta" and self.description is None:
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in ("description", "og:description") and isinstance(attrs.get("content"), str):
                self.description = attrs["content"]
        if tag in _BLOCK_TAGS:
            self._break()
        if tag in ("main", "article"):
            self.main_depth += 1
        if tag not in _VOID_TAGS:
            classes = set((attrs.get("class") or "").split())
            own_pre = tag == "pre" or bool(classes & _PRE_CLASSES)
            # (tag, preformatted, body-data count at start): an empty code
            # cell/pre still stands for one (blank) source line.
            self.pre_stack.append((tag, own_pre, self.data_count))
            # Bound the open-element stack for malformed input.
            del self.pre_stack[:-256]

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag == "body":
            self.in_body = False
        for index in range(len(self.pre_stack) - 1, -1, -1):
            if self.pre_stack[index][0] == tag:
                _, own_pre, started_at = self.pre_stack[index]
                del self.pre_stack[index:]
                if own_pre and started_at == self.data_count and self.in_body and not self.skip:
                    self._append((True, ""))
                break
        if tag in _BLOCK_TAGS:
            self._break()
        if tag in ("main", "article") and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        if not self.in_body:
            return
        self.data_count += 1
        self._append((any(pre for _, pre, _ in self.pre_stack), data))

    def _append(self, run):
        self.body_runs.append(run)
        if self.main_depth:
            self.main_runs.append(run)


def _layout(runs) -> str:
    """Join runs into lines; collapse whitespace only outside preformatted text."""
    blocks = []
    current = []
    for run in runs + [None]:
        if run is None:
            if current:
                blocks.append(current)
            current = []
        else:
            current.append(run)
    lines = []
    for block in blocks:
        if any(pre for pre, _ in block):
            text = "".join(data if pre else re.sub(r"\s+", " ", data) for pre, data in block)
            text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            lines.extend(line.rstrip() for line in text.split("\n"))
        else:
            text = re.sub(r"\s+", " ", "".join(data for _, data in block)).strip()
            if text:
                lines.append(text)
    # Ordinary blocks never yield blank lines; blank lines that remain are
    # source lines of preformatted code and are kept as-is (review M-1).
    return "\n".join(lines).strip("\n")


def _extract_technical(body: bytes):
    page = _TechnicalHTML()
    decoded = body.decode("utf-8", errors="replace")
    for start in range(0, len(decoded), 1024):
        page.feed(decoded[start:start + 1024])
    page.close()
    main_text = _layout(page.main_runs)
    text = main_text if main_text.strip() else _layout(page.body_runs)
    if not text.strip():
        excerpt, truncated = None, False
    else:
        excerpt, truncated = text[:MAX_PAGE_TEXT], len(text) > MAX_PAGE_TEXT
    return (_normalize_text(" ".join(page.title), 512),
            _normalize_text(page.description or "", 1024),
            excerpt, truncated)


def main() -> int:
    data = sys.stdin.buffer.read(MAX_HTML_BYTES + 1)
    if len(data) > MAX_HTML_BYTES:
        return 2
    technical = sys.argv[1:] == ["--technical"]
    if sys.argv[1:] and not technical:
        return 2
    try:
        result = _extract_technical(data) if technical else _extract(data)
        raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > 32768:
            return 2
    except Exception:
        return 2
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
