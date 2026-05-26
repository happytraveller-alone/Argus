// tainted_sprintf_buffer.sc — rule_id: joern-c-tainted-sprintf-buffer, CWE-120, severity HIGH
// Detects sprintf/vsprintf with literal format string but tainted value arguments (orders >= 3).
import $file.common
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.Cpg

object tainted_sprintf_buffer {
  def run(cpg: Cpg): Seq[Finding] =
    cpg.call.name("(?i)(sprintf|vsprintf)")
      .where(_.argument.order(2).isLiteral)
      .l
      .flatMap { call =>
        val line     = call.lineNumber.getOrElse(0)
        val valueArgs = call.argument.order(3).l ++ call.argument.orderGte(4).l
        val taintedArg = valueArgs.find { a =>
          common.reachableBySafe(a, common.externSources(cpg)).nonEmpty
        }
        taintedArg match {
          case None => None
          case Some(_) =>
            Some(Finding(
              ruleId       = "joern-c-tainted-sprintf-buffer",
              cwe          = Seq("CWE-120"),
              cve          = Seq.empty,
              severity     = "HIGH",
              confidence   = "HIGH",
              filePath     = call.file.name.headOption.getOrElse(""),
              function     = call.method.name,
              startLine    = line,
              endLine      = line,
              evidenceCall = call.name,
              evidenceCode = call.code,
              taintSource  = Some("extern")
            ))
        }
      }
}
