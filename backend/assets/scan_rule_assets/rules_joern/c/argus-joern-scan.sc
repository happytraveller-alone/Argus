// Argus Joern first-pass scan script.
//
// Sources for the wrapper contract are recorded in backend/src/scan/joern.rs:
// - Joern interpreter supports `joern --script ... --param ...` and file output.
// - Joern export/frontends docs document `joern-parse` CPG construction.
//
// This initial script is intentionally narrow. It emits Argus-owned JSON for
// graph proof and findings, and the backend parser owns the stable mapping.

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

import io.circe.syntax._
import io.circe.Json

@main def exec(cpgFile: String, sourceDir: String, graphProofOut: String, findingsOut: String): Unit = {
  importCpg(cpgFile)

  val files = cpg.file.name.l.distinct.sorted
  val functions = cpg.method.name.l.distinct.sorted
  val proof = Json.obj(
    "schema_version" -> "argus.joern.graph-proof.v1".asJson,
    "engine" -> "joern".asJson,
    "source_dir" -> sourceDir.asJson,
    "files" -> files.asJson,
    "functions" -> functions.asJson,
    "queries" -> Json.obj(
      "file_count" -> files.size.asJson,
      "function_count" -> functions.size.asJson
    )
  )

  // CVE-2017-6439 / libplist 1.12 first-pass query. The target evidence is
  // finalized by the fixture story; this query intentionally checks for the
  // expected vulnerable function and unsafe copy-style calls in that function.
  val candidateCalls = cpg.method.name("parse_string_node").call.name("(?i)(memcpy|strcpy|strncpy|sprintf|vsprintf)").l
  val findings = candidateCalls.map { call =>
    val fileName = call.file.name.headOption.getOrElse("")
    val lineNumber = call.lineNumber.getOrElse(1)
    Json.obj(
      "id" -> s"libplist-cve-2017-6439-${lineNumber}".asJson,
      "rule_id" -> "joern-c-buffer-overflow-libplist-cve-2017-6439".asJson,
      "title" -> "libplist parse_string_node buffer overflow".asJson,
      "message" -> "Potential buffer overflow pattern in libplist parse_string_node".asJson,
      "severity" -> "HIGH".asJson,
      "confidence" -> "HIGH".asJson,
      "file_path" -> fileName.asJson,
      "start_line" -> lineNumber.asJson,
      "end_line" -> lineNumber.asJson,
      "function" -> "parse_string_node".asJson,
      "cwe" -> List("CWE-120").asJson,
      "cve" -> List("CVE-2017-6439").asJson,
      "evidence" -> Json.obj(
        "call" -> call.name.asJson,
        "code" -> call.code.asJson
      )
    )
  }
  val findingsDoc = Json.obj(
    "schema_version" -> "argus.joern.findings.v1".asJson,
    "engine" -> "joern".asJson,
    "findings" -> findings.asJson
  )

  Files.write(Paths.get(graphProofOut), proof.noSpaces.getBytes(StandardCharsets.UTF_8))
  Files.write(Paths.get(findingsOut), findingsDoc.noSpaces.getBytes(StandardCharsets.UTF_8))
}
