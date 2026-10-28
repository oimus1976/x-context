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

## M-1 ancestor ACL remediation (pre-commit)

On Windows, the new disposable profile-chain test produced RED against
`7d26e3cdeecc9d08f273a826bd85b3af4cd74030`: the positive chain stopped as
`GOOGLE_PRIVATE_PATH_BLOCKED`. After the change the real profile-chain test
passed, including a SYSTEM-owned profile ancestor, synthetic read/traverse and
mutation ACEs, an inherit-only synthetic capability SID, strict private
parent/leaf, and a synthetic junction. Symlink detection is simulated because
the user lacks Windows symlink creation privilege. Deleting the owner check produced the intended owner-test failure.
The full pre-commit suite passed 475 tests before the final owner-mutant and
junction assertions were added; committed-head full validation is separate.
Setting a synthetic directory owner to SYSTEM or Administrators was unavailable
to this non-admin user. SYSTEM and Administrators owner acceptance and
untrusted-owner refusal were also tested by replacing only the owner in an
in-memory descriptor built from a real synthetic DACL; actual Administrators-
owned filesystem acceptance remains unverified. Tests make no changes to existing directory ACLs or actual evidence.

The ancestor rule conservatively rejects a third-party mutating allow ACE even
when a deny ACE might mask it. Unsupported and unknown ACEs fail closed. No
real Google, credentials, incident evidence, Gate R/W, Ready or merge is used.
