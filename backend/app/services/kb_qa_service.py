"""KB QA service: multi-turn Q&A orchestration with feedback and auto-indexing."""
import json
import time
from app.extensions import db
from app.models.kb_session import KBSession, KBMessage
from app.models.ai_config import AIConfig
from app.services.logging_service import get_logger

logger = get_logger("ai")

# System prompt for multi-turn Q&A with RAG context
# NOTE: Literal braces in JSON examples are doubled ({{ }}) to escape str.format()
KBQA_SYSTEM_PROMPT = """你是一名知识库问答助手。以下是从知识库中检索到的相关内容（需求、模块、测试用例、业务代码、历史问答）。

请分析用户的问题：

1. 如果问题清晰且信息充分，直接基于知识库内容回答，返回 JSON：
   {{"type": "answer", "content": "你的回答"}}

2. 如果问题模糊或缺少关键信息，提出一个针对性的澄清问题，返回 JSON：
   {{"type": "clarification", "content": "你的追问"}}

3. 最多追问 3 轮，之后必须给出答案。

4. 回答要求：
   - 优先使用知识库中的内容，不要编造不存在的信息
   - 如果知识库内容不足以回答，请明确说明
   - 结构化输出，使用清晰的排版

{force_answer_instruction}
---
知识库内容：
{context}
---"""

FORCE_ANSWER_INSTRUCTION = "用户要求直接回答，请不要追问，基于已有信息给出最佳答案。"


