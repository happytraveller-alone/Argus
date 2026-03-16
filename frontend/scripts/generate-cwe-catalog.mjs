#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { strFromU8, unzipSync } from "fflate";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const outputPath = path.resolve(
  frontendDir,
  "src/shared/security/cweCatalog.generated.json",
);

const CWE_XML_ZIP_URL = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip";
const REQUEST_TIMEOUT_MS = 30_000;

const MANUAL_ZH_OVERRIDES = {
  "CWE-20": "输入验证不当",
  "CWE-22": "路径遍历",
  "CWE-23": "相对路径遍历",
  "CWE-36": "绝对路径遍历",
  "CWE-73": "外部控制文件名或路径",
  "CWE-74": "下游组件特殊元素注入",
  "CWE-77": "命令中特殊元素注入",
  "CWE-78": "操作系统命令注入",
  "CWE-79": "跨站脚本",
  "CWE-80": "基础跨站脚本",
  "CWE-89": "SQL注入",
  "CWE-90": "LDAP注入",
  "CWE-94": "代码注入",
  "CWE-95": "动态代码执行",
  "CWE-98": "远程文件包含",
  "CWE-119": "内存边界限制不当",
  "CWE-120": "经典缓冲区溢出",
  "CWE-121": "栈缓冲区溢出",
  "CWE-122": "堆缓冲区溢出",
  "CWE-125": "越界读取",
  "CWE-134": "格式化字符串",
  "CWE-190": "整数溢出或回绕",
  "CWE-200": "敏感信息暴露",
  "CWE-287": "认证不当",
  "CWE-295": "证书验证不当",
  "CWE-306": "关键功能缺少认证",
  "CWE-307": "认证尝试次数限制不当",
  "CWE-319": "敏感信息明文传输",
  "CWE-327": "受损或高风险加密算法",
  "CWE-330": "随机数不足",
  "CWE-352": "跨站请求伪造",
  "CWE-362": "竞态条件",
  "CWE-367": "检查时与使用时竞争条件",
  "CWE-377": "不安全临时文件",
  "CWE-400": "资源消耗失控",
  "CWE-415": "重复释放",
  "CWE-416": "释放后使用",
  "CWE-434": "危险类型文件上传不受限制",
  "CWE-476": "空指针解引用",
  "CWE-489": "调试代码遗留",
  "CWE-502": "不可信数据反序列化",
  "CWE-601": "开放重定向",
  "CWE-611": "XML 外部实体",
  "CWE-639": "用户控制键导致越权访问",
  "CWE-703": "异常条件处理不当",
  "CWE-798": "硬编码凭据",
  "CWE-840": "业务逻辑缺陷",
  "CWE-918": "服务器端请求伪造",
  "CWE-943": "NoSQL注入",
};

const EXACT_SHORT_TRANSLATIONS = new Map(
  Object.entries({
    "cross-site scripting": "跨站脚本",
    "sql injection": "SQL注入",
    "nosql injection": "NoSQL注入",
    "xpath injection": "XPath注入",
    "ldap injection": "LDAP注入",
    "code injection": "代码注入",
    "command injection": "命令注入",
    "os command injection": "操作系统命令注入",
    "path traversal": "路径遍历",
    "relative path traversal": "相对路径遍历",
    "absolute path traversal": "绝对路径遍历",
    "open redirect": "开放重定向",
    "xml external entity": "XML 外部实体",
    "cross-site request forgery": "跨站请求伪造",
    "race condition": "竞态条件",
    "use after free": "释放后使用",
    "double free": "重复释放",
    "out-of-bounds read": "越界读取",
    "out-of-bounds write": "越界写入",
    "null pointer dereference": "空指针解引用",
    "hard-coded password": "硬编码密码",
    "hard-coded credentials": "硬编码凭据",
    "hard-coded cryptographic key": "硬编码加密密钥",
    "improper access control": "访问控制不当",
    "improper authentication": "认证不当",
    "improper authorization": "授权不当",
    "cleartext transmission of sensitive information":
      "敏感信息明文传输",
    "cleartext storage of sensitive information": "敏感信息明文存储",
    "classic buffer overflow": "经典缓冲区溢出",
    "stack-based buffer overflow": "栈缓冲区溢出",
    "heap-based buffer overflow": "堆缓冲区溢出",
    "format string bug": "格式化字符串缺陷",
    "format string vulnerability": "格式化字符串漏洞",
    "regular expression injection": "正则表达式注入",
    "regular expression denial of service": "正则表达式拒绝服务",
    "server-side request forgery": "服务器端请求伪造",
    "deserialization of untrusted data": "不可信数据反序列化",
  }),
);

