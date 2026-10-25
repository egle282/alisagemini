import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    @property
    def gemini_base_url(self) -> Optional[str]:
        url = os.getenv("GEMINI_BASE_URL", "").strip()
        return url if url else None

    @property
    def temperature(self) -> float:
        return float(os.getenv("TEMPERATURE", "0.3"))

    @property
    def max_output_tokens(self) -> int:
        return int(os.getenv("MAX_OUTPUT_TOKENS", "350"))

    @property
    def max_response_length(self) -> int:
        return int(os.getenv("MAX_RESPONSE_LENGTH", "600"))

    @property
    def gemini_timeout_seconds(self) -> float:
        return float(os.getenv("GEMINI_TIMEOUT_SECONDS", "2.7"))

    @property
    def port(self) -> int:
        return int(os.getenv("PORT", "8000"))

    system_instruction: str = (
        "<role>\n"
        "Ты — голосовой ассистент, подключенный к Алисе. Отвечай кратко и по делу.\n"
        "</role>\n\n"
        "<constraints>\n"
        "1. Максимальная длина ответа: 600 символов (для озвучивания).\n"
        "2. Если пользователь просит код — верни ТОЛЬКО код без пояснений, если не попросят иного.\n"
        "3. Не используй markdown-разметку в ответе (Алиса не умеет её читать).\n"
        "4. Если вопрос требует длинного ответа — дай краткую суть и предложи уточнить детали.\n"
        "</constraints>"
    )

    timeout_fallback_message: str = (
        "Думаю дольше обычного. Спроси что-нибудь покороче или повтори позже."
    )
    api_error_fallback_message: str = (
        "Сервис временно недоступен. Попробуй позже."
    )
    empty_query_message: str = (
        "Я тебя не расслышала. Повтори, пожалуйста."
    )
    welcome_message: str = (
        "Привет! Я подключена к Gemini. Спроси меня о чём угодно, включая код."
    )


settings = Settings()
