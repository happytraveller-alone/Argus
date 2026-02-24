"""
模式匹配工具
快速扫描代码中的危险模式

优化版本：
- 支持直接扫描文件（无需先读取）
- 支持传入代码内容扫描
- 增强的漏洞模式库（OWASP Top 10 2025）
- 更好的输出格式化
"""

import os
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass

from .base import AgentTool, ToolResult


@dataclass
class PatternMatch:
    """模式匹配结果"""
    pattern_name: str
    pattern_type: str
    file_path: str
    line_number: int
    matched_text: str
    context: str
    severity: str
    description: str
    cwe_id: str = ""  # 🔥 添加 CWE ID 引用


class PatternMatchInput(BaseModel):
    """模式匹配输入 - 支持两种模式"""
    # 🔥 模式1: 传入代码内容
    code: Optional[str] = Field(
        default=None, 
        description="要扫描的代码内容（与 scan_file 二选一）"
    )
    # 🔥 模式2: 直接扫描文件
    scan_file: Optional[str] = Field(
        default=None,
        description="要扫描的文件路径（相对于项目根目录，与 code 二选一）"
    )
    file_path: str = Field(default="unknown", description="文件路径（用于上下文）")
    pattern_types: Optional[List[str]] = Field(
        default=None,
        description="要检测的漏洞类型列表，如 ['sql_injection', 'xss']。为空则检测所有类型"
    )
    language: Optional[str] = Field(default=None, description="编程语言，用于选择特定模式")


