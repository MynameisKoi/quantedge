"""LLM Observability and Model Inspector for QuantEdge AI.

Tracks and exposes full model inputs, system prompts, output rationales,
latencies, and token costs for transparent debugging (Helicone / LangSmith / Local).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

OBSERVABILITY_FILE = Path("data/llm_logs.json")


def setup_langsmith_env() -> bool:
    """Ensure LangSmith / LangChain environment variables are set for automatic tracing."""
    if settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project or "quantedge"
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project or "quantedge"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        return True
    return False


@dataclass
class LLMInteractionRecord:
    timestamp: str
    agent_name: str
    provider: str
    model: str
    system_prompt: str
    user_prompt: str
    response_text: str
    parsed_json: dict[str, Any]
    latency_ms: float
    cached: bool = False
    helicone_enabled: bool = False
    langsmith_enabled: bool = False


class LLMObservabilityManager:
    """Stores and serves transparent logs of all model inputs and outputs."""

    def __init__(self, log_file: Path | None = None, max_entries: int = 100) -> None:
        self.log_file = log_file or OBSERVABILITY_FILE
        self.max_entries = max_entries
        self.records: list[LLMInteractionRecord] = []
        self._load()
        setup_langsmith_env()

    def _load(self) -> None:
        if not self.log_file.exists():
            return
        try:
            data = json.loads(self.log_file.read_text(encoding="utf-8"))
            self.records = [LLMInteractionRecord(**r) for r in data]
        except Exception as e:
            logger.warning("Failed to load LLM observability logs: %s", e)

    def _save(self) -> None:
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            dicts = [asdict(r) for r in self.records[-self.max_entries:]]
            self.log_file.write_text(json.dumps(dicts, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save LLM observability logs: %s", e)

    def record(
        self,
        agent_name: str,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_text: str,
        parsed_json: dict[str, Any],
        latency_ms: float,
        cached: bool = False,
        helicone_enabled: bool = False,
        langsmith_enabled: bool = False,
    ) -> LLMInteractionRecord:
        """Record an LLM request/response cycle locally and to LangSmith."""
        ls_active = langsmith_enabled or bool(settings.langsmith_api_key)

        rec = LLMInteractionRecord(
            timestamp=datetime.now(UTC).isoformat(),
            agent_name=agent_name,
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            parsed_json=parsed_json,
            latency_ms=round(latency_ms, 2),
            cached=cached,
            helicone_enabled=helicone_enabled,
            langsmith_enabled=ls_active,
        )
        self.records.append(rec)
        if len(self.records) > self.max_entries:
            self.records = self.records[-self.max_entries:]
        self._save()

        # Direct ingestion to LangSmith Project
        if ls_active and settings.langsmith_api_key:
            try:
                from langsmith import Client

                setup_langsmith_env()
                client = Client(api_key=settings.langsmith_api_key)
                client.create_run(
                    name=f"quantedge_{agent_name}",
                    run_type="llm",
                    inputs={
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                    },
                    outputs={
                        "response_text": response_text,
                        "parsed_json": parsed_json,
                    },
                    extra={
                        "metadata": {
                            "provider": provider,
                            "model": model,
                            "latency_ms": round(latency_ms, 2),
                            "cached": cached,
                            "helicone": helicone_enabled,
                        }
                    },
                    tags=["quantedge", provider, model, agent_name],
                    end_time=datetime.now(UTC),
                    project_name=settings.langsmith_project or "quantedge",
                )
                logger.debug("✓ Telemetry run for %s dispatched to LangSmith project '%s'", agent_name, settings.langsmith_project)
            except Exception as e:
                logger.debug("Failed posting run to LangSmith: %s", e)

        return rec

    def get_logs(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return formatted logs in reverse chronological order."""
        return [asdict(r) for r in reversed(self.records[-limit:])]

    def get_langsmith_status(self) -> dict[str, Any]:
        """Return real-time LangSmith connection and configuration status."""
        active = bool(settings.langsmith_api_key)
        return {
            "active": active,
            "project": settings.langsmith_project if active else None,
            "endpoint": "https://api.smith.langchain.com",
            "dashboard_url": f"https://smith.langchain.com/o/default/projects/p/{settings.langsmith_project or 'quantedge'}" if active else None,
        }


# Global singleton observer
llm_observer = LLMObservabilityManager()
