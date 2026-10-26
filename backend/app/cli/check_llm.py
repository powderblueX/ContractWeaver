"""Opt-in provider check with synthetic data only; one small billed API request."""

import asyncio
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings, get_settings
from app.model_client import ChatModel, ModelUnavailable


class ConnectionResult(BaseModel):
    """保存脱敏连接检查结论，不包含服务商密钥。"""

    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


async def check_connection(settings: Settings) -> None:
    """Do not read workspaces, send contracts, log credentials or retry billing."""
    probe_settings = settings.model_copy(update={"structured_output_retries": 0})
    async with ChatModel(probe_settings) as model:
        await model.generate_structured(
            '这是 API 连通性测试。仅返回 JSON：{"status":"ok"}。',
            {"purpose": "configuration_smoke_test"},
            ConnectionResult,
        )


def main() -> int:
    """读取运行配置并执行合成数据连通检查；实际检查可能产生一次模型费用。"""
    try:
        asyncio.run(check_connection(get_settings()))
    except ValidationError:
        print("Invalid backend configuration; check .env settings.", file=sys.stderr)
        return 1
    except ModelUnavailable as error:
        print(str(error), file=sys.stderr)
        return 1
    print("LLM connection and structured JSON check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
