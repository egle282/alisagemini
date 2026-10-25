import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

import main
from main import app, handler
from config import settings


@pytest.fixture
def sample_alice_request():
    return {
        "meta": {
            "client_id": "ru.yandex.searchplugin/7.16 (none none; android 4.4.2)",
            "locale": "ru-RU",
            "timezone": "UTC",
            "interfaces": {"screen": {}},
        },
        "session": {
            "message_id": 1,
            "session_id": "2eac4854-fce721f3-b8451d09-cd476ac1",
            "skill_id": "test-skill-uuid",
            "user_id": "test-user-id",
            "new": False,
            "application": {"application_id": "test-app-id"},
        },
        "request": {
            "command": "напиши функцию сложения на python",
            "original_utterance": "напиши функцию сложения на python",
            "type": "SimpleUtterance",
        },
        "version": "1.0",
    }


@pytest.fixture
def new_session_alice_request():
    return {
        "meta": {
            "client_id": "ru.yandex.searchplugin/7.16",
            "locale": "ru-RU",
            "timezone": "UTC",
            "interfaces": {},
        },
        "session": {
            "message_id": 0,
            "session_id": "session-1",
            "skill_id": "skill-1",
            "user_id": "user-1",
            "new": True,
            "application": {"application_id": "app-1"},
        },
        "request": {
            "command": "",
            "original_utterance": "",
            "type": "SimpleUtterance",
        },
        "version": "1.0",
    }


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ping_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ping")
        assert response.status_code == 200
        assert response.json()["status"] == "pong"


@pytest.mark.asyncio
async def test_webhook_new_session(new_session_alice_request):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/webhook", json=new_session_alice_request)
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["response"]["text"] == settings.welcome_message
        assert data["response"]["end_session"] is False


@pytest.mark.asyncio
async def test_webhook_successful_gemini_query(sample_alice_request):
    mock_answer = "def add(a, b):\n    return a + b"
    with patch.object(main.gemini_client, "generate_response", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_answer

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhook", json=sample_alice_request)

            assert response.status_code == 200
            data = response.json()
            assert data["response"]["text"] == mock_answer
            mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_gemini_timeout_handling(sample_alice_request):
    async def timeout_side_effect(*args, **kwargs):
        return settings.timeout_fallback_message

    with patch.object(main.gemini_client, "generate_response", side_effect=timeout_side_effect):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhook", json=sample_alice_request)

            assert response.status_code == 200
            data = response.json()
            assert data["response"]["text"] == settings.timeout_fallback_message


@pytest.mark.asyncio
async def test_gemini_client_timeout_returns_fallback():
    def slow_generate(*args, **kwargs):
        import time
        time.sleep(0.3)
        return type("Resp", (), {"text": "slow response"})()

    with patch.object(main.gemini_client, "client") as mock_client:
        mock_client.models.generate_content = slow_generate
        original_timeout = main.gemini_client.timeout
        main.gemini_client.timeout = 0.05
        try:
            res = await main.gemini_client.generate_response("сложный запрос")
            assert res == settings.timeout_fallback_message
        finally:
            main.gemini_client.timeout = original_timeout


def test_yandex_cloud_functions_handler(new_session_alice_request):
    event = {
        "httpMethod": "POST",
        "body": new_session_alice_request,
        "isBase64Encoded": False,
    }
    result = handler(event, None)
    assert result["statusCode"] == 200
    assert "Привет! Я подключена к Gemini" in result["body"]
