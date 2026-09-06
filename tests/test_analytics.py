"""Unit tests for Daily Analytics and Dashboard API endpoints."""

import pytest
import httpx
from api.main import app


@pytest.mark.asyncio
async def test_dashboard_routes():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

        # 2. Dashboard HTML
        res_dash = await client.get("/dashboard")
        assert res_dash.status_code == 200
        assert "QuantEdge" in res_dash.text
        assert "Executive Overview" in res_dash.text

        # 3. Daily Analytics endpoint
        res_daily = await client.get("/api/v1/analytics/daily")
        assert res_daily.status_code == 200
        data = res_daily.json()
        assert "account" in data
        assert "daily_performance" in data
        assert "macro" in data
        assert "open_positions" in data

        # 4. Reports endpoint
        res_rep = await client.get("/api/v1/analytics/reports")
        assert res_rep.status_code == 200
        rep_data = res_rep.json()
        assert "benchmarks" in rep_data
        assert "equity_curve" in rep_data
        assert "XAUUSD" in rep_data["benchmarks"]

        # 5. Macro Schedule endpoint
        res_sched = await client.get("/api/v1/analytics/schedule")
        assert res_sched.status_code == 200
        sched_data = res_sched.json()
        assert "scheduled_catalysts" in sched_data
        assert "current_time_utc" in sched_data

        # 6. Strategy Details Transparency endpoint
        res_strat = await client.get("/api/v1/analytics/strategy-details/XAUUSD")
        assert res_strat.status_code == 200
        strat_data = res_strat.json()
        assert strat_data["asset"] == "XAUUSD"
        assert "strategy_name" in strat_data
        assert "rl_intel" in strat_data
        assert "math_rules" in strat_data
        assert "educational_guide" in strat_data
        assert "agent_votes" in strat_data

        # 7. Missed Opportunities 24h Post-Mortem endpoint
        res_missed = await client.get("/api/v1/analytics/missed-opportunities")
        assert res_missed.status_code == 200
        missed_data = res_missed.json()
        assert "total_missed_detected" in missed_data
        assert "diagnostics" in missed_data
        assert len(missed_data["diagnostics"]) >= 4

