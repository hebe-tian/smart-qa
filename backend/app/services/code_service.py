"""Code service: manage business code documents, chunk and index for RAG."""
import io
import json
import os
import zipfile
from datetime import datetime
from app.extensions import db
from app.models.code_document import CodeDocument
from app.models.embedding import Embedding
from app.services.logging_service import get_logger

logger = get_logger("ai")

# Language detection from file extension
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
}

# Keywords that indicate function/class boundaries for chunking
BOUNDARY_KEYWORDS = (
    "def ", "class ", "function ", "export function",
    "export class", "export default", "public ", "private ",
    "protected ", "static ", "func ", "fn ", "impl ",
    "async ", "export async",
)

MAX_FILE_SIZE = 1024 * 1024  # 1MB per code file
MAX_CHUNK_LINES = 200
MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50MB max zip upload
MAX_FILES_PER_ZIP = 200  # max code files extracted per zip

# Directories to skip when extracting code files from a zip archive
EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".idea", ".vscode", "vendor", "target",
    ".pytest_cache", ".mypy_cache", ".tox", "eggs", ".eggs",
}


class CodeService:
    """Manages business code documents: zip upload import, chunk, and index."""

    def __init__(self, ai_config=None, user_id=None):
        self._config = ai_config
        self.user_id = user_id

    def _ensure_embedding_service(self):
        """Lazily initialize EmbeddingService with the default embedding config."""
        if self._config is None:
            from app.models.ai_config import AIConfig
            self._config = AIConfig.get_default_embedding_config()
            if not self._config:
                raise ValueError("No default embedding configuration found")

        from app.services.embedding_service import EmbeddingService
        return EmbeddingService(self._config, user_id=self.user_id)

    # ------------------------------------------------------------------
    # Import from ZIP upload
    # ------------------------------------------------------------------

    def import_zip(self, file_storage, user_id, title, description=""):
        """Import code files from an uploaded zip archive.

        Extracts code files (filtered by LANGUAGE_MAP extensions), skips
        excluded directories (node_modules, .git, etc.), enforces per-file
        size and total file-count limits, then creates a CodeDocument per
        file and batch-indexes them all.

        Args:
            file_storage: Flask FileStorage object (the uploaded .zip).
            user_id: Owner user ID.
            title: Document title (shared across all extracted files).
            description: Optional description.

        Returns:
            dict: {"created": int, "skipped": int, "documents": [...]}
        """
        zip_bytes = file_storage.read()
        if len(zip_bytes) > MAX_ZIP_SIZE:
            raise ValueError(
                f"Zip too large ({len(zip_bytes)} bytes). "
                f"Max is {MAX_ZIP_SIZE // 1024 // 1024}MB."
            )

        code_extensions = set(LANGUAGE_MAP.keys())
        created = []
        skipped = 0

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            raise ValueError("Invalid zip file. Please ensure the file is a valid .zip archive.")

        with zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue

                # Skip files inside excluded directories
                parts = info.filename.split("/")
                if any(p in EXCLUDED_DIRS for p in parts):
                    continue

                # Skip non-code files by extension
                ext = os.path.splitext(info.filename)[1].lower()
                if ext not in code_extensions:
                    skipped += 1
                    continue

                # Skip oversized individual files
                if info.file_size > MAX_FILE_SIZE:
                    skipped += 1
                    continue

                # Stop if too many files
                if len(created) >= MAX_FILES_PER_ZIP:
                    logger.warning("Zip import reached MAX_FILES_PER_ZIP (%d), truncating.", MAX_FILES_PER_ZIP)
                    break

                content = zf.read(info.filename).decode("utf-8", errors="replace")
                file_name = os.path.basename(info.filename)

                doc = CodeDocument(
                    user_id=user_id,
                    title=title,
                    description=description,
                    source_type="upload",
                    file_name=file_name,
                    relative_path=info.filename,
                    language=self._detect_language(file_name),
                    content=content,
                )
                db.session.add(doc)
                created.append(doc)

        if not created:
            raise ValueError("No code files found in the zip archive.")

        db.session.commit()

        # Batch index all created documents
        for doc in created:
            self.index_document(doc.id)

        logger.info(
            "Zip import complete: user=%d created=%d skipped=%d",
            user_id, len(created), skipped,
        )
        return {
            "created": len(created),
            "skipped": skipped,
            "documents": [d.to_dict() for d in created],
        }

    # ------------------------------------------------------------------
    # List / Delete
    # ------------------------------------------------------------------

    def list_documents(self, user_id):
        """List all code documents for a user."""
        docs = CodeDocument.query.filter_by(user_id=user_id).order_by(CodeDocument.created_at.desc()).all()
        return [d.to_dict() for d in docs]

    def delete_document(self, doc_id, user_id):
        """Delete a code document and its embeddings."""
        doc = CodeDocument.query.get(doc_id)
        if not doc or doc.user_id != user_id:
            return False

        # Delete associated embeddings
        Embedding.query.filter_by(chunk_type="code", source_id=doc_id).delete()
        db.session.delete(doc)
        db.session.commit()
        logger.info("Code document deleted: doc_id=%d", doc_id)
        return True

    # ------------------------------------------------------------------
    # Indexing: chunk code → embed → store
    # ------------------------------------------------------------------

    def index_document(self, doc_id):
        """Chunk and index a single code document.

        1. Split code into chunks (by function/class boundaries, fall back to line count)
        2. Embed chunks via EmbeddingService.embed_and_store_chunks()
        3. Update CodeDocument.indexed and chunk_count
        """
        doc = CodeDocument.query.get(doc_id)
        if not doc:
            raise ValueError("Code document not found")

        # Build chunks
        chunks = self._chunk_code(doc.content, doc.file_name, doc.language, doc.relative_path)
        if not chunks:
            logger.warning("No chunks generated for code document: doc_id=%d", doc_id)
            return 0

        # Set source_id for each chunk (needed for embed_and_store_chunks dedup)
        for chunk in chunks:
            chunk["source_id"] = doc_id

        # Remove existing embeddings for this document
        Embedding.query.filter_by(chunk_type="code", source_id=doc_id).delete()
        db.session.commit()

        # Embed and store
        emb_service = self._ensure_embedding_service()
        stored = emb_service.embed_and_store_chunks(chunks)

        # Update document status
        doc.indexed = True
        doc.chunk_count = stored
        db.session.commit()
        logger.info("Code indexed: doc_id=%d chunks=%d stored=%d", doc_id, len(chunks), stored)
        return stored

    def rebuild_all(self, user_id=None):
        """Re-index all code documents (optionally filtered by user)."""
        query = CodeDocument.query
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        docs = query.all()

        total = 0
        for doc in docs:
            try:
                total += self.index_document(doc.id)
            except Exception as e:
                logger.error("Code re-index failed: doc_id=%d error=%s", doc.id, str(e))

        logger.info("Code rebuild complete: docs=%d total_chunks=%d", len(docs), total)
        return {"status": "success", "document_count": len(docs), "chunk_count": total}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_language(self, file_name):
        """Detect programming language from file extension."""
        import os
        _, ext = os.path.splitext(file_name)
        return LANGUAGE_MAP.get(ext.lower(), "text")

    def _chunk_code(self, content, file_name, language, relative_path=None):
        """Split code into chunks by function/class boundaries.

        Falls back to fixed-size line chunks if no boundaries found.
        Returns list of chunk dicts ready for embed_and_store_chunks().
        """
        lines = content.split("\n")
        if not lines:
            return []

        # Try boundary-based chunking
        chunks = []
        current_lines = []
        current_start = 0

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            is_boundary = any(stripped.startswith(kw) for kw in BOUNDARY_KEYWORDS)

            # Start new chunk at boundary if current chunk is large enough
            if is_boundary and len(current_lines) >= 20:
                chunks.append({
                    "lines": current_lines,
                    "start": current_start,
                    "end": i - 1,
                })
                current_lines = []
                current_start = i

            current_lines.append(line)

        # Add remaining lines
        if current_lines:
            chunks.append({
                "lines": current_lines,
                "start": current_start,
                "end": len(lines) - 1,
            })

        # If only one chunk and file is large, split by MAX_CHUNK_LINES
        if len(chunks) == 1 and len(lines) > MAX_CHUNK_LINES:
            chunks = []
            for i in range(0, len(lines), MAX_CHUNK_LINES):
                chunk_lines = lines[i:i + MAX_CHUNK_LINES]
                chunks.append({
                    "lines": chunk_lines,
                    "start": i,
                    "end": min(i + MAX_CHUNK_LINES - 1, len(lines) - 1),
                })

        # Format chunks with context
        result = []
        for idx, chunk in enumerate(chunks):
            text = self.CHUNK_TEMPLATES_format(file_name, language, idx, len(chunks), chunk, relative_path)
            result.append({
                "chunk_type": "code",
                "source_id": 0,  # Will be set by caller
                "requirement_id": 0,
                "module_id": None,
                "text": text,
                "metadata": {
                    "file_name": file_name,
                    "relative_path": relative_path,
                    "language": language,
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                    "start_line": chunk["start"],
                    "end_line": chunk["end"],
                },
                "project_type": "production",
            })

        logger.debug("Code chunked: file=%s chunks=%d lines=%d", file_name, len(result), len(lines))
        return result

    @staticmethod
    def CHUNK_TEMPLATES_format(file_name, language, idx, total, chunk, relative_path=None):
        """Format a code chunk with context header."""
        path_display = relative_path or file_name
        header = f"# 文件：{path_display} ({language})\n# 分块 {idx + 1}/{total} (行 {chunk['start']}-{chunk['end']})\n\n"
        return header + "\n".join(chunk["lines"])