class KBQAService:
    """Orchestrates multi-turn Q&A: RAG retrieval → AI analysis → clarification or answer → feedback → indexing."""

    def __init__(self, embedding_config, chat_config=None, user_id=None):
        self.config = embedding_config
        self.user_id = user_id
        self.embedding_service = None
        self.ai_service = None
        self._embedding_config = embedding_config
        self._chat_config = chat_config

    def _ensure_services(self):
        """Lazily initialize embedding and AI services (deferred to avoid import issues)."""
        if self.embedding_service is None:
            from app.services.embedding_service import EmbeddingService
            from app.services.ai_service import AIService
            self.embedding_service = EmbeddingService(self._embedding_config, user_id=self.user_id)
            self.ai_service = AIService(self._chat_config or self._embedding_config, user_id=self.user_id)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(self, user_id, title=None):
        """Create a new Q&A session. Returns KBSession."""
        session = KBSession(
            user_id=user_id,
            title=title or "新问答",
            status="active",
        )
        db.session.add(session)
        db.session.commit()
        logger.info("KB session created: id=%d user_id=%s title=%s", session.id, user_id, session.title)
        return session

    def list_sessions(self, user_id):
        """List Q&A sessions newest first, with linked sop_id.

        Guests pass user_id=None and see all users' sessions (global read-only);
        regular users only see their own.
        """
        query = KBSession.query
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        sessions = query.order_by(KBSession.updated_at.desc()).all()

        from app.models.sop import SOP
        sop_query = SOP.query
        if user_id is not None:
            sop_query = sop_query.filter_by(user_id=user_id)
        sop_map = {s.kb_session_id: s.id for s in sop_query.all() if s.kb_session_id}
        result = []
        for s in sessions:
            d = s.to_dict()
            d["sop_id"] = sop_map.get(s.id)
            result.append(d)
        return result

    def get_session(self, session_id, user_id=None):
        """Get a session with all messages. If user_id is given, verify ownership."""
        session = KBSession.query.get(session_id)
        if not session:
            return None
        if user_id is not None and session.user_id != user_id:
            return None
        d = session.to_dict(include_messages=True)
        # Attach linked SOP (if any) so the UI can show a "view SOP" entry
        from app.models.sop import SOP
        sop = SOP.query.filter_by(
            kb_session_id=session_id, user_id=session.user_id
        ).first()
        d["sop_id"] = sop.id if sop else None
        return d

    def delete_session(self, session_id, user_id):
        """Delete a session and all its messages."""
        session = KBSession.query.get(session_id)
        if not session or session.user_id != user_id:
            return False
        db.session.delete(session)
        db.session.commit()
        logger.info("KB session deleted: id=%d user_id=%s", session_id, user_id)
        return True

    # ------------------------------------------------------------------
    # Core: send message and get AI response (clarification or answer)
    # ------------------------------------------------------------------

    def send_message(self, session_id, content, force_answer=False):
        """Send a user message and get AI response.

        Flow:
        1. Save user message
        2. RAG retrieval for the latest question
        3. Build conversation history + system prompt with context
        4. Call AI (json_mode) → parse {"type": "clarification"|"answer", "content": "..."}
        5. Save assistant message
        6. If answer: update session status to "answered"

        Returns: {message_type, content, sources, round, session_status}
        """
        session = KBSession.query.get(session_id)
        if not session:
            raise ValueError("Session not found")

        # Determine current round
        current_round = max((m.round for m in session.messages), default=0) + 1

        # Save user message
        user_msg = KBMessage(
            session_id=session_id,
            role="user",
            content=content,
            message_type="question",
            round=current_round,
        )
        db.session.add(user_msg)
        db.session.commit()
        logger.debug("KB user message saved: session_id=%d round=%d len=%d", session_id, current_round, len(content))

        # RAG retrieval
        sources = []
        context = ""
        try:
            self._ensure_services()
            query_vector, dim = self.embedding_service.embed_query(content)
            results = self.embedding_service.search(query_vector, top_k=5, dim=dim)

            if results:
                context = self._build_context(results)
                sources = [
                    {
                        "chunk_type": r["chunk_type"],
                        "source_id": r["source_id"],
                        "text": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"],
                        "score": round(r["score"], 4),
                        "metadata": r.get("metadata", {}),
                    }
                    for r in results
                ]
                logger.debug("KB RAG retrieval: sources=%d top_score=%.4f", len(sources), sources[0]["score"] if sources else 0)
        except Exception as e:
            logger.warning("KB RAG retrieval failed, continuing without context: %s", str(e))

        # Build conversation history
        chat_messages = self._build_chat_messages(session, context, force_answer)

        # Call AI
        try:
            raw_response = self.ai_service.chat(
                chat_messages,
                json_mode=True,
                task_type="kb_qa",
            )
        except Exception as e:
            logger.error("KB AI call failed: session_id=%d error=%s", session_id, str(e))
            # Save error as answer to unblock user
            raw_response = json.dumps({"type": "answer", "content": f"AI 调用失败：{str(e)}"})

        # Parse AI response
        msg_type, msg_content = self._parse_response(raw_response)

        # Force answer if requested and AI tried to clarify
        if force_answer and msg_type == "clarification":
            # Re-call with stronger instruction
            chat_messages[-1]["content"] = content + "\n\n（请直接给出答案，不要再追问）"
            try:
                raw_response = self.ai_service.chat(chat_messages, json_mode=True, task_type="kb_qa")
                msg_type, msg_content = self._parse_response(raw_response)
            except Exception:
                pass

        # Save assistant message
        assistant_msg = KBMessage(
            session_id=session_id,
            role="assistant",
            content=msg_content,
            message_type=msg_type,
            round=current_round,
            sources_json=json.dumps(sources, ensure_ascii=False) if sources else None,
        )
        db.session.add(assistant_msg)

        # Update session status
        if msg_type == "answer":
            session.status = "answered"
        # Auto-derive title from first question if still default
        if session.title == "新问答" and current_round == 1:
            session.title = content[:30] + ("..." if len(content) > 30 else "")

        db.session.commit()
        logger.info("KB message exchange: session_id=%d round=%d type=%s", session_id, current_round, msg_type)

        return {
            "message_type": msg_type,
            "content": msg_content,
            "sources": sources,
            "round": current_round,
            "session_status": session.status,
            "message_id": assistant_msg.id,
        }

    # ------------------------------------------------------------------
    # Feedback and indexing
    # ------------------------------------------------------------------

    def submit_feedback(self, session_id, feedback, comment=None):
        """Submit feedback for a session and trigger indexing.

        positive → index as chunk_type="qa" (verified correct answer)
        negative → index as chunk_type="qa_negative" (incorrect answer reference)

        Returns: {indexed, chunk_type}
        """
        session = KBSession.query.get(session_id)
        if not session:
            raise ValueError("Session not found")

        session.feedback = feedback
        session.feedback_comment = comment
        session.status = "feedback_given"
        db.session.commit()
        logger.info("KB feedback: session_id=%d feedback=%s", session_id, feedback)

        # Index the session
        if feedback in ("positive", "negative"):
            chunk_type = "qa" if feedback == "positive" else "qa_negative"
            try:
                self._index_session(session, chunk_type)
                session.indexed = True
                db.session.commit()
                logger.info("KB session indexed: session_id=%d chunk_type=%s", session_id, chunk_type)
                return {"indexed": True, "chunk_type": chunk_type}
            except Exception as e:
                logger.error("KB session indexing failed: session_id=%d error=%s", session_id, str(e))
                return {"indexed": False, "error": str(e)}

        return {"indexed": False}

    def _index_session(self, session, chunk_type):
        """Embed the Q&A pair and store in Embedding table.

        Extracts all question-answer pairs from the session and creates
        one chunk per pair. Uses the chunk_type template to format text.
        """
        from app.models.embedding import Embedding as EmbeddingModel
        from app.services.embedding_service import EmbeddingService

        # Extract Q&A pairs (question messages with corresponding answer/clarification messages)
        messages = sorted(session.messages, key=lambda m: m.id)
        pairs = []
        current_q = None
        for msg in messages:
            if msg.role == "user":
                current_q = msg.content
            elif msg.role == "assistant" and current_q:
                # Only index the final answer, not intermediate clarifications
                if msg.message_type == "answer":
                    pairs.append((current_q, msg.content))
                current_q = None

        if not pairs:
            logger.warning("KB session has no Q&A pairs to index: session_id=%d", session.id)
            return 0

        # Build chunks
        chunks = []
        for q, a in pairs:
            template = EmbeddingService.CHUNK_TEMPLATES.get(chunk_type, EmbeddingService.CHUNK_TEMPLATES["qa"])
            text = template.format(question=q, answer=a)
            chunks.append({
                "chunk_type": chunk_type,
                "source_id": session.id,
                "requirement_id": 0,
                "module_id": None,
                "text": text,
                "metadata": {
                    "session_id": session.id,
                    "session_title": session.title,
                    "feedback": session.feedback,
                },
                "project_type": "production",
            })

        # Embed and store (use the embedding service)
        self._ensure_services()
        stored = self.embedding_service.embed_and_store_chunks(chunks)
        logger.info("KB session indexed: session_id=%d pairs=%d stored=%d chunk_type=%s",
                     session.id, len(pairs), stored, chunk_type)
        return stored

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_context(self, results):
        """Build context text from search results, including qa/code/qa_negative types."""
        parts = []
        type_labels = {
            "requirement": "需求",
            "module": "模块",
            "test_case": "测试用例",
            "qa": "历史问答（正确）",
            "qa_negative": "历史问答（错误参考）",
            "code": "业务代码",
            "sop": "SOP 文档",
        }

        for i, r in enumerate(results, 1):
            label = type_labels.get(r["chunk_type"], r["chunk_type"])
            metadata = r.get("metadata", {})
            meta_parts = []
            if "title" in metadata:
                meta_parts.append(f"标题：{metadata['title']}")
            if "file_name" in metadata:
                meta_parts.append(f"文件：{metadata['file_name']}")
            if "language" in metadata:
                meta_parts.append(f"语言：{metadata['language']}")
            if "session_title" in metadata:
                meta_parts.append(f"会话：{metadata['session_title']}")

            meta_str = f"（{', '.join(meta_parts)}）" if meta_parts else ""
            parts.append(f"[{i}] [{label}]{meta_str}\n{r['text']}")

        return "\n\n---\n\n".join(parts)

    def _build_chat_messages(self, session, context, force_answer):
        """Build chat messages: system prompt + conversation history + new question."""
        force_instruction = FORCE_ANSWER_INSTRUCTION if force_answer else ""
        system_content = KBQA_SYSTEM_PROMPT.format(
            context=context or "（知识库为空或检索失败）",
            force_answer_instruction=force_instruction,
        )

        chat_messages = [{"role": "system", "content": system_content}]

        # Add conversation history (all previous messages in this session)
        prev_messages = sorted(session.messages, key=lambda m: m.id)
        # Exclude the last user message (already saved, will be added as the "new" question)
        # Actually, the user message IS already saved in the session at this point.
        # We need to include all messages as history, and the last user message is the current question.
        for msg in prev_messages:
            if msg.role == "user":
                chat_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                chat_messages.append({"role": "assistant", "content": msg.content})

        # The last message in chat_messages should be the user's latest question
        # (it's already included since we saved it before building)
        return chat_messages

    def _parse_response(self, raw_response):
        """Parse AI JSON response. Returns (message_type, content).

        Expected format: {"type": "clarification"|"answer", "content": "..."}
        Falls back to treating the raw text as an answer if parsing fails.
        """
        try:
            data = json.loads(raw_response)
            msg_type = data.get("type", "answer")
            content = data.get("content", "")
            if msg_type not in ("clarification", "answer"):
                msg_type = "answer"
            if not content:
                content = raw_response
                msg_type = "answer"
            return msg_type, content
        except (json.JSONDecodeError, AttributeError):
            # If JSON parsing fails, treat the raw response as an answer
            logger.warning("KB AI response not valid JSON, treating as answer: %s", raw_response[:100])
            return "answer", raw_response
