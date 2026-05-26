//> using file common.sc

// tainted_memcpy.sc — rule_id: joern-c-tainted-memcpy, CWE-120/787, severity HIGH
// Structural: memcpy where size arg is non-literal AND not sizeof-bounded (fires on bplist.c:288).
// Taint upgrades confidence only; structural path is the primary anchor.
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.Cpg

object tainted_memcpy {
  def run(cpg: Cpg): Seq[Finding] =
    cpg.call.name("memcpy")
      .whereNot(_.argument.order(3).isLiteral)
      .whereNot(_.argument.order(3).code(".*sizeof\\s*\\(.*\\).*"))
      .l
      .map { call =>
        val line  = call.lineNumber.getOrElse(0)
        val arg3  = call.argument.order(3).headOption
        val tainted = arg3.exists { a =>
          common.reachableBySafe(a, common.externSources(cpg)).nonEmpty
        }
        val bounded = common.hasBoundsCheckDominator(call)
        val (conf, tsrc) = if (tainted && !bounded) ("HIGH", Some("extern"))
                           else if (tainted || !bounded) ("MEDIUM", if (tainted) Some("extern") else None)
                           else ("LOW", None)
        Finding(
          ruleId       = "joern-c-tainted-memcpy",
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
