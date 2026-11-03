"""大模型客户端：封装大模型 API（OpenAI 兼容格式），只处理真实调用

Mock 逻辑在 prompts.py 中，由调用方按 settings.LLM_MOCK 分支选择。
"""
import json
import math
import asyncio
import logging
import time
from urllib.parse import urlsplit

import httpx

from ..config import settings


REQUEST_TIMEOUT = settings.LLM_ANALYSIS_TIMEOUT_SECONDS
logger = logging.getLogger('uvicorn.error.model')


def response_stats(data, limit):
    """仅提取用量与长度，不记录提示词、思考正文、资料、Key或响应正文。"""
    def number(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10**9 else None
    usage = data.get('usage') if isinstance(data.get('usage'), dict) else {}
    details = usage.get('completion_tokens_details') if isinstance(usage.get('completion_tokens_details'), dict) else {}
    completion, reasoning = number(usage.get('completion_tokens')), number(details.get('reasoning_tokens'))
    choices = data.get('choices') or []
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get('message') if isinstance(choice.get('message'), dict) else {}
    return {'max_tokens': limit, 'prompt_tokens': number(usage.get('prompt_tokens')),
        'completion_tokens': completion, 'reasoning_tokens': reasoning,
        'answer_tokens': completion - reasoning if completion is not None and reasoning is not None and completion >= reasoning else None,
        'reasoning_chars': len(message.get('reasoning_content')) if isinstance(message.get('reasoning_content'), str) else 0,
        'answer_chars': len(message.get('content')) if isinstance(message.get('content'), str) else 0,
        'finish_reason': choice.get('finish_reason') if choice.get('finish_reason') in ('stop','length','content_filter','tool_calls') else 'unknown'}


class LLMError(Exception):
    """大模型调用或返回解析失败"""
    def __init__(self,message,*,retryable=False,code=''):
        super().__init__(message)
        self.retryable=retryable
        self.code=code


def retry_once(function,*args,**kwargs):
    """画像、问答及周报仅对暂时传输错误重试一次；分析由业务层统一两次校验。"""
    try: return function(*args,**kwargs)
    except LLMError as exc:
        if not exc.retryable: raise
    return function(*args,**kwargs)


async def _post_with_deadline(url,body,headers,timeout=None):
    # wait_for约束总等待；仅read timeout会被上游心跳空行反复续期。
    deadline = REQUEST_TIMEOUT if timeout is None else timeout
    async with httpx.AsyncClient(timeout=deadline) as client:
        return await asyncio.wait_for(client.post(url,json=body,headers=headers),timeout=deadline)


def _content(system_prompt, messages, max_tokens=None, *, json_mode=False, timeout=None):
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
    }
    if max_tokens is not None:
        body['max_tokens'] = max_tokens
    try:
        provider_host = urlsplit(settings.DEEPSEEK_BASE_URL).hostname
    except ValueError:
        provider_host = None
    if (provider_host == 'api.deepseek.com'
            and settings.DEEPSEEK_MODEL.startswith(('deepseek-flash', 'deepseek-v4-'))):
        body['thinking'] = {'type': 'enabled'}
    if json_mode:
        body['response_format'] = {'type':'json_object'}
    from .model_usage import reserve_call
    reserve_call()
    started_at = time.perf_counter()
    try:
        resp = asyncio.run(_post_with_deadline(f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions",body,headers,timeout))
        resp.raise_for_status()
    except (httpx.TimeoutException,TimeoutError) as exc:
        raise LLMError('大模型请求超时，请稍后重试',retryable=True) from exc
    except httpx.HTTPStatusError as exc:
        # 不透传上游正文/URL，避免错误页或认证信息进入页面与业务日志。
        raise LLMError(f'大模型服务请求失败（HTTP {exc.response.status_code}），请检查配置或稍后重试',retryable=exc.response.status_code==429 or exc.response.status_code>=500) from exc
    except httpx.InvalidURL as exc:
        raise LLMError('大模型服务地址不合法，请检查后端配置') from exc
    except httpx.HTTPError as exc:
        raise LLMError('无法连接大模型服务，请检查后端服务地址或稍后重试',retryable=True) from exc
    finally:
        logger.info('model_request_finished elapsed_seconds=%.3f', time.perf_counter() - started_at)
    try:
        data = resp.json()
        logger.info('model_response stats=%s', response_stats(data, max_tokens))
        choice = data['choices'][0]
        if choice.get('finish_reason') == 'length':
            stats = response_stats(data, max_tokens)
            logger.warning('model_response_truncated stats=%s', stats)
            counts = f"；思考 {stats['reasoning_tokens']}、正文 {stats['answer_tokens']} Token" if stats['answer_tokens'] is not None else ''
            limit = str(max_tokens) if max_tokens is not None else '模型平台限制'
            raise LLMError(f'大模型输出被平台截断（{limit}{counts}），未返回完整内容；本次未自动重试，已保存的数据未受影响',code='output_truncated')
        content = choice['message']['content']
        if not isinstance(content,str) or not content.strip():
            raise LLMError('大模型未返回有效文字，请重试')
        return content.strip()
    except (ValueError,KeyError,IndexError,TypeError,AttributeError) as exc:
        raise LLMError('大模型响应格式不正确，请重试') from exc


def chat_json(system_prompt: str, user_prompt: str, max_tokens: int | None = None, *, timeout=None) -> dict:
    """真实HTTP调用；JSON必须是对象，数组/无效内容由调用方按原策略重试。"""
    content = _content(system_prompt,[{'role':'user','content':user_prompt}],max_tokens,json_mode=True,timeout=timeout)
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


def chat_text(system_prompt: str, messages: list[dict], max_tokens: int | None = None) -> str:
    """真实HTTP多轮问答，空内容和非文字内容统一为可恢复错误。"""
    return _content(system_prompt,messages,max_tokens)
