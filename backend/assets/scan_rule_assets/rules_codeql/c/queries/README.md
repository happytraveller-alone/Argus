# Argus C CodeQL queries

This pack contains C-applicable security queries copied from the official GitHub CodeQL repository, plus Argus supplemental security queries.

- Source repository: https://v6.gh-proxy.org/https://github.com/github/codeql
- Source commit: 154d213fd231e8d76d9c11ff4ac69842d0783d0b
- Upstream license: MIT, copyright GitHub, Inc.; see `../LICENSE-codeql-MIT.txt`.
- Imported upstream paths:
  - `cpp/ql/src/Critical/DoubleFree.ql`
  - `cpp/ql/src/Critical/NewDelete.qll`
  - `cpp/ql/src/Critical/NewFreeMismatch.ql`
  - `cpp/ql/src/Critical/UseAfterFree.ql`
  - `cpp/ql/src/Likely Bugs/Memory Management/Buffer.qll`
  - `cpp/ql/src/Likely Bugs/Memory Management/ImproperNullTermination.ql`
  - `cpp/ql/src/Likely Bugs/Memory Management/ReturnStackAllocatedMemory.ql`
  - `cpp/ql/src/Likely Bugs/Memory Management/StrncpyFlippedArgs.ql`
  - `cpp/ql/src/Likely Bugs/Memory Management/SuspiciousCallToStrncat.ql`
  - `cpp/ql/src/Likely Bugs/Memory Management/UnsafeUseOfStrcat.ql`
  - `cpp/ql/src/Likely Bugs/Memory Management/UsingExpiredStackAddress.ql`
  - `cpp/ql/src/Security/CWE/CWE-014/MemsetMayBeDeleted.ql`
  - `cpp/ql/src/Security/CWE/CWE-022/TaintedPath.ql`
  - `cpp/ql/src/Security/CWE/CWE-078/ExecTainted.ql`
  - `cpp/ql/src/Security/CWE/CWE-089/SqlTainted.ql`
  - `cpp/ql/src/Security/CWE/CWE-119/OverflowBuffer.ql`
  - `cpp/ql/src/Security/CWE/CWE-120/BadlyBoundedWrite.ql`
  - `cpp/ql/src/Security/CWE/CWE-120/OverrunWrite.ql`
  - `cpp/ql/src/Security/CWE/CWE-120/OverrunWriteFloat.ql`
  - `cpp/ql/src/Security/CWE/CWE-120/UnboundedWrite.ql`
  - `cpp/ql/src/Security/CWE/CWE-120/VeryLikelyOverrunWrite.ql`
  - `cpp/ql/src/Security/CWE/CWE-129/ImproperArrayIndexValidation.ql`
  - `cpp/ql/src/Security/CWE/CWE-131/NoSpaceForZeroTerminator.ql`
  - `cpp/ql/src/Security/CWE/CWE-134/UncontrolledFormatString.ql`
  - `cpp/ql/src/Security/CWE/CWE-170/ImproperNullTerminationTainted.ql`
  - `cpp/ql/src/Security/CWE/CWE-190/ArithmeticTainted.ql`
  - `cpp/ql/src/Security/CWE/CWE-190/Bounded.qll`
  - `cpp/ql/src/Security/CWE/CWE-190/IntegerOverflowTainted.ql`
  - `cpp/ql/src/Security/CWE/CWE-190/TaintedAllocationSize.ql`
  - `cpp/ql/src/Security/CWE/CWE-193/InvalidPointerDeref.ql`
  - `cpp/ql/src/Security/CWE/CWE-468/IncorrectPointerScaling.ql`
  - `cpp/ql/src/Security/CWE/CWE-468/IncorrectPointerScalingChar.ql`
  - `cpp/ql/src/Security/CWE/CWE-468/IncorrectPointerScalingCommon.qll`
  - `cpp/ql/src/Security/CWE/CWE-468/IncorrectPointerScalingVoid.ql`
  - `cpp/ql/src/Security/CWE/CWE-468/SuspiciousAddWithSizeof.ql`
  - `cpp/ql/src/Security/CWE/CWE-676/DangerousFunctionOverflow.ql`

Coverage focus:

- direct exploit primitives such as command/path/SQL injection, tainted arithmetic, and tainted allocation sizes
- memory-corruption and bounds errors (`InvalidPointerDeref`, array index validation, pointer scaling, and no terminator space)
- string and buffer overflow mistakes (`UnboundedWrite`, overrun/badly bounded writes, null termination, `strncpy`/`strncat`/`strcat` misuse)
- pointer lifetime and ownership vulnerabilities (`DoubleFree`, `UseAfterFree`, mismatched allocation/free, returned/expired stack addresses)

Excluded scope:

- coding-standard, quality, efficiency, or generic reliability checks that do not directly report an exploitable vulnerability class, such as leak-only checks, null-check recommendations, suspicious `sizeof` style checks, generic uninitialized-local checks, and deprecated broad potential-overflow queries.

Argus supplemental queries:

- `UncheckedStringCopyLength.ql` detects unbounded `strcpy`/`strcat`-style string copies that do not pass an explicit destination length.
