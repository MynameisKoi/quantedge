from unittest.mock import MagicMock, patch
import pytest

from macro.agents.asset_agent import AssetMacroAgent
from macro.asset_macro_manager import AssetMacroManager


def test_asset_agent_init():
    for sym in ["XAUUSD", "USOIL", "EURUSD", "BTCUSD"]:
        agent = AssetMacroAgent(sym)
        assert agent.asset == sym
        assert sym.lower() in agent.name
        assert len(agent.role) > 10


def test_asset_agent_fallback():
    agent = AssetMacroAgent("XAUUSD")
    res = agent._fallback_asset(["Gold hits record high on central bank reserve demand"])
    assert res["asset"] == "XAUUSD"
    assert res["bias"] > 0
    assert res["stance"] == "BULLISH"
    assert "quant_impact" in res
    assert "multi_agent_perspectives" in res


@pytest.mark.asyncio
async def test_asset_agent_anthropic_mock():
    agent = AssetMacroAgent("BTCUSD")
    agent.provider = "anthropic"

    mock_resp = MagicMock()
    mock_content = MagicMock()
    mock_content.text = (
        '{"bias": 0.6, "stance": "BULLISH", "confidence": 0.85, '
        '"summary": "Institutional ETF inflows accelerate", '
        '"quant_impact": "Favor momentum breakouts above EMA20", '
        '"multi_agent_perspectives": {"monetary_policy": "loose", "growth_liquidity": "expanding"}, '
        '"key_catalysts": ["ETF net inflows"]}'
    )
    mock_resp.content = [mock_content]

    with patch("config.settings.settings.anthropic_api_key", "test_key"), \
         patch("anthropic.Anthropic") as mock_anthropic:
        mock_instance = MagicMock()
        mock_anthropic.return_value = mock_instance
        mock_instance.messages.create.return_value = mock_resp

        res = await agent.analyze_asset(
            headlines=["Bitcoin spot ETFs record massive inflows"],
            global_regime="risk-on",
        )
        assert res["asset"] == "BTCUSD"
        assert res["bias"] == 0.6
        assert res["stance"] == "BULLISH"
        assert "Institutional ETF inflows" in res["summary"]


@pytest.mark.asyncio
async def test_asset_macro_manager_summary():
    manager = AssetMacroManager()
    summary = manager.get_summary()
    assert "assets" in summary
    assert "XAUUSD" in summary["assets"]
    assert "USOIL" in summary["assets"]
    assert "EURUSD" in summary["assets"]
    assert "BTCUSD" in summary["assets"]
