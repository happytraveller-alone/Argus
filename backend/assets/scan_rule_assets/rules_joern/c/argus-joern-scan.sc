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

def jsonString(value: String): String =
  "\"" + value.flatMap {
    case '"' => "\\\""
    case '\\' => "\\\\"
    case '\b' => "\\b"
    case '\f' => "\\f"
    case '\n' => "\\n"
    case '\r' => "\\r"
    case '\t' => "\\t"
    case char if char.isControl => "\\u%04x".format(char.toInt)
    case char => char.toString
  } + "\""

def jsonArray(values: Iterable[String]): String =
  values.map(jsonString).mkString("[", ",", "]")

def jsonObject(fields: Iterable[(String, String)]): String =
  fields.map { case (key, value) => s"${jsonString(key)}:$value" }.mkString("{", ",", "}")

def jsonStringField(key: String, value: String): (String, String) =
  key -> jsonString(value)

def jsonNumberField(key: String, value: Int): (String, String) =
  key -> value.toString

@main def exec(cpgFile: String, sourceDir: String, graphProofOut: String, findingsOut: String): Unit = {
  importCpg(cpgFile)

  val files = cpg.file.name.l.distinct.sorted
  val functions = cpg.method.name.l.distinct.sorted
  val proof = jsonObject(
    Seq(
      jsonStringField("schema_version", "argus.joern.graph-proof.v1"),
      jsonStringField("engine", "joern"),
      jsonStringField("source_dir", sourceDir),
      "files" -> jsonArray(files),
      "functions" -> jsonArray(functions),
      "queries" -> jsonObject(
        Seq(
          jsonNumberField("file_count", files.size),
          jsonNumberField("function_count", functions.size)
        )
      )
    )
  )

  // CVE-2017-6439 / libplist 1.12 first-pass query. The target evidence is
  // finalized by the fixture story; this query intentionally checks for the
  // expected vulnerable function and unsafe copy-style calls in that function.
  val candidateCalls = cpg.method.name("parse_string_node").call.name("(?i)(memcpy|strcpy|strncpy|sprintf|vsprintf)").l
  val findings = candidateCalls.map { call =>
    val fileName = call.file.name.headOption.getOrElse("")
    val lineNumber = call.lineNumber.getOrElse(1)
    jsonObject(
      Seq(
        jsonStringField("id", s"libplist-cve-2017-6439-${lineNumber}"),
        jsonStringField("rule_id", "joern-c-buffer-overflow-libplist-cve-2017-6439"),
        jsonStringField("title", "libplist parse_string_node buffer overflow"),
        jsonStringField("message", "Potential buffer overflow pattern in libplist parse_string_node"),
        jsonStringField("severity", "HIGH"),
        jsonStringField("confidence", "HIGH"),
        jsonStringField("file_path", fileName),
        jsonNumberField("start_line", lineNumber),
        jsonNumberField("end_line", lineNumber),
        jsonStringField("function", "parse_string_node"),
        "cwe" -> jsonArray(List("CWE-120")),
        "cve" -> jsonArray(List("CVE-2017-6439")),
        "evidence" -> jsonObject(
          Seq(
            jsonStringField("call", call.name),
            jsonStringField("code", call.code)
          )
        )
      )
    )
  }
  val findingsDoc = jsonObject(
    Seq(
      jsonStringField("schema_version", "argus.joern.findings.v1"),
      jsonStringField("engine", "joern"),
      "findings" -> findings.mkString("[", ",", "]")
    )
  )

  Files.write(Paths.get(graphProofOut), proof.getBytes(StandardCharsets.UTF_8))
  Files.write(Paths.get(findingsOut), findingsDoc.getBytes(StandardCharsets.UTF_8))
}
