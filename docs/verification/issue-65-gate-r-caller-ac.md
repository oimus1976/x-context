# Issue #65 Gate R caller acceptance contract

Gate S only; actual evidence, credentials, Google, Gate R and Gate W are not authorized. This contract is frozen before RED. A single incident is bound to explicit paths and the 29-event sidecar, not discovered by name.

- R-CALL-01: validate explicit safe private paths and bounded raw evidence, fixture, and unchanged bytes before credential access. Invalid, missing, unsafe, duplicate or drifting evidence stops with zero credential/network calls.
- R-CALL-02: `drive GET about?fields=user(permissionId,me)` under the same access token must establish `me=true` and exact permissionId equality with incident owner before document reads. The existing snapshot validates folder/document owner permissions against this owner. Missing, invalid, mismatch or error stops.
- R-CALL-03: only `Store.load` after local proof and separately approved plan; exact drive.file scope and enough remaining token life for the entire deadline. Never Provider.access_token, refresh, login, exchange or save. Fail closed.
- R-CALL-04: enforce GET and a precise incident-derived path and query allowlist at the outgoing request boundary, prior to network. Reject writes, unrelated identities, and unexpected query values.
- R-CALL-05: the measured synthetic two-snapshot baseline is 80 Drive and 24 Docs GET, excluding one about GET. Freeze limits 90 Drive snapshot GET, 28 Docs GET, one about GET, and a 120 second wall-clock deadline. Every request counts, including pages; each network timeout cannot exceed remaining time. There is no retry.
- R-CALL-06: bind actual caller and dependency source bytes, compiled fixture digest, explicit paths and raw evidence hashes, selected Windows user, incident owner/folder/six IDs, limits and nonsecret approval reference into a deterministic digest. A caller flag or reviewed-code string is not authorization; a separate owner decision on the exact plan is required before live access. Only status and digest leave the caller.
- R-CALL-07: call existing read-only planner only after prechecks, preserve strict historical revisions, validate bounded local bytes at every relevant boundary, and stop on any mismatch/error/deadline without refresh, retry, fallback, remote writes or local evidence/credential/claim mutation. No unbounded secondary reads.
- R-CALL-08: synthetic RED then GREEN, fault tests, full Windows and exact-head verification, Draft PR and hosted CI. Independent L2 at immutable HEAD is required before human Ready/merge. No actual provider or private-data qualification is implied.

The SPEC-0008 single-writer/quiescence and protected-user requirements remain prerequisites; a hash or boolean does not establish OS identity, path ownership, or authorization. Uncertainty stops the operation.
