//> using file common.sc

// tainted_strcpy.sc — rule_id: joern-c-tainted-strcpy, CWE-120/787, severity HIGH
// Detects strcpy() with non-literal src; taint + bounds-check dominator tier confidence.
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.Cpg

object tainted_strcpy {
  def run(cpg: Cpg): Seq[RuleFinding] =
    cpg.call.name("strcpy")
      .whereNot(_.argument.order(2).isLiteral)
      .l
      .map { call =>
        val line  = call.lineNumber.getOrElse(0)
        val arg2  = call.argument.order(2).headOption
        val tainted = arg2.exists { a =>
          common.reachableBySafe(a, common.externSources(cpg)).nonEmpty
        }
        val bounded = common.hasBoundsCheckDominator(call)
        val (conf, tsrc) = if (tainted && !bounded) ("HIGH", Some("extern"))
                           else if (tainted || !bounded) ("MEDIUM", if (tainted) Some("extern") else None)
                           else ("LOW", None)
        RuleFinding(
          ruleId       = "joern-c-tainted-strcpy",
          cwe          = Seq("CWE-120", "CWE-787"),
          cve          = Seq.empty,
          severity     = "HIGH",
          confidence   = conf,
          filePath     = call.file.name.headOption.getOrElse(""),
          function     = call.method.name,
          startLine    = line,
          endLine      = line,
          evidenceCall = call.name,
          evidenceCode = call.code,
          taintSource  = tsrc
        )
      }
}
