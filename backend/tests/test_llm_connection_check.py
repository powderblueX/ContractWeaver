"""Verify the opt-in probe without using a developer's key or the network."""

import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx
from pydantic import SecretStr

from app.cli.check_llm import check_connection
from app.config import Settings
from app.model_client import ChatModel, ModelUnavailable


class ConnectionCheckTests(IsolatedAsyncioTestCase):
    """测试夹具或替身：ConnectionCheckTests，用于隔离验证本模块行为。"""

    async def test_probe_sends_synthetic_data_once(self):
        """Verify probe sends synthetic data once."""
        requests = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            requests.append(request)
            payload = json.loads(request.content)
            self.assertIn("configuration_smoke_test", payload["messages"][1]["content"])
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"status":"ok"}'}}]})

        settings = Settings(
            _env_file=None,
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            llm_api_key=SecretStr("test-only-key"),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch("app.cli.check_llm.ChatModel", lambda value: ChatModel(value, client)):
                await check_connection(settings)
        self.assertEqual(len(requests), 1)

    async def test_missing_key_fails_before_network(self):
        """Verify missing key fails before network."""
        requests = []
        settings = Settings(
            _env_file=None,
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            llm_api_key=SecretStr(""),
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: requests.append(request))
        ) as client:
            with patch("app.cli.check_llm.ChatModel", lambda value: ChatModel(value, client)):
                with self.assertRaises(ModelUnavailable):
                    await check_connection(settings)
        self.assertEqual(requests, [])