class PatternMatchTool(AgentTool):
    """
    模式匹配工具
    使用正则表达式快速扫描代码中的危险模式
    """
    
    def __init__(self, project_root: str = None):
        """
        初始化模式匹配工具
        
        Args:
            project_root: 项目根目录（可选，用于上下文）
        """
        super().__init__()
        self.project_root = project_root

    MAX_SCAN_FILES = 200
    MAX_FILE_SIZE_BYTES = 1024 * 1024
    SCAN_EXCLUDE_DIRS = {
        ".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".pytest_cache"
    }
    SCAN_TEXT_EXTENSIONS = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".php", ".go", ".rb", ".rs",
        ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".swift", ".kt", ".kts",
        ".m", ".mm", ".cs", ".scala", ".sh", ".bash", ".zsh", ".sql", ".yaml", ".yml",
        ".xml", ".json", ".toml", ".ini", ".cfg", ".conf",
    }
    BINARY_EXTENSIONS = {
        ".so", ".dll", ".dylib", ".a", ".o", ".obj", ".class", ".jar", ".war",
        ".exe", ".bin", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
        ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    }
    
    # 危险模式定义
    PATTERNS: Dict[str, Dict[str, Any]] = {
        # SQL 注入模式
        "sql_injection": {
            "patterns": {
                "python": [
                    (r'cursor\.execute\s*\(\s*["\'].*%[sd].*["\'].*%', "格式化字符串构造SQL"),
                    (r'cursor\.execute\s*\(\s*f["\']', "f-string构造SQL"),
                    (r'cursor\.execute\s*\([^,)]+\+', "字符串拼接构造SQL"),
                    (r'\.execute\s*\(\s*["\'][^"\']*\{', "format()构造SQL"),
                    (r'text\s*\(\s*["\'].*\+.*["\']', "SQLAlchemy text()拼接"),
                ],
                "javascript": [
                    (r'\.query\s*\(\s*[`"\'].*\$\{', "模板字符串构造SQL"),
                    (r'\.query\s*\(\s*["\'].*\+', "字符串拼接构造SQL"),
                    (r'mysql\.query\s*\([^,)]+\+', "MySQL查询拼接"),
                ],
                "java": [
                    (r'Statement.*execute.*\+', "Statement字符串拼接"),
                    (r'createQuery\s*\([^,)]+\+', "JPA查询拼接"),
                    (r'\.executeQuery\s*\([^,)]+\+', "executeQuery拼接"),
                ],
                "php": [
                    (r'mysql_query\s*\(\s*["\'].*\.\s*\$', "mysql_query拼接"),
                    (r'mysqli_query\s*\([^,]+,\s*["\'].*\.\s*\$', "mysqli_query拼接"),
                    (r'\$pdo->query\s*\(\s*["\'].*\.\s*\$', "PDO query拼接"),
                ],
                "go": [
                    (r'\.Query\s*\([^,)]+\+', "Query字符串拼接"),
                    (r'\.Exec\s*\([^,)]+\+', "Exec字符串拼接"),
                    (r'fmt\.Sprintf\s*\([^)]+\)\s*\)', "Sprintf构造SQL"),
                ],
            },
            "severity": "high",
            "description": "SQL注入漏洞：用户输入直接拼接到SQL语句中",
        },
        
        # XSS 模式
        "xss": {
            "patterns": {
                "javascript": [
                    (r'innerHTML\s*=\s*[^;]+', "innerHTML赋值"),
                    (r'outerHTML\s*=\s*[^;]+', "outerHTML赋值"),
                    (r'document\.write\s*\(', "document.write"),
                    (r'\.html\s*\([^)]+\)', "jQuery html()"),
                    (r'dangerouslySetInnerHTML', "React dangerouslySetInnerHTML"),
                ],
                "python": [
                    (r'\|\s*safe\b', "Django safe过滤器"),
                    (r'Markup\s*\(', "Flask Markup"),
                    (r'mark_safe\s*\(', "Django mark_safe"),
                ],
                "php": [
                    (r'echo\s+\$_(?:GET|POST|REQUEST)', "直接输出用户输入"),
                    (r'print\s+\$_(?:GET|POST|REQUEST)', "打印用户输入"),
                ],
                "java": [
                    (r'out\.print(?:ln)?\s*\([^)]*request\.getParameter', "直接输出请求参数"),
                ],
            },
            "severity": "high",
            "description": "XSS跨站脚本漏洞：未转义的用户输入被渲染到页面",
        },
        
        # 命令注入模式
        "command_injection": {
            "patterns": {
                "python": [
                    (r'os\.system\s*\([^)]*\+', "os.system拼接"),
                    (r'os\.system\s*\([^)]*%', "os.system格式化"),
                    (r'os\.system\s*\(\s*f["\']', "os.system f-string"),
                    (r'subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True', "shell=True"),
                    (r'subprocess\.(?:call|run|Popen)\s*\(\s*["\'][^"\']+%', "subprocess格式化"),
                    (r'eval\s*\(', "eval()"),
                    (r'exec\s*\(', "exec()"),
                ],
                "javascript": [
                    (r'exec\s*\([^)]+\+', "exec拼接"),
                    (r'spawn\s*\([^)]+,\s*\{[^}]*shell:\s*true', "spawn shell"),
                    (r'eval\s*\(', "eval()"),
                    (r'Function\s*\(', "Function构造器"),
                ],
                "php": [
                    (r'exec\s*\(\s*\$', "exec变量"),
                    (r'system\s*\(\s*\$', "system变量"),
                    (r'passthru\s*\(\s*\$', "passthru变量"),
                    (r'shell_exec\s*\(\s*\$', "shell_exec变量"),
                    (r'`[^`]*\$[^`]*`', "反引号命令执行"),
                ],
                "java": [
                    (r'Runtime\.getRuntime\(\)\.exec\s*\([^)]+\+', "Runtime.exec拼接"),
                    (r'ProcessBuilder[^;]+\+', "ProcessBuilder拼接"),
                ],
                "go": [
                    (r'exec\.Command\s*\([^)]+\+', "exec.Command拼接"),
                ],
            },
            "severity": "critical",
            "description": "命令注入漏洞：用户输入被用于执行系统命令",
        },
        
        # 路径遍历模式
        "path_traversal": {
            "patterns": {
                "python": [
                    (r'open\s*\([^)]*\+', "open()拼接"),
                    (r'open\s*\([^)]*%', "open()格式化"),
                    (r'os\.path\.join\s*\([^)]*request', "join用户输入"),
                    (r'send_file\s*\([^)]*request', "send_file用户输入"),
                ],
                "javascript": [
                    (r'fs\.read(?:File|FileSync)\s*\([^)]+\+', "readFile拼接"),
                    (r'path\.join\s*\([^)]*req\.', "path.join用户输入"),
                    (r'res\.sendFile\s*\([^)]+\+', "sendFile拼接"),
                ],
                "php": [
                    (r'include\s*\(\s*\$', "include变量"),
                    (r'require\s*\(\s*\$', "require变量"),
                    (r'file_get_contents\s*\(\s*\$', "file_get_contents变量"),
                    (r'fopen\s*\(\s*\$', "fopen变量"),
                ],
                "java": [
                    (r'new\s+File\s*\([^)]+request\.getParameter', "File构造用户输入"),
                    (r'new\s+FileInputStream\s*\([^)]+\+', "FileInputStream拼接"),
                ],
            },
            "severity": "high",
            "description": "路径遍历漏洞：用户可以访问任意文件",
        },
        
        # SSRF 模式
        "ssrf": {
            "patterns": {
                "python": [
                    (r'requests\.(?:get|post|put|delete)\s*\([^)]*request\.', "requests用户URL"),
                    (r'urllib\.request\.urlopen\s*\([^)]*request\.', "urlopen用户URL"),
                    (r'httpx\.(?:get|post)\s*\([^)]*request\.', "httpx用户URL"),
                ],
                "javascript": [
                    (r'fetch\s*\([^)]*req\.', "fetch用户URL"),
                    (r'axios\.(?:get|post)\s*\([^)]*req\.', "axios用户URL"),
                    (r'http\.request\s*\([^)]*req\.', "http.request用户URL"),
                ],
                "java": [
                    (r'new\s+URL\s*\([^)]*request\.getParameter', "URL构造用户输入"),
                    (r'HttpClient[^;]+request\.getParameter', "HttpClient用户URL"),
                ],
                "php": [
                    (r'curl_setopt[^;]+CURLOPT_URL[^;]+\$', "curl用户URL"),
                    (r'file_get_contents\s*\(\s*\$_', "file_get_contents用户URL"),
                ],
            },
            "severity": "high",
            "description": "SSRF漏洞：服务端请求用户控制的URL",
        },
        
        # 不安全的反序列化
        "deserialization": {
            "patterns": {
                "python": [
                    (r'pickle\.loads?\s*\(', "pickle反序列化"),
                    (r'yaml\.load\s*\([^)]*(?!Loader)', "yaml.load无安全Loader"),
                    (r'yaml\.unsafe_load\s*\(', "yaml.unsafe_load"),
                    (r'marshal\.loads?\s*\(', "marshal反序列化"),
                ],
                "javascript": [
                    (r'serialize\s*\(', "serialize"),
                    (r'unserialize\s*\(', "unserialize"),
                ],
                "java": [
                    (r'ObjectInputStream\s*\(', "ObjectInputStream"),
                    (r'XMLDecoder\s*\(', "XMLDecoder"),
                    (r'readObject\s*\(', "readObject"),
                ],
                "php": [
                    (r'unserialize\s*\(\s*\$', "unserialize用户输入"),
                ],
            },
            "severity": "critical",
            "description": "不安全的反序列化：可能导致远程代码执行",
        },
        
        # 硬编码密钥
        "hardcoded_secret": {
            "patterns": {
                "_common": [
                    (r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']', "硬编码密码"),
                    (r'(?:secret|api_?key|apikey|token|auth)\s*=\s*["\'][^"\']{8,}["\']', "硬编码密钥"),
                    (r'(?:private_?key|priv_?key)\s*=\s*["\'][^"\']+["\']', "硬编码私钥"),
                    (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', "私钥"),
                    (r'(?:aws_?access_?key|aws_?secret)\s*=\s*["\'][^"\']+["\']', "AWS密钥"),
                    (r'(?:ghp_|gho_|github_pat_)[a-zA-Z0-9]{36,}', "GitHub Token"),
                    (r'sk-[a-zA-Z0-9]{48}', "OpenAI API Key"),
                    (r'(?:bearer|authorization)\s*[=:]\s*["\'][^"\']{20,}["\']', "Bearer Token"),
                ],
            },
            "severity": "medium",
            "description": "硬编码密钥：敏感信息不应该硬编码在代码中",
        },
        
        # 弱加密
        "weak_crypto": {
            "patterns": {
                "python": [
                    (r'hashlib\.md5\s*\(', "MD5哈希"),
                    (r'hashlib\.sha1\s*\(', "SHA1哈希"),
                    (r'DES\s*\(', "DES加密"),
                    (r'random\.random\s*\(', "不安全随机数"),
                ],
                "javascript": [
                    (r'crypto\.createHash\s*\(\s*["\']md5["\']', "MD5哈希"),
                    (r'crypto\.createHash\s*\(\s*["\']sha1["\']', "SHA1哈希"),
                    (r'Math\.random\s*\(', "Math.random"),
                ],
                "java": [
                    (r'MessageDigest\.getInstance\s*\(\s*["\']MD5["\']', "MD5哈希"),
                    (r'MessageDigest\.getInstance\s*\(\s*["\']SHA-?1["\']', "SHA1哈希"),
                    (r'DESKeySpec', "DES密钥"),
                ],
                "php": [
                    (r'md5\s*\(', "MD5哈希"),
                    (r'sha1\s*\(', "SHA1哈希"),
                    (r'mcrypt_', "mcrypt已废弃"),
                ],
            },
            "severity": "low",
            "description": "弱加密算法：使用了不安全的加密或哈希算法",
            "cwe_id": "CWE-327",
        },
    }
    
    @property
    def name(self) -> str:
        return "pattern_match"
    
    @property
    def description(self) -> str:
        vuln_types = ", ".join(self.PATTERNS.keys())
        return f"""🔍 快速扫描代码中的危险模式和常见漏洞。

支持两种使用方式：
1. ⭐ 推荐：直接扫描文件 - 使用 scan_file 参数指定文件路径
2. 传入代码内容 - 使用 code 参数传入已读取的代码

支持的漏洞类型: {vuln_types}

使用示例:
- 方式1（推荐）: {{"scan_file": "app/views.py", "pattern_types": ["sql_injection", "xss"]}}
- 方式2: {{"code": "...", "file_path": "app/views.py"}}

输入参数:
- scan_file (推荐): 要扫描的文件路径（相对于项目根目录）
- code: 要扫描的代码内容（与 scan_file 二选一）
- file_path: 文件路径（用于上下文，如果使用 code 模式）
- pattern_types: 要检测的漏洞类型列表
- language: 指定编程语言（通常自动检测）

这是一个快速扫描工具，发现的问题需要进一步分析确认。"""
    
    @property
    def args_schema(self):
        return PatternMatchInput
    
    async def _execute(
        self,
        code: Optional[str] = None,
        scan_file: Optional[str] = None,
        file_path: str = "unknown",
        pattern_types: Optional[List[str]] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """执行模式匹配 - 支持直接文件扫描或代码内容扫描"""
        normalized_pattern_types = self._normalize_pattern_types(pattern_types)

        # 🔥 模式1: 直接扫描文件 / 目录
        if scan_file:
            if not self.project_root:
                return ToolResult(
                    success=False,
                    error="无法扫描文件：未配置项目根目录"
                )
            
            full_path = os.path.normpath(os.path.join(self.project_root, scan_file))
            
            # 安全检查：防止路径遍历
            if not full_path.startswith(os.path.normpath(self.project_root)):
                return ToolResult(
                    success=False,
                    error="安全错误：不允许访问项目目录外的文件"
                )
            
            if not os.path.exists(full_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {scan_file}"
                )

            if os.path.isdir(full_path):
                return self._scan_directory(
                    full_path=full_path,
                    scan_root=scan_file,
                    pattern_types=normalized_pattern_types,
                    language=language,
                )

            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
                file_path = scan_file
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=f"读取文件失败: {str(e)}"
                )
        
        # 🔥 检查是否有代码可以扫描
        if not code:
            return ToolResult(
                success=False,
                error="必须提供 scan_file（文件路径）或 code（代码内容）其中之一"
            )

        matches = self._scan_code_content(
            code=code,
            file_path=file_path,
            pattern_types=normalized_pattern_types,
            language=language,
        )

        if not matches:
            return ToolResult(
                success=True,
                data="没有检测到已知的危险模式",
                metadata={"patterns_checked": len(normalized_pattern_types), "matches": 0}
            )
        return self._build_result(
            matches=matches,
            patterns_checked=len(normalized_pattern_types),
        )

    @staticmethod
    def _normalize_pattern_types(pattern_types: Optional[Any]) -> List[str]:
        if pattern_types is None:
            return list(PatternMatchTool.PATTERNS.keys())

        normalized: List[str] = []
        if isinstance(pattern_types, str):
            candidates = re.split(r"[|,;]", pattern_types)
            normalized = [item.strip() for item in candidates if item.strip()]
        elif isinstance(pattern_types, list):
            normalized = [str(item).strip() for item in pattern_types if str(item).strip()]
        else:
            normalized = [str(pattern_types).strip()] if str(pattern_types).strip() else []

        known = [item for item in normalized if item in PatternMatchTool.PATTERNS]
        return known or list(PatternMatchTool.PATTERNS.keys())

    def _scan_code_content(
        self,
        code: str,
        file_path: str,
        pattern_types: List[str],
        language: Optional[str],
    ) -> List[PatternMatch]:
        matches: List[PatternMatch] = []
        lines = code.split('\n')

        language_value = language or self._detect_language(file_path)
        types_to_check = pattern_types or list(self.PATTERNS.keys())

        for vuln_type in types_to_check:
            if vuln_type not in self.PATTERNS:
                continue

            pattern_config = self.PATTERNS[vuln_type]
            patterns_dict = pattern_config["patterns"]

            patterns_to_use = []
            if language_value and language_value in patterns_dict:
                patterns_to_use.extend(patterns_dict[language_value])
            if "_common" in patterns_dict:
                patterns_to_use.extend(patterns_dict["_common"])

            if not patterns_to_use:
                for lang, pats in patterns_dict.items():
                    if lang != "_common":
                        patterns_to_use.extend(pats)

            for pattern, pattern_name in patterns_to_use:
                try:
                    for i, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            start = max(0, i - 2)
                            end = min(len(lines), i + 3)
                            context = '\n'.join(f"{j+1}: {lines[j]}" for j in range(start, end))

                            matches.append(PatternMatch(
                                pattern_name=pattern_name,
                                pattern_type=vuln_type,
                                file_path=file_path,
                                line_number=i + 1,
                                matched_text=line.strip()[:200],
                                context=context,
                                severity=pattern_config["severity"],
                                description=pattern_config["description"],
                            ))
                except re.error:
                    continue

        return matches

    def _scan_directory(
        self,
        full_path: str,
        scan_root: str,
        pattern_types: List[str],
        language: Optional[str],
    ) -> ToolResult:
        base_root = os.path.normpath(self.project_root or "")
        matches: List[PatternMatch] = []
        files_scanned = 0
        skipped_files: List[Dict[str, str]] = []
        reached_limit = False

        for root, dirs, files in os.walk(full_path):
            rel_dir = os.path.relpath(root, base_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirs[:] = [
                d for d in dirs
                if d not in self.SCAN_EXCLUDE_DIRS
                and not d.startswith(".")
            ]

            for filename in files:
                if files_scanned >= self.MAX_SCAN_FILES:
                    reached_limit = True
                    break

                ext = os.path.splitext(filename)[1].lower()
                if ext in self.BINARY_EXTENSIONS:
                    continue
                if ext and ext not in self.SCAN_TEXT_EXTENSIONS:
                    continue

                file_full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_full_path, base_root).replace("\\", "/")

                try:
                    file_size = os.path.getsize(file_full_path)
                except Exception:
                    skipped_files.append({"file": rel_path, "reason": "无法读取文件大小"})
                    continue

                if file_size > self.MAX_FILE_SIZE_BYTES:
                    skipped_files.append({
                        "file": rel_path,
                        "reason": f"文件过大({file_size} bytes)",
                    })
                    continue

                try:
                    with open(file_full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except Exception as exc:
                    skipped_files.append({"file": rel_path, "reason": f"读取失败: {exc}"})
                    continue

                files_scanned += 1
                matches.extend(
                    self._scan_code_content(
                        code=content,
                        file_path=rel_path,
                        pattern_types=pattern_types,
                        language=language,
                    )
                )

            if reached_limit:
                break

        if files_scanned == 0:
            reason = (
                "目录中没有可扫描的源码文件，请传入具体源码文件，或确认目录下存在可读文本源码。"
            )
            return ToolResult(
                success=False,
                error=reason,
                metadata={
                    "scan_root": scan_root,
                    "files_scanned": 0,
                    "skipped_files": skipped_files[:20],
                },
            )

        if not matches:
            return ToolResult(
                success=True,
                data="没有检测到已知的危险模式",
                metadata={
                    "patterns_checked": len(pattern_types),
                    "matches": 0,
                    "scan_root": scan_root,
                    "files_scanned": files_scanned,
                    "skipped_files": skipped_files[:20],
                    "scan_limited": reached_limit,
                },
            )

        return self._build_result(
            matches=matches,
            patterns_checked=len(pattern_types),
            extra_metadata={
                "scan_root": scan_root,
                "files_scanned": files_scanned,
                "skipped_files": skipped_files[:20],
                "scan_limited": reached_limit,
            },
        )

    def _build_result(
        self,
        matches: List[PatternMatch],
        patterns_checked: int,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        output_parts = [f"检测到 {len(matches)} 个潜在问题:\n"]

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        matches.sort(key=lambda x: severity_order.get(x.severity, 4))

        for match in matches:
            output_parts.append(f"\n[{match.severity.upper()}] {match.pattern_type}")
            output_parts.append(f"   位置: {match.file_path}:{match.line_number}")
            output_parts.append(f"   模式: {match.pattern_name}")
            output_parts.append(f"   描述: {match.description}")
            output_parts.append(f"   匹配: {match.matched_text}")
            output_parts.append(f"   上下文:\n{match.context}")

        metadata = {
            "patterns_checked": patterns_checked,
            "matches": len(matches),
            "by_severity": {
                s: len([m for m in matches if m.severity == s])
                for s in ["critical", "high", "medium", "low"]
            },
            "details": [
                {
                    "type": m.pattern_type,
                    "severity": m.severity,
                    "line": m.line_number,
                    "pattern": m.pattern_name,
                    "file_path": m.file_path,
                }
                for m in matches
            ],
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata=metadata,
        )
    
    def _detect_language(self, file_path: str) -> Optional[str]:
        """根据文件扩展名检测语言"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "javascript",
            ".tsx": "javascript",
            ".java": "java",
            ".php": "php",
            ".go": "go",
            ".rb": "ruby",
        }
        
        for ext, lang in ext_map.items():
            if file_path.lower().endswith(ext):
                return lang
        
        return None
