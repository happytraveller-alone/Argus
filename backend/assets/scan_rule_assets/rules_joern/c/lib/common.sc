// common.sc — shared Finding type, JSON helpers, dataflow gate, CVE map
// N1: this is the ONLY file permitted to import io.joern.dataflowengineoss.*

import io.shiftleft.codepropertygraph.generated.{Cpg, nodes}
import io.shiftleft.semanticcpg.language._
import io.joern.dataflowengineoss.language._
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}
import scala.util.Try

// ----- Finding case class -----
case class Finding(
  ruleId: String,
  cwe: Seq[String],
  cve: Seq[String],
  severity: String,
  confidence: String,
  filePath: String,
  function: String,
  startLine: Int,
  endLine: Int,
  evidenceCall: String,
  evidenceCode: String,
  taintSource: Option[String] = None,
  excludedBy: Option[String] = None
)

// ----- JSON helpers (verbatim from argus-joern-scan.sc) -----
def jsonString(value: String): String =
  "\"" + value.flatMap {
    case '"'  => "\\\""
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
  fields.map { case (k, v) => s"${jsonString(k)}:$v" }.mkString("{", ",", "}")

// ----- Stable ID: "<rule_id>-<basename>-<startLine>-<sha8(evidenceCode)>" [C4] -----
def sha8(s: String): String =
  java.security.MessageDigest.getInstance("SHA-256")
    .digest(s.getBytes(StandardCharsets.UTF_8))
    .take(4).map("%02x".format(_)).mkString

def stableId(f: Finding): String = {
  val basename = f.filePath.split("/").lastOption.getOrElse(f.filePath)
  s"${f.ruleId}-$basename-${f.startLine}-${sha8(f.evidenceCode)}"
}

// ----- External taint sources [C8] -----
def externSources(cpg: Cpg): Iterator[nodes.CfgNode] = {
  val calls  = cpg.method("(?i)(getenv|recv|read|fgets|gets|scanf|fscanf|fread)").callIn
  val params = cpg.parameter.name("argv")
  (calls.iterator: Iterator[nodes.CfgNode]) ++ (params.iterator: Iterator[nodes.CfgNode])
}

// ----- Dataflow gate [A4/S2] -----
// common.sc is the SOLE file allowed to import dataflowengineoss at the static level (N1).
// Rule modules must not import it; they call reachableBySafe(...) instead.
val dataflowAvailable: Boolean =
  Try(Class.forName("io.joern.dataflowengineoss.language.package$")).isSuccess

def reachableBySafe(sink: nodes.CfgNode, sources: Iterator[nodes.CfgNode]): Iterator[nodes.CfgNode] = {
  if (!dataflowAvailable) Iterator.empty
  else Try {
    val sourceList = sources.toList
    if (sourceList.isEmpty) Iterator.empty
    else sink.reachableBy(sourceList).iterator
  }.getOrElse(Iterator.empty)
}

// ----- Bounds-check dominator heuristic -----
def hasBoundsCheckDominator(call: nodes.Call): Boolean = {
  Try {
    call.controlledBy.isControlStructure.isIf.condition
      .code(".*sizeof\\s*\\(.*\\).*|.*<=?\\s*[A-Z_][A-Z0-9_]*\\s*.*").nonEmpty
  }.getOrElse(false)
}

def isStackBuffer(call: nodes.Call): Boolean =
  Try(call.argument.order(1).isIdentifier.refsTo.isLocal.nonEmpty).getOrElse(false)

// ----- Known CVE map [C8] -----
// Key: (basename, functionName, startLine) → CVE list
val knownCves: Map[(String, String, Int), Seq[String]] = Map(
  ("bplist.c", "parse_string_node", 288) -> Seq("CVE-2017-6439")
)

def tagCves(f: Finding): Finding = {
  val basename = f.filePath.split("/").lastOption.getOrElse(f.filePath)
  val key = (basename, f.function, f.startLine)
  knownCves.get(key) match {
    case Some(cves) if cves.nonEmpty => f.copy(cve = (f.cve ++ cves).distinct)
    case _                           => f
  }
}

// ----- Output writers -----
private def findingToJson(f: Finding): String = jsonObject(
  Seq(
    "id"         -> jsonString(stableId(f)),
    "rule_id"    -> jsonString(f.ruleId),
    "cwe"        -> jsonArray(f.cwe),
    "cve"        -> jsonArray(f.cve),
    "severity"   -> jsonString(f.severity),
    "confidence" -> jsonString(f.confidence),
    "file_path"  -> jsonString(f.filePath),
    "function"   -> jsonString(f.function),
    "start_line" -> f.startLine.toString,
    "end_line"   -> f.endLine.toString,
    "title"      -> jsonString(f.ruleId),
    "message"    -> jsonString(s"${f.ruleId}: pattern matched at ${f.filePath}:${f.startLine}"),
    "evidence"   -> jsonObject(
      Seq(
        "call" -> jsonString(f.evidenceCall),
        "code" -> jsonString(f.evidenceCode)
      ) ++ f.taintSource.map(t => "taint_source" -> jsonString(t))
        ++ f.excludedBy.map(e => "excluded_by"   -> jsonString(e))
    )
  )
)

def writeFindings(path: String, findings: Seq[Finding], engine: String = "joern"): Unit = {
  val doc = jsonObject(Seq(
    "schema_version" -> jsonString("argus.joern.findings.v1"),
    "engine"         -> jsonString(engine),
    "findings"       -> findings.map(findingToJson).mkString("[", ",", "]")
  ))
  Files.write(Paths.get(path), doc.getBytes(StandardCharsets.UTF_8))
}

def writeProof(path: String, cpg: Cpg, sourceDir: String): Unit = {
  val files     = cpg.file.name.l.distinct.sorted
  val functions = cpg.method.name.l.distinct.sorted
  val proof = jsonObject(Seq(
    "schema_version" -> jsonString("argus.joern.graph-proof.v1"),
    "engine"         -> jsonString("joern"),
    "source_dir"     -> jsonString(sourceDir),
    "files"          -> jsonArray(files),
    "functions"      -> jsonArray(functions),
    "queries"        -> jsonObject(Seq(
      "file_count"     -> files.size.toString,
      "function_count" -> functions.size.toString
    ))
  ))
  Files.write(Paths.get(path), proof.getBytes(StandardCharsets.UTF_8))
}
