"""SOP service: template management and AI-based SOP generation."""
import json
from app.extensions import db
from app.models.sop import SOP, SopTemplate
from app.models.kb_session import KBSession
from app.services.logging_service import get_logger

logger = get_logger("ai")

# Built-in default SOP format template (plain text / txt). This seeds the DB on
# first run and serves as the fallback when no template row exists. It is also
# what the administrator can edit on the settings page.
DEFAULT_SOP_TEMPLATE = """请按以下纯文本（txt）格式组织输出，不要使用任何 Markdown 语法（如 #、**、-、``` 等）：

标题：<SOP 标题>

一、背景与目的
（说明本操作要解决的问题、目标与适用场景）

二、适用范围
（说明本 SOP 适用的角色、系统或业务范围）

三、前置条件
（列出执行前需要满足的条件、权限、数据或环境准备）

四、操作步骤
1. （具体操作步骤，按顺序编号）
2. （具体操作步骤）

五、注意事项
（列出执行过程中需要特别留意的风险点、常见错误与规避方法）

六、验收标准
（说明操作完成后如何判断结果正确）"""

# Marker for the legacy Markdown default template, used to auto-upgrade
# untouched templates to the plain-text default.
LEGACY_MD_TEMPLATE_MARKER = "请按以下标准操作程序（SOP）格式组织输出，Markdown 格式"


