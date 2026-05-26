//> using file common.sc

// signed_left_shift.sc — rule_id: joern-c-signed-left-shift, CWE-190, severity MEDIUM
// Verbatim predicate from upstream SignedLeftShift::signedLeftShift (joernio/joern).
// Detects left-shift on signed integer operands (undefined behavior per C99/C11 §6.5.7).
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.{Cpg, Operators}

object signed_left_shift {
  def run(cpg: Cpg): Seq[Finding] =
    // Upstream predicate (byte-identical): cpg.call.name(Operators.shiftLeft).where(_.argument.order(1).evalType("(g?)int.*"))
    cpg.call.name(Operators.shiftLeft)
      .where(_.argument.order(1).evalType("(g?)int.*"))
      .l
      .map { call =>
        val line = call.lineNumber.getOrElse(0)
        Finding(
          ruleId       = "joern-c-signed-left-shift",
          cwe          = Seq("CWE-190"),
          cve          = Seq.empty,
          severity     = "MEDIUM",
          confidence   = "MEDIUM",
          filePath     = call.file.name.headOption.getOrElse(""),
          function     = call.method.name,
          startLine    = line,
          endLine      = line,
          evidenceCall = call.name,
          evidenceCode = call.code
        )
      }
}
