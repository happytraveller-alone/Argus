//> using file common.sc

// alloc_mul_tainted.sc — rule_id: joern-c-alloc-mul-tainted, CWE-190/680, severity HIGH
// Detects malloc/alloca/realloc/calloc whose size arg is a multiplication with tainted factor.
import common._
import io.shiftleft.semanticcpg.language._
import io.shiftleft.codepropertygraph.generated.{Cpg, Operators, nodes}
import scala.util.Try

object alloc_mul_tainted {
  private val mulOp = Operators.multiplication

  private def findingForAlloc(
    cpg: Cpg,
    call: nodes.Call,
    factors: List[nodes.StoredNode]
  ): Option[Finding] = {
    val literals = factors.collect { case l: nodes.Literal => l }
    val sizeofCalls = factors.collect {
      case c: nodes.Call
        if c.name.toLowerCase == "sizeof" || c.methodFullName == Operators.sizeOf => c
    }
    if (literals.size == factors.size) return None  // all literals → compile-time constant
    val tainted = factors.exists {
      case n: nodes.CfgNode => common.reachableBySafe(n, common.externSources(cpg)).nonEmpty
      case _                => false
    }
    val conf = if (tainted) "HIGH" else if (sizeofCalls.nonEmpty) "MEDIUM" else "LOW"
    val line = call.lineNumber.getOrElse(0)
    Some(Finding(
      ruleId       = "joern-c-alloc-mul-tainted",
      cwe          = Seq("CWE-190", "CWE-680"),
      cve          = Seq.empty,
      severity     = "HIGH",
      confidence   = conf,
      filePath     = call.file.name.headOption.getOrElse(""),
      function     = call.method.name,
      startLine    = line,
      endLine      = line,
      evidenceCall = call.name,
      evidenceCode = call.code,
      taintSource  = if (tainted) Some("extern") else None
    ))
  }

  def run(cpg: Cpg): Seq[Finding] = {
    // malloc/alloca/realloc: size is arg order 1
    val singleArgFindings = cpg.call.name("(?i)(malloc|alloca|realloc)").l.flatMap { allocCall =>
      allocCall.argument.order(1).headOption match {
        case Some(mulCall: nodes.Call) if mulCall.methodFullName == mulOp =>
          findingForAlloc(cpg, allocCall, mulCall.argument.l)
        case _ => None
      }
    }

    // calloc(count, size): both args are independent size factors
    val callocFindings = cpg.call.name("(?i)calloc").l.flatMap { allocCall =>
      val factors = List(
        allocCall.argument.order(1).headOption,
        allocCall.argument.order(2).headOption
      ).flatten.collect { case n: nodes.StoredNode => n }
      if (factors.isEmpty) None
      else findingForAlloc(cpg, allocCall, factors)
    }

    singleArgFindings ++ callocFindings
  }
}
