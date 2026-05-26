//> using file common.sc

// strlen_int_truncation.sc — rule_id: joern-c-strlen-int-truncation, CWE-192/190, severity MEDIUM
// Verbatim predicate from upstream IntegerTruncations::strlenAssignmentTruncations (joernio/joern).
// Detects strlen() return value assigned to int (narrowing from size_t truncates on 64-bit).
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.Cpg

object strlen_int_truncation {
  def run(cpg: Cpg): Seq[Finding] =
    // Upstream predicate (byte-identical): cpg.method.name("(?i)strlen").callIn.inAssignment.target.evalType("(g?)int")
    cpg.method.name("(?i)strlen").callIn.inAssignment.target.evalType("(g?)int").l.map { target =>
      val call = target.inAssignment.astChildren.isCall.name("(?i)strlen").headOption
      val line = target.lineNumber.getOrElse(0)
      Finding(
        ruleId       = "joern-c-strlen-int-truncation",
        cwe          = Seq("CWE-192", "CWE-190"),
        cve          = Seq.empty,
        severity     = "MEDIUM",
        confidence   = "MEDIUM",
        filePath     = target.file.name.headOption.getOrElse(""),
        function     = target.method.name,
        startLine    = line,
        endLine      = line,
        evidenceCall = call.map(_.name).getOrElse("strlen"),
        evidenceCode = call.map(_.code).getOrElse(target.code)
      )
    }
}
