//> using file common.sc

// strncpy_missing_null_term.sc — rule_id: joern-c-strncpy-missing-null-term, CWE-170, severity MEDIUM
// Detects strncpy(dest, src, sizeof(dest)) with no null-termination in next 5 block siblings.
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.Cpg

object strncpy_missing_null_term {
  private val nullTermPattern = """.*\[.*\]\s*=\s*['"]\\?0['"].*""".r

  def run(cpg: Cpg): Seq[Finding] =
    cpg.call.name("strncpy")
      .where(_.argument.order(3).code(".*sizeof\\s*\\(.*\\).*"))
      .l
      .filter { call =>
        val parentBlock = call.parentBlock.headOption
        parentBlock match {
          case None => true  // conservative: flag when block unavailable
          case Some(block) =>
            val siblings = block.astChildren.l
            val ix = siblings.indexWhere(n => n.id == call.id)
            if (ix < 0) true  // conservative: flag when call not located
            else {
              val next5 = siblings.drop(ix + 1).take(5)
              !next5.exists { sibling =>
                sibling.ast.isCall.code.exists(c => nullTermPattern.findFirstIn(c).isDefined)
              }
            }
        }
      }
      .map { call =>
        val line = call.lineNumber.getOrElse(0)
        Finding(
          ruleId       = "joern-c-strncpy-missing-null-term",
          cwe          = Seq("CWE-170"),
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
