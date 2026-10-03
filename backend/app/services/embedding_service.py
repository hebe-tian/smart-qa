"""Embedding service: chunk data, call Embedding API, store/retrieve vectors."""
import json
import time
from openai import OpenAI
from datetime import datetime
from app.extensions import db
from app.models.ai_config import AIConfig
from app.models.embedding import Embedding
from app.models.requirement import Requirement
from app.models.module import Module
from app.models.test_case import TestCase
from app.core.security import decrypt_api_key
from app.services.call_log_service import call_log_service
from app.services.logging_service import get_logger

logger = get_logger("ai")


class EmbeddingService:
    """Handles embedding generation, vector storage, and similarity search."""

    # Chunk text templates by type
    CHUNK_TEMPLATES = {
        "requirement": "需求：{title}\n{content}",
        "module": "模块：{name}\n描述：{description}\n关键测试点：{key_points}",
        "test_case": "用例：{title}\n前置条件：{preconditions}\n步骤：{steps}\n预期结果：{expected_result}",
        "qa": "历史问答（已验证正确）：\n问题：{question}\n回答：{answer}",
        "qa_negative": "历史问答（标记为错误回答，请避免类似答案）：\n问题：{question}\n回答：{answer}",
        "code": "代码：{file_name} ({language})\n{content}",
    }

    def __init__(self, ai_config, user_id=None):
        """Initialize with an AIConfig that has embedding_model set."""
        self.config = ai_config
        self.user_id = user_id
        self.embedding_model = ai_config.embedding_model

        if not self.embedding_model:
            raise ValueError("Embedding model is not configured for this AI config")

        api_key = decrypt_api_key(ai_config.api_key_encrypted)
        self.client = OpenAI(
            base_url=ai_config.base_url,
            api_key=api_key,
        )

    # ------------------------------------------------------------------
    # Embedding API call
    # ------------------------------------------------------------------

    def embed_texts(self, texts):
        """Call Embedding API for a list of texts. Returns list of numpy arrays.

        Uses OpenAI-compatible /v1/embeddings endpoint.
        Records the call via call_log_service for audit trail.
        """
        if not texts:
            return []

        import numpy as np

        call_id = call_log_service.start_call(
            ai_config_id=self.config.id,
            user_id=self.user_id,
            requirement_id=None,
            task_type="embedding",
            model_name=self.embedding_model,
            messages=[{"role": "system", "content": f"Embedding {len(texts)} texts"}],
        )

        try:
            logger.debug(
                "Embedding request: model=%s count=%d",
                self.embedding_model, len(texts),
            )

            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )

            vectors = [item.embedding for item in response.data]
            dim = len(vectors[0]) if vectors else 0

            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": 0,
                    "total_tokens": response.usage.total_tokens,
                }

            call_log_service.end_call(
                call_id,
                f"Embedded {len(vectors)} texts, dim={dim}",
                usage,
                "success",
            )
            logger.debug(
                "Embedding success: count=%d dim=%d tokens=%s",
                len(vectors), dim, usage,
            )

            return [np.array(v, dtype=np.float32) for v in vectors], dim

        except Exception as e:
            logger.error("Embedding failed: error=%s", str(e))
            call_log_service.end_call(call_id, None, None, "failed", str(e))
            raise

    def embed_query(self, text):
        """Embed a single query text. Returns (numpy_array, dim)."""
        vectors, dim = self.embed_texts([text])
        return vectors[0], dim

    # ------------------------------------------------------------------
    # Chunking: build text chunks from database records
    # ------------------------------------------------------------------

    def build_all_chunks(self, project_type="production"):
        """Build chunks from requirements, modules, and test cases.

        Args:
            project_type: If "production" (default), only build production chunks.
                         If "test", only build test chunks.
                         If None, build all chunks regardless of project_type.

        Returns list of dicts: {chunk_type, source_id, requirement_id, module_id, text, metadata, project_type}
        """
        chunks = []

        # Query requirements, optionally filtered by project_type
        req_query = Requirement.query
        if project_type is not None:
            req_query = req_query.filter(Requirement.project_type == project_type)
        requirements = req_query.all()

        # Build a map: requirement_id -> project_type for efficient lookup
        req_pt_map = {r.id: (r.project_type or "production") for r in requirements}

        # Requirement chunks
        for req in requirements:
            pt = req_pt_map[req.id]
            text = self.CHUNK_TEMPLATES["requirement"].format(
                title=req.title,
                content=req.content or "",
            )
            chunks.append({
                "chunk_type": "requirement",
                "source_id": req.id,
                "requirement_id": req.id,
                "module_id": None,
                "text": text,
                "metadata": {"title": req.title, "status": req.status},
                "project_type": pt,
            })

        # Module chunks - only for matching requirements (avoid N+1 via IN clause)
        req_id_set = set(req_pt_map.keys())
        modules = (
            Module.query.filter(Module.requirement_id.in_(req_id_set)).all()
            if req_id_set else []
        )

        # Build module_id -> requirement_id map for test case lookup
        mod_req_map = {m.id: m.requirement_id for m in modules}
        mod_map = {m.id: m for m in modules}

        for mod in modules:
            pt = req_pt_map.get(mod.requirement_id, "production")
            key_points = json.loads(mod.key_points) if mod.key_points else []
            text = self.CHUNK_TEMPLATES["module"].format(
                name=mod.name,
                description=mod.description or "",
                key_points="、".join(key_points) if key_points else "无",
            )
            chunks.append({
                "chunk_type": "module",
                "source_id": mod.id,
                "requirement_id": mod.requirement_id,
                "module_id": None,
                "text": text,
                "metadata": {"name": mod.name, "key_points": key_points},
                "project_type": pt,
            })

        # Test case chunks - only for matching modules (avoid N+1 via IN clause)
        mod_id_set = set(mod_req_map.keys())
        cases = (
            TestCase.query.filter(TestCase.module_id.in_(mod_id_set)).all()
            if mod_id_set else []
        )

        for case in cases:
            req_id = mod_req_map.get(case.module_id, 0)
            pt = req_pt_map.get(req_id, "production")
            steps = json.loads(case.steps_json) if case.steps_json else []
            step_text = "\n".join(
                f"{i+1}. {s}" for i, s in enumerate(steps)
            ) if steps else "无"
            text = self.CHUNK_TEMPLATES["test_case"].format(
                title=case.title,
                preconditions=case.preconditions or "无",
                steps=step_text,
                expected_result=case.expected_result or "无",
            )
            module = mod_map.get(case.module_id)

            chunks.append({
                "chunk_type": "test_case",
                "source_id": case.id,
                "requirement_id": req_id,
                "module_id": case.module_id,
                "text": text,
                "metadata": {
                    "title": case.title,
                    "priority": case.priority,
                    "case_type": case.case_type,
                    "module_name": module.name if module else "",
                },
                "project_type": pt,
            })

        logger.debug("Built %d chunks (project_type=%s): %d requirements, %d modules, %d test_cases",
                     len(chunks), project_type,
                     sum(1 for c in chunks if c["chunk_type"] == "requirement"),
                     sum(1 for c in chunks if c["chunk_type"] == "module"),
                     sum(1 for c in chunks if c["chunk_type"] == "test_case"))
        return chunks

    # ------------------------------------------------------------------
    # Build index: embed all chunks and store to DB
    # ------------------------------------------------------------------

    def build_index(self, project_type="production"):
        """Build the embedding index from database records.

        Args:
            project_type: If "production" (default), only index production data.
                         If None, index all data (both production and test).

        Clears existing embeddings for the specified project_type (or all if None),
        chunks data, embeds in batches, stores to DB.
        Returns (chunk_count, dim).
        """
        # Clear existing embeddings ONLY for requirement/module/test_case types.
        # This preserves code, qa, and qa_negative chunks that are indexed independently.
        chunk_types_to_clear = ['requirement', 'module', 'test_case']
        clear_query = Embedding.query.filter(Embedding.chunk_type.in_(chunk_types_to_clear))
        if project_type is not None:
            clear_query = clear_query.filter_by(project_type=project_type)
        clear_query.delete()
        logger.debug("Cleared existing embeddings for types=%s project_type=%s", chunk_types_to_clear, project_type)
        db.session.commit()

        chunks = self.build_all_chunks(project_type=project_type)
        if not chunks:
            logger.warning("No data to embed - empty database (project_type=%s)", project_type)
            return 0, 0

        # Embed in batches of 50 to avoid API limits
        batch_size = 50
        total_stored = 0
        dim = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]
            vectors, dim = self.embed_texts(texts)

            for chunk, vec in zip(batch, vectors):
                emb = Embedding(
                    chunk_type=chunk["chunk_type"],
                    source_id=chunk["source_id"],
                    requirement_id=chunk["requirement_id"],
                    module_id=chunk["module_id"],
                    text=chunk["text"],
                    embedding=vec.tobytes(),
                    dim=dim,
                    metadata_json=json.dumps(chunk["metadata"], ensure_ascii=False),
                    project_type=chunk.get("project_type", "production"),
                    created_at=datetime.utcnow(),
                )
                db.session.add(emb)

            db.session.commit()
            total_stored += len(batch)
            logger.debug("Embedded batch %d/%d (%d chunks)", i // batch_size + 1,
                        (len(chunks) + batch_size - 1) // batch_size, len(batch))

        logger.info("Index build complete: %d chunks, dim=%d, project_type=%s",
                     total_stored, dim, project_type)
        return total_stored, dim

    def embed_and_store_chunks(self, chunks):
        """Embed and store pre-built chunks for incremental indexing.

        Removes any existing embeddings with the same (chunk_type, source_id,
        project_type) before inserting new ones, so re-indexing is safe.

        Args:
            chunks: List of chunk dicts, each with keys: chunk_type, source_id,
                    requirement_id, module_id, text, metadata, project_type.

        Returns: number of chunks stored.
        """
        if not chunks:
            return 0

        # Remove existing embeddings for these chunks (deduplicate by source)
        for chunk in chunks:
            Embedding.query.filter_by(
                chunk_type=chunk["chunk_type"],
                source_id=chunk["source_id"],
                project_type=chunk.get("project_type", "production"),
            ).delete()
        db.session.commit()

        # Embed in batches
        batch_size = 50
        total_stored = 0
        dim = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]
            vectors, dim = self.embed_texts(texts)

            for chunk, vec in zip(batch, vectors):
                emb = Embedding(
                    chunk_type=chunk["chunk_type"],
                    source_id=chunk["source_id"],
                    requirement_id=chunk["requirement_id"],
                    module_id=chunk["module_id"],
                    text=chunk["text"],
                    embedding=vec.tobytes(),
                    dim=dim,
                    metadata_json=json.dumps(chunk["metadata"], ensure_ascii=False),
                    project_type=chunk.get("project_type", "production"),
                    created_at=datetime.utcnow(),
                )
                db.session.add(emb)

            db.session.commit()
            total_stored += len(batch)

        logger.debug("Incremental index: stored %d chunks, dim=%d", total_stored, dim)
        return total_stored

    # ------------------------------------------------------------------
    # Vector search: cosine similarity Top-K
    # ------------------------------------------------------------------

    def search(self, query_vector, top_k=5, dim=None, chunk_type=None, project_type="production"):
        """Search for Top-K most similar chunks to query_vector.

        Args:
            query_vector: numpy array query vector.
            top_k: Number of top results to return.
            dim: Expected vector dimension for filtering.
            chunk_type: If specified, only search within this chunk type
                        (e.g. "module", "test_case").
            project_type: If specified, only search within this project type
                         (default: "production"). Set to None to search all.

        Returns list of dicts: {chunk_type, source_id, text, score, metadata, project_type}
        """
        import numpy as np

        # Build SQL with optional filters to reduce memory load
        sql = "SELECT id, chunk_type, source_id, requirement_id, module_id, text, dim, metadata_json, embedding, project_type FROM embeddings"
        conditions = []
        params = {}

        if project_type is not None:
            conditions.append("project_type = :project_type")
            params["project_type"] = project_type
        if chunk_type is not None:
            conditions.append("chunk_type = :chunk_type")
            params["chunk_type"] = chunk_type

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        rows = db.session.execute(db.text(sql), params).fetchall()

        if not rows:
            return []

        # Filter by dimension if specified
        expected_dim = dim or len(query_vector)
        valid_rows = [r for r in rows if r[6] == expected_dim]

        if not valid_rows:
            logger.warning("No embeddings with matching dimension %d", expected_dim)
            return []

        # Build matrix: (N, dim) float32
        matrix = np.array([
            np.frombuffer(r[8], dtype=np.float32) for r in valid_rows
        ])  # shape: (N, dim)

        # Cosine similarity: dot(q, m) / (|q| * |m|)
        # Normalize both query and matrix rows
        query_norm = query_vector / (np.linalg.norm(query_vector) + 1e-8)
        matrix_norms = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)

        similarities = matrix_norms @ query_norm  # shape: (N,)

        # Get Top-K indices
        k = min(top_k, len(valid_rows))
        top_indices = np.argpartition(similarities, -k)[-k:]
        top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            row = valid_rows[idx]
            metadata = json.loads(row[7]) if row[7] else {}
            results.append({
                "id": row[0],
                "chunk_type": row[1],
                "source_id": row[2],
                "requirement_id": row[3],
                "module_id": row[4],
                "text": row[5],
                "score": float(similarities[idx]),
                "metadata": metadata,
                "project_type": row[9] if row[9] else "production",
            })

        logger.debug("Vector search: top_k=%d chunk_type=%s project_type=%s results_count=%d max_score=%.4f",
                     top_k, chunk_type, project_type, len(results),
                     results[0]["score"] if results else 0)
        return results

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_status():
        """Return knowledge base status: chunk_count, last_built_at, is_ready, by_project_type."""
        from sqlalchemy import func

        total = db.session.query(func.count(Embedding.id)).scalar() or 0
        last = db.session.query(func.max(Embedding.created_at)).scalar()

        # Count by project_type and chunk_type for detailed breakdown
        breakdown = {}
        rows = db.session.query(
            Embedding.project_type,
            Embedding.chunk_type,
            func.count(Embedding.id)
        ).group_by(Embedding.project_type, Embedding.chunk_type).all()

        for pt, ct, cnt in rows:
            pt_key = pt or "production"
            if pt_key not in breakdown:
                breakdown[pt_key] = {"total": 0}
            breakdown[pt_key]["total"] += cnt
            breakdown[pt_key][ct] = breakdown[pt_key].get(ct, 0) + cnt

        return {
            "chunk_count": total,
            "last_built_at": last.isoformat() if last else None,
            "is_ready": total > 0,
            "by_project_type": breakdown,
        }

    @staticmethod
    def is_configured():
        """Check if any default embedding config has embedding_model set."""
        config = AIConfig.get_default_embedding_config()
        return config is not None and bool(config.embedding_model)

    @staticmethod
    def get_default_config():
        """Get the default AI config for embeddings. Returns AIConfig or None."""
        return AIConfig.get_default_embedding_config()
