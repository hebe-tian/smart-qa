"""Case generation orchestration service.
Coordinates the Prompt chain: analyze -> QA -> module generation -> case generation.
Runs in background thread, updates task_store for frontend polling."""
import json
import re
from app.extensions import db
from app.models.requirement import Requirement
from app.models.qa_session import QAMessage
from app.models.module import Module
from app.models.test_case import TestCase
from app.models.ai_config import AIConfig
from app.models.regeneration import RegenerationLog
from app.services.ai_service import AIService
from app.services.prompt_service import PromptService
from app.services.task_store import task_store
from app.services.logging_service import get_logger

logger = get_logger("generation")


def _parse_json_response(text):
    """Robustly parse JSON from AI response. Handles markdown fences, extra text, etc."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON block (with or without markdown fences)
    patterns = [
        r"```json\s*\n?(.*?)\n?\s*```",
        r"```\s*\n?(.*?)\n?\s*```",
        r"(\{.*\})",
        r"(\[.*\])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Try json_repair as last resort
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        return json.loads(repaired)
    except Exception:
        pass

    raise ValueError(f"Failed to parse JSON from AI response: {text[:200]}...")


def _get_default_ai_config(user_id):
    """Get the default AI config for chat operations. Returns None if no config exists."""
    config = AIConfig.get_default_chat_config()
    if not config:
        config = AIConfig.query.filter_by(is_active=True).first()
    return config


def _get_embedding_config():
    """Get the default AI config for embedding operations. Returns None if not configured."""
    config = AIConfig.get_default_embedding_config()
    if not config:
        config = AIConfig.query.filter(
            AIConfig.is_active == True,  # noqa: E712
            AIConfig.embedding_model.isnot(None),
        ).first()
    return config


def _cleanup_embeddings_for_modules(module_ids):
    """Delete embeddings for the given module IDs and their associated test cases.

    Called before deleting/regenerating modules to prevent orphaned embedding records
    that would pollute RAG search results with stale data.
    """
    if not module_ids:
        return
    try:
        from app.models.embedding import Embedding
        Embedding.query.filter(
            db.or_(
                db.and_(Embedding.chunk_type == "module", Embedding.source_id.in_(module_ids)),
                db.and_(Embedding.chunk_type == "test_case", Embedding.module_id.in_(module_ids)),
            )
        ).delete(synchronize_session=False)
        db.session.commit()
        logger.debug("Cleaned up embeddings for modules: %s", module_ids)
    except Exception as e:
        logger.warning("Embedding cleanup failed (non-blocking): %s", str(e))
        db.session.rollback()


def _cleanup_embeddings_for_cases(case_ids):
    """Delete embeddings for the given test case IDs.

    Called before deleting/regenerating test cases to prevent orphaned embedding records.
    """
    if not case_ids:
        return
    try:
        from app.models.embedding import Embedding
        Embedding.query.filter(
            Embedding.chunk_type == "test_case",
            Embedding.source_id.in_(case_ids),
        ).delete(synchronize_session=False)
        db.session.commit()
        logger.debug("Cleaned up embeddings for cases: %s", case_ids)
    except Exception as e:
        logger.warning("Embedding cleanup failed (non-blocking): %s", str(e))
        db.session.rollback()


class CaseService:
    """Orchestrates the full test case generation pipeline."""

    def analyze_requirement(self, requirement, user_id):
        """Step 1: Analyze requirement for clarification needs. Returns analysis dict."""
        config = _get_default_ai_config(user_id)
        if not config:
            raise ValueError("No AI configuration found. Please configure an AI model first.")

        ai_service = AIService(config, user_id=user_id, requirement_id=requirement.id)
        messages = PromptService.analyze_requirement_prompt(requirement.content)
        response = ai_service.chat(messages, json_mode=True, task_type="analyze")

        result = _parse_json_response(response)
        logger.info("Requirement analyzed: req_id=%d need_clarification=%s",
                     requirement.id, result.get("need_clarification"))
        return result

    def qa_followup(self, requirement, user_id):
        """Step 2: Get AI follow-up questions or confirm context is sufficient."""
        config = _get_default_ai_config(user_id)
        if not config:
            raise ValueError("No AI configuration found.")

        qa_messages = QAMessage.query.filter_by(requirement_id=requirement.id).order_by(QAMessage.round).all()
        qa_history = [{"role": m.role, "content": m.content} for m in qa_messages]

        ai_service = AIService(config, user_id=user_id, requirement_id=requirement.id)
        messages = PromptService.qa_followup_prompt(requirement.content, qa_history)
        response = ai_service.chat(messages, json_mode=True, task_type="qa")

        result = _parse_json_response(response)
        logger.info("QA followup: req_id=%d sufficient=%s", requirement.id, result.get("context_sufficient"))
        return result

    # ------------------------------------------------------------------
    # RAG helpers: retrieval + incremental indexing (graceful degradation)
    # ------------------------------------------------------------------

    # Similarity threshold: results below this score are not injected
    RAG_SIMILARITY_THRESHOLD = 0.75

    def _retrieve_rag_context(self, query_text, chunk_type, top_k=5):
        """Retrieve RAG context from the production knowledge base.

        Searches for similar chunks in the production knowledge base only,
        regardless of the current project's type.

        Args:
            query_text: Text to embed and search for.
            chunk_type: "module" or "test_case" — which type of chunks to search.
            top_k: Max results to retrieve.

        Returns: Formatted context string, or None if no results / RAG unavailable.
        """
        try:
            config = _get_embedding_config()
            if not config or not config.embedding_model:
                return None

            from app.services.embedding_service import EmbeddingService
            emb_service = EmbeddingService(config, user_id=None)
            query_vector, dim = emb_service.embed_query(query_text)
            results = emb_service.search(
                query_vector, top_k=top_k, dim=dim,
                chunk_type=chunk_type, project_type="production",
            )

            # Filter by similarity threshold to avoid noise
            results = [r for r in results if r["score"] >= self.RAG_SIMILARITY_THRESHOLD]
            if not results:
                return None

            # Format results as context string
            type_label = {"module": "模块", "test_case": "测试用例"}.get(chunk_type, chunk_type)
            parts = []
            for i, r in enumerate(results, 1):
                metadata = r.get("metadata", {})
                meta_parts = []
                if "name" in metadata:
                    meta_parts.append(f"名称：{metadata['name']}")
                if "key_points" in metadata and metadata["key_points"]:
                    meta_parts.append(f"关键测试点：{'、'.join(metadata['key_points'])}")
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

            context = "\n\n---\n\n".join(parts)
            logger.debug("RAG context retrieved: chunk_type=%s results=%d", chunk_type, len(results))
            return context

        except Exception as e:
            logger.warning("RAG retrieval failed (degrading): chunk_type=%s error=%s", chunk_type, str(e))
            return None

    # Code similarity threshold: lower than module/case threshold because
    # code semantic matching is less precise than natural language matching
    CODE_SIMILARITY_THRESHOLD = 0.60

    def _retrieve_code_context(self, query_text, top_k=3):
        """Retrieve similar business code snippets from the RAG knowledge base.

        Searches for code chunks (chunk_type="code") relevant to the query.
        Returns a formatted context string, or None if no results / RAG unavailable.
        """
        try:
            config = _get_embedding_config()
            if not config or not config.embedding_model:
                return None

            from app.services.embedding_service import EmbeddingService
            emb_service = EmbeddingService(config, user_id=None)
            query_vector, dim = emb_service.embed_query(query_text)
            results = emb_service.search(
                query_vector, top_k=top_k, dim=dim,
                chunk_type="code", project_type="production",
            )

            # Filter by code similarity threshold (lower than module/case)
            results = [r for r in results if r["score"] >= self.CODE_SIMILARITY_THRESHOLD]
            if not results:
                return None

            parts = []
            for i, r in enumerate(results, 1):
                metadata = r.get("metadata", {})
                meta_parts = []
                if metadata.get("relative_path"):
                    meta_parts.append(f"路径：{metadata['relative_path']}")
                elif metadata.get("file_name"):
                    meta_parts.append(f"文件：{metadata['file_name']}")
                if metadata.get("language"):
                    meta_parts.append(f"语言：{metadata['language']}")
                meta_str = f"（{', '.join(meta_parts)}）" if meta_parts else ""
                parts.append(f"[{i}] [业务代码]{meta_str}\n{r['text']}")

            context = "\n\n---\n\n".join(parts)
            logger.debug("Code context retrieved: results=%d", len(results))
            return context

        except Exception as e:
            logger.warning("Code RAG retrieval failed (degrading): error=%s", str(e))
            return None

    def _incremental_index_cases(self, cases, requirement):
        """Incrementally index test cases into the knowledge base.

        Only indexes if requirement.project_type == "production".
        Failures are logged as warnings and do not block the generation flow.
        """
        try:
            if not requirement or requirement.project_type != "production":
                return
            if not cases:
                return

            config = _get_embedding_config()
            if not config or not config.embedding_model:
                return

            from app.services.embedding_service import EmbeddingService
            emb_service = EmbeddingService(config, user_id=None)

            # Build chunks for the new cases (load modules for metadata)
            module_ids = set(c.module_id for c in cases)
            modules_map = {}
            if module_ids:
                modules_map = {m.id: m for m in Module.query.filter(Module.id.in_(module_ids)).all()}

            chunks = []
            for case in cases:
                module = modules_map.get(case.module_id)
                steps = json.loads(case.steps_json) if case.steps_json else []
                step_text = "\n".join(
                    f"{i+1}. {s}" for i, s in enumerate(steps)
                ) if steps else "无"
                text = EmbeddingService.CHUNK_TEMPLATES["test_case"].format(
                    title=case.title,
                    preconditions=case.preconditions or "无",
                    steps=step_text,
                    expected_result=case.expected_result or "无",
                )
                chunks.append({
                    "chunk_type": "test_case",
                    "source_id": case.id,
                    "requirement_id": requirement.id,
                    "module_id": case.module_id,
                    "text": text,
                    "metadata": {
                        "title": case.title,
                        "priority": case.priority,
                        "case_type": case.case_type,
                        "module_name": module.name if module else "",
                    },
                    "project_type": "production",
                })

            if chunks:
                count = emb_service.embed_and_store_chunks(chunks)
                logger.debug("Incremental index: req_id=%d indexed %d test cases",
                            requirement.id, count)

        except Exception as e:
            logger.warning("Incremental indexing failed (non-blocking): req_id=%s error=%s",
                           getattr(requirement, 'id', '?'), str(e))

    def generate_modules_task(self, requirement_id, user_id, task_id):
        """Step 3: Generate modules in background thread."""
        try:
            requirement = db.session.get(Requirement, requirement_id)
            if not requirement:
                task_store.update(task_id, status="failed", error="Requirement not found")
                return

            task_store.update(task_id, status="running", progress=10, message="Preparing to generate modules...")

            config = _get_default_ai_config(user_id)
            if not config:
                task_store.update(task_id, status="failed", error="No AI configuration found")
                return

            qa_messages = QAMessage.query.filter_by(requirement_id=requirement.id).all()
            qa_context = [{"role": m.role, "content": m.content} for m in qa_messages]

            # RAG: retrieve similar module structures from production knowledge base
            rag_context = self._retrieve_rag_context(
                requirement.content, chunk_type="module"
            )
            if rag_context:
                logger.debug("RAG context injected for module generation: req_id=%d", requirement_id)

            # RAG: retrieve relevant business code as implementation reference
            code_context = self._retrieve_code_context(requirement.content)
            if code_context:
                logger.debug("Code context injected for module generation: req_id=%d", requirement_id)

            ai_service = AIService(config, user_id=user_id, requirement_id=requirement.id)
            messages = PromptService.generate_modules_prompt(
                requirement.content, qa_context, rag_context=rag_context,
                code_context=code_context,
            )

            task_store.update(task_id, progress=30, message="AI is generating module breakdown...")
            response = ai_service.chat(messages, json_mode=True, task_type="module_gen")
            result = _parse_json_response(response)

            task_store.update(task_id, progress=60, message="Parsing and saving modules...")
            modules = result.get("modules", [])

            # Clean up orphaned embeddings for existing modules
            old_module_ids = [m.id for m in Module.query.filter_by(requirement_id=requirement_id).all()]
            _cleanup_embeddings_for_modules(old_module_ids)
            # Clear existing modules
            Module.query.filter_by(requirement_id=requirement_id).delete()
            db.session.commit()

            # Save new modules
            for i, m in enumerate(modules):
                module = Module(
                    requirement_id=requirement_id,
                    name=m.get("module_name", f"Module {i+1}"),
                    description=m.get("description", ""),
                    key_points=json.dumps(m.get("key_points", []), ensure_ascii=False),
                    order=i,
                )
                db.session.add(module)
            db.session.commit()

            requirement.status = "completed"
            db.session.commit()

            modules_data = [m.to_dict() for m in Module.query.filter_by(requirement_id=requirement_id).order_by(Module.order).all()]
            task_store.update(
                task_id, status="completed", progress=100,
                message=f"Generated {len(modules_data)} modules",
                result={"modules": modules_data},
            )
            logger.info("Modules generated: req_id=%d count=%d", requirement_id, len(modules_data))

        except Exception as e:
            logger.error("Module generation failed: req_id=%d error=%s", requirement_id, str(e))
            task_store.update(task_id, status="failed", error=str(e))

    def generate_cases_task(self, module_id, user_id, task_id):
        """Step 4: Generate test cases for a module in background thread."""
        try:
            module = db.session.get(Module, module_id)
            if not module:
                task_store.update(task_id, status="failed", error="Module not found")
                return

            requirement = db.session.get(Requirement, module.requirement_id)

            task_store.update(task_id, status="running", progress=10, message=f"Generating cases for: {module.name}")

            config = _get_default_ai_config(user_id)
            if not config:
                task_store.update(task_id, status="failed", error="No AI configuration found")
                return

            # RAG: retrieve similar test cases from production knowledge base
            rag_query = f"{module.name}\n{module.description or ''}"
            rag_context = self._retrieve_rag_context(rag_query, chunk_type="test_case")
            if rag_context:
                logger.debug("RAG context injected for case generation: module_id=%d", module_id)

            # RAG: retrieve relevant business code as implementation reference
            code_context = self._retrieve_code_context(rag_query)
            if code_context:
                logger.debug("Code context injected for case generation: module_id=%d", module_id)

            ai_service = AIService(config, user_id=user_id, requirement_id=requirement.id if requirement else None)
            messages = PromptService.generate_cases_prompt(
                requirement.content if requirement else "",
                module.name,
                module.description or "",
                json.loads(module.key_points) if module.key_points else [],
                rag_context=rag_context,
                code_context=code_context,
            )

            task_store.update(task_id, progress=40, message=f"AI is generating test cases for: {module.name}")
            response = ai_service.chat(messages, json_mode=True, task_type="case_gen")
            result = _parse_json_response(response)

            task_store.update(task_id, progress=70, message="Parsing and saving test cases...")
            cases = result.get("test_cases", [])

            # Clean up orphaned embeddings for existing cases
            old_case_ids = [c.id for c in TestCase.query.filter_by(module_id=module_id).all()]
            _cleanup_embeddings_for_cases(old_case_ids)
            # Clear existing cases
            TestCase.query.filter_by(module_id=module_id).delete()
            db.session.commit()

            # Save new cases
            for i, c in enumerate(cases):
                case = TestCase(
                    module_id=module_id,
                    title=c.get("title", f"Test Case {i+1}"),
                    preconditions=c.get("preconditions", ""),
                    steps_json=json.dumps(c.get("steps", []), ensure_ascii=False),
                    expected_result=c.get("expected_result", ""),
                    priority=c.get("priority", "medium"),
                    case_type=c.get("case_type", "functional"),
                    order=i,
                )
                db.session.add(case)
            db.session.commit()

            # Incremental index new cases for production projects
            saved_cases = TestCase.query.filter_by(module_id=module_id).all()
            self._incremental_index_cases(saved_cases, requirement)

            cases_data = [c.to_dict() for c in TestCase.query.filter_by(module_id=module_id).order_by(TestCase.order).all()]
            task_store.update(
                task_id, status="completed", progress=100,
                message=f"Generated {len(cases_data)} test cases",
                result={"cases": cases_data},
            )
            logger.info("Cases generated: module_id=%d count=%d", module_id, len(cases_data))

        except Exception as e:
            logger.error("Case generation failed: module_id=%d error=%s", module_id, str(e))
            task_store.update(task_id, status="failed", error=str(e))

    def generate_all_cases_task(self, requirement_id, user_id, task_id):
        """Generate cases for all modules of a requirement sequentially."""
        try:
            requirement = db.session.get(Requirement, requirement_id)
            if not requirement:
                task_store.update(task_id, status="failed", error="Requirement not found")
                return

            modules = Module.query.filter_by(requirement_id=requirement_id).order_by(Module.order).all()
            if not modules:
                task_store.update(task_id, status="failed", error="No modules found. Generate modules first.")
                return

            config = _get_default_ai_config(user_id)
            if not config:
                task_store.update(task_id, status="failed", error="No AI configuration found")
                return

            total = len(modules)
            all_cases = []

            for i, module in enumerate(modules):
                task_store.update(
                    task_id, status="running",
                    progress=int(i / total * 90),
                    message=f"Generating cases for module {i+1}/{total}: {module.name}",
                )

                # RAG: retrieve similar test cases from production knowledge base
                rag_query = f"{module.name}\n{module.description or ''}"
                rag_context = self._retrieve_rag_context(rag_query, chunk_type="test_case")
                if rag_context:
                    logger.debug("RAG context injected for case generation (all): module_id=%d", module.id)

                # RAG: retrieve relevant business code as implementation reference
                code_context = self._retrieve_code_context(rag_query)
                if code_context:
                    logger.debug("Code context injected for case generation (all): module_id=%d", module.id)

                ai_service = AIService(config, user_id=user_id, requirement_id=requirement_id)
                messages = PromptService.generate_cases_prompt(
                    requirement.content,
                    module.name,
                    module.description or "",
                    json.loads(module.key_points) if module.key_points else [],
                    rag_context=rag_context,
                    code_context=code_context,
                )

                response = ai_service.chat(messages, json_mode=True, task_type="case_gen")
                result = _parse_json_response(response)
                cases = result.get("test_cases", [])

                # Clean up orphaned embeddings for existing cases
                old_case_ids = [c.id for c in TestCase.query.filter_by(module_id=module.id).all()]
                _cleanup_embeddings_for_cases(old_case_ids)
                # Clear and save cases for this module
                TestCase.query.filter_by(module_id=module.id).delete()
                db.session.commit()

                for j, c in enumerate(cases):
                    case = TestCase(
                        module_id=module.id,
                        title=c.get("title", f"Test Case {j+1}"),
                        preconditions=c.get("preconditions", ""),
                        steps_json=json.dumps(c.get("steps", []), ensure_ascii=False),
                        expected_result=c.get("expected_result", ""),
                        priority=c.get("priority", "medium"),
                        case_type=c.get("case_type", "functional"),
                        order=j,
                    )
                    db.session.add(case)
                db.session.commit()

                # Incremental index new cases for production projects
                saved_cases = TestCase.query.filter_by(module_id=module.id).all()
                self._incremental_index_cases(saved_cases, requirement)

                module_cases = TestCase.query.filter_by(module_id=module.id).order_by(TestCase.order).all()
                all_cases.extend([c.to_dict() for c in module_cases])

            task_store.update(
                task_id, status="completed", progress=100,
                message=f"Generated {len(all_cases)} test cases across {total} modules",
                result={"cases": all_cases, "module_count": total},
            )
            logger.info("All cases generated: req_id=%d total_cases=%d", requirement_id, len(all_cases))

        except Exception as e:
            logger.error("All case generation failed: req_id=%d error=%s", requirement_id, str(e))
            task_store.update(task_id, status="failed", error=str(e))

    def regenerate_task(self, target_type, target_id, reason, description, user_id, task_id):
        """Step 5: Regenerate cases or module in background thread."""
        try:
            config = _get_default_ai_config(user_id)
            if not config:
                task_store.update(task_id, status="failed", error="No AI configuration found")
                return

            task_store.update(task_id, status="running", progress=20, message="Preparing regeneration...")

            if target_type == "case":
                case = db.session.get(TestCase, target_id)
                if not case:
                    task_store.update(task_id, status="failed", error="Test case not found")
                    return

                module = db.session.get(Module, case.module_id)
                requirement = db.session.get(Requirement, module.requirement_id) if module else None

                original_content = json.dumps(case.to_dict(), ensure_ascii=False, indent=2)
                ai_service = AIService(config, user_id=user_id,
                                       requirement_id=requirement.id if requirement else None)
                messages = PromptService.regenerate_prompt(
                    "case", original_content, reason, description,
                    requirement.content if requirement else None,
                )

                task_store.update(task_id, progress=50, message="AI is regenerating test case...")
                response = ai_service.chat(messages, json_mode=True, task_type="regen")
                result = _parse_json_response(response)
                new_cases = result.get("test_cases", [])

                if new_cases:
                    new_case = new_cases[0]
                    # Log regeneration
                    regen_log = RegenerationLog(
                        target_type="case",
                        target_id=target_id,
                        reason=reason,
                        description=description,
                        old_snapshot=original_content,
                        new_snapshot=json.dumps(new_case, ensure_ascii=False),
                        status="completed",
                        user_id=user_id,
                    )
                    db.session.add(regen_log)

                    # Update case
                    case.title = new_case.get("title", case.title)
                    case.preconditions = new_case.get("preconditions", case.preconditions)
                    case.steps_json = json.dumps(new_case.get("steps", []), ensure_ascii=False)
                    case.expected_result = new_case.get("expected_result", case.expected_result)
                    case.priority = new_case.get("priority", case.priority)
                    case.case_type = new_case.get("case_type", case.case_type)
                    db.session.commit()

                    task_store.update(
                        task_id, status="completed", progress=100,
                        message="Test case regenerated",
                        result={"case": case.to_dict()},
                    )
                else:
                    task_store.update(task_id, status="failed", error="AI returned no cases")

            elif target_type == "module":
                module = db.session.get(Module, target_id)
                if not module:
                    task_store.update(task_id, status="failed", error="Module not found")
                    return

                requirement = db.session.get(Requirement, module.requirement_id)
                original_content = json.dumps(module.to_dict(), ensure_ascii=False, indent=2)

                ai_service = AIService(config, user_id=user_id,
                                       requirement_id=module.requirement_id)
                messages = PromptService.regenerate_prompt(
                    "module", original_content, reason, description,
                    requirement.content if requirement else None,
                )

                task_store.update(task_id, progress=50, message="AI is regenerating module...")
                response = ai_service.chat(messages, json_mode=True, task_type="regen")
                result = _parse_json_response(response)

                # Log regeneration
                regen_log = RegenerationLog(
                    target_type="module",
                    target_id=target_id,
                    reason=reason,
                    description=description,
                    old_snapshot=original_content,
                    new_snapshot=json.dumps(result, ensure_ascii=False),
                    status="completed",
                    user_id=user_id,
                )
                db.session.add(regen_log)

                # Update module
                module.name = result.get("module_name", module.name)
                module.description = result.get("description", module.description)
                module.key_points = json.dumps(result.get("key_points", []), ensure_ascii=False)
                db.session.commit()

                task_store.update(
                    task_id, status="completed", progress=100,
                    message="Module regenerated",
                    result={"module": module.to_dict(include_cases=True)},
                )

            logger.info("Regeneration completed: type=%s id=%d", target_type, target_id)

        except Exception as e:
            logger.error("Regeneration failed: type=%s id=%d error=%s", target_type, target_id, str(e))
            task_store.update(task_id, status="failed", error=str(e))


case_service = CaseService()
