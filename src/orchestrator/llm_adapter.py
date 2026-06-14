"""LiteLLM adapter — unified LLM call interface with failover, BYOK, and cost tracking.

Follows the design from docs/models.md. Handles provider routing,
automatic failover, rate-limit retry, and usage logging.
"""

import asyncio
import logging
import os
from typing import Any, Optional

import litellm
from litellm import acompletion

from src.api.models import ModelConfig

logger = logging.getLogger(__name__)

# Provider → LiteLLM model prefix mapping
PROVIDER_PREFIXES: dict[str, str] = {
    "anthropic": "claude-",
    "openai": "gpt-",
    "deepseek": "deepseek/",
    "nvidia": "nvidia_nim/",
    "together": "together_ai/",
    "fireworks": "fireworks_ai/",
    "ollama": "ollama/",
    "custom": "",
}

# Platform-managed fallback key (for failover)
FALLBACK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

litellm.set_verbose = False


async def call_llm(
    messages: list[dict[str, str]],
    model_config: ModelConfig,
    tools: Optional[list[dict[str, Any]]] = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Unified LLM call with automatic failover and cost tracking.

    Args:
        messages: Chat messages in OpenAI format [{"role": ..., "content": ...}].
        model_config: The user's resolved model configuration (provider, model, key, base_url).
        tools: Optional tool definitions for structured output / function calling.
        max_tokens: Maximum output tokens (default 4096 for code generation).

    Returns:
        The raw LiteLLM response dict.

    Raises:
        litellm.exceptions.ServiceUnavailableError: Both primary and fallback failed.
        litellm.exceptions.RateLimitError: After one retry with 10s backoff.
    """
    kwargs: dict[str, Any] = {
        "model": model_config.litellm_model_string,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,  # low temp for deterministic code generation
    }

    # BYOK: inject user's own API key
    if model_config.api_key_encrypted:
        kwargs["api_key"] = _decrypt_key(model_config.api_key_encrypted)

    # Custom base URL (NVIDIA NIM, Ollama, local endpoints)
    if model_config.base_url:
        kwargs["base_url"] = model_config.base_url

    if tools:
        kwargs["tools"] = tools

    # Primary attempt
    try:
        response = await acompletion(**kwargs)
        _log_usage(response, model_config)
        return response
    except litellm.exceptions.ServiceUnavailableError:
        logger.warning(
            "Service unavailable for %s — failing over to deepseek/deepseek-chat",
            model_config.model_name,
        )
        return await _failover_call(messages, tools, max_tokens)
    except litellm.exceptions.RateLimitError:
        logger.info("Rate limited on %s — retrying after 10s backoff", model_config.model_name)
        await asyncio.sleep(10)
        response = await acompletion(**kwargs)
        _log_usage(response, model_config)
        return response


async def _failover_call(
    messages: list[dict[str, str]],
    tools: Optional[list[dict[str, Any]]],
    max_tokens: int,
) -> dict[str, Any]:
    """Fall back to platform's secondary model (DeepSeek Chat) on provider failure."""
    logger.info("Failing over to deepseek/deepseek-chat")
    return await acompletion(
        model="deepseek/deepseek-chat",
        messages=messages,
        tools=tools,
        max_tokens=max_tokens,
        api_key=FALLBACK_API_KEY,
    )


def _decrypt_key(encrypted: str) -> str:
    """Decrypt a stored API key.

    Phase 1: pass-through (encryption layer added in later phase).
    In production this would use Fernet or AWS KMS.
    """
    return encrypted


def _log_usage(response: dict[str, Any], model_config: ModelConfig) -> None:
    """Log LLM usage via LiteLLM's built-in cost calculator.

    The actual DB write happens in the calling agent, which has access
    to the session and project context.
    """
    try:
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = litellm.completion_cost(completion_response=response)

        logger.debug(
            "LLM call: model=%s input=%d output=%d cost=$%.6f",
            model_config.model_name,
            prompt_tokens,
            completion_tokens,
            cost,
        )
    except Exception as exc:
        logger.warning("Failed to log LLM usage: %s", exc)
