# Security policy

judgeswap is an evaluation library. It opens no connections of its own: every
model call goes through a client object the caller supplies, and the only
files it writes are the artifact directory the caller names. A flaw that lets
a prompt or a model response reach outside those (for example, a path built
from a row field) is a security issue, not just a bug.

## Reporting

Report suspected vulnerabilities privately. Do not open a public issue: an
issue is visible to everyone the moment it is filed, before any fix exists.

1. **Preferred:** GitHub private vulnerability reporting —
   <https://github.com/BrandonLewis/judgeswap/security/advisories/new>
   ("Report a vulnerability" on the repository's Security tab). Only you and
   the maintainer can see the advisory; the fix is coordinated there and the
   advisory is published when it ships.
2. **Fallback**, if you cannot use GitHub: email
   <security@anvilrockroad.com>.

Include a minimal reproduction (a failing test is ideal) and the package
version (`pip show judgeswap`).

You will get an acknowledgement within 5 business days. Fixes ship in the next
release with credit in the advisory and changelog unless you ask otherwise.

## Scope

- In scope: the `judgeswap` package.
- Out of scope: the model clients and products that use it, and the libraries
  it builds on (numpy). Report those upstream, and tell us so we can raise the
  pinned minimum.

## Supported versions

Only the latest release on PyPI receives fixes.