const ORDERED_PHRASE_TRANSLATIONS = [
  ["Cross-site Scripting", "跨站脚本"],
  ["Cross Site Scripting", "跨站脚本"],
  ["Cross-site Request Forgery", "跨站请求伪造"],
  ["Server-side Request Forgery", "服务器端请求伪造"],
  ["Regular Expression Denial of Service", "正则表达式拒绝服务"],
  ["Regular Expression Injection", "正则表达式注入"],
  ["XML External Entity", "XML 外部实体"],
  ["SQL Injection", "SQL注入"],
  ["NoSQL Injection", "NoSQL注入"],
  ["XPath Injection", "XPath注入"],
  ["LDAP Injection", "LDAP注入"],
  ["Code Injection", "代码注入"],
  ["Command Injection", "命令注入"],
  ["Path Traversal", "路径遍历"],
  ["Open Redirect", "开放重定向"],
  ["Use After Free", "释放后使用"],
  ["Double Free", "重复释放"],
  ["Race Condition", "竞态条件"],
  ["NULL Pointer Dereference", "空指针解引用"],
  ["Out-of-bounds Read", "越界读取"],
  ["Out-of-bounds Write", "越界写入"],
  ["Hard-coded Password", "硬编码密码"],
  ["Hard-coded Credentials", "硬编码凭据"],
  ["Hard-coded Cryptographic Key", "硬编码加密密钥"],
  ["Cleartext Transmission", "明文传输"],
  ["Cleartext Storage", "明文存储"],
  ["Classic Buffer Overflow", "经典缓冲区溢出"],
  ["Stack-based Buffer Overflow", "栈缓冲区溢出"],
  ["Heap-based Buffer Overflow", "堆缓冲区溢出"],
  ["Integer Overflow", "整数溢出"],
  ["Integer Underflow", "整数下溢"],
  ["Format String", "格式化字符串"],
  ["Authentication", "认证"],
  ["Authorization", "授权"],
  ["Access Control", "访问控制"],
  ["Permissions", "权限"],
  ["Permission", "权限"],
  ["Credentials", "凭据"],
  ["Password", "密码"],
  ["Key", "密钥"],
  ["Pathname", "路径名"],
  ["Path", "路径"],
  ["Directory", "目录"],
  ["Filename", "文件名"],
  ["File", "文件"],
  ["Buffer", "缓冲区"],
  ["Bounds", "边界"],
  ["Boundary", "边界"],
  ["Memory", "内存"],
  ["Pointer", "指针"],
  ["Resource", "资源"],
  ["Leak", "泄露"],
  ["Exposure", "暴露"],
  ["Sensitive Information", "敏感信息"],
  ["Sensitive Data", "敏感数据"],
  ["Input Validation", "输入验证"],
  ["Input", "输入"],
  ["Output", "输出"],
  ["Neutralization", "中和"],
  ["Neutralize", "中和"],
  ["Neutralization of Special Elements", "特殊元素中和"],
  ["Special Elements", "特殊元素"],
  ["Cryptographic", "加密"],
  ["Encryption", "加密"],
  ["Certificate", "证书"],
  ["Temporary File", "临时文件"],
  ["Temporary Files", "临时文件"],
  ["Serialization", "序列化"],
  ["Deserialization", "反序列化"],
  ["Business Logic", "业务逻辑"],
  ["Debug Code", "调试代码"],
  ["Privilege", "权限"],
  ["Protection Mechanism", "保护机制"],
  ["Improper", "不当"],
  ["Incorrect", "错误"],
  ["Missing", "缺少"],
  ["Insufficient", "不足"],
  ["Failure", "失败"],
  ["Uncontrolled", "未受控"],
  ["Unexpected", "意外"],
  ["Expired", "过期"],
  ["Unsafe", "不安全"],
  ["Weak", "弱"],
  ["Untrusted", "不可信"],
  ["Improperly", "不当地"],
];

