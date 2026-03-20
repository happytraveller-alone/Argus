"""
代码检索器
支持语义检索和混合检索
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .embeddings import EmbeddingService
from .indexer import ChromaVectorStore, InMemoryVectorStore, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""

    chunk_id: str
    content: str
    file_path: str
    language: str
    chunk_type: str
    line_start: int
    line_end: int
    score: float  # 相似度分数 (0-1, 越高越相似)

    # 可选的元数据
    name: str | None = None
    parent_name: str | None = None
    signature: str | None = None
    security_indicators: list[str] = field(default_factory=list)

    # 🆕 块间链接（用于获取相邻代码上下文）
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None

    # 🆕 文件位置信息
    file_total_lines: int = 0
    file_total_chunks: int = 0
    chunk_index: int = 0

    # 原始元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def position_context(self) -> str:
        """生成位置描述，用于 LLM 理解代码在文件中的位置"""
        if self.file_total_lines > 0:
            return f"lines {self.line_start}-{self.line_end} of {self.file_total_lines}"
        return f"lines {self.line_start}-{self.line_end}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "file_path": self.file_path,
            "language": self.language,
            "chunk_type": self.chunk_type,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "score": self.score,
            "name": self.name,
            "parent_name": self.parent_name,
            "signature": self.signature,
            "security_indicators": self.security_indicators,
            # 🆕 块间链接信息
            "prev_chunk_id": self.prev_chunk_id,
            "next_chunk_id": self.next_chunk_id,
            "file_total_lines": self.file_total_lines,
            "file_total_chunks": self.file_total_chunks,
            "chunk_index": self.chunk_index,
            "position_context": self.position_context,
        }

    def to_context_string(self, include_metadata: bool = True) -> str:
        """转换为上下文字符串（用于 LLM 输入）"""
        parts = []

        if include_metadata:
            header = f"File: {self.file_path}"
            if self.line_start and self.line_end:
                header += f" (lines {self.line_start}-{self.line_end})"
            if self.name:
                header += f"\n{self.chunk_type.title()}: {self.name}"
            if self.parent_name:
                header += f" in {self.parent_name}"
            parts.append(header)

        parts.append(f"```{self.language}\n{self.content}\n```")

        return "\n".join(parts)


class CodeRetriever:
    """
    代码检索器
    支持语义检索、关键字检索和混合检索

     自动兼容不同维度的向量：
    - 查询时自动检测 collection 的 embedding 配置
    - 动态创建对应的 embedding 服务
    """

    def __init__(
        self,
        collection_name: str,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
        persist_directory: str | None = None,
        api_key: str | None = None,  #  新增：用于动态创建 embedding 服务
    ):
        """
        初始化检索器

        Args:
            collection_name: 向量集合名称
            embedding_service: 嵌入服务（可选，会根据 collection 配置自动创建）
            vector_store: 向量存储
            persist_directory: 持久化目录
            api_key: API Key（用于动态创建 embedding 服务）
        """
        self.collection_name = collection_name
        self._provided_embedding_service = embedding_service  # 用户提供的 embedding 服务
        self.embedding_service = embedding_service  # 实际使用的 embedding 服务
        self._api_key = api_key

        # 创建向量存储
        if vector_store:
            self.vector_store = vector_store
        else:
            try:
                self.vector_store = ChromaVectorStore(
                    collection_name=collection_name,
                    persist_directory=persist_directory,
                )
            except ImportError:
                logger.warning("Chroma not available, using in-memory store")
                self.vector_store = InMemoryVectorStore(collection_name=collection_name)

        self._initialized = False

    async def initialize(self):
        """初始化检索器，自动检测并适配 collection 的 embedding 配置"""
        if self._initialized:
            return

        await self.vector_store.initialize()

        #  自动检测 collection 的 embedding 配置
        if hasattr(self.vector_store, "get_embedding_config"):
            stored_config = self.vector_store.get_embedding_config()
            stored_provider = stored_config.get("provider")
            stored_model = stored_config.get("model")
            stored_dimension = stored_config.get("dimension")
            stored_base_url = stored_config.get("base_url")

            #  如果没有存储的配置（旧的 collection），尝试通过维度推断
            if not stored_provider or not stored_model:
                inferred = await self._infer_embedding_config_from_dimension()
                if inferred:
                    stored_provider = inferred.get("provider")
                    stored_model = inferred.get("model")
                    stored_dimension = inferred.get("dimension")
                    logger.info(
                        f"📊 从向量维度推断 embedding 配置: {stored_provider}/{stored_model}"
                    )

            if stored_provider and stored_model:
                # 检查是否需要使用不同的 embedding 服务
                current_provider = (
                    getattr(self.embedding_service, "provider", None)
                    if self.embedding_service
                    else None
                )
                current_model = (
                    getattr(self.embedding_service, "model", None)
                    if self.embedding_service
                    else None
                )

                if current_provider != stored_provider or current_model != stored_model:
                    logger.info(
                        f"🔄 Collection 使用的 embedding 配置与当前不同: "
                        f"{stored_provider}/{stored_model} (维度: {stored_dimension}) vs "
                        f"{current_provider}/{current_model}"
                    )
                    logger.info("🔄 自动切换到 collection 的 embedding 配置")

                    # 动态创建对应的 embedding 服务
                    api_key = self._api_key
                    if not api_key and self._provided_embedding_service:
                        api_key = getattr(self._provided_embedding_service, "api_key", None)

                    self.embedding_service = EmbeddingService(
                        provider=stored_provider,
                        model=stored_model,
                        api_key=api_key,
                        base_url=stored_base_url,
                    )
                    logger.info(f"已切换到: {stored_provider}/{stored_model}")

        # 如果仍然没有 embedding 服务，创建默认的
        if not self.embedding_service:
            self.embedding_service = EmbeddingService()

        self._initialized = True

    async def _infer_embedding_config_from_dimension(self) -> dict[str, Any] | None:
        """
         从向量维度推断 embedding 配置（用于处理旧的 collection）

        Returns:
            推断的 embedding 配置，如果无法推断则返回 None
        """
        try:
            # 获取一个样本向量来检查维度
            if hasattr(self.vector_store, "_collection") and self.vector_store._collection:
                count = await self.vector_store.get_count()
                if count > 0:
                    sample = await asyncio.to_thread(self.vector_store._collection.peek, limit=1)
                    embeddings = sample.get("embeddings")
                    if embeddings is not None and len(embeddings) > 0:
                        dim = len(embeddings[0])

                        #  根据维度推断模型（优先选择常用模型）
                        dimension_mapping = {
                            # OpenAI 系列
                            1536: {
                                "provider": "openai",
                                "model": "text-embedding-3-small",
                                "dimension": 1536,
                            },
                            3072: {
                                "provider": "openai",
                                "model": "text-embedding-3-large",
                                "dimension": 3072,
                            },
                            # HuggingFace 系列
                            1024: {
                                "provider": "huggingface",
                                "model": "BAAI/bge-m3",
                                "dimension": 1024,
                            },
                            384: {
                                "provider": "huggingface",
                                "model": "sentence-transformers/all-MiniLM-L6-v2",
                                "dimension": 384,
                            },
                            # Ollama 系列
                            768: {
                                "provider": "ollama",
                                "model": "nomic-embed-text",
                                "dimension": 768,
                            },
                            # Jina 系列
                            512: {
                                "provider": "jina",
                                "model": "jina-embeddings-v2-small-en",
                                "dimension": 512,
                            },
                            # Cohere 系列
                            # 1024 已被 HuggingFace 占用，Cohere 维度相同时会默认使用 HuggingFace
                        }

                        inferred = dimension_mapping.get(dim)
                        if inferred:
                            logger.info(
                                f"📊 检测到向量维度 {dim}，推断为: {inferred['provider']}/{inferred['model']}"
                            )
                        return inferred
        except Exception as e:
            logger.warning(f"无法推断 embedding 配置: {e}")

        return None

    def get_collection_embedding_config(self) -> dict[str, Any]:
        """
        获取 collection 存储的 embedding 配置

        Returns:
            包含 provider, model, dimension, base_url 的字典
        """
        if hasattr(self.vector_store, "get_embedding_config"):
            return self.vector_store.get_embedding_config()
        return {}

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filter_file_path: str | None = None,
        filter_language: str | None = None,
        filter_chunk_type: str | None = None,
        min_score: float = 0.0,
    ) -> list[RetrievalResult]:
        """
        语义检索

        Args:
            query: 查询文本
            top_k: 返回数量
            filter_file_path: 文件路径过滤
            filter_language: 语言过滤
            filter_chunk_type: 块类型过滤
            min_score: 最小相似度分数

        Returns:
            检索结果列表
        """
        await self.initialize()

        # 生成查询嵌入
        query_embedding = await self.embedding_service.embed(query)

        # 构建过滤条件
        where = {}
        if filter_file_path:
            where["file_path"] = filter_file_path
        if filter_language:
            where["language"] = filter_language
        if filter_chunk_type:
            where["chunk_type"] = filter_chunk_type

        # 查询向量存储
        raw_results = await self.vector_store.query(
            query_embedding=query_embedding,
            n_results=top_k * 2,  # 多查一些，后面过滤
            where=where if where else None,
        )

        # 转换结果
        results = []
        for _i, (id_, doc, meta, dist) in enumerate(
            zip(
                raw_results["ids"],
                raw_results["documents"],
                raw_results["metadatas"],
                raw_results["distances"],
                strict=False,
            )
        ):
            # 将距离转换为相似度分数 (余弦距离)
            score = 1 - dist

            if score < min_score:
                continue

            # 解析安全指标（可能是 JSON 字符串）
            security_indicators = meta.get("security_indicators", [])
            if isinstance(security_indicators, str):
                try:
                    import json

                    security_indicators = json.loads(security_indicators)
                except (json.JSONDecodeError, ValueError):
                    security_indicators = []

            result = RetrievalResult(
                chunk_id=id_,
                content=doc,
                file_path=meta.get("file_path", ""),
                language=meta.get("language", "text"),
                chunk_type=meta.get("chunk_type", "unknown"),
                line_start=meta.get("line_start", 0),
                line_end=meta.get("line_end", 0),
                score=score,
                name=meta.get("name"),
                parent_name=meta.get("parent_name"),
                signature=meta.get("signature"),
                security_indicators=security_indicators,
                # 🆕 块间链接信息
                prev_chunk_id=meta.get("prev_chunk_id"),
                next_chunk_id=meta.get("next_chunk_id"),
                file_total_lines=meta.get("file_total_lines", 0),
                file_total_chunks=meta.get("file_total_chunks", 0),
                chunk_index=meta.get("chunk_index", 0),
                metadata=meta,
            )
            results.append(result)

        # 按分数排序并截取
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def retrieve_by_file(
        self,
        file_path: str,
        top_k: int = 50,
    ) -> list[RetrievalResult]:
        """
        按文件路径检索

        Args:
            file_path: 文件路径
            top_k: 返回数量

        Returns:
            该文件的所有代码块
        """
        await self.initialize()

        # 使用一个通用查询
        query_embedding = await self.embedding_service.embed(f"code in {file_path}")

        raw_results = await self.vector_store.query(
            query_embedding=query_embedding,
            n_results=top_k,
            where={"file_path": file_path},
        )

        results = []
        for id_, doc, meta, dist in zip(
            raw_results["ids"],
            raw_results["documents"],
            raw_results["metadatas"],
            raw_results["distances"],
            strict=False,
        ):
            result = RetrievalResult(
                chunk_id=id_,
                content=doc,
                file_path=meta.get("file_path", ""),
                language=meta.get("language", "text"),
                chunk_type=meta.get("chunk_type", "unknown"),
                line_start=meta.get("line_start", 0),
                line_end=meta.get("line_end", 0),
                score=1 - dist,
                name=meta.get("name"),
                parent_name=meta.get("parent_name"),
                # 🆕 块间链接信息
                prev_chunk_id=meta.get("prev_chunk_id"),
                next_chunk_id=meta.get("next_chunk_id"),
                file_total_lines=meta.get("file_total_lines", 0),
                file_total_chunks=meta.get("file_total_chunks", 0),
                chunk_index=meta.get("chunk_index", 0),
                metadata=meta,
            )
            results.append(result)

        # 按行号排序
        results.sort(key=lambda x: x.line_start)
        return results

    async def retrieve_security_related(
        self,
        vulnerability_type: str | None = None,
        top_k: int = 20,
    ) -> list[RetrievalResult]:
        """
        检索与安全相关的代码

        Args:
            vulnerability_type: 漏洞类型（如 sql_injection, xss 等）
            top_k: 返回数量

        Returns:
            安全相关的代码块
        """
        # 根据漏洞类型构建查询
        security_queries = {
            "sql_injection": "SQL query execute database user input",
            "xss": "HTML render user input innerHTML template",
            "command_injection": "system exec command shell subprocess",
            "path_traversal": "file path read open user input",
            "ssrf": "HTTP request URL user input fetch",
            "deserialization": "deserialize pickle yaml load object",
            "auth_bypass": "authentication login password token session",
            "hardcoded_secret": "password secret key token credential",
        }

        if vulnerability_type and vulnerability_type in security_queries:
            query = security_queries[vulnerability_type]
        else:
            query = "security vulnerability dangerous function user input"

        return await self.retrieve(query, top_k=top_k)

    async def retrieve_function_context(
        self,
        function_name: str,
        file_path: str | None = None,
        include_callers: bool = True,
        include_callees: bool = True,
        top_k: int = 10,
    ) -> dict[str, list[RetrievalResult]]:
        """
        检索函数上下文

        Args:
            function_name: 函数名
            file_path: 文件路径（可选）
            include_callers: 是否包含调用者
            include_callees: 是否包含被调用者
            top_k: 每类返回数量

        Returns:
            包含函数定义、调用者、被调用者的字典
        """
        context = {
            "definition": [],
            "callers": [],
            "callees": [],
        }

        # 查找函数定义
        definition_query = f"function definition {function_name}"
        definitions = await self.retrieve(
            definition_query,
            top_k=5,
            filter_file_path=file_path,
        )

        # 过滤出真正的定义
        for result in definitions:
            if result.name == function_name or function_name in (result.content or ""):
                context["definition"].append(result)

        if include_callers:
            # 查找调用此函数的代码
            caller_query = f"calls {function_name} invoke {function_name}"
            callers = await self.retrieve(caller_query, top_k=top_k)

            for result in callers:
                # 检查是否真的调用了这个函数
                if re.search(rf"\b{re.escape(function_name)}\s*\(", result.content):
                    if result not in context["definition"]:
                        context["callers"].append(result)

        if include_callees and context["definition"]:
            # 从函数定义中提取调用的其他函数
            for definition in context["definition"]:
                calls = re.findall(r"\b(\w+)\s*\(", definition.content)
                unique_calls = list(set(calls))[:5]  # 限制数量

                for call in unique_calls:
                    if call == function_name:
                        continue
                    callees = await self.retrieve(
                        f"function {call} definition",
                        top_k=2,
                    )
                    context["callees"].extend(callees)

        return context

    async def retrieve_similar_code(
        self,
        code_snippet: str,
        top_k: int = 5,
        exclude_file: str | None = None,
    ) -> list[RetrievalResult]:
        """
        检索相似的代码

        Args:
            code_snippet: 代码片段
            top_k: 返回数量
            exclude_file: 排除的文件

        Returns:
            相似代码列表
        """
        results = await self.retrieve(
            f"similar code: {code_snippet}",
            top_k=top_k * 2,
        )

        if exclude_file:
            results = [r for r in results if r.file_path != exclude_file]

        return results[:top_k]

    async def hybrid_retrieve(
        self,
        query: str,
        keywords: list[str] | None = None,
        top_k: int = 10,
        semantic_weight: float = 0.7,
    ) -> list[RetrievalResult]:
        """
        混合检索（语义 + 关键字）

        Args:
            query: 查询文本
            keywords: 额外的关键字
            top_k: 返回数量
            semantic_weight: 语义检索权重

        Returns:
            检索结果列表
        """
        # 语义检索
        semantic_results = await self.retrieve(query, top_k=top_k * 2)

        # 如果有关键字，进行关键字过滤/增强
        if keywords:
            keyword_pattern = "|".join(re.escape(kw) for kw in keywords)

            enhanced_results = []
            for result in semantic_results:
                # 计算关键字匹配度
                matches = len(re.findall(keyword_pattern, result.content, re.IGNORECASE))
                keyword_score = min(1.0, matches / len(keywords))

                # 混合分数
                hybrid_score = (
                    semantic_weight * result.score + (1 - semantic_weight) * keyword_score
                )

                result.score = hybrid_score
                enhanced_results.append(result)

            enhanced_results.sort(key=lambda x: x.score, reverse=True)
            return enhanced_results[:top_k]

        return semantic_results[:top_k]

    def format_results_for_llm(
        self,
        results: list[RetrievalResult],
        max_tokens: int = 4000,
        include_metadata: bool = True,
    ) -> str:
        """
        将检索结果格式化为 LLM 输入

        Args:
            results: 检索结果
            max_tokens: 最大 Token 数
            include_metadata: 是否包含元数据

        Returns:
            格式化的字符串
        """
        if not results:
            return "No relevant code found."

        parts = []
        total_tokens = 0

        for i, result in enumerate(results):
            context = result.to_context_string(include_metadata=include_metadata)
            estimated_tokens = len(context) // 4

            if total_tokens + estimated_tokens > max_tokens:
                break

            parts.append(f"### Code Block {i + 1} (Score: {result.score:.2f})\n{context}")
            total_tokens += estimated_tokens

        return "\n\n".join(parts)

    async def get_chunk_by_id(self, chunk_id: str) -> RetrievalResult | None:
        """
        通过 chunk_id 获取单个代码块

        Args:
            chunk_id: 代码块 ID

        Returns:
            代码块，如果不存在则返回 None
        """
        await self.initialize()

        try:
            if hasattr(self.vector_store, "_collection") and self.vector_store._collection:
                result = await asyncio.to_thread(
                    self.vector_store._collection.get,
                    ids=[chunk_id],
                    include=["documents", "metadatas"],
                )

                if result and result.get("ids") and result["ids"][0]:
                    doc = result["documents"][0] if result.get("documents") else ""
                    meta = result["metadatas"][0] if result.get("metadatas") else {}

                    # 解析安全指标
                    security_indicators = meta.get("security_indicators", [])
                    if isinstance(security_indicators, str):
                        try:
                            import json

                            security_indicators = json.loads(security_indicators)
                        except (json.JSONDecodeError, ValueError):
                            security_indicators = []

                    return RetrievalResult(
                        chunk_id=chunk_id,
                        content=doc,
                        file_path=meta.get("file_path", ""),
                        language=meta.get("language", "text"),
                        chunk_type=meta.get("chunk_type", "unknown"),
                        line_start=meta.get("line_start", 0),
                        line_end=meta.get("line_end", 0),
                        score=1.0,  # 直接获取，分数为 1
                        name=meta.get("name"),
                        parent_name=meta.get("parent_name"),
                        signature=meta.get("signature"),
                        security_indicators=security_indicators,
                        prev_chunk_id=meta.get("prev_chunk_id"),
                        next_chunk_id=meta.get("next_chunk_id"),
                        file_total_lines=meta.get("file_total_lines", 0),
                        file_total_chunks=meta.get("file_total_chunks", 0),
                        chunk_index=meta.get("chunk_index", 0),
                        metadata=meta,
                    )
        except Exception as e:
            logger.warning(f"获取代码块失败 {chunk_id}: {e}")

        return None

    async def get_neighbor_chunks(
        self,
        chunk_id: str,
        prev_count: int = 1,
        next_count: int = 1,
    ) -> dict[str, list[RetrievalResult]]:
        """
        获取相邻的代码块（解决"代码跳着读"的问题）

        Args:
            chunk_id: 当前代码块 ID
            prev_count: 获取前几个 chunk
            next_count: 获取后几个 chunk

        Returns:
            {"prev": [...], "current": ..., "next": [...]}
        """
        await self.initialize()

        result = {
            "prev": [],
            "current": None,
            "next": [],
        }

        # 获取当前 chunk
        current = await self.get_chunk_by_id(chunk_id)
        if not current:
            return result

        result["current"] = current

        # 获取前面的 chunks
        if prev_count > 0 and current.prev_chunk_id:
            prev_id = current.prev_chunk_id
            for _ in range(prev_count):
                if not prev_id:
                    break
                prev_chunk = await self.get_chunk_by_id(prev_id)
                if prev_chunk:
                    result["prev"].insert(0, prev_chunk)  # 插入到开头，保持顺序
                    prev_id = prev_chunk.prev_chunk_id
                else:
                    break

        # 获取后面的 chunks
        if next_count > 0 and current.next_chunk_id:
            next_id = current.next_chunk_id
            for _ in range(next_count):
                if not next_id:
                    break
                next_chunk = await self.get_chunk_by_id(next_id)
                if next_chunk:
                    result["next"].append(next_chunk)
                    next_id = next_chunk.next_chunk_id
                else:
                    break

        return result

    async def retrieve_with_context(
        self,
        query: str,
        top_k: int = 5,
        context_chunks: int = 1,
        **kwargs,
    ) -> list[RetrievalResult]:
        """
        语义检索并自动获取相邻上下文

        Args:
            query: 查询文本
            top_k: 返回的主要结果数量
            context_chunks: 每个结果前后获取几个相邻 chunk
            **kwargs: 传递给 retrieve 的其他参数

        Returns:
            包含上下文的检索结果列表（去重后）
        """
        # 先进行语义检索
        main_results = await self.retrieve(query, top_k=top_k, **kwargs)

        if context_chunks <= 0:
            return main_results

        # 为每个结果获取上下文
        all_results: dict[str, RetrievalResult] = {}

        for main_result in main_results:
            # 添加主结果
            all_results[main_result.chunk_id] = main_result

            # 获取相邻块
            neighbors = await self.get_neighbor_chunks(
                main_result.chunk_id,
                prev_count=context_chunks,
                next_count=context_chunks,
            )

            # 添加前面的块
            for prev_chunk in neighbors.get("prev", []):
                if prev_chunk.chunk_id not in all_results:
                    prev_chunk.score = main_result.score * 0.8  # 稍微降低分数
                    all_results[prev_chunk.chunk_id] = prev_chunk

            # 添加后面的块
            for next_chunk in neighbors.get("next", []):
                if next_chunk.chunk_id not in all_results:
                    next_chunk.score = main_result.score * 0.8  # 稍微降低分数
                    all_results[next_chunk.chunk_id] = next_chunk

        # 按文件路径和行号排序，保证代码的连贯性
        sorted_results = sorted(all_results.values(), key=lambda x: (x.file_path, x.line_start))

        return sorted_results

    def format_results_with_context(
        self,
        results: list[RetrievalResult],
        max_tokens: int = 8000,
        include_position: bool = True,
    ) -> str:
        """
        将带有上下文的检索结果格式化为 LLM 输入
        按 file_path + line_start 排序后，合并相邻的代码块

        Args:
            results: 检索结果（应该已按 file_path, line_start 排序）
            max_tokens: 最大 Token 数
            include_position: 是否包含位置信息

        Returns:
            格式化的字符串
        """
        if not results:
            return "No relevant code found."

        # 按文件分组
        files: dict[str, list[RetrievalResult]] = {}
        for r in results:
            if r.file_path not in files:
                files[r.file_path] = []
            files[r.file_path].append(r)

        parts = []

        for file_path, file_chunks in files.items():
            # 再次按行号排序
            file_chunks.sort(key=lambda x: x.line_start)

            # 构建文件头
            header = f"File: {file_path}"
            if include_position and file_chunks:
                first = file_chunks[0]
                last = file_chunks[-1]
                header += f" (lines {first.line_start}-{last.line_end}"
                if first.file_total_lines > 0:
                    header += f" of {first.file_total_lines}"
                header += ")"
            parts.append(header)

            # 合并相邻的代码块（避免重复内容）
            merged_content = []
            for chunk in file_chunks:
                # 检查是否与上一个块重叠
                if merged_content:
                    last_chunk = merged_content[-1]
                    if chunk.line_start <= last_chunk.line_end:
                        # 有重叠，需要截取非重叠部分
                        overlap_lines = last_chunk.line_end - chunk.line_start + 1
                        if overlap_lines > 0:
                            lines = chunk.content.split("\n")
                            non_overlap = "\n".join(lines[overlap_lines:])
                            if non_overlap:
                                last_chunk.content += "\n" + non_overlap
                                last_chunk.line_end = chunk.line_end
                            continue
                merged_content.append(chunk)

            # 添加合并后的代码
            for chunk in merged_content:
                code_block = f"```{chunk.language}\n{chunk.content}\n```"
                parts.append(code_block)

            parts.append("")  # 文件间空行

            # 检查 token 限制
            estimated = sum(len(p) // 4 for p in parts)
            if estimated > max_tokens:
                break

        return "\n".join(parts)
