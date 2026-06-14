# models.md — LLM Provider Configuration & Tiers

## Overview

Cave uses LiteLLM as a unified abstraction layer over all LLM providers. Users can either bring their own API keys (BYOK) or use platform-managed keys on a credits system.

---

## Supported Providers

| Provider | Models | Use Case | Notes |
|----------|--------|----------|-------|
| **Anthropic** | claude-sonnet-4-6, claude-haiku-4-5 | Orchestrator, Security Agent | Best reasoning, highest cost |
| **OpenAI** | gpt-4o, gpt-4o-mini | General fallback | Strong code generation |
| **DeepSeek** | deepseek-coder-v2, deepseek-chat | Backend/Frontend agents | Best cost/quality for code |
| **NVIDIA NIM** | nemotron-4-340b, llama-3.1-nemotron | Enterprise on-prem | Custom base URL per user |
| **Together AI** | Llama 3.1 405B, Qwen 2.5 Coder | Budget tier | Open source, low cost |
| **Fireworks AI** | DeepSeek V3, Llama 3.3 | Budget tier | Fast inference |
| **Ollama (local)** | Any GGUF model | Self-hosted | Dev/enterprise use |
| **Custom OpenAI-compatible** | Any | Enterprise | User provides base URL + key |

---

## Subscription Tiers

### Free Tier
- 100 credits on signup (~2-3 project runs)
- Platform provides API access (budget models)
- Model: DeepSeek Coder V2 for all agents
- Max 1 concurrent run
- No BYOK

### Pro Tier ($29/month or credit top-ups)
- 500 credits/month included
- Access to premium models (Claude, GPT-4o)
- BYOK enabled — use your own keys, credits only charged for platform usage
- Per-agent model assignment
- Max 3 concurrent runs

### Enterprise Tier (custom pricing)
- Unlimited runs
- NVIDIA NIM / private endpoint support
- On-prem deployment option
- SLA + dedicated support
- Custom model fine-tuning integration

---

## Credit Pricing

Credits are consumed per agent call based on model tier:

| Model Tier | Cost per 1K input tokens | Cost per 1K output tokens | Platform markup |
|------------|--------------------------|---------------------------|-----------------|
| Budget (DeepSeek, Llama) | 0.5 credits | 1 credit | 30% |
| Standard (GPT-4o-mini) | 1 credit | 2 credits | 25% |
| Premium (Claude Sonnet, GPT-4o) | 3 credits | 6 credits | 20% |
| BYOK | 0 credits (free) | 0 credits | Platform fee only |

**Estimated credits per full project run (4 agents, no retries):**
- Budget models: ~15–25 credits
- Premium models: ~60–120 credits

---

## LiteLLM Configuration

```python
# src/orchestrator/llm_adapter.py

import litellm
from typing import Optional
from src.models import ModelConfig

litellm.set_verbose = False

# Provider routing map
PROVIDER_PREFIXES = {
    "anthropic": "claude-",
    "openai": "gpt-",
    "deepseek": "deepseek/",
    "nvidia": "nvidia_nim/",
    "together": "together_ai/",
    "fireworks": "fireworks_ai/",
    "ollama": "ollama/",
    "custom": "",  # user provides full model string
}

async def call_llm(
    messages: list,
    model_config: ModelConfig,
    tools: Optional[list] = None,
    max_tokens: int = 4096,
) -> dict:
    """
    Unified LLM call with automatic failover.
    model_config comes from the user's saved model configuration.
    """
    kwargs = {
        "model": model_config.litellm_model_string,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,  # low temp for code generation
    }

    # BYOK: inject user's key
    if model_config.api_key_encrypted:
        kwargs["api_key"] = decrypt(model_config.api_key_encrypted)

    # Custom base URL (NVIDIA NIM, Ollama, etc.)
    if model_config.base_url:
        kwargs["base_url"] = model_config.base_url

    if tools:
        kwargs["tools"] = tools

    # Primary attempt
    try:
        response = await litellm.acompletion(**kwargs)
        return response
    except litellm.exceptions.ServiceUnavailableError:
        # Failover to secondary model
        return await _failover_call(messages, tools, max_tokens)
    except litellm.exceptions.RateLimitError:
        # Wait and retry once
        await asyncio.sleep(10)
        return await litellm.acompletion(**kwargs)


async def _failover_call(messages, tools, max_tokens):
    """Falls back to platform's secondary model on provider failure."""
    return await litellm.acompletion(
        model="deepseek/deepseek-chat",
        messages=messages,
        tools=tools,
        max_tokens=max_tokens,
        api_key=settings.DEEPSEEK_API_KEY,
    )
```

---

## Per-Agent Model Assignment

Users can assign different models to different agents. Example configuration stored in `model_configs` table:

```json
{
  "user_id": "abc-123",
  "assignments": {
    "orchestrator": "claude-sonnet-4-6",
    "database_agent": "deepseek/deepseek-coder-v2",
    "backend_agent": "deepseek/deepseek-coder-v2",
    "frontend_agent": "gpt-4o-mini",
    "security_agent": "claude-sonnet-4-6"
  }
}
```

**Recommended defaults by agent:**

| Agent | Recommended Model | Why |
|-------|------------------|-----|
| Orchestrator | Claude Sonnet | Best at decomposition and planning |
| Database Agent | DeepSeek Coder V2 | Strong SQL, cheap |
| Backend Agent | DeepSeek Coder V2 | Best code/cost ratio |
| Frontend Agent | GPT-4o-mini | Good React, low cost |
| Security Agent | Claude Sonnet | Best at vulnerability reasoning |

---

## Adding a New Provider

To add any OpenAI-compatible provider:

1. User goes to Dashboard → Settings → Models → Add Provider
2. Enters: Provider Name, Base URL, API Key, Model Name
3. System stores encrypted key in `model_configs` table
4. LiteLLM routes automatically via `base_url` override

**Example: Adding a local Ollama instance**
```
Provider: Custom
Base URL: http://host.docker.internal:11434
Model: ollama/qwen2.5-coder:32b
API Key: (leave blank)
```

**Example: Adding NVIDIA NIM**
```
Provider: NVIDIA NIM
Base URL: https://integrate.api.nvidia.com/v1
Model: nvidia_nim/meta/llama-3.1-70b-instruct
API Key: nvapi-...
```

---

## Cost Tracking Implementation

Every LLM call logs usage to the `llm_usage` table:

```python
# Automatically captured via LiteLLM callback
def log_llm_usage(response, project_id, user_id, agent_name):
    usage = response.usage
    cost = litellm.completion_cost(completion_response=response)

    db.execute("""
        INSERT INTO llm_usage 
        (project_id, user_id, agent, model, input_tokens, output_tokens, cost_usd)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, project_id, user_id, agent_name,
        response.model, usage.prompt_tokens,
        usage.completion_tokens, cost)

    # Deduct credits if using platform keys
    if not user_brought_own_key:
        deduct_credits(user_id, calculate_credits(cost, model_tier))
```
