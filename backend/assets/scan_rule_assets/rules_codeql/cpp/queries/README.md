# Argus C++ CodeQL queries

This pack contains C++-specific security queries copied from the official GitHub CodeQL repository.

- Source repository: https://v6.gh-proxy.org/https://github.com/github/codeql
- Source commit: 154d213fd231e8d76d9c11ff4ac69842d0783d0b
- Upstream license: MIT, copyright GitHub, Inc.; see `../LICENSE-codeql-MIT.txt`.
- Imported upstream paths:
  - `cpp/ql/src/Security/CWE/CWE-416/IteratorToExpiredContainer.ql`
  - `cpp/ql/src/Security/CWE/CWE-416/Temporaries.qll`
  - `cpp/ql/src/Security/CWE/CWE-416/UseOfStringAfterLifetimeEnds.ql`
  - `cpp/ql/src/Security/CWE/CWE-416/UseOfUniquePointerAfterLifetimeEnds.ql`
  - `cpp/ql/src/Security/CWE/CWE-428/UnsafeCreateProcessCall.ql`
  - `cpp/ql/src/Security/CWE/CWE-843/TypeConfusion.ql`
