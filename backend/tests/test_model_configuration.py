"""Offline checks for model settings, request shape and safe error messages."""

import json
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.domain.contract_workflow import NegotiationAnalysis
from app.model_client import ChatModel, ModelUnavailable


class ModelSettingsTests(TestCase):
    def test_model_provider_must_be_explicitly_configured(self):
        settings = Settings(_env_file=None, llm_base_url="", llm_model="", llm_api_key=SecretStr(""))
        self.assertFalse(settings.model_configured)
        self.assertEqual(
            set(settings.missing_model_settings), {"LAW_LLM_BASE_URL", "LAW_LLM_MODEL", "LAW_LLM_API_KEY"}
        )

    def test_remote_endpoint_requires_https(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, llm_base_url="http://models.example.com/v1")

    def test_loopback_endpoint_can_use_http(self):
        settings = Settings(_env_file=None, llm_base_url="http://127.0.0.1:8001/v1")
        self.assertEqual(settings.llm_base_url, "http://127.0.0.1:8001/v1")

    def test_full_completion_url_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, llm_base_url="https://models.example.com/v1/chat/completions")

    def test_generation_controls_are_validated(self):
        for options in ({"llm_thinking_mode": "automatic"}, {"llm_max_tokens": 0}, {"llm_temperature": 3}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                Settings(_env_file=None, **options)


class ChatModelTests(IsolatedAsyncioTestCase):
    async def test_missing_key_does_not_send_request(self):
        settings = Settings(_env_file=None, llm_api_key=SecretStr(""))
        with self.assertRaisesRegex(ModelUnavailable, "backend/.env|后端 .env"):
            await ChatModel(settings).complete([{"role": "user", "content": "测试"}])

    async def test_request_uses_backend_credential_and_json_mode(self):
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(str(request.url), "https://models.example.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-only-key")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "example-model")
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertNotIn("tools", payload)
            self.assertNotIn("thinking", payload)
            return httpx.Response(200, json={"choices": [{"message": {"content": "测试回复"}}]})

        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://models.example.com/v1",
            llm_model="example-model",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            response = await ChatModel(settings, client).complete(
                [{"role": "user", "content": "测试"}], {"type": "json_object"}
            )
        self.assertEqual(response["content"], "测试回复")

    async def test_deepseek_flash_uses_explicit_non_thinking_json_payload(self):
        def respond(request):
            self.assertEqual(str(request.url), "https://api.deepseek.com/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-only-key")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "deepseek-flash")
            self.assertEqual(payload["thinking"], {"type": "disabled"})
            self.assertEqual(payload["max_tokens"], 4096)
            self.assertEqual(payload["temperature"], 0.3)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})

        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            llm_thinking_mode="disabled",
            llm_max_tokens=4096,
            llm_temperature=0.3,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            response = await ChatModel(settings, client).complete(
                [{"role": "user", "content": "Return JSON"}], {"type": "json_object"}
            )
        self.assertEqual(json.loads(response["content"]), {"ok": True})

    async def test_enabled_thinking_does_not_send_temperature(self):
        def respond(request):
            payload = json.loads(request.content)
            self.assertEqual(payload["thinking"], {"type": "enabled"})
            self.assertNotIn("temperature", payload)
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            llm_thinking_mode="enabled",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await ChatModel(settings, client).complete([])

    async def test_truncated_output_fails_without_repeating_paid_requests(self):
        calls = []

        def respond(request):
            calls.append(request)
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}
            )

        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(ModelUnavailable, "LAW_LLM_MAX_TOKENS"):
                await ChatModel(settings, client).generate_structured("输出 JSON", {}, NegotiationAnalysis)
        self.assertEqual(len(calls), 1)

    async def test_upstream_auth_error_never_exposes_key(self):
        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://models.example.com/v1",
            llm_model="example-model",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401))) as client:
            with self.assertRaises(ModelUnavailable) as raised:
                await ChatModel(settings, client).complete([])
        self.assertIn("LAW_LLM_API_KEY", str(raised.exception))
        self.assertNotIn("test-only-key", str(raised.exception))

    async def test_invalid_structured_output_is_retried_and_validated(self):
        calls = []

        def respond(request):
            payload = json.loads(request.content)
            calls.append(payload)
            content = (
                "not-json"
                if len(calls) == 1
                else json.dumps(
                    {"summary": "设备采购协商", "contract_type": "买卖", "search_query": "设备买卖合同"}
                )
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://models.example.com/v1",
            llm_model="example-model",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await ChatModel(settings, client).generate_structured(
                "提取交易类型", {"source": "协商记录"}, NegotiationAnalysis
            )
        self.assertEqual(result.contract_type, "买卖")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})

    async def test_invalid_structured_output_does_not_retry_indefinitely(self):
        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://models.example.com/v1",
            llm_model="example-model",
        )
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ModelUnavailable):
                await ChatModel(settings, client).generate_structured("分析", {}, NegotiationAnalysis)
        self.assertEqual(len(requests), settings.structured_output_retries + 1)