const CONNECTOR_REPLACEMENTS = [
  [" During ", " 期间 "],
  [" Within ", " 在 "],
  [" Without ", " 缺少 "],
  [" With ", " 使用 "],
  [" From ", " 来自 "],
  [" Into ", " 到 "],
  [" In ", " 在 "],
  [" On ", " 在 "],
  [" To ", " 到 "],
  [" Of ", " 的 "],
  [" By ", " 通过 "],
  [" And ", " 与 "],
  [" Or ", " 或 "],
  [" For ", " 的 "],
];

const GENERIC_PREFIXES = [
  "Improper ",
  "Incorrect ",
  "Inconsistent ",
  "Use of ",
  "Missing ",
  "Reliance on ",
  "Exposure of ",
  "Generation of ",
  "Insertion of ",
  "Creation of ",
  "Operation on ",
  "Execution with ",
  "Download of Code Without Integrity Check ",
];

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function normalizeCweId(value) {
  if (value == null) return null;

  if (Array.isArray(value)) {
    for (const item of value) {
      const normalized = normalizeCweId(item);
      if (normalized) return normalized;
    }
    return null;
  }

  if (typeof value === "object") {
    for (const key of ["cwe", "cwe_id", "id"]) {
      if (key in value) {
        const normalized = normalizeCweId(value[key]);
        if (normalized) return normalized;
      }
    }
    return null;
  }

  const raw = String(value).trim();
  if (!raw) return null;

  const cweMatch = raw.match(/CWE[\s:_-]*(\d{1,6})/i);
  if (cweMatch?.[1]) {
    return `CWE-${Number.parseInt(cweMatch[1], 10)}`;
  }

  const definitionMatch = raw.match(/definitions\/(\d{1,6})(?:\.html)?/i);
  if (definitionMatch?.[1]) {
    return `CWE-${Number.parseInt(definitionMatch[1], 10)}`;
  }

  if (/^\d{1,6}$/.test(raw)) {
    return `CWE-${Number.parseInt(raw, 10)}`;
  }

  return null;
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }

  return await response.json();
}

async function fetchTextFromZip(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/zip, application/octet-stream" },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }

  const archive = new Uint8Array(await response.arrayBuffer());
  const files = unzipSync(archive);
  const xmlEntryName = Object.keys(files).find((name) => name.endsWith(".xml"));
  if (!xmlEntryName) {
    throw new Error(`No XML entry found in ${url}`);
  }

  return strFromU8(files[xmlEntryName]);
}

function replaceAllIgnoreCase(text, search, replacement) {
  return String(text).replace(
    new RegExp(escapeRegExp(search), "gi"),
    replacement,
  );
}

function cleanupDisplayText(text) {
  return String(text)
    .replace(/[()]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s*-\s*/g, "-")
    .replace(/\s+([,./:;])/g, "$1")
    .trim();
}

export function extractShortEnglishName(name) {
  const officialName = cleanupDisplayText(name);
  if (!officialName) return "";

  const trailingQuotedAliasMatch = officialName.match(/'([^']+)'\s*$/);
  if (trailingQuotedAliasMatch?.[1]) {
    return cleanupDisplayText(trailingQuotedAliasMatch[1]);
  }

  const quotedAliasMatch = officialName.match(/\('([^']+)'\)\s*$/);
  if (quotedAliasMatch?.[1]) {
    return cleanupDisplayText(quotedAliasMatch[1]);
  }

  const aliasMatch = officialName.match(/\(([A-Za-z0-9 /,-]+)\)\s*$/);
  if (aliasMatch?.[1]) {
    const alias = cleanupDisplayText(aliasMatch[1]);
    if (alias && alias.length <= officialName.length) {
      return alias;
    }
  }

  for (const prefix of GENERIC_PREFIXES) {
    if (officialName.startsWith(prefix)) {
      const stripped = cleanupDisplayText(officialName.slice(prefix.length));
      if (stripped) return stripped;
    }
  }

  return officialName;
}

