"""Document service: parse uploaded documents (PDF/Word/Markdown) and AI-extract structured requirements."""
import io
import json
import os
import re

from app.models.ai_config import AIConfig
from app.services.ai_service import AIService
from app.services.logging_service import get_logger

logger = get_logger("ai")

# Supported upload extensions
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".txt"}
# Truncate extracted text to stay within model context limits
MAX_TEXT_LENGTH = 12000
# Max upload size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024


class DocumentService:
    """Parses uploaded requirement documents and uses AI to extract structured requirements."""

    def parse_and_extract(self, file_storage, user_id):
        """Parse an uploaded document and AI-extract {title, content}.

        Args:
            file_storage: Flask FileStorage object (from request.files).
            user_id: Owner user ID (for AI call logging).

        Returns:
            dict: {"title": str, "content": str, "source_filename": str}
        """
        filename = file_storage.filename or "document"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        raw_bytes = file_storage.read()
        if not raw_bytes:
            raise ValueError("Uploaded file is empty")
        if len(raw_bytes) > MAX_FILE_SIZE:
            raise ValueError(
                f"File too large ({len(raw_bytes)} bytes). Max size is {MAX_FILE_SIZE // 1024 // 1024}MB."
            )

        # Dispatch parsing by extension
        if ext == ".pdf":
            text = self._parse_pdf(raw_bytes)
        elif ext == ".docx":
            text = self._parse_docx(raw_bytes)
        else:  # .md / .markdown / .txt
            text = self._parse_text(raw_bytes)

        text = (text or "").strip()
        if not text:
            raise ValueError("No text could be extracted from the document")

        # Truncate to stay within model context limits
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]
            logger.info(
                "Document text truncated to %d chars: file=%s", MAX_TEXT_LENGTH, filename
            )

        # AI extract structured requirement
        result = self._ai_extract(text, filename, user_id)
        logger.info(
            "Document parsed and extracted: file=%s title=%s content_len=%d",
            filename, result.get("title", ""), len(result.get("content", "")),
        )
        return result

    # ------------------------------------------------------------------
    # AI extraction
    # ------------------------------------------------------------------

    def _ai_extract(self, text, filename, user_id):
        """Call AI to extract a structured requirement {title, content} from document text."""
        config = AIConfig.get_default_chat_config()
        if not config:
            config = AIConfig.query.filter_by(is_active=True).first()
        if not config:
            raise ValueError(
                "No AI configuration found. Please configure an AI model first."
            )

        from app.services.prompt_service import PromptService
        ai_service = AIService(config, user_id=user_id)
        messages = PromptService.extract_requirement_prompt(text)
        response = ai_service.chat(messages, json_mode=True, task_type="doc_extract")
        parsed = self._parse_json_response(response)

        title = (parsed.get("title") or "").strip()
        content = (parsed.get("content") or "").strip()
        if not title:
            # Fallback: derive a title from the filename (strip extension)
            title = os.path.splitext(filename)[0] or "导入的需求文档"
        if not content:
            # Fallback: use the raw (truncated) document text
            content = text
        return {"title": title, "content": content}

    @staticmethod
    def _parse_json_response(text):
        """Robustly parse JSON from AI response. Handles markdown fences and extra text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        patterns = [
            r"```json\s*\n?(.*?)\n?\s*```",
            r"```\s*\n?(.*?)\n?\s*```",
            r"(\{.*\})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Last resort: json_repair
        try:
            from json_repair import repair_json
            return json.loads(repair_json(text))
        except Exception:
            pass

        raise ValueError(f"Failed to parse JSON from AI response: {text[:200]}...")

    # ------------------------------------------------------------------
    # Format-specific parsers
    # ------------------------------------------------------------------

    def _parse_pdf(self, file_bytes):
        """Extract text from PDF using PyMuPDF."""
        import pymupdf
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        return "\n".join(parts)

    def _parse_docx(self, file_bytes):
        """Extract text from .docx using python-docx (paragraphs + tables)."""
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        parts = []
        for para in doc.paragraphs:
            if para.text:
                parts.append(para.text)
        # Also extract table cell text as pipe-separated rows
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)

    def _parse_text(self, file_bytes):
        """Decode markdown/txt directly as UTF-8."""
        return file_bytes.decode("utf-8", errors="replace")
