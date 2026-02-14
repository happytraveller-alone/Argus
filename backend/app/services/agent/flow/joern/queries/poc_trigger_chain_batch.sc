// Batch PoC trigger chain extractor (source -> sink) using Joern dataflow engine.
//
// Params:
//   project: absolute project root
//   input: json file path, format: { "items": [ { "key": "...", "sink_file": "...", "sink_line": 123, "sink_hint": "...", "entry_file": "...", "entry_func": "..." } ] }
//   maxFlows: number, default 3
//   maxNodes: number, default 80
//
// Output (printed between markers; caller should extract and parse JSON):
//   {
//     "version": 1,
//     "engine": "joern_dataflow",
//     "results": { "<key>": { ...poc_trigger_chain... } },
//     "errors": { "<key>": "reason" }
//   }
//
// Notes:
// - This script is best-effort. It tries to locate sink by (file,line) + optional code hint.
// - It builds source candidates from the entry method (if provided) or the sink's enclosing method.

import io.joern.console.*
import io.shiftleft.semanticcpg.language.*
import io.shiftleft.semanticcpg.language.locationCreator
import io.joern.dataflowengineoss.language.*
import io.joern.dataflowengineoss.queryengine.*
import ujson.*

private val JSON_START = "<<<POC_TRIGGER_CHAIN_JSON_START>>>"
private val JSON_END = "<<<POC_TRIGGER_CHAIN_JSON_END>>>"

private def normPath(value: String): String = {
  if (value == null) return ""
  value.replace("\\", "/").trim
}

private def firstFilename(node: StoredNode): String = {
  try node.location.filename
  catch { case _: Throwable => "" }
}

private def readFileText(path: String): String = {
  val bytes = java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(path))
  new String(bytes, java.nio.charset.StandardCharsets.UTF_8)
}

private def toInt(value: Value, fallback: Int): Int = {
  try value.num.toInt
  catch { case _: Throwable =>
    try value.str.trim.toInt
    catch { case _: Throwable => fallback }
  }
}

private def pickSinkCall(
  sinkFile: String,
  sinkLine: Int,
  sinkHint: String
): Option[Call] = {
  val fileNorm = normPath(sinkFile)
  val candidates = cpg.call.l
    .filter(c => c.lineNumber.contains(sinkLine))
    .filter(c => normPath(firstFilename(c)).endsWith(fileNorm))

  if (candidates.isEmpty) return None
  if (sinkHint != null && sinkHint.trim.nonEmpty) {
    candidates.find(_.code.contains(sinkHint.trim)).orElse(candidates.headOption)
  } else {
    candidates.headOption
  }
}

private def pickEntryMethod(entryFile: String, entryFunc: String): Option[Method] = {
  val fileNorm = normPath(entryFile)
  val funcNorm = (if (entryFunc == null) "" else entryFunc).trim
  if (fileNorm.isEmpty || funcNorm.isEmpty) return None
  cpg.method.name(funcNorm).l.filter(m => normPath(firstFilename(m)).endsWith(fileNorm)).headOption
}

private def nodeObj(idx: Int, filePath: String, line: Int, code: String): Obj = {
  Obj(
    "index" -> idx,
    "file_path" -> normPath(filePath),
    "line" -> line,
    // function/context will be filled by backend for better multi-language support
    "function" -> "",
    "code" -> (if (code == null) "" else code.take(400))
  )
}

