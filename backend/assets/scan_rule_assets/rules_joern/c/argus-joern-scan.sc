//> using file lib/common.sc
//> using file lib/unsafe_gets.sc
//> using file lib/tainted_strcpy.sc
//> using file lib/tainted_memcpy.sc
//> using file lib/tainted_sprintf_buffer.sc
//> using file lib/strncpy_missing_null_term.sc
//> using file lib/alloc_mul_tainted.sc
//> using file lib/strlen_int_truncation.sc
//> using file lib/signed_left_shift.sc

// argus-joern-scan.sc — thin orchestrator; rule logic lives under c/lib/*.sc
//
// Wrapper contract preserved: backend/src/scan/joern.rs passes exactly these 4 params.
// CPG is loaded once here; modules receive cpg directly via run(cpg).
// Per-module errors are isolated via Try; a failing module yields empty findings.

import common._
import scala.util.Try
import io.shiftleft.codepropertygraph.generated.Cpg

@main def exec(cpgFile: String, sourceDir: String, graphProofOut: String, findingsOut: String): Unit = {
  importCpg(cpgFile)

  val modules: Seq[Cpg => Seq[RuleFinding]] = Seq(
    unsafe_gets.run,
    tainted_strcpy.run,
    tainted_memcpy.run,
    tainted_sprintf_buffer.run,
    strncpy_missing_null_term.run,
    alloc_mul_tainted.run,
    strlen_int_truncation.run,
    signed_left_shift.run
  )

  val raw      = modules.flatMap(r => Try(r(cpg)).toOption.getOrElse(Seq.empty))
  val findings = raw.map(common.tagCves)

  common.writeProof(graphProofOut, cpg, sourceDir)
  common.writeFindings(findingsOut, findings)
}
