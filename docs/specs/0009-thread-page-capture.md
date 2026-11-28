# SPEC-0009: Issue #77 stage 3 — one saved thread reference page

Status: stage 3 merged in PR #81 (merge commit
`8bd7505249203eded1f04b1c6f8a4b58eccffd9f`, PR head `a77ba9b`); real Gist UAT
PASS with an extraction-volume constraint (PR #81 comment 7236789348);
post-merge LOCAL CLOSEOUT PASS; SAFE CLEANUP plan-only BLOCKED by unrelated
legacy worktrees (deferred maintenance). The capture-quality topic below
(Q-1..Q-6) is a Draft implementation verified with synthetic tests only.
Base (stage 3): `main` `7c8878c3c83bb765de07a1b84006b3d82a6e1bd6` (PR #79 merged).
Base (capture quality): `main` `8bd7505249203eded1f04b1c6f8a4b58eccffd9f`.
Design source: Issue #77 comment 7232454206 (stage 3); comment 7236934301
(capture quality, 2026-11-28).
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
  `excerpt_truncated`. Stage 3 kept 4096 characters / 32768 worker bytes;
  the capture-quality topic below separates the technical limits and adds
  Gist file-body selection. The legacy extraction is unchanged.
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

## Capture-quality topic (Issue #77 comment 7236934301; Draft, synthetic only)

Evidence from the real Gist UAT: the 4096-character excerpt was full
(`excerpt_truncated=true`), 1,203 characters of it were page UI inside `main`,
and the 512 KiB HTML limit was not binding (150,354 bytes). The original full
text length was not observed and is not inferred from the HTML size.

- **Extraction (technical path only).** The worker collects GitHub-Gist-like
  file text structurally: inside an element of class `file`, the file name
  (`gist-blob-name`) and the file body region (`blob-wrapper` code table or
  rendered `markdown-body`), in document order, each starting on its own line;
  the file-name line (page text) separates files. Line-number cells
  (`blob-num`, `js-line-number`) inside a region are excluded. Page actions
  (Embed/Share/Clone/Download/Star, navigation), file actions and comments are
  outside these regions and so are not collected; no UI word is deleted from
  text, so the same words inside a file body stay. Code layout rules (blank
  lines, tabs, indentation, empty code cells) are unchanged. When no file
  region holds text, the unchanged `main`/`article` → body fallback applies; a
  `markdown-body` outside a `file` container is not a file region. **These
  class names are a hypothesis from public GitHub markup; the real Gist DOM was
  not re-fetched or compared.** Rendered Markdown stays rendered text
  (paragraphs are one line); the raw Markdown source is not reconstructed and
  no extra raw GET is made. Region flags are counted on push/pop of the
  bounded (256) element stack, so lookups are O(1); a 512 KiB adversarial
  nesting input took about 1.0–1.5 s in the worker locally (main `8bd7505`:
  about 1.9–2.2 s), well within the shared 8 s deadline.
- **Saved-text limit.** Technical path: `TECHNICAL_MAX_PAGE_TEXT` = 65,536
  characters (legacy path keeps 4096). Worker output bound
  `TECHNICAL_MAX_WORKER_BYTES` = 6 × (512 + 1024 + 65,536) + 64 = 402,496
  bytes: with `ensure_ascii=False` one character is at most 6 JSON bytes (a
  control character becomes a 6-byte escape), so title + description + excerpt
  always fit; the parent checks the same bound and the per-field character
  limits, the worker mirrors the constants (tested for equality), and the
  legacy worker bound stays 32,768 bytes. `thread_pages` record validation
  uses the technical limit. Records stay in `bookmark-thread-pages-v1.json`,
  schema `"1"`, same fields; stage-3 records (≤ 4096 characters) remain valid
  without migration. **Read restriction:** an x-context build from before this
  change (e.g. `8bd7505`) rejects a store containing an excerpt longer than
  4096 characters as `storage_error` for `page capture --source-post-id` and
  `context --include-saved-details` (fails closed; no data is changed). The
  16 MiB store limit and the atomic replace are unchanged: a save that would
  exceed it fails closed as `storage_error` with the previous store bytes kept.
  Capacity (canonical JSON per maximal record, synthetic measurement): ASCII
  ≈ 65.8 KB (≈ 254 records per 16 MiB), Japanese ≈ 197 KB (≈ 85), worst-case
  control characters ≈ 394 KB (≈ 42); at 4096 characters: 4.4 / 12.6 / 24.9 KB.
- **Display separated from storage.** `context --include-saved-details` shows
  at most `THREAD_PAGE_DISPLAY_CHARS` = 4096 characters of each saved
  thread-page excerpt (the former saved amount, so the default output size and
  the 256 KiB cap without `--post-id` stay as before). When the saved excerpt
  is longer, one line `Excerpt display: shortened (shown N of M saved
  characters; display only, the saved text continues; full view: --post-id
  <id> --full-page-text)` is added. `Excerpt truncated:` keeps meaning
  capture-time truncation. Views of records ≤ 4096 characters are unchanged
  (no new line).
- **Explicit long view.** `context --include-saved-details --post-id <id>
  --full-page-text` (one explicit bookmark only; otherwise `invalid_input`,
  exit 2) shows saved excerpts in full, page by page, until
  `FULL_PAGE_TEXT_BUDGET_CHARS` = 262,144 characters (4 maximal pages) have
  been shown; later pages get the default 4096 characters with a `shortened …
  full-text display budget of 262144 characters used` line. The total shown is
  at most 262,144 + 4096 × pages characters and every page shows at least the
  default amount. Each page states `Excerpt display: complete (all M saved
  characters)` or `shortened`. It is offline, read-only and local stdout only:
  same preflight/render path, no network, no store write; the literal fence,
  provenance, `stale_reference` and the record-derived `--post-id` section
  bound are reused. The thread section and the stage-2 thread output contract
  are unchanged.
- **Capture boundary unchanged.** One explicitly selected saved URL, at most
  3 GETs, shared 8 s, 512 KiB, X API 0, DNS/public-IP pinning/TLS/redirect
  checks, X/Twitter/t.co refusal, isolated worker, no credentials, no retry.

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
  the exact head. Real Gist UAT: PASS with an extraction-volume constraint
  (PR #81 comment 7236789348; original-text comparison and real tab
  preservation were not observed).

Capture-quality topic (`tests/test_reference_capture_quality.py`, synthetic):

- **Q-1 body quality:** a synthetic Gist-like page (page UI twice inside
  `main`, two files, line numbers, a comment, UI words inside a file body)
  yields exactly the file names and bodies in document order, with a code blank
  line, tabs and an ASCII diagram kept; UI, line numbers and the comment are
  absent. A `markdown-body` outside `file` keeps the `main` fallback; an empty
  file region falls back to `main`/body; no text at all is
  `no_extractable_text`.
- **Q-2 storage:** a 20,000-character ASCII/Japanese/code text is saved to its
  end marker and re-read; 65,535 / 65,536 / 65,537 boundaries; worst-case JSON
  escaping (control characters in title, description and excerpt) fits the
  worker/parent bound; worker constants equal the parent constants; a store
  near 16 MiB fails closed with every file byte unchanged; legacy 4096 limits
  unchanged.
- **Q-3 storage vs display:** one saved record gives the 4096-character default
  view with the `shortened` line and the full view with `complete`, store hash
  unchanged; `--full-page-text` without `--post-id` or without
  `--include-saved-details` is `invalid_input`; capture truncation and display
  shortening are reported independently; the multi-page full view follows the
  262,144-character budget; the part of the view before the thread-page section
  (incl. the thread section) is identical in both views; without `--post-id`,
  20 maximal records stay within 256 KiB.
- **Q-4 compatibility/safety:** a stage-3 record (4096 characters, truncated)
  reads and renders unchanged; a record above the technical limit is rejected;
  all existing stage-3, legacy page, network-boundary and output-cap tests pass
  (two stage-3 tests moved their truncation boundary from 4096 to the technical
  limit and additionally check the full view).
- **Q-5 evidence:** RED (13 of 17 new tests failed before implementation) →
  GREEN; full product suite, `verify_repo`, `git diff --check`; exact-head CI
  and independent L2 review on the published head are separate steps.
- **Q-6 real use (separate approval; NOT_RUN):** re-capturing the same Gist URL
  to measure UI removal, saved volume, structure and default/full views needs
  new owner approval; no real data or URL goes into PR/CI.