function translateByDictionary(name) {
  const normalized = cleanupDisplayText(name);
  const exact = EXACT_SHORT_TRANSLATIONS.get(normalized.toLowerCase());
  if (exact) return exact;

  let translated = normalized;
  for (const [search, replacement] of ORDERED_PHRASE_TRANSLATIONS) {
    translated = replaceAllIgnoreCase(translated, search, replacement);
  }

  for (const [search, replacement] of CONNECTOR_REPLACEMENTS) {
    translated = replaceAllIgnoreCase(translated, search, replacement);
  }

  translated = translated
    .replace(/\bthe\b/gi, "")
    .replace(/\ba\b/gi, "")
    .replace(/\ban\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();

  return cleanupDisplayText(translated);
}

export function translateShortNameToChinese(name, cweId = "") {
  const normalizedCweId = normalizeCweId(cweId);
  if (normalizedCweId && MANUAL_ZH_OVERRIDES[normalizedCweId]) {
    return MANUAL_ZH_OVERRIDES[normalizedCweId];
  }

  const normalized = cleanupDisplayText(name);
  if (!normalized) return null;

  const translated = translateByDictionary(normalized);
  if (!translated) return null;

  return translated;
}

function decodeXmlEntities(value) {
  return String(value)
    .replace(/&quot;/g, "\"")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) =>
      String.fromCodePoint(Number.parseInt(code, 16)),
    );
}

function extractCatalogMetadata(xml) {
  const matched = String(xml).match(/Version="([^"]+)".*?Date="([^"]+)"/);

  return {
    contentVersion: matched?.[1] || "",
    contentDate: matched?.[2] || "",
  };
}

function extractWeaknessDetails(xml) {
  const weaknessPattern = /<Weakness\b[^>]*ID="(\d+)"[^>]*Name="([^"]+)"[^>]*>/g;
  const details = [];
  const seenIds = new Set();

  for (const match of String(xml).matchAll(weaknessPattern)) {
    const numericId = Number.parseInt(String(match[1] || ""), 10);
    if (!Number.isFinite(numericId) || numericId < 1) continue;
    if (seenIds.has(numericId)) continue;
    seenIds.add(numericId);
    details.push({
      ID: String(numericId),
      Name: decodeXmlEntities(match[2] || ""),
    });
  }

  return details.sort(
    (left, right) => Number.parseInt(left.ID, 10) - Number.parseInt(right.ID, 10),
  );
}

function buildCatalogEntry(weakness) {
  const numericId = Number.parseInt(String(weakness?.ID || ""), 10);
  if (!Number.isFinite(numericId)) {
    throw new Error(`Invalid weakness ID: ${JSON.stringify(weakness)}`);
  }

  const cweId = `CWE-${numericId}`;
  const nameEnOfficial = cleanupDisplayText(weakness?.Name);
  const nameEnShort = extractShortEnglishName(nameEnOfficial);
  const nameZh =
    translateShortNameToChinese(nameEnShort, cweId) ||
    translateShortNameToChinese(nameEnOfficial, cweId);

  if (!nameZh) {
    throw new Error(`Missing zh name for ${cweId}`);
  }

  return {
    id: cweId,
    numericId,
    nameEnOfficial,
    nameEnShort: nameEnShort || nameEnOfficial,
    nameZh,
  };
}

export async function generateCweCatalog() {
  const catalogXml = await fetchTextFromZip(CWE_XML_ZIP_URL);
  const versionInfo = extractCatalogMetadata(catalogXml);
  const weaknesses = extractWeaknessDetails(catalogXml);
  const entries = weaknesses
    .map((weakness) => buildCatalogEntry(weakness))
    .sort((left, right) => left.numericId - right.numericId);

  return {
    contentVersion: String(versionInfo?.contentVersion || ""),
    contentDate: String(versionInfo?.contentDate || ""),
    generatedAt: new Date().toISOString(),
    entries,
  };
}

export async function writeCweCatalog() {
  const catalog = await generateCweCatalog();
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(catalog, null, 2)}\n`, "utf8");
  return {
    outputPath,
    entryCount: catalog.entries.length,
    contentVersion: catalog.contentVersion,
    contentDate: catalog.contentDate,
  };
}

async function main() {
  const result = await writeCweCatalog();
  console.log(
    `Wrote ${result.entryCount} CWE entries to ${result.outputPath} (MITRE ${result.contentVersion} / ${result.contentDate})`,
  );
}

if (
  process.argv[1] &&
  pathToFileURL(process.argv[1]).href === import.meta.url
) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
