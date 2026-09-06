"""Shared LLM agent adapter supporting Anthropic Claude and OpenAI."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import os
import time

from config.settings import settings
from macro.observability import llm_observer, setup_langsmith_env

logger = logging.getLogger(__name__)


def _setup_langsmith() -> None:
    setup_langsmith_env()


def _extract_json(text: str) -> dict[str, Any]:
    """Clean markdown code fences and extract JSON object."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Match outermost braces if present
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


class LLMAgent:
    name: str = "base"
    role: str = ""
    model: str | None = None

    def __init__(self) -> None:
        self.model = self.model or settings.primary_macro_model
        self.provider = settings.llm_provider.lower()

    async def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        """Return structured bias. Falls back to heuristic if no API key or call fails."""
        prompt = self._build_prompt(context)
        system_prompt = (
            f"You are the {self.name} macro agent for QuantEdge AI. "
            f"Role: {self.role}. "
            "Respond ONLY with a valid JSON object containing exactly these keys: "
            "bias (number from -1 to 1), "
            "confidence (number from 0 to 1), "
            "rationale (short string), "
            "regime_hint (one of: risk-on, risk-off, stagflation, deflation)."
        )

        _setup_langsmith()
        start_time = time.monotonic()
        helicone_on = bool(settings.helicone_api_key)
        langsmith_on = bool(settings.langsmith_api_key)

        try:
            if self.provider == "anthropic" and settings.anthropic_api_key:
                from anthropic import Anthropic

                headers: dict[str, str] = {}
                if helicone_on:
                    headers["Helicone-Auth"] = f"Bearer {settings.helicone_api_key}"
                if settings.anthropic_workspace_id:
                    headers["anthropic-workspace-id"] = settings.anthropic_workspace_id

                base_url = "https://anthropic.helicone.ai" if helicone_on else None
                client = Anthropic(
                    api_key=settings.anthropic_api_key,
                    base_url=base_url,
                    default_headers=headers if headers else None,
                )
                response = client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text if response.content else "{}"
                data = _extract_json(text)
                latency_ms = (time.monotonic() - start_time) * 1000.0

                llm_observer.record(
                    agent_name=self.name,
                    provider="anthropic",
                    model=self.model,
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    response_text=text,
                    parsed_json=data,
                    latency_ms=latency_ms,
                    helicone_enabled=helicone_on,
                    langsmith_enabled=langsmith_on,
                )

                return {
                    "agent": self.name,
                    "bias": float(data.get("bias", 0)),
                    "confidence": float(data.get("confidence", 0.5)),
                    "rationale": str(data.get("rationale", "")),
                    "regime_hint": str(data.get("regime_hint", "risk-on")),
                }

            elif self.provider == "openai" and settings.openai_api_key:
                from openai import OpenAI

                headers = {}
                if helicone_on:
                    headers["Helicone-Auth"] = f"Bearer {settings.helicone_api_key}"
                base_url = "https://oai.helicone.ai/v1" if helicone_on else None
                client = OpenAI(
                    api_key=settings.openai_api_key,
                    base_url=base_url,
                    default_headers=headers if headers else None,
                )
                response = client.chat.completions.create(
                    model=self.model,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                )
                content = response.choices[0].message.content or "{}"
                data = json.loads(content)
                latency_ms = (time.monotonic() - start_time) * 1000.0

                llm_observer.record(
                    agent_name=self.name,
                    provider="openai",
                    model=self.model,
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    response_text=content,
                    parsed_json=data,
                    latency_ms=latency_ms,
                    helicone_enabled=helicone_on,
                    langsmith_enabled=langsmith_on,
                )

                return {
                    "agent": self.name,
                    "bias": float(data.get("bias", 0)),
                    "confidence": float(data.get("confidence", 0.5)),
                    "rationale": str(data.get("rationale", "")),
                    "regime_hint": str(data.get("regime_hint", "risk-on")),
                }

            else:
                return self._fallback(context)

        except Exception:
            logger.exception("%s LLM call failed (%s); using fallback", self.name, self.provider)
            return self._fallback(context)

    def _build_prompt(self, context: dict[str, Any]) -> str:
        return json.dumps(context, default=str)

    def _fallback(self, context: dict[str, Any]) -> dict[str, Any]:
        """Deterministic offline stub so the stack runs without active API keys."""
        headline = " ".join(str(x) for x in context.get("headlines", [])).lower()
        bias = 0.0
        hint = "risk-on"
        if any(k in headline for k in ("inflation", "cpi", "hike", "hawkish")):
            bias = 0.4
            hint = "stagflation"
        if any(k in headline for k in ("recession", "layoff", "cut rates", "dovish")):
            bias = -0.3
            hint = "risk-off"
        if any(k in headline for k in ("opec", "supply", "inventory")):
            bias = 0.2
            hint = "stagflation"
        return {
            "agent": self.name,
            "bias": bias,
            "confidence": 0.35,
            "rationale": f"{self.name} fallback heuristic (no {self.provider} key/error)",
            "regime_hint": hint,
        }


# Backwards compatibility alias
OpenAIAgent = LLMAgent

