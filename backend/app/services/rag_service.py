"""RAG service: orchestrate retrieval, context building, and answer generation."""
import time
from app.services.embedding_service import EmbeddingService
from app.services.ai_service import AIService
from app.services.logging_service import get_logger

logger = get_logger("ai")

# System prompt for RAG answer generation
RAG_SYSTEM_PROMPT = """你是一名专业的测试工程师和需求分析专家。

以下是从知识库中检索到的相关内容，包括需求、功能模块和测试用例。
请基于这些内容回答用户的问题。回答要求：
1. 优先使用知识库中的内容，不要编造不存在的信息
2. 如果知识库内容不足以回答问题，请明确说明
3. 结构化输出，使用清晰的排版（列表、代码块等）
4. 如果涉及测试用例，请标注用例的标题和类型

---
知识库内容：
{context}
---"""

RAG_QUERY_PROMPT = """用户问题：{question}

请基于上方知识库内容回答。"""


class RAGService:
    """Orchestrates the RAG pipeline: embed query -> search -> build context -> generate answer."""

    def __init__(self, embedding_config, chat_config=None, user_id=None):
        """Initialize with separate configs for embedding and chat.

        Args:
            embedding_config: AIConfig for embedding operations (must have embedding_model).
            chat_config: AIConfig for chat/answer generation. If None, falls back to embedding_config.
            user_id: Current user ID for call logging.
        """
        self.config = embedding_config
        self.user_id = user_id
        self.embedding_service = EmbeddingService(embedding_config, user_id=user_id)
        self.ai_service = AIService(chat_config or embedding_config, user_id=user_id)

    def query(self, question, top_k=5):
        """Execute a RAG query.

        1. Embed the question
        2. Search for Top-K similar chunks
        3. Build context text from results
        4. Call Chat API to generate answer

        Returns: {answer, sources, tokens_used, search_time_ms}
        """
        start_time = time.time()

        # Step 1: Embed the query
        logger.debug("RAG query: question_len=%d top_k=%d", len(question), top_k)
        query_vector, dim = self.embedding_service.embed_query(question)
        embed_time = time.time() - start_time

        # Step 2: Search for similar chunks
        search_start = time.time()
        results = self.embedding_service.search(query_vector, top_k=top_k, dim=dim)
        search_time = time.time() - search_start

        if not results:
            logger.warning("RAG query: no results found in knowledge base")
            return {
                "answer": "知识库为空，请先构建知识库索引。",
                "sources": [],
                "tokens_used": 0,
                "search_time_ms": int(search_time * 1000),
                "embed_time_ms": int(embed_time * 1000),
            }

        # Step 3: Build context text
        context = self._build_context(results)

        # Step 4: Generate answer via Chat API
        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT.format(context=context)},
            {"role": "user", "content": RAG_QUERY_PROMPT.format(question=question)},
        ]

        chat_start = time.time()
        answer = self.ai_service.chat(messages, task_type="rag_query")
        chat_time = time.time() - chat_start

        # Format sources for response
        sources = []
        for r in results:
            sources.append({
                "chunk_type": r["chunk_type"],
                "source_id": r["source_id"],
                "requirement_id": r["requirement_id"],
                "text": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"],
                "score": round(r["score"], 4),
                "metadata": r.get("metadata", {}),
            })

        total_time = time.time() - start_time
        logger.info(
            "RAG complete: sources=%d embed=%dms search=%dms chat=%dms total=%dms",
            len(sources),
            int(embed_time * 1000),
            int(search_time * 1000),
            int(chat_time * 1000),
            int(total_time * 1000),
        )

        return {
            "answer": answer,
            "sources": sources,
            "search_time_ms": int(search_time * 1000),
            "embed_time_ms": int(embed_time * 1000),
        }

    def rebuild(self, project_type=None):
        """Rebuild the knowledge base index.

        Args:
            project_type: If specified (e.g. "production"), only index that project type.
                         If None, index all data (both production and test).

        Clears existing embeddings for the specified project_type (or all if None),
        chunks data, embeds, stores.
        Returns: {status, chunk_count, dim}
        """
        logger.info("RAG rebuild: starting index rebuild (project_type=%s)", project_type)
        start_time = time.time()

        chunk_count, dim = self.embedding_service.build_index(project_type=project_type)
        elapsed = time.time() - start_time

        logger.info(
            "RAG rebuild complete: chunks=%d dim=%d elapsed=%.1fs project_type=%s",
            chunk_count, dim, elapsed, project_type,
        )
        return {
            "status": "success",
            "chunk_count": chunk_count,
            "dim": dim,
            "elapsed_ms": int(elapsed * 1000),
            "project_type": project_type,
        }

    def _build_context(self, results):
        """Build context text from search results.

        Each result is formatted with a type label and content.
        Supports all chunk types including qa, qa_negative, and code.
        """
        parts = []
        type_labels = {
            "requirement": "需求",
            "module": "模块",
            "test_case": "测试用例",
            "qa": "历史问答（正确）",
            "qa_negative": "历史问答（错误参考）",
            "code": "业务代码",
        }

        for i, r in enumerate(results, 1):
            type_label = type_labels.get(r["chunk_type"], r["chunk_type"])

            metadata = r.get("metadata", {})
            meta_parts = []
            if "title" in metadata:
                meta_parts.append(f"标题：{metadata['title']}")
            if "priority" in metadata:
                meta_parts.append(f"优先级：{metadata['priority']}")
            if "case_type" in metadata:
                meta_parts.append(f"类型：{metadata['case_type']}")
            if "module_name" in metadata:
                meta_parts.append(f"模块：{metadata['module_name']}")

            meta_str = f"（{', '.join(meta_parts)}）" if meta_parts else ""
            parts.append(f"[{i}] [{type_label}]{meta_str}\n{r['text']}")

        return "\n\n---\n\n".join(parts)
