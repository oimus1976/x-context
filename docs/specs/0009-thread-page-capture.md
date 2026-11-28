# SPEC-0009: Issue #77 stage 3 — one saved thread reference page

Status: Draft implementation (synthetic tests only).
Base: `main` `7c8878c3c83bb765de07a1b84006b3d82a6e1bd6` (PR #79 merged).
Design source: Issue #77 comment 7232454206 (2026-11-28).
Risk facets: `PRIVATE_DATA`, `CREDENTIALS`, `PLATFORM_DEPENDENT`, `SECURITY_BOUNDARY` → `HIGH_IMPACT`.

## Requirement

For one explicitly selected saved bookmark whose same-author thread was already
saved by `thread capture` (`bookmark-threads-v1.json`), the owner can capture one
external page referenced by one saved thread Post or saved thread-related
referenced Post, keep it locally, and read it in the offline combined Markdown.

```
page capture --post-id <bookmark id> --source-post-id <saved Post id> --url-index <0..49> --confirm-network-request
```

- Reuse `page_capture.capture_one` (DNS-vetted public IP pinning, TLS, redirect
  re-validation, shared 8-second deadline, 512 KiB body, isolated HTML worker).
  No new general-purpose fetcher, crawler, batch or retry.
- Only a URL already saved in the thread record is selectable. No arbitrary URL
  input and no X re-fetch. X API requests: 0. At most 1 URL and at most 3 HTTP GETs
  (2 redirects).
- X/Twitter hosts (`x.com`, `twitter.com`, `t.co` and their subdomains) are never
  a page target: the initial URL is rejected before any network access, and a
  redirect to such a host stops as `blocked_target` (checked locally before the
  redirect-count limit, so also when the last allowed GET redirects to X; no
  further request). An unexpanded `t.co` short
  link is therefore not followed.
- `--source-post-id` requires an explicit `--url-index` (0..49, the thread-record
  URL bound). The legacy path (no `--source-post-id`) keeps the 0..19 range,
  default 0, its sidecar and its behavior unchanged.
- If the source Post appears more than once in the thread record (thread Post
  and referenced Post), it is accepted only when the selected URL is identical
  in every occurrence; otherwise the command stops before network access.
- Results are saved to a separate subject-bound sidecar
  `bookmark-thread-pages-v1.json` keyed `<bookmark>:<source post>:<url index>`,
  reusing the existing atomic replace (temp file + fsync + compare-before-replace
  + read-back). `bookmarks-v1.json`, `bookmark-enrichment-v1.json`,
  `bookmark-pages-v1.json` and `bookmark-threads-v1.json` are not modified.
- New-path extraction ("technical" mode of the existing worker) prefers
  `main`/`article` text when present, keeps line breaks and indentation inside
  `pre` and GitHub-Gist-like `blob-code` cells (including blank lines and empty
  code cells, which stay blank lines; only ordinary text is whitespace-
  normalized), separates block elements by line breaks, and records
  `excerpt_truncated`. Limits are unchanged (4096 characters,
  32768 worker bytes). The legacy extraction is unchanged.
- `context --include-saved-details [--post-id <id>]` shows saved thread pages in
  their own section: source Post / URL index / relation, capture state, HTTP
  status, time, requested URL, the network-observed final URL of the last HTTP
  response (also for `http_error` etc.; the state line tells whether content was
  obtained), title, description and the excerpt, plus whether the excerpt was
  truncated. These untrusted fields are shown literally in backtick-fenced code
  blocks whose fence is longer than any backtick run in the value, so Markdown
  emphasis, links, images, headings and HTML are not interpreted and the value
  cannot close the fence. Tabs and blank lines are kept; other control/format
  characters are shown as `\uXXXX`. The legacy page/thread rendering is unchanged. When the
  current thread record no longer has the same URL at that position (or no
  thread record exists), only `stale_reference` is shown and the old content is
  not joined. The thread-page sidecar is read independently of the enrichment /
  legacy page sidecars.
- Output bounds: the view without `--post-id` keeps the 256 KiB combined cap.
  With `--post-id`, the thread-page section is bounded by its saved records
  (8x canonical JSON bytes — 6x escaping plus 2x fence lines — + fixed
  per-entry labels), like the thread section;
  exceeding the derived bound fails closed, never truncates silently.

Out of scope: Issue #80, Issue #64 AC-4/AC-6, G1–G3, batches, Grok, cloud
publishing, AI re-assessment, general crawling, real-site extraction tuning.

Independent L2 review 6096552383 (at `2ea14a5`) remediation: M-1 blank lines and
tabs in code kept from storage to Markdown; M-2 literal fenced display; m-1
redirect to X on the last allowed GET is `blocked_target`; m-2 observed final URL
shown for non-captured states. Delta re-review 6096632061 (at `e6f5cd9`): M-1
completed by also keeping leading and trailing blank code lines (no newline
stripping of preformatted text or of the excerpt; they count toward the
4096-character truncation boundary).

## Acceptance criteria

- **AC-1 selection:** the correct saved URL (unwound > expanded > url) is selected
  for a thread Post and for a referenced Post. Unknown bookmark, bookmark without
  thread record, unknown source Post, unknown index, out-of-range index, missing
  `--url-index`, missing confirmation flag, ambiguous duplicate URL, X/Twitter/t.co
  URL, subject mismatch: exit 2 before any DNS/transport call and without writes.
- **AC-2 capture:** one fake-transport capture reuses the existing boundary
  (public-IP check, redirect re-validation, redirect to X blocked), failure states
  are stored distinctly from success, and synthetic code-bearing HTML keeps title,
  `pre`/Gist line breaks and indentation, `main` preference, and the truncation flag.
- **AC-3 storage:** only the new sidecar changes; it is atomically saved, re-read
  and validated (subject, key/record consistency, URL policy). Other sidecars and
  other records keep their bytes. Corrupt or mixed-subject stores stop before any
  network access.
- **AC-4 display:** offline Markdown shows text, source and state; changed URL or
  missing thread record yields `stale_reference` without old content. Existing
  views without a thread-page sidecar are byte-identical; the long-form thread and
  output-cap regressions still pass.
- **AC-5 evidence:** existing tests and exact-head CI pass; independent L2 review on
  the exact head. A real Gist UAT (one URL, save, offline re-read, text comparison)
  needs separate approval and is NOT_RUN here.
