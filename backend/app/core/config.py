from typing import List, Union, Optional
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "DeepAudit"
    API_V1_STR: str = "/api/v1"
    
    # SECURITY
    SECRET_KEY: str = "changethis_in_production_to_a_long_random_string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @validator("FUNCTION_LOCATOR_LANGUAGES", pre=True)
    def assemble_function_locator_languages(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            text = v.strip()
            if not text:
                return []
            if text.startswith("[") and text.endswith("]"):
                try:
                    import json

                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    # POSTGRES
    POSTGRES_SERVER: str = "db"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "deepaudit"
    DATABASE_URL: str | None = None

    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: str | None, values: dict[str, any]) -> str:
        if isinstance(v, str):
            return v
        return str(f"postgresql+asyncpg://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}/{values.get('POSTGRES_DB')}")

    # LLM配置
    LLM_PROVIDER: str = "openai"  # gemini, openai, claude, qwen, deepseek, zhipu, moonshot, baidu, minimax, doubao, ollama
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: Optional[str] = None  # 不指定时使用provider的默认模型
    LLM_BASE_URL: Optional[str] = None  # 自定义API端点（如中转站）
    LLM_TIMEOUT: int = 150  # 超时时间（秒）
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096

    # Agent 流式超时配置（秒）
    LLM_FIRST_TOKEN_TIMEOUT: int = 90  # 等待首个Token的超时时间
    LLM_STREAM_TIMEOUT: int = 60  # 流式输出中两个Token之间的超时时间
    SUB_AGENT_TIMEOUT_SECONDS: int = 600  # 子Agent超时时间（10分钟）
    TOOL_TIMEOUT_SECONDS: int = 60  # 工具执行默认超时时间
    
    # 各LLM提供商的API Key配置（兼容单独配置）
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    CLAUDE_API_KEY: Optional[str] = None
    QWEN_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    ZHIPU_API_KEY: Optional[str] = None
    MOONSHOT_API_KEY: Optional[str] = None
    BAIDU_API_KEY: Optional[str] = None  # 格式: api_key:secret_key
    MINIMAX_API_KEY: Optional[str] = None
    DOUBAO_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: Optional[str] = "http://localhost:11434/v1"
    
    # GitHub配置
    GITHUB_TOKEN: Optional[str] = None
    
    # GitLab配置
    GITLAB_TOKEN: Optional[str] = None
    
    # Gitea配置
    GITEA_TOKEN: Optional[str] = None
    
    # 扫描配置
    MAX_ANALYZE_FILES: int = 0  # 最大分析文件数，0表示无限制
    MAX_FILE_SIZE_BYTES: int = 200 * 1024  # 最大文件大小 200KB
    LLM_CONCURRENCY: int = 3  # LLM并发数
    LLM_GAP_MS: int = 2000  # LLM请求间隔（毫秒）
    
    # ZIP文件存储配置
    ZIP_STORAGE_PATH: str = "./uploads/zip_files"  # ZIP文件存储目录

    # 通用缓存目录（git缓存等）
    CACHE_DIR: str = "./data/cache"  # 缓存目录基础路径
    
    # 输出语言配置 - 支持 zh-CN（中文）和 en-US（英文）
    OUTPUT_LANGUAGE: str = "zh-CN"
    
    # ============ Agent 模块配置 ============

    # 嵌入模型配置（独立于 LLM 配置）
    EMBEDDING_PROVIDER: str = "openai"  # openai, azure, ollama, cohere, huggingface, jina, qwen
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_API_KEY: Optional[str] = None  # 嵌入模型专用 API Key（留空则使用 LLM_API_KEY）
    EMBEDDING_BASE_URL: Optional[str] = None  # 嵌入模型专用 Base URL（留空使用提供商默认地址）
    
    # 向量数据库配置
    VECTOR_DB_PATH: str = "./data/vector_db"  # 向量数据库持久化目录

    # SSH配置
    SSH_CONFIG_PATH: str = "./data/ssh"  # SSH配置目录（存储known_hosts等）
    SSH_CLONE_TIMEOUT: int = 300  # SSH克隆超时时间（秒）
    SSH_TEST_TIMEOUT: int = 15  # SSH测试连接超时时间（秒）
    SSH_CONNECT_TIMEOUT: int = 10  # SSH连接超时时间（秒）
    
    # Agent 配置
    AGENT_MAX_ITERATIONS: int = 50  # Agent 最大迭代次数
    AGENT_TOKEN_BUDGET: int = 100000  # Agent Token 预算
    AGENT_TIMEOUT_SECONDS: int = 1800  # Agent 超时时间（30分钟）
    
    # 沙箱配置（必须）
    SANDBOX_IMAGE: str = "deepaudit/sandbox:latest"  # 沙箱 Docker 镜像
    SANDBOX_MEMORY_LIMIT: str = "512m"  # 沙箱内存限制
    SANDBOX_CPU_LIMIT: float = 1.0  # 沙箱 CPU 限制
    SANDBOX_TIMEOUT: int = 60  # 沙箱命令超时（秒）
    SANDBOX_NETWORK_MODE: str = "none"  # 沙箱网络模式 (none, bridge)
    
    # RAG 配置
    # 🔥 默认禁用 RAG（Embedding/向量索引）初始化：智能审计任务不应依赖 embedding 配置
    # 如需启用，可通过环境变量显式开启（例如：RAG_ENABLED=true）
    RAG_ENABLED: bool = False
    RAG_CHUNK_SIZE: int = 1500  # 代码块大小（Token）
    RAG_CHUNK_OVERLAP: int = 50  # 代码块重叠（Token）
    RAG_TOP_K: int = 10  # 检索返回数量

    # Flow 分析配置（三轨）
    FLOW_LIGHTWEIGHT_ENABLED: bool = True
    FLOW_JOERN_ENABLED: bool = True
    FLOW_JOERN_TIMEOUT_SEC: int = 45
    FLOW_JOERN_TRIGGER_SEVERITY: str = "high,critical"
    FLOW_JOERN_TRIGGER_CONFIDENCE: float = 0.7
    LOGIC_AUTHZ_ENABLED: bool = True
    FLOW_UNREACHABLE_POLICY: str = "degrade_likely"

    # 命中代码归属函数定位配置
    FUNCTION_LOCATOR_LANGUAGES: List[str] = [
        "python",
        "javascript",
        "typescript",
        "java",
        "kotlin",
        "c",
        "cpp",
    ]

    # 工具文档同步到 Markdown Memory（shared.md）
    TOOL_DOC_SYNC_ENABLED: bool = True
    TOOL_DOC_SYNC_MAX_CHARS: int = 8000

    # Generic MCP runtime configuration
    MCP_ENABLED: bool = True
    MCP_PREFER: bool = True
    MCP_STRICT_MODE: bool = True
    MCP_TIMEOUT_SECONDS: int = 30
    MCP_REQUIRE_ALL_READY_ON_STARTUP: bool = True
    MCP_REQUIRED_RUNTIME_DOMAIN: str = "all"  # backend | sandbox | all
    MCP_RUNTIME_MODE_DEFAULT: str = "backend_then_sandbox"

    # Write policy hard constraints (applies to every task)
    MCP_WRITE_HARD_LIMIT: int = 50
    MCP_DEFAULT_MAX_WRITABLE_FILES_PER_TASK: int = 50
    MCP_ALL_AGENTS_WRITABLE: bool = True
    MCP_REQUIRE_EVIDENCE_BINDING: bool = True
    MCP_FORBID_PROJECT_WIDE_WRITES: bool = True

    # MCP adapters (stdio)
    MCP_FILESYSTEM_ENABLED: bool = False
    MCP_FILESYSTEM_RUNTIME_MODE: str = "sandbox_only"
    MCP_FILESYSTEM_COMMAND: str = "pnpm"
    MCP_FILESYSTEM_ARGS: str = "dlx @modelcontextprotocol/server-filesystem"
    MCP_FILESYSTEM_SANDBOX_ENABLED: bool = True
    MCP_FILESYSTEM_SANDBOX_COMMAND: str = "pnpm"
    MCP_FILESYSTEM_SANDBOX_ARGS: str = "dlx @modelcontextprotocol/server-filesystem"
    MCP_FILESYSTEM_FORCE_STDIO: bool = True
    MCP_FILESYSTEM_BACKEND_URL: Optional[str] = None
    MCP_FILESYSTEM_SANDBOX_URL: Optional[str] = None
    MCP_FILESYSTEM_DAEMON_HOST: str = "127.0.0.1"
    MCP_FILESYSTEM_DAEMON_PORT: int = 8770
    MCP_FILESYSTEM_DAEMON_COMMAND: str = "fastmcp"
    MCP_FILESYSTEM_DAEMON_ARGS: str = ""
    MCP_FILESYSTEM_DAEMON_ALLOWED_DIRS: str = "/tmp,/app"
    MCP_FILESYSTEM_DAEMON_SOURCE_DIR: str = "/app/mcp-src/filesystem"
    MCP_FILESYSTEM_DAEMON_STARTUP_TIMEOUT_SECONDS: int = 45

    MCP_CODE_INDEX_ENABLED: bool = True
    MCP_CODE_INDEX_RUNTIME_MODE: str = "backend_then_sandbox"
    MCP_CODE_INDEX_COMMAND: str = "code-index-mcp"
    MCP_CODE_INDEX_ARGS: str = "--indexer-path /app/data/mcp/code-index"
    MCP_CODE_INDEX_SANDBOX_ENABLED: bool = True
    MCP_CODE_INDEX_SANDBOX_COMMAND: str = "code-index-mcp"
    MCP_CODE_INDEX_SANDBOX_ARGS: str = "--indexer-path /app/data/mcp/code-index"
    MCP_CODE_INDEX_BACKEND_URL: Optional[str] = None
    MCP_CODE_INDEX_SANDBOX_URL: Optional[str] = None

    MCP_DAEMON_AUTOSTART: bool = True
    MCP_DAEMON_LOG_DIR: str = "/tmp/deepaudit/mcp-daemons"
    GIT_MIRROR_ENABLED: bool = True
    GIT_MIRROR_PREFIX: str = "https://ghfast.top"
    GIT_MIRROR_HOSTS: str = "github.com"
    GIT_MIRROR_ALLOW_AUTH_URL: bool = False

    MCP_CODE_INDEX_DAEMON_HOST: str = "127.0.0.1"
    MCP_CODE_INDEX_DAEMON_PORT: int = 8765
    MCP_CODE_INDEX_DAEMON_COMMAND: str = "code-index-mcp"
    MCP_CODE_INDEX_DAEMON_ARGS: str = "--transport streamable-http"
    MCP_CODE_INDEX_DAEMON_INDEXER_PATH: str = "/app/data/mcp/code-index"
    MCP_CODE_INDEX_DAEMON_SOURCE_DIR: str = "/app/mcp-src/code-index-mcp"
    MCP_CODE_INDEX_DAEMON_STARTUP_TIMEOUT_SECONDS: int = 45

    MCP_SEQUENTIAL_THINKING_ENABLED: bool = True
    MCP_SEQUENTIAL_THINKING_RUNTIME_MODE: str = "backend_then_sandbox"
    MCP_SEQUENTIAL_THINKING_COMMAND: str = "pnpm"
    MCP_SEQUENTIAL_THINKING_ARGS: str = "dlx @modelcontextprotocol/server-sequential-thinking"
    MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED: bool = True
    MCP_SEQUENTIAL_THINKING_SANDBOX_COMMAND: str = "pnpm"
    MCP_SEQUENTIAL_THINKING_SANDBOX_ARGS: str = "dlx @modelcontextprotocol/server-sequential-thinking"
    MCP_SEQUENTIAL_THINKING_BACKEND_URL: Optional[str] = None
    MCP_SEQUENTIAL_THINKING_SANDBOX_URL: Optional[str] = None
    MCP_SEQUENTIAL_THINKING_DAEMON_HOST: str = "127.0.0.1"
    MCP_SEQUENTIAL_THINKING_DAEMON_PORT: int = 8771
    MCP_SEQUENTIAL_THINKING_DAEMON_COMMAND: str = "node"
    MCP_SEQUENTIAL_THINKING_DAEMON_ARGS: str = "dist/index.js --transport streamable-http --port 8771"
    MCP_SEQUENTIAL_THINKING_DAEMON_SOURCE_DIR: str = "/app/mcp-src/sequential-thinking"
    MCP_SEQUENTIAL_THINKING_DAEMON_STARTUP_TIMEOUT_SECONDS: int = 45

    MCP_QMD_ENABLED: bool = False
    MCP_QMD_RUNTIME_MODE: str = "sandbox_only"
    MCP_QMD_COMMAND: str = "qmd"
    MCP_QMD_ARGS: str = "mcp"
    MCP_QMD_SANDBOX_ENABLED: bool = False
    MCP_QMD_SANDBOX_COMMAND: str = "qmd"
    MCP_QMD_SANDBOX_ARGS: str = "mcp"
    MCP_QMD_BACKEND_URL: Optional[str] = None
    MCP_QMD_SANDBOX_URL: Optional[str] = None
    MCP_QMD_DAEMON_HOST: str = "localhost"
    MCP_QMD_DAEMON_PORT: int = 8181
    MCP_QMD_DAEMON_COMMAND: str = "node"
    MCP_QMD_DAEMON_ARGS: str = "dist/index.js mcp --transport streamable-http"
    MCP_QMD_DAEMON_SOURCE_DIR: str = "/app/mcp-src/qmd"
    MCP_QMD_DAEMON_STARTUP_TIMEOUT_SECONDS: int = 60
    QMD_COLLECTION_PREFIX: str = "project"
    QMD_INDEX_GLOB: str = "**/*.{c,cc,cpp,cxx,h,hpp,hh,py,js,ts,tsx,java,go,rs,php,rb,swift}"
    QMD_LAZY_INDEX_ENABLED: bool = True
    QMD_AUTO_EMBED_ON_FIRST_USE: bool = False
    QMD_DATA_DIR: str = "./data/qmd"
    QMD_CLI_COMMAND: str = "qmd"
    QMD_CLI_TIMEOUT_SECONDS: int = 120
    QMD_TASK_KB_ENABLED: bool = True
    QMD_TASK_ROOT_REL: str = ".deepaudit/qmd"
    QMD_TASK_COLLECTION_PREFIX: str = "task"
    QMD_TASK_DOC_GLOB: str = "**/*.{md,txt,json,yml,yaml}"
    QMD_TASK_AUTO_EMBED: bool = False
    QMD_TASK_QUERY_CACHE: bool = True
    XDG_CONFIG_HOME: str = "/app/data/mcp/xdg-config"

    MCP_CATALOG_SOURCE_URL: str = ""

    # PoC trigger chain (source -> sink) extraction (Joern preferred, LLM fallback)
    POC_TRIGGER_CHAIN_ENABLED: bool = True
    POC_TRIGGER_CHAIN_MAX_FLOWS: int = 3
    POC_TRIGGER_CHAIN_MAX_NODES: int = 80
    POC_TRIGGER_CHAIN_LLM_FALLBACK: bool = True

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"  # 忽略额外的环境变量（如 VITE_* 前端变量）


settings = Settings()