class SOPService:
    """Handles SOP template management and AI-driven SOP generation."""

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------

    def get_template(self):
        """Return the current SOP template content, falling back to the default."""
        template = SopTemplate.query.first()
        return template.content if template else DEFAULT_SOP_TEMPLATE

    def update_template(self, content, user_id):
        """Create or update the single-row template record."""
        content = (content or "").strip()
        if not content:
            raise ValueError("模板内容不能为空")

        template = SopTemplate.query.first()
        if not template:
            template = SopTemplate(id=1, content=content, updated_by=user_id)
            db.session.add(template)
        else:
            template.content = content
            template.updated_by = user_id
        db.session.commit()
        logger.info("SOP template updated: user_id=%s", user_id)
        return template.to_dict()

    def reset_template(self, user_id):
        """Reset the template to the built-in default."""
        return self.update_template(DEFAULT_SOP_TEMPLATE, user_id)

    # ------------------------------------------------------------------
    # SOP queries
    # ------------------------------------------------------------------

    def list_sops(self, user_id):
        """List all SOPs for a user, newest first, with indexed flag."""
        sops = SOP.query.filter_by(user_id=user_id).order_by(SOP.created_at.desc()).all()
        return [self._to_dict_with_indexed(s) for s in sops]

    def get_sop_dict(self, sop_id, user_id):
        """Return a single SOP dict (ownership-checked) with indexed flag."""
        sop = SOP.query.get(sop_id)
        if not sop or sop.user_id != user_id:
            return None
        return self._to_dict_with_indexed(sop)

    def get_session_sop(self, session_id, user_id):
        """Return the SOP linked to a Q&A session (if any)."""
        sop = SOP.query.filter_by(kb_session_id=session_id, user_id=user_id).first()
        return self._to_dict_with_indexed(sop) if sop else None

    def is_indexed(self, sop_id):
        """Whether a SOP has been indexed into the knowledge base."""
        from app.models.embedding import Embedding
        return (
            Embedding.query.filter_by(chunk_type="sop", source_id=sop_id).first()
            is not None
        )

    def _to_dict_with_indexed(self, sop):
        d = sop.to_dict()
        d["indexed"] = self.is_indexed(sop.id)
        return d

    # ------------------------------------------------------------------
    # SOP generation
    # ------------------------------------------------------------------

    def generate_from_session(self, session_id, user_id, message_id=None):
        """Generate a SOP from a Q&A session's answer and persist it.

        Idempotency is per session: one SOP per Q&A session. message_id, if
        provided, is recorded as the source answer message for traceability.
        """
        session = KBSession.query.get(session_id)
        if not session or session.user_id != user_id:
            raise ValueError("Session not found")

        # Idempotency: one SOP per session
        existing = SOP.query.filter_by(kb_session_id=session_id, user_id=user_id).first()
        if existing:
            logger.info("SOP already exists for session_id=%s, returning existing id=%d", session_id, existing.id)
            return self._to_dict_with_indexed(existing)

        # Assemble conversation context
        messages = sorted(session.messages, key=lambda m: m.id)
        context_parts = []
        first_question = None
        for msg in messages:
            if msg.role == "user":
                if first_question is None:
                    first_question = msg.content
                context_parts.append(f"【用户提问】{msg.content}")
            elif msg.role == "assistant":
                label = "追问" if msg.message_type == "clarification" else "回答"
                context_parts.append(f"【{label}】{msg.content}")
        context_text = "\n\n".join(context_parts)

        if not context_text.strip():
            raise ValueError("会话内容为空，无法生成 SOP")

        template = self.get_template()

        system_prompt = (
            "你是一名标准操作程序（SOP）撰写助手。"
            "请根据下方提供的问答内容，严格按照给定模板格式，将解答总结成一份清晰、可执行、可直接落地执行的 SOP。\n"
            "要求：\n"
            "1. 只输出一个 JSON 对象，格式为 {\"title\": \"...\", \"content\": \"...\"}；\n"
            "2. title 为简短的 SOP 标题（不超过 30 字）；\n"
            "3. content 为纯文本，使用「一、二、三…」章节标题和数字编号步骤组织，"
            "禁止使用任何 Markdown 语法（如 #、**、```、- 等）；"
            "必须包含模板中规定的所有章节，并根据问答内容填充具体信息；\n"
            "4. 不要编造问答中不存在的信息；若某章节信息不足，请根据常识合理补充并标注。\n\n"
            "【SOP 格式模板】\n"
            f"{template}"
        )

        chat_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"【问答内容】\n{context_text}"},
        ]

        from app.services.ai_service import AIService
        from app.models.ai_config import AIConfig
        chat_config = AIConfig.get_default_chat_config()
        if not chat_config:
            raise ValueError("No default chat model configuration found. Please configure a chat model first.")

        ai_service = AIService(chat_config, user_id=user_id)
        try:
            raw_response = ai_service.chat(chat_messages, json_mode=True, task_type="sop_generate")
        except Exception as e:
            logger.error("SOP AI call failed: session_id=%d error=%s", session_id, str(e))
            raise RuntimeError(f"AI 生成 SOP 失败：{str(e)}")

        title, content = self._parse_response(raw_response, first_question, context_text)

        sop = SOP(
            user_id=user_id,
            title=title,
            content=content,
            kb_session_id=session_id,
            kb_message_id=message_id,
        )
        db.session.add(sop)
        db.session.commit()
        logger.info("SOP generated: id=%d session_id=%d message_id=%s title=%s", sop.id, session_id, message_id, title)
        return self._to_dict_with_indexed(sop)

    def _parse_response(self, raw_response, first_question, context_text):
        """Parse AI JSON response into (title, content) with graceful fallback."""
        try:
            data = json.loads(raw_response)
            title = (data.get("title") or "").strip()
            content = (data.get("content") or "").strip()
            if not title and not content:
                raise ValueError("empty")
        except (json.JSONDecodeError, AttributeError, ValueError):
            logger.warning("SOP AI response not valid JSON, falling back: %s", str(raw_response)[:100])
            title = ""
            content = raw_response

        if not title:
            title = (first_question or "SOP").strip()
            if len(title) > 30:
                title = title[:30] + "..."
        if not content:
            content = context_text

        return title, content

    # ------------------------------------------------------------------
    # Index SOP into the knowledge base (RAG)
    # ------------------------------------------------------------------

    def index_to_kb(self, sop_id, user_id):
        """Embed a SOP and store it in the embeddings table (chunk_type='sop').

        Re-indexing is safe: existing 'sop' chunks for this SOP are removed
        before inserting.
        """
        sop = SOP.query.get(sop_id)
        if not sop or sop.user_id != user_id:
            raise ValueError("SOP not found")

        from app.models.ai_config import AIConfig
        from app.services.embedding_service import EmbeddingService
        emb_config = AIConfig.get_default_embedding_config()
        if not emb_config or not emb_config.embedding_model:
            raise ValueError("No default embedding configuration found. Please configure an embedding model first.")

        embedding_service = EmbeddingService(emb_config, user_id=user_id)

        text = f"SOP：{sop.title}\n\n{sop.content}"
        chunks = [{
            "chunk_type": "sop",
            "source_id": sop.id,
            "requirement_id": 0,
            "module_id": None,
            "text": text,
            "metadata": {
                "title": sop.title,
                "sop_id": sop.id,
                "session_id": sop.kb_session_id,
            },
            "project_type": "production",
        }]
        stored = embedding_service.embed_and_store_chunks(chunks)
        logger.info("SOP indexed to KB: id=%d stored=%d", sop_id, stored)
        return {"indexed": True, "stored": stored}
