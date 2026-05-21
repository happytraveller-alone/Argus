/**
 * @name String copy without destination length check
 * @description Copying or appending a string into a destination buffer without
 *              passing an explicit destination length can overflow the destination.
 * @kind problem
 * @problem.severity warning
 * @security-severity 9.1
 * @precision medium
 * @id cpp/unchecked-string-copy-length
 * @tags reliability
 *       correctness
 *       security
 *       external/cwe/cwe-120
 *       external/cwe/cwe-676
 */

import cpp
import semmle.code.cpp.models.implementations.Strcat
import semmle.code.cpp.models.implementations.Strcpy

class UncheckedStringCopyCall extends FunctionCall {
  UncheckedStringCopyCall() {
    exists(StrcpyFunction strcpy |
      this.getTarget() = strcpy and
      not exists(strcpy.getParamSize())
    )
    or
    exists(StrcatFunction strcat |
      this.getTarget() = strcat and
      not exists(strcat.getParamSize())
    )
  }

  string getFunctionName() { result = this.getTarget().getName() }
}

from UncheckedStringCopyCall call
select call, "This call to '" + call.getFunctionName() + "' copies string data without an explicit destination length."
