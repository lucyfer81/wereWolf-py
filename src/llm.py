from __future__ import annotations

import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class PlayerResponse(BaseModel):
    action: str = Field(description="speech | vote | night_action")
    target: str = Field(description="目标玩家 Seat1-Seat8")
    content: str = Field(description="发言内容或决策理由（<=120字）")
    confidence: str = Field(description="high | medium | low")
    risk_if_wrong: str = Field(default="", description="投错后果（投票时必填）")
    alt_target: str = Field(default="", description="备选目标")
    target_vs_alt_reason: str = Field(default="", description="为什么target比alt_target更可疑")
    evidence: list[str] = Field(default_factory=list, description="证据列表")
    changed_vote: bool = Field(default=False)
    why_change: str = Field(default="")


class GMSummary(BaseModel):
    summary: str = Field(description="当天发言的6行摘要")


class Reflection(BaseModel):
    observation: str = Field(description="你今天观察到的重要信息（<=150字）")
    updated_suspicion: dict[str, float] = Field(
        default_factory=dict,
        description="对其他存活玩家的怀疑度更新 (0.0-1.0)",
    )


def _get_model(model_name: str | None = None) -> OpenAIChatModel:
    base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    name = model_name or os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3.2")
    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    return OpenAIChatModel(name, provider=provider)


def _get_bak_model() -> OpenAIChatModel | None:
    name = os.getenv("SILICONFLOW_BAK_MODEL", "")
    if not name:
        return None
    base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    return OpenAIChatModel(name, provider=provider)


def _get_gm_model() -> OpenAIChatModel:
    base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    name = os.getenv("SILICONFLOW_GM_MODEL", "Qwen/Qwen3-8B")
    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    return OpenAIChatModel(name, provider=provider)


def _siliconflow_settings(temperature: float) -> ModelSettings:
    return ModelSettings(
        temperature=temperature,
        extra_body={"enable_thinking": False},
    )


def create_player_agent(system_prompt: str = "", use_bak: bool = False) -> Agent:
    model = _get_bak_model() if use_bak else _get_model()
    return Agent(
        model=model,
        output_type=PlayerResponse,
        retries=3,
        model_settings=_siliconflow_settings(0.7),
        system_prompt=system_prompt,
    )


def create_gm_agent(system_prompt: str = "") -> Agent:
    model = _get_gm_model()
    return Agent(
        model=model,
        output_type=GMSummary,
        retries=3,
        model_settings=_siliconflow_settings(0.2),
        system_prompt=system_prompt,
    )


def create_reflection_agent() -> Agent:
    model = _get_model()
    return Agent(
        model=model,
        output_type=Reflection,
        retries=2,
        model_settings=_siliconflow_settings(0.5),
    )
