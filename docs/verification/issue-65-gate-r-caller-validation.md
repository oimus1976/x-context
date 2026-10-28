# Issue #65 Gate R caller — synthetic validation

The contract was recorded before the caller tests. This work remains Gate S;
no actual incident evidence, credential, Google API, Gate R or W was used.

RED evidence includes: missing caller entry; unbounded evidence read tripwire;
unbounded credential read tripwire; deadline-crossing response accepted; local
raw-byte drift reaching credential load; duplicate provider JSON keys accepted;
missing Windows caller lock; and prepare without lock. The corresponding focused
synthetic tests were run before each correction. These are distinct from the
original initial import failure. The existing planner fake trace is 80 Drive and
24 Docs GET; the new principal check adds one Drive GET.

The tests cover exact approval/source binding, explicit selected SID, synthetic
Windows ACL restrictions and local mutex, unchanged local evidence, unexpired
single-scope token without refresh/save, same-token principal equality, GET-only
method/path/query/ID restrictions, capped extra pagination, request deadlines,
redacted output, malformed JSON and existing historical revision checks. The
real Windows ACL/mutex tests use disposable synthetic objects. No remote lock,
protection from same-user malicious processes, or live provider behavior is
claimed. The final exact-head Windows result, hosted CI and independent L2 must
be recorded against the immutable PR HEAD rather than inferred here.
