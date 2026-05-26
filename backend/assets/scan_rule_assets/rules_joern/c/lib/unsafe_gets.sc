//> using file common.sc

// unsafe_gets.sc — rule_id: joern-c-unsafe-gets, CWE-120, severity HIGH
// Detects any call to gets() — always unsafe, no bounds checking possible.
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.Cpg

object unsafe_gets {
  def run(cpg: Cpg): Seq[RuleFinding] =
    cpg.method("(?i)gets").callIn.l.map { call =>
      val line = call.lineNumber.getOrElse(0)
      RuleFinding(
        ruleId      = "joern-c-unsafe-gets",
        cwe         = Seq("CWE-120"),
        cve         = Seq.empty,
        severity    = "HIGH",
        confidence  = "MEDIUM",
        filePath    = call.file.name.headOption.getOrElse(""),
        function    = call.method.name,
        startLine   = line,
        endLine     = line,
        evidenceCall = call.name,
        evidenceCode = call.code
      )
    }
}
