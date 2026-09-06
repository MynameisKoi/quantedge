from unittest.mock import MagicMock, patch

import pytest

from macro.agents.base import LLMAgent, _extract_json
from macro.agents.pm_agent import PortfolioManagerAgent
from macro.regime_classifier import RegimeClassifier


def test_extract_json():
    # Direct json
    assert _extract_json('{"bias": 0.5, "confidence": 0.8}')["bias"] == 0.5
    # Markdown block
    assert (
        _extract_json('```json\n{"bias": -0.2, "regime_hint": "risk-off"}\n```')["regime_hint"]
        == "risk-off"
    )
    # Surrounding text
    assert _extract_json('Here is the JSON: {"bias": 0.1} and more text')["bias"] == 0.1


def test_pm_synthesize_votes_regime():
    pm = PortfolioManagerAgent()
    decision = pm.synthesize(
        [
            {
                "agent": "hawkish",
                "regime_hint": "stagflation",
                "confidence": 0.8,
                "rationale": "cpi",
            },
            {
                "agent": "dovish",
                "regime_hint": "stagflation",
                "confidence": 0.6,
                "rationale": "sticky",
            },
            {
                "agent": "commodity_specialist",
                "regime_hint": "risk-on",
                "confidence": 0.4,
                "rationale": "oil",
            },
        ]
    )
    assert decision["regime"] == "stagflation"


@pytest.mark.asyncio
async def test_agent_anthropic_mock():
    agent = LLMAgent()
    agent.provider = "anthropic"
    mock_content = MagicMock()
    mock_content.text = (
        '{"bias": 0.7, "confidence": 0.85, "rationale": "Rate hike", "regime_hint": "stagflation"}'
    )
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]

    with patch("config.settings.settings.anthropic_api_key", "test_key"), \
         patch("anthropic.Anthropic") as mock_anthropic:
        mock_instance = MagicMock()
        mock_anthropic.return_value = mock_instance
        mock_instance.messages.create.return_value = mock_resp

        res = await agent.analyze({"headlines": ["Fed raises rates"]})
        assert res["bias"] == 0.7
        assert res["regime_hint"] == "stagflation"


@pytest.mark.asyncio
async def test_regime_refresh_offline():
    clf = RegimeClassifier()
    clf.update_context(headlines=["CPI inflation surprise forces hawkish Fed"])
    result = await clf.refresh()
    assert result.state.name in {"risk-on", "risk-off", "stagflation", "deflation"}

