"""大模型客户端：封装大模型 API（OpenAI 兼容格式），只处理真实调用

Mock 逻辑在 prompts.py 中，由调用方按 settings.LLM_MOCK 分支选择。
"""
import json
import math

import httpx

from ..config import settings


REQUEST_TIMEOUT = 120


class LLMError(Exception):
    """大模型调用或返回解析失败"""


def _content(system_prompt, messages, max_tokens, *, json_mode=False):
    if not settings.DEEPSEEK_API_KEY.strip():
        raise LLMError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写，或保持 LLM_MOCK=true")

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body['response_format'] = {'type':'json_object'}
    try:
        resp = httpx.post(
            f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions",
            json=body,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMError('大模型请求超时，请稍后重试') from exc
    except httpx.HTTPStatusError as exc:
        # 不透传上游正文/URL，避免错误页或认证信息进入页面与业务日志。
        raise LLMError(f'大模型服务请求失败（HTTP {exc.response.status_code}），请检查配置或稍后重试') from exc
    except (httpx.HTTPError,httpx.InvalidURL) as exc:
        raise LLMError('无法连接大模型服务，请检查后端服务地址或稍后重试') from exc
    try:
        data = resp.json()
        choice = data['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise LLMError('大模型输出被截断，请缩小内容范围后重试')
        content = choice['message']['content']
        if not isinstance(content,str) or not content.strip():
            raise LLMError('大模型未返回有效文字，请重试')
        return content.strip()
    except (ValueError,KeyError,IndexError,TypeError,AttributeError) as exc:
        raise LLMError('大模型响应格式不正确，请重试') from exc


def chat_json(system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> dict:
    """真实HTTP调用；JSON必须是对象，数组/无效内容由调用方按原策略重试。"""
    content = _content(system_prompt,[{'role':'user','content':user_prompt}],max_tokens,json_mode=True)
    def finite_number(value):
        number=float(value)
        if not math.isfinite(number):
            raise ValueError('non-finite number')
        return number
    def invalid_constant(value):
        raise ValueError('invalid JSON numeric constant')
    try:
        result = json.loads(content,parse_float=finite_number,parse_constant=invalid_constant)
    except (ValueError,RecursionError) as exc:
        raise LLMError('大模型未返回有效JSON对象，请重试') from exc
    if not isinstance(result,dict):
        raise LLMError('大模型返回的JSON必须是对象，请重试')
    return result


def chat_text(system_prompt: str, messages: list[dict], max_tokens: int = 1200) -> str:
    """真实HTTP多轮问答，空内容和非文字内容统一为可恢复错误。"""
    return _content(system_prompt,messages,max_tokens)
