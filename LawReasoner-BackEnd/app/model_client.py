"""OpenAI-compatible chat model client."""

import httpx

from app.config import Settings


class ModelUnavailable(RuntimeError):
    pass


class ChatModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        if not self.settings.llm_api_key.get_secret_value():
            raise ModelUnavailable("尚未配置 LAW_LLM_API_KEY，Agent 无法调用模型")
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout) as client:
                response = await client.post(
                    f"{self.settings.llm_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}"},
                    json=payload,
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ModelUnavailable("模型服务暂时不可用，请检查模型配置和连接") from exc
