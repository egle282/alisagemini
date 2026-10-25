import asyncio
import logging
from typing import Any, List, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import settings

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper around google-genai client for Alice skill with timeout and fallback protection."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key
        self._model = model
        self._client = None
        self._timeout: Optional[float] = None

    @property
    def api_key(self) -> str:
        return self._api_key or settings.gemini_api_key

    @property
    def model(self) -> str:
        return self._model or settings.gemini_model

    @property
    def timeout(self) -> float:
        if self._timeout is not None:
            return self._timeout
        return settings.gemini_timeout_seconds

    @timeout.setter
    def timeout(self, value: float) -> None:
        self._timeout = value

    @property
    def client(self):
        if self._client is not None:
            return self._client
        key = self.api_key
        if key:
            http_opts = None
            if settings.gemini_base_url:
                http_opts = types.HttpOptions(base_url=settings.gemini_base_url)
            return genai.Client(api_key=key, http_options=http_opts)
        return None

    @client.setter
    def client(self, value: Any) -> None:
        self._client = value

    @client.deleter
    def client(self) -> None:
        self._client = None

    def _clean_markdown_for_speech(self, text: str) -> str:
        """Strip markdown markers (like backticks, asterisks) so Alice speaks naturally."""
        cleaned = text.replace("```python", "").replace("```", "").strip()
        cleaned = cleaned.replace("**", "").replace("*", "")
        if len(cleaned) > settings.max_response_length:
            cleaned = cleaned[: settings.max_response_length].rstrip() + "..."
        return cleaned

    async def generate_response(self, user_text: str, history: Optional[List[dict]] = None) -> str:
        """
        Generate response from Gemini model within timeout.
        Returns clean text or fallback message on timeout/API error.
        """
        if not user_text or not user_text.strip():
            return settings.empty_query_message

        if not self.client:
            logger.error("Attempted to generate response without GEMINI_API_KEY")
            return settings.api_error_fallback_message

        config = types.GenerateContentConfig(
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            system_instruction=settings.system_instruction,
        )

        # Build contents from history if provided (last 3 interactions)
        contents = []
        if history:
            for item in history[-3:]:
                role = item.get("role", "user")
                part_text = item.get("text", "")
                if part_text:
                    contents.append(types.Content(role=role, parts=[types.Part.from_text(text=part_text)]))

        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

        try:
            # Wrap Gemini generation in thread with strict timeout <= 2.5s
            client = self.client
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model,
                    contents=contents,
                    config=config,
                ),
                timeout=self.timeout,
            )

            generated_text = (response.text or "").strip()
            if not generated_text:
                return settings.empty_query_message

            return self._clean_markdown_for_speech(generated_text)

        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            logger.warning("Gemini API call timed out or cancelled (%s: %s) after %s seconds", type(e).__name__, str(e), self.timeout)
            return settings.timeout_fallback_message
        except APIError as e:
            logger.error("Gemini API error (%s): %s", getattr(e, "code", "unknown"), str(e))
            return f"Ошибка Gemini API ({getattr(e, 'code', 'unknown')}): {str(e)[:250]}"
        except BaseException as e:
            logger.exception("Unexpected error calling Gemini API: %s", str(e))
            return f"Ошибка сервиса ({type(e).__name__}): {str(e)[:250]}"


gemini_client = GeminiClient()
