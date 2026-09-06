"""Multi-Agent Macro & Catalyst Analyst per Asset using Anthropic Claude Haiku.

Performs institutional macroeconomic, geopolitical, and supply/demand catalyst analysis
for individual CFD assets (XAUUSD, USOIL, EURUSD, BTCUSD).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from config.settings import settings
from macro.agents.base import LLMAgent, _extract_json, _setup_langsmith
from macro.observability import llm_observer

logger = logging.getLogger(__name__)


class AssetMacroAgent(LLMAgent):
    """Institutional macro catalyst analyst for a specific trading asset."""

    def __init__(self, asset: str) -> None:
        self.asset = asset.upper()
        self.name = f"{self.asset.lower()}_macro_analyst"
        self.role = self._get_asset_role()
        super().__init__()
        # Ensure Anthropic Haiku is prioritized
        self.model = settings.primary_macro_model or "claude-haiku-4-5-20251001"

    def _get_asset_role(self) -> str:
        roles = {
            "XAUUSD": (
                "Institutional Gold & Precious Metals Strategist. Analyze real yields, "
                "US Dollar trajectory, central bank reserve accumulation, and safe-haven geopolitical demand."
            ),
            "USOIL": (
                "Institutional Energy & Commodities Strategist. Analyze OPEC+ output quotas, "
                "EIA crude inventory shifts, Middle East maritime transit risks, and global economic demand."
            ),
            "EURUSD": (
                "Institutional Foreign Exchange (FX) Strategist. Analyze ECB vs. Federal Reserve "
                "interest rate differentials, Eurozone inflation prints, trade balances, and US dollar liquidity."
            ),
            "BTCUSD": (
                "Institutional Digital Assets & Macro Liquidity Strategist. Analyze global risk appetite, "
                "Federal Reserve balance sheet expansion, institutional spot ETF flows, and crypto macro beta."
            ),
        }
        return roles.get(self.asset, f"Institutional Macro Strategist specializing in {self.asset}.")

    def _build_system_prompt(self) -> str:
        return (
            f"You are the {self.name} for QuantEdge AI.\n"
            f"Role: {self.role}\n"
            f"Your objective is to evaluate recent news headlines, global macro regime, and market conditions specifically for {self.asset}.\n"
            "Respond ONLY with a valid JSON object containing exactly these keys:\n"
            "{\n"
            '  "bias": float (-1.0 to 1.0, where >0 is bullish, <0 is bearish, 0 is neutral),\n'
            '  "stance": "BULLISH" | "BEARISH" | "NEUTRAL",\n'
            '  "confidence": float (0.0 to 1.0),\n'
            '  "summary": "Concise 1-2 sentence institutional macroeconomic summary for this asset.",\n'
            '  "quant_impact": "Actionable instructions for the quantitative technical engine (e.g. favor trend pullbacks, breakout confirmation, etc.)",\n'
            '  "multi_agent_perspectives": {\n'
            '    "monetary_policy": "Interest rate & central bank policy impact on this asset",\n'
            '    "growth_liquidity": "Economic growth & liquidity cycle impact on this asset",\n'
            '    "asset_fundamentals": "Specific supply, demand, inventory, or flow drivers"\n'
            "  },\n"
            '  "key_catalysts": ["catalyst 1", "catalyst 2"]\n'
            "}"
        )

    async def analyze_asset(
        self,
        headlines: list[str],
        global_regime: str = "risk-on",
        regime_summary: str = "",
        live_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze asset with Anthropic Claude Haiku, falling back to deterministic heuristic if unavailable."""
        prompt = json.dumps(
            {
                "asset": self.asset,
                "global_regime": global_regime,
                "regime_summary": regime_summary,
                "headlines": headlines[:6],
                "live_stats": live_stats or {},
            },
            default=str,
        )

        system_prompt = self._build_system_prompt()
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

                bias = float(data.get("bias", 0.0))
                bias = max(-1.0, min(1.0, bias))
                stance = str(data.get("stance", "NEUTRAL")).upper()
                if stance not in ("BULLISH", "BEARISH", "NEUTRAL"):
                    stance = "BULLISH" if bias >= 0.20 else ("BEARISH" if bias <= -0.20 else "NEUTRAL")

                return {
                    "asset": self.asset,
                    "agent": self.name,
                    "model": self.model,
                    "bias": round(bias, 2),
                    "stance": stance,
                    "confidence": float(data.get("confidence", 0.8)),
                    "summary": str(data.get("summary", "")),
                    "quant_impact": str(data.get("quant_impact", "")),
                    "multi_agent_perspectives": data.get("multi_agent_perspectives", {}),
                    "key_catalysts": data.get("key_catalysts", []),
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

                bias = float(data.get("bias", 0.0))
                bias = max(-1.0, min(1.0, bias))
                stance = str(data.get("stance", "NEUTRAL")).upper()
                if stance not in ("BULLISH", "BEARISH", "NEUTRAL"):
                    stance = "BULLISH" if bias >= 0.20 else ("BEARISH" if bias <= -0.20 else "NEUTRAL")

                return {
                    "asset": self.asset,
                    "agent": self.name,
                    "model": self.model,
                    "bias": round(bias, 2),
                    "stance": stance,
                    "confidence": float(data.get("confidence", 0.8)),
                    "summary": str(data.get("summary", "")),
                    "quant_impact": str(data.get("quant_impact", "")),
                    "multi_agent_perspectives": data.get("multi_agent_perspectives", {}),
                    "key_catalysts": data.get("key_catalysts", []),
                }

            else:
                return self._fallback_asset(headlines)

        except Exception as e:
            logger.exception("%s Anthropic Haiku asset analysis failed (%s); using fallback: %s", self.name, self.provider, e)
            return self._fallback_asset(headlines)

    def _fallback_asset(self, headlines: list[str]) -> dict[str, Any]:
        """Deterministic keyword fallback if API call fails or key is unset."""
        text = " ".join(headlines).lower()
        bull_words = ["surge", "rally", "gain", "climb", "high", "demand", "cut", "easing", "bullish", "record", "jump"]
        bear_words = ["drop", "fall", "plunge", "decline", "recession", "glut", "hike", "hawkish", "slowdown", "bearish"]
        bull = sum(1 for w in bull_words if w in text)
        bear = sum(1 for w in bear_words if w in text)
        tot = bull + bear
        bias = 0.05 if tot == 0 else round((bull - bear) / max(tot, 1), 2)
        stance = "BULLISH" if bias >= 0.20 else ("BEARISH" if bias <= -0.20 else "NEUTRAL")

        fallbacks = {
            "XAUUSD": ("Consolidating between real yields and geopolitical hedge demand.", "Pure technical execution on M15 EMA 21 value tap."),
            "USOIL": ("OPEC+ supply discipline balances inventory prints.", "Trade strictly within NY session breakout bounds."),
            "EURUSD": ("Policy parity between ECB and Federal Reserve.", "Two-way mean reversion between Bollinger Band extremes."),
            "BTCUSD": ("Institutional ETF demand balances broader macro risk appetite.", "Momentum trend-following above M15 EMA 20."),
        }
        summ, q_imp = fallbacks.get(self.asset, ("Neutral macro flow.", "Technical execution."))

        return {
            "asset": self.asset,
            "agent": self.name,
            "model": f"fallback_{self.provider}",
            "bias": bias,
            "stance": stance,
            "confidence": 0.5,
            "summary": summ,
            "quant_impact": q_imp,
            "multi_agent_perspectives": {
                "monetary_policy": "Central bank policy trajectory monitored",
                "growth_liquidity": "Liquidity conditions neutral",
                "asset_fundamentals": "Supply/demand in equilibrium",
            },
            "key_catalysts": ["Headline flow monitoring"],
        }
