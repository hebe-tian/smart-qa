"""Call log service: automatically records every AI API call."""
import time
import json
import threading
from app.extensions import db
from app.models.ai_call_log import AICallLog
from app.services.logging_service import get_logger

logger = get_logger("call_log")


class CallLogService:
    """Service for recording AI API calls to the database."""

    def __init__(self):
        self._call_map = {}
        self._lock = threading.Lock()

    def start_call(self, ai_config_id, user_id, requirement_id, task_type, model_name, messages):
        """Record the start of an AI call. Returns a call_id (in-memory)."""
        call_id = str(time.time_ns())
        # Store pending record in DB
        log = AICallLog(
            ai_config_id=ai_config_id,
            user_id=user_id,
            requirement_id=requirement_id,
            task_type=task_type,
            model_name=model_name,
            prompt_messages_json=json.dumps(messages, ensure_ascii=False),
            status="running",
        )
        db.session.add(log)
        db.session.commit()
        # Map in-memory call_id to DB record id (thread-safe)
        with self._lock:
            self._call_map[call_id] = {
                "log_id": log.id,
                "start_time": time.time(),
            }
        logger.debug("AI call started: task_type=%s model=%s log_id=%d", task_type, model_name, log.id)
        return call_id

    def end_call(self, call_id, response_content, usage_tokens, status, error_msg=None):
        """Record the end of an AI call."""
        with self._lock:
            call_info = self._call_map.pop(call_id, None)
        if not call_info:
            logger.warning("end_call: call_id %s not found", call_id)
            return

        log_id = call_info["log_id"]
        duration_ms = int((time.time() - call_info["start_time"]) * 1000)

        log = db.session.get(AICallLog, log_id)
        if log:
            log.response_content = response_content
            log.prompt_tokens = usage_tokens.get("prompt_tokens") if usage_tokens else None
            log.completion_tokens = usage_tokens.get("completion_tokens") if usage_tokens else None
            log.total_tokens = usage_tokens.get("total_tokens") if usage_tokens else None
            log.duration_ms = duration_ms
            log.status = status
            log.error_message = error_msg
            db.session.commit()
            logger.debug(
                "AI call ended: log_id=%d status=%s duration=%dms tokens=%s",
                log_id, status, duration_ms,
                usage_tokens.get("total_tokens") if usage_tokens else "N/A",
            )


call_log_service = CallLogService()
