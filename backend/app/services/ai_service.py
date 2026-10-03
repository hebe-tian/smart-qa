"""AI service: OpenAI-compatible API calls with automatic call logging."""
import time
from openai import OpenAI
from app.core.security import decrypt_api_key
from app.services.call_log_service import call_log_service
from app.services.logging_service import get_logger

logger = get_logger("ai")


class AIService:
    """Wrapper around OpenAI SDK for all AI operations. Automatically logs every call."""

    def __init__(self, ai_config, user_id=None, requirement_id=None):
        self.config = ai_config
        self.user_id = user_id
        self.requirement_id = requirement_id
        api_key = decrypt_api_key(ai_config.api_key_encrypted)
        self.client = OpenAI(
            base_url=ai_config.base_url,
            api_key=api_key,
        )
        self.model = ai_config.model
        self.temperature = ai_config.temperature
        self.max_tokens = ai_config.max_tokens

    def chat(self, messages, json_mode=False, task_type="chat"):
        """Synchronous chat completion. Automatically records the call."""
        call_id = call_log_service.start_call(
            ai_config_id=self.config.id,
            user_id=self.user_id,
            requirement_id=self.requirement_id,
            task_type=task_type,
            model_name=self.model,
            messages=messages,
        )

        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            logger.debug("AI chat request: task=%s model=%s msg_count=%d", task_type, self.model, len(messages))

            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            call_log_service.end_call(call_id, content, usage, "success")
            logger.debug("AI chat success: task=%s tokens=%s", task_type, usage)
            return content

        except Exception as e:
            logger.error("AI chat failed: task=%s error=%s", task_type, str(e))
            call_log_service.end_call(call_id, None, None, "failed", str(e))
            raise

    def test_connection(self):
        """Test connection to the AI API. Returns (success: bool, message: str).

        Branches by config_type:
        - embedding: calls the /v1/embeddings endpoint with embedding_model
        - chat: calls /v1/chat/completions with the chat model
        - both: tests chat first, then embedding if chat passes
        """
        config_id = getattr(self.config, "id", None)
        config_name = getattr(self.config, "name", "unknown")
        config_type = getattr(self.config, "config_type", "both") or "both"

        if config_type == "embedding":
            return self._test_embedding_connection(config_id, config_name)

        # chat or both: test chat endpoint first
        chat_ok, chat_msg = self._test_chat_connection(config_id, config_name)

        # both: also test embedding endpoint if chat passed and embedding_model is set
        if config_type == "both" and chat_ok and self.config.embedding_model:
            emb_ok, emb_msg = self._test_embedding_connection(config_id, config_name)
            if not emb_ok:
                logger.warning(
                    "Both-type test: chat passed but embedding failed: config_id=%s chat_model=%s embedding_model=%s",
                    config_id, self.model, self.config.embedding_model,
                )
                return False, f"Chat passed but embedding failed: {emb_msg}"
            return True, f"Chat: {chat_msg} | Embedding: {emb_msg}"

        return chat_ok, chat_msg

    def _test_chat_connection(self, config_id, config_name):
        """Test chat completions endpoint. Returns (success, message)."""
        logger.info(
            "Chat connection test starting: config_id=%s name=%s model=%s base_url=%s",
            config_id, config_name, self.model, self.config.base_url,
        )
        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=200,
            )
            elapsed_ms = int((time.time() - start) * 1000)
            content = response.choices[0].message.content or ""
            # Some reasoning models consume tokens for reasoning_content; content may be empty
            # but the call succeeding still means the connection works
            if "OK" in content.upper():
                logger.info(
                    "Chat connection test passed: config_id=%s model=%s elapsed=%dms response=%s",
                    config_id, self.model, elapsed_ms, content,
                )
                return True, f"Chat OK. Model: {self.model}, Response: {content}"
            logger.info(
                "Chat connection test passed (empty response, reasoning model): config_id=%s model=%s elapsed=%dms",
                config_id, self.model, elapsed_ms,
            )
            return True, f"Chat OK. Model: {self.model} (response may be empty for reasoning models)"
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.error(
                "Chat connection test failed: config_id=%s model=%s elapsed=%dms error=%s",
                config_id, self.model, elapsed_ms, str(e),
            )
            return False, "Chat connection failed. Please verify the API key, model name, and base URL."

    def _test_embedding_connection(self, config_id, config_name):
        """Test embeddings endpoint. Returns (success, message)."""
        embedding_model = self.config.embedding_model
        if not embedding_model:
            return False, "Embedding model is not configured"

        logger.info(
            "Embedding connection test starting: config_id=%s name=%s model=%s base_url=%s",
            config_id, config_name, embedding_model, self.config.base_url,
        )
        start = time.time()
        try:
            response = self.client.embeddings.create(
                model=embedding_model,
                input="connection test",
            )
            elapsed_ms = int((time.time() - start) * 1000)
            dim = len(response.data[0].embedding) if response.data else 0
            logger.info(
                "Embedding connection test passed: config_id=%s model=%s elapsed=%dms dim=%d",
                config_id, embedding_model, elapsed_ms, dim,
            )
            return True, f"Embedding OK. Model: {embedding_model}, dim={dim}"
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.error(
                "Embedding connection test failed: config_id=%s model=%s elapsed=%dms error=%s",
                config_id, embedding_model, elapsed_ms, str(e),
            )
            return False, "Embedding connection failed. Please verify the embedding model name and API key."