@main def main(
  project: String,
  input: String,
  maxFlows: String = "3",
  maxNodes: String = "80"
): Unit = {
  val runName = "poc_" + java.util.UUID.randomUUID().toString.replace("-", "")
  importCode(project, runName)

  implicit val context: EngineContext = EngineContext()

  val maxFlowsN = try maxFlows.toInt catch { case _: Throwable => 3 }
  val maxNodesN = try maxNodes.toInt catch { case _: Throwable => 80 }

  val payloadText = readFileText(input)
  val payload = ujson.read(payloadText)
  val items = payload.obj.get("items").map(_.arr.toSeq).getOrElse(Seq.empty)

  val results = collection.mutable.LinkedHashMap[String, Value]()
  val errors = collection.mutable.LinkedHashMap[String, Value]()

  val inputRegex = "(?i).*\\b(req|request|params|query|body|args|getParameter|header|cookie)\\b.*"

  items.foreach { item =>
    val obj = item.obj
    val key = obj.get("key").map(_.str).getOrElse("").trim
    if (key.isEmpty) {
      // skip invalid item
    } else {
      try {
        val sinkFile = obj.get("sink_file").map(_.str).getOrElse("")
        val sinkLine = obj.get("sink_line").map(v => toInt(v, -1)).getOrElse(-1)
        val sinkHint = obj.get("sink_hint").map(_.str).getOrElse("")
        val entryFile = obj.get("entry_file").map(_.str).getOrElse("")
        val entryFunc = obj.get("entry_func").map(_.str).getOrElse("")

        if (sinkFile.trim.isEmpty || sinkLine <= 0) {
          errors.put(key, Str("missing_sink_location"))
        } else {
          val sinkCallOpt = pickSinkCall(sinkFile, sinkLine, sinkHint)
          if (sinkCallOpt.isEmpty) {
            errors.put(key, Str("sink_not_found"))
          } else {
            val sinkCall = sinkCallOpt.get
            val methodOpt = pickEntryMethod(entryFile, entryFunc).orElse(Option(sinkCall.method))
            if (methodOpt.isEmpty) {
              errors.put(key, Str("enclosing_method_not_found"))
            } else {
              val method = methodOpt.get
              val sources = (method.parameter ++ method.call.code(inputRegex))

              val flows = sinkCall.start.reachableByFlows(sources).l
              if (flows.isEmpty) {
                errors.put(key, Str("no_flow"))
              } else {
                val selected = flows.sortBy(f => -f.elements.size).take(maxFlowsN).headOption
                if (selected.isEmpty) {
                  errors.put(key, Str("no_selected_flow"))
                } else {
                  val elements = selected.get.elements.take(maxNodesN)

                  // Build nodes, keep only nodes with valid line numbers.
                  val rawNodes = elements.flatMap { e =>
                    val line = e.lineNumber.getOrElse(-1)
                    if (line <= 0) None
                    else Some((normPath(firstFilename(e)), line, e.code))
                  }.toList

                  // Ensure the sink call is included as the last node.
                  val sinkFileNorm = normPath(firstFilename(sinkCall))
                  val sinkLineNorm = sinkCall.lineNumber.getOrElse(-1)
                  val sinkCode = sinkCall.code
                  val nodesWithSink =
                    if (rawNodes.nonEmpty && rawNodes.last._1 == sinkFileNorm && rawNodes.last._2 == sinkLineNorm && rawNodes.last._3 == sinkCode) rawNodes
                    else rawNodes :+ (sinkFileNorm, sinkLineNorm, sinkCode)

                  // Deduplicate consecutive duplicates.
                  val compacted = nodesWithSink.foldLeft(List.empty[(String, Int, String)]) { (acc, cur) =>
                    if (acc.nonEmpty && acc.last._1 == cur._1 && acc.last._2 == cur._2 && acc.last._3 == cur._3) acc
                    else acc :+ cur
                  }

                  if (compacted.size < 2) {
                    errors.put(key, Str("flow_too_short"))
                  } else {
                    val nodeValues = compacted.zipWithIndex.map { case ((fp, ln, cd), idx) =>
                      nodeObj(idx, fp, ln, cd)
                    }

                    val sourceNode = nodeValues.head.obj
                    val sinkNode = nodeValues.last.obj

                    val chain = Obj(
                      "version" -> 1,
                      "engine" -> "joern_dataflow",
                      "source" -> Obj(
                        "file_path" -> sourceNode("file_path"),
                        "line" -> sourceNode("line"),
                        "function" -> sourceNode("function"),
                        "code" -> sourceNode("code")
                      ),
                      "sink" -> Obj(
                        "file_path" -> sinkNode("file_path"),
                        "line" -> sinkNode("line"),
                        "function" -> sinkNode("function"),
                        "code" -> sinkNode("code")
                      ),
                      "nodes" -> Arr.from(nodeValues),
                      "generated_at" -> java.time.Instant.now().toString
                    )
                    results.put(key, chain)
                  }
                }
              }
            }
          }
        }
      } catch {
        case e: Throwable =>
          errors.put(key, Str("exception:" + e.getClass.getSimpleName))
      }
    }
  }

  val out = Obj(
    "version" -> 1,
    "engine" -> "joern_dataflow",
    "results" -> Obj.from(results),
    "errors" -> Obj.from(errors)
  )

  println(JSON_START)
  println(ujson.write(out))
  println(JSON_END)
}
