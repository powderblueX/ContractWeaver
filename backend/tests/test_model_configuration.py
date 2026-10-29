"""Offline checks for model settings, request shape and safe error messages."""

import json
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.domain.contract_workflow import NegotiationAnalysis
from app.model_client import ChatModel, ModelUnavailable


class ModelSettingsTests(TestCase):
    """测试夹具或替身：ModelSettingsTests，用于隔离验证本模块行为。"""

    def test_model_provider_must_be_explicitly_configured(self):
        """Verify model provider must be explicitly configured."""
        settings = Settings(_env_file=None, llm_base_url="", llm_model="", llm_api_key=SecretStr(""))
        self.assertFalse(settings.model_configured)
        self.assertEqual(
            set(settings.missing_model_settings), {"LAW_LLM_BASE_URL", "LAW_LLM_MODEL", "LAW_LLM_API_KEY"}
        )

    def test_remote_endpoint_requires_https(self):
        """Verify remote endpoint requires https."""
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, llm_base_url="http://models.example.com/v1")

    def test_loopback_endpoint_can_use_http(self):
        """Verify loopback endpoint can use http."""
        settings = Settings(_env_file=None, llm_base_url="http://127.0.0.1:8001/v1")
        self.assertEqual(settings.llm_base_url, "http://127.0.0.1:8001/v1")

    def test_full_completion_url_is_rejected(self):
        """Verify full completion url is rejected."""
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, llm_base_url="https://models.example.com/v1/chat/completions")

    def test_generation_controls_are_validated(self):
        """Verify generation controls are validated."""
        for options in ({"llm_thinking_mode": "automatic"}, {"llm_max_tokens": 0}, {"llm_temperature": 3}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                Settings(_env_file=None, **options)


class ChatModelTests(IsolatedAsyncioTestCase):
    """测试夹具或替身：ChatModelTests，用于隔离验证本模块行为。"""

    async def test_safe_error_categories_distinguish_transport_provider_and_response(self):
        """连接、服务和返回格式失败具有不同公开分类且不泄露上游正文。"""
        settings = Settings(
            _env_file=None,
            llm_base_url="https://model.example.org",
            llm_api_key="secret-test",
            llm_model="test",
        )
        cases = [
            (httpx.ConnectError("private proxy error"), "model_network"),
            (httpx.ReadTimeout("private timeout"), "model_timeout"),
            (httpx.Response(401, text="secret-test"), "model_auth"),
            (httpx.Response(429, text="private quota detail"), "model_rate_limit"),
            (httpx.Response(500, text="private upstream trace"), "model_provider"),
            (httpx.Response(200, json=[]), "model_response"),
        ]
        for response, expected in cases:
            with self.subTest(code=expected):

                def respond(_):
                    """返回指定错误或模拟响应。"""
                    if isinstance(response, Exception):
                        raise response
                    return response

                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                    with self.assertRaises(ModelUnavailable) as raised:
                        await ChatModel(settings, client).complete([])
                public = raised.exception.public_error()
                self.assertEqual(public["code"], expected)
                self.assertTrue(public["hint"])
                self.assertNotIn("secret-test", json.dumps(public))
                self.assertNotIn("private", json.dumps(public))

    async def test_missing_key_does_not_send_request(self):
        """Verify missing key does not send request."""
        settings = Settings(_env_file=None, llm_api_key=SecretStr(""))
        with self.assertRaisesRegex(ModelUnavailable, "backend/.env|后端 .env"):
            await ChatModel(settings).complete([{"role": "user", "content": "测试"}])

    async def test_request_uses_backend_credential_and_json_mode(self):
        """Verify request uses backend credential and json mode."""

        def respond(request: httpx.Request) -> httpx.Response:
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
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
        """Verify deepseek flash uses explicit non thinking json payload."""

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
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
        """Verify enabled thinking does not send temperature."""

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
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

    async def test_reasoning_only_truncation_does_not_invite_batch_retries(self):
        """Reasoning without answer text must not be logged, parsed or blindly repeated."""
        def respond(_request):
            """Return a synthetic reasoning-only provider cutoff."""
            return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {
                "content": "", "reasoning_content": "private reasoning fixture"}}]})
        settings = Settings(_env_file=None, llm_api_key="fake", llm_base_url="https://example.org", llm_model="fixture")
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ModelUnavailable) as raised:
                await ChatModel(settings, client).complete([])
        self.assertFalse(raised.exception.allow_batch_split)
        self.assertNotIn("private reasoning", str(raised.exception))
        self.assertIn("尚未返回正文", str(raised.exception))

    async def test_truncated_output_fails_without_repeating_paid_requests(self):
        """Verify truncated output fails without repeating paid requests."""
        calls = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
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
            with self.assertRaisesRegex(ModelUnavailable, "长度上限") as raised:
                await ChatModel(settings, client).generate_structured("输出 JSON", {}, NegotiationAnalysis)
        self.assertEqual(raised.exception.code, "output_truncated")
        self.assertEqual(len(calls), 1)

    async def test_upstream_auth_error_never_exposes_key(self):
        """Verify upstream auth error never exposes key."""
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
        """Verify invalid structured output is retried and validated."""
        calls = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
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
        """Verify invalid structured output does not retry indefinitely."""
        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-only-key"),
            llm_base_url="https://models.example.com/v1",
            llm_model="example-model",
        )
        requests = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ModelUnavailable):
                await ChatModel(settings, client).generate_structured("分析", {}, NegotiationAnalysis)
        self.assertEqual(len(requests), settings.structured_output_retries + 1)
