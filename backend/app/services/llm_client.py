"""大模型客户端：封装 DeepSeek API（OpenAI 兼容格式），只处理真实调用

Mock 逻辑在 prompts.py 中，由调用方按 settings.LLM_MOCK 分支选择。
"""
import json

import httpx

from ..config import settings


class LLMError(Exception):
    """大模型调用或返回解析失败"""


def chat_json(system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> dict:
    """调用 DeepSeek 并要求返回 JSON 对象

    返回解析后的 dict；失败时抛出 LLMError。
    """
    if not settings.DEEPSEEK_API_KEY:
        raise LLMError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写，或保持 LLM_MOCK=true")

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},  # DeepSeek 的 JSON 模式
    }
    try:
        resp = httpx.post(
            f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
            json=body,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMError(f"大模型调用失败：{e}") from e
