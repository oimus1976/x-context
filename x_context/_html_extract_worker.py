"""Private one-page HTML extraction subprocess; no imports from the product.

``--technical`` (Issue #77 stage 3, thread reference pages only) keeps code
line breaks/indentation, prefers GitHub-Gist-like file bodies, then
main/article text, and reports truncation against its own larger text limit.
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
MAX_OUTPUT_BYTES = 32768
# Technical mode (thread reference pages): its own saved-text limit. JSON with
# ensure_ascii=False expands one character to at most 6 bytes (a control
# character becomes \u00XX), so title + description + excerpt plus the fixed
# array syntax stay within MAX_TECHNICAL_OUTPUT_BYTES. Mirrored and checked by
# page_capture (this worker imports nothing from the product).
MAX_TECHNICAL_TEXT = 65536
MAX_TECHNICAL_OUTPUT_BYTES = 6 * (512 + 1024 + MAX_TECHNICAL_TEXT) + 64

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
# GitHub-Gist-like file structure (hypothesis from public class names, not
# compared with the real DOM): a ``file`` container holds a file header with
# the ``gist-blob-name`` and a body region (``blob-wrapper`` code table or
# rendered ``markdown-body``). Page actions (Embed/Share/Clone/Download/Star),
# file actions and comments are outside these regions, so they are left out
# structurally, without deleting UI words from the text. Line-number cells are
# excluded inside a region.
_FILE_CLASS = "file"
_FILE_NAME_CLASS = "gist-blob-name"
_FILE_BODY_CLASSES = frozenset(("blob-wrapper", "markdown-body"))
_LINE_NUMBER_CLASSES = frozenset(("blob-num", "js-line-number"))
_VOID_TAGS = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input",
                        "link", "meta", "source", "track", "wbr"))


class _TechnicalHTML(HTMLParser):
    """Issue #77 stage 3: keep code layout and prefer main/article content.

    Text is collected as (preformatted, text) runs separated by block breaks
    (None): for the whole body, for main/article subtrees, and for Gist-like
    file names and file bodies (``file_runs``); extraction prefers file runs,
    then main/article, then body, whichever first contains text.
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
        self.file_runs = []
        # Per-index counts of true flags on pre_stack, kept in step with every
        # push/pop/trim so that a flag lookup is O(1) even at the 256-entry
        # stack bound (adversarial nesting stays within the shared deadline).
        self.flag_counts = [0] * 7

    def _count(self, entries, sign: int) -> None:
        for entry in entries:
            for index in (1, 3, 4, 5, 6):
                if entry[index]:
                    self.flag_counts[index] += sign

    def _flag(self, index: int) -> bool:
        return self.flag_counts[index] > 0

    def _in_file_region(self) -> bool:
        """Inside a file name or file body (line-number cells included)."""
        return self._flag(3) or self._flag(4)

    def _break(self):
        targets = ([self.body_runs] + ([self.main_runs] if self.main_depth else [])
                   + ([self.file_runs] if self._in_file_region() else []))
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
            in_file = self._flag(6)
            in_region = self._in_file_region()
            own_name = in_file and not in_region and _FILE_NAME_CLASS in classes
            own_body = in_file and not in_region and bool(classes & _FILE_BODY_CLASSES)
            if (own_name or own_body) and self.file_runs and self.file_runs[-1] is not None:
                # Each file name/body starts on its own line, in document order.
                self.file_runs.append(None)
            # (tag, preformatted, body-data count at start, file name, file
            # body, line-number cell, file container): an empty code cell/pre
            # still stands for one (blank) source line.
            entry = (tag, own_pre, self.data_count, own_name, own_body,
                     bool(classes & _LINE_NUMBER_CLASSES), _FILE_CLASS in classes)
            self.pre_stack.append(entry)
            self._count((entry,), 1)
            # Bound the open-element stack for malformed input.
            self._count(self.pre_stack[:-256], -1)
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
                own_pre, started_at = self.pre_stack[index][1:3]
                if own_pre and started_at == self.data_count and self.in_body and not self.skip:
                    self._append((True, ""))
                # Break while the closing element is still on the stack, so a
                # file name/body region also ends its own line in file_runs.
                if tag in _BLOCK_TAGS or any(self.pre_stack[index][3:5]):
                    self._break()
                self._count(self.pre_stack[index:], -1)
                del self.pre_stack[index:]
                break
        else:
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
        self._append((self._flag(1), data))

    def _append(self, run):
        self.body_runs.append(run)
        if self.main_depth:
            self.main_runs.append(run)
        if self._in_file_region() and not self._flag(5):
            self.file_runs.append(run)


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
            # No newline stripping: leading/inner/trailing blank lines are
            # source lines of the code (L2 re-review M-1).
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            lines.extend(line.rstrip() for line in text.split("\n"))
        else:
            text = re.sub(r"\s+", " ", "".join(data for _, data in block)).strip()
            if text:
                lines.append(text)
    # Ordinary blocks never yield blank lines, so every blank line here comes
    # from preformatted code and is kept, including at the edges (M-1).
    return "\n".join(lines)


def _extract_technical(body: bytes):
    page = _TechnicalHTML()
    decoded = body.decode("utf-8", errors="replace")
    for start in range(0, len(decoded), 1024):
        page.feed(decoded[start:start + 1024])
    page.close()
    # Gist-like file bodies first; otherwise the unchanged main/article -> body
    # fallback (also when a file region exists but holds no text).
    text = ""
    for runs in (page.file_runs, page.main_runs, page.body_runs):
        text = _layout(runs)
        if text.strip():
            break
    if not text.strip():
        excerpt, truncated = None, False
    else:
        excerpt, truncated = text[:MAX_TECHNICAL_TEXT], len(text) > MAX_TECHNICAL_TEXT
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
        if len(raw) > (MAX_TECHNICAL_OUTPUT_BYTES if technical else MAX_OUTPUT_BYTES):
            return 2
    except Exception:
        return 2
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
