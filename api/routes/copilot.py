"""Natural language copilot workspace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.settings import settings
from core.portfolio import portfolio
from macro.regime_classifier import regime_classifier

router = APIRouter()


class CopilotQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)


@router.post("/copilot/query")
async def copilot_query(body: CopilotQuery) -> dict[str, Any]:
    context = {
        "portfolio": portfolio.summary(),
        "regime": regime_classifier.current.as_dict(),
    }

    provider = settings.llm_provider.lower()
    system_instruction = (
        "You are QuantEdge AI cloud copilot. Answer operator questions about "
        "portfolio heat, regime, and signal reasoning. Never invent fills. "
        "Never suggest bypassing the 1% risk rule."
    )

    if provider == "anthropic" and settings.anthropic_api_key:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.fast_sentiment_model,
            max_tokens=1024,
            temperature=0.3,
            system=system_instruction,
            messages=[
                {
                    "role": "user",
                    "content": f"Context JSON: {context}\n\nQuestion: {body.query}",
                }
            ],
        )
        answer = response.content[0].text if response.content else ""
        return {"answer": answer, "mode": "anthropic", "context": context}

    if provider == "openai" and settings.openai_api_key:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.fast_sentiment_model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": system_instruction,
                },
                {
                    "role": "user",
                    "content": f"Context JSON: {context}\n\nQuestion: {body.query}",
                },
            ],
        )
        answer = response.choices[0].message.content or ""
        return {"answer": answer, "mode": "openai", "context": context}

    return {
        "answer": (
            f"(offline copilot) Regime={context['regime'].get('regime')}, "
            f"equity={context['portfolio'].get('equity')}, "
            f"heat={context['portfolio'].get('portfolio_heat_pct')}%. "
            f"You asked: {body.query}"
        ),
        "mode": "fallback",
        "context": context,
    }

