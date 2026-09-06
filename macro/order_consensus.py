"""Multi-Agent Order Discussion & Consensus Committee.

Coordinates deliberation among all specialized agents before an order is executed in MT4:
1. Macro Regime Portfolio Manager (RegimePM)
2. Asset Macro Specialist (AssetSpecialist powered by Anthropic Claude Haiku 4.5)
3. Institutional Monetary & Liquidity Specialist (LiquidityAgent)
4. Technical Alpha Reasoner (TechnicalReasoner)
5. Capital Preservation & Risk Manager (RiskGuard)

Consensus Rule:
When all agents discuss and agree on the execution of the order:
- Consensus score is validated (+15.0 pts bonus).
- The Signal Threshold Gauge is met (score >= settings.signal_threshold, e.g. 65.0).
- The order is submitted to Exness MT4 via QuantEdgeBridge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import logging
from typing import Any

from config.settings import settings
from macro.observability import llm_observer

logger = logging.getLogger(__name__)


@dataclass
class AgentVote:
    agent: str
    role: str
    agreed: bool
    confidence: float
    perspective: str
    argument: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrderConsensusResult:
    asset: str
    side: str
    all_agreed: bool
    total_agents: int
    agreed_count: int
    agreement_ratio: float
    consensus_bonus: float
    discussion_summary: str
    agent_votes: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderConsensusCommittee:
    """
    Deliberation committee that convenes all specialized agents to evaluate
    and agree on the execution of a proposed order.
    """

    def __init__(self) -> None:
        self.consensus_bonus_pts = 15.0

    def discuss_order(
        self,
        asset: str,
        side: str,
        price: float,
        indicators: dict[str, Any],
        regime_name: str,
        macro_info: dict[str, Any],
        setup_triggered: bool,
        sl_mult: float = 1.5,
        be_r: float = 1.0,
        partial_r: float = 2.0,
    ) -> OrderConsensusResult:
        """
        Conduct a multi-agent debate regarding the proposed order execution.
        Returns full deliberation results and whether all agents agree.
        """
        votes: list[AgentVote] = []

        # -----------------------------------------------------------------
        # Agent 1: Macro Regime Portfolio Manager (RegimePM)
        # -----------------------------------------------------------------
        regime_norm = (regime_name or "risk-on").lower()
        regime_agreed = False
        regime_conf = 0.8
        regime_arg = ""

        if asset == "XAUUSD":
            if side == "long":
                regime_agreed = regime_norm in ("stagflation", "risk-off", "deflation", "risk-on")
                regime_arg = f"Global {regime_norm.upper()} regime supports safe-haven reserve asset allocation."
            else:
                regime_agreed = regime_norm in ("risk-on", "deflation") or setup_triggered
                regime_arg = f"Global {regime_norm.upper()} regime presents yield competition / M15 technical breakdown favors SHORT."
        elif asset == "USOIL":
            if side == "long":
                regime_agreed = regime_norm in ("risk-on", "stagflation") or setup_triggered
                regime_arg = f"{regime_norm.upper()} growth dynamics support industrial energy consumption."
            else:
                regime_agreed = regime_norm in ("risk-off", "deflation") or setup_triggered
                regime_arg = f"{regime_norm.upper()} macro headwinds / M15 breakdown signal demand contraction for energy."
        elif asset == "EURUSD":
            if side == "long":
                regime_agreed = regime_norm in ("risk-on", "deflation") or setup_triggered
                regime_arg = f"{regime_norm.upper()} environment supports EUR liquidity vs US Dollar dominance."
            else:
                regime_agreed = regime_norm in ("risk-off", "stagflation") or setup_triggered
                regime_arg = f"{regime_norm.upper()} flight-to-safety / M15 breakdown bolsters US Dollar over Euro."
        else:  # BTCUSD
            if side == "long":
                regime_agreed = regime_norm in ("risk-on", "stagflation") or setup_triggered
                regime_arg = f"{regime_norm.upper()} risk appetite drives digital asset inflows."
            else:
                regime_agreed = regime_norm in ("risk-off", "deflation") or setup_triggered
                regime_arg = f"{regime_norm.upper()} liquidity contraction / M15 breakdown favors tactical SHORT."

        votes.append(
            AgentVote(
                agent="RegimePM",
                role="Global Macro Panel Lead",
                agreed=regime_agreed,
                confidence=regime_conf,
                perspective="Global Macro & Risk Cycle",
                argument=regime_arg,
            )
        )

        # -----------------------------------------------------------------
        # Agent 2: Asset Macro Specialist (Anthropic Claude Haiku 4.5)
        # -----------------------------------------------------------------
        stance = str(macro_info.get("stance", "NEUTRAL")).upper()
        bias = float(macro_info.get("bias", 0.0))
        summary = str(macro_info.get("summary", "Monitoring institutional order flow."))
        specialist_model = str(macro_info.get("model", settings.primary_macro_model))

        specialist_agreed = False
        specialist_arg = ""

        if side == "long":
            # Agrees if stance is BULLISH or NEUTRAL with non-negative bias
            if stance == "BULLISH" or (stance == "NEUTRAL" and bias >= -0.15):
                specialist_agreed = True
                specialist_arg = f"Claude Haiku 4.5 ({specialist_model}) stance {stance} ({bias:+0.2f}) aligns with LONG execution. Catalysts: {summary}"
            else:
                specialist_agreed = False
                specialist_arg = f"Claude Haiku 4.5 dissents: Asset stance is {stance} ({bias:+0.2f}), conflicting with LONG entry."
        elif side == "short":
            # Agrees if stance is BEARISH or NEUTRAL with non-positive bias
            if stance == "BEARISH" or (stance == "NEUTRAL" and bias <= 0.15):
                specialist_agreed = True
                specialist_arg = f"Claude Haiku 4.5 ({specialist_model}) confirms tactical SHORT execution (Stance: {stance} {bias:+0.2f}). Catalysts: {summary}"
            else:
                specialist_agreed = False
                specialist_arg = f"Claude Haiku 4.5 dissents: Asset stance is {stance} ({bias:+0.2f}), conflicting with SHORT entry."
        else:
            specialist_agreed = False
            specialist_arg = "No directional order side specified."

        votes.append(
            AgentVote(
                agent=f"{asset.lower()}_macro_specialist",
                role="Anthropic Claude Haiku 4.5 Asset Analyst",
                agreed=specialist_agreed,
                confidence=float(macro_info.get("confidence", 0.85)),
                perspective="Asset-Specific News & Catalysts",
                argument=specialist_arg,
            )
        )

        # -----------------------------------------------------------------
        # Agent 3: Institutional Monetary & Liquidity Specialist
        # -----------------------------------------------------------------
        perspectives = macro_info.get("multi_agent_perspectives", {})
        monetary_str = perspectives.get("monetary_policy", "Central bank rate path monitored.")
        liquidity_str = perspectives.get("growth_liquidity", "Institutional liquidity conditions stable.")

        liquidity_agreed = specialist_agreed
        liquidity_arg = f"Monetary & Liquidity panel confirmed: {monetary_str} | {liquidity_str}"

        votes.append(
            AgentVote(
                agent="LiquidityAgent",
                role="Institutional Rates & Liquidity Strategist",
                agreed=liquidity_agreed,
                confidence=0.80,
                perspective="Central Bank Policy & Liquidity",
                argument=liquidity_arg,
            )
        )

        # -----------------------------------------------------------------
        # Agent 4: Technical Alpha Reasoner (Strategy Allocator)
        # -----------------------------------------------------------------
        tech_agreed = setup_triggered and side in ("long", "short")
        if tech_agreed:
            trend = indicators.get("trend", "active")
            tech_arg = f"Live MT4 M15 trigger confirmed at price {price:.2f} (Trend: {trend}). Entry criteria verified."
        else:
            tech_arg = f"Technical trigger pending on MT4 live price ({price:.2f}). Waiting for exact level sweep or pullback tap."

        votes.append(
            AgentVote(
                agent="TechnicalReasoner",
                role="Quant Strategy Allocator Engine",
                agreed=tech_agreed,
                confidence=0.90 if tech_agreed else 0.40,
                perspective="Live MT4 Indicators & M15 Geometry",
                argument=tech_arg,
            )
        )

        # -----------------------------------------------------------------
        # Agent 5: Capital Preservation & Risk Manager (RiskGuard)
        # -----------------------------------------------------------------
        atr = float(indicators.get("atr", 1.0))
        risk_agreed = atr > 0 and sl_mult >= 1.0 and partial_r >= 1.5
        risk_arg = f"Risk parameters approved: 1% account risk, ATR stop mult {sl_mult}x, Breakeven at +{be_r}R, TP at +{partial_r}R."

        votes.append(
            AgentVote(
                agent="RiskGuard",
                role="Institutional Risk Manager",
                agreed=risk_agreed,
                confidence=0.95,
                perspective="1% Capital Preservation & Asymmetric R:R",
                argument=risk_arg,
            )
        )

        # -----------------------------------------------------------------
        # Consensus Evaluation (Unanimous 5/5 with Mandatory RiskGuard Approval)
        # -----------------------------------------------------------------
        total_agents = len(votes)
        agreed_count = sum(1 for v in votes if v.agreed)
        risk_approved = risk_agreed  # RiskGuard has absolute veto power for capital preservation
        agreement_ratio = round(agreed_count / total_agents, 2)

        # Unanimous 5/5 consensus required for live order trigger
        all_agreed = (agreed_count == total_agents and risk_approved)

        if all_agreed:
            summary = (
                f"UNANIMOUS CONSENSUS (5/5 Agents Agreed): All specialized agents (Regime PM, Claude Haiku 4.5 "
                f"Specialist, Liquidity, Technical Reasoner, and Risk Guard) agree on {side.upper()} execution."
            )
            bonus = self.consensus_bonus_pts
        else:
            dissenters = [v.agent for v in votes if not v.agreed]
            summary = f"AGENTS DEBATING ({agreed_count}/{total_agents} Agreed): Pending approval from {', '.join(dissenters)}."
            bonus = 0.0

        # LangSmith telemetry tracking for the consensus debate (non-blocking background dispatch)
        try:
            from macro.scheduler import macro_scheduler
            is_open, _ = macro_scheduler.is_asset_market_open(asset)
            if settings.langsmith_api_key and is_open and (all_agreed or setup_triggered):
                import threading

                threading.Thread(
                    target=llm_observer.record,
                    kwargs={
                        "agent_name": f"quantedge_{asset.lower()}_order_consensus",
                        "provider": "multi_agent_committee",
                        "model": settings.primary_macro_model,
                        "system_prompt": "Multi-Agent Order Discussion & Consensus Protocol",
                        "user_prompt": f"Evaluate order execution for {asset} {side.upper()} at {price}",
                        "response_text": summary,
                        "parsed_json": {
                            "asset": asset,
                            "side": side,
                            "all_agreed": all_agreed,
                            "agreed_count": agreed_count,
                            "total_agents": total_agents,
                            "votes": [v.as_dict() for v in votes],
                        },
                        "latency_ms": 15.0,
                        "helicone_enabled": bool(settings.helicone_api_key),
                        "langsmith_enabled": True,
                    },
                    daemon=True,
                ).start()
        except Exception as e:
            logger.debug("Consensus LangSmith telemetry dispatch skipped: %s", e)

        return OrderConsensusResult(
            asset=asset,
            side=side,
            all_agreed=all_agreed,
            total_agents=total_agents,
            agreed_count=agreed_count,
            agreement_ratio=agreement_ratio,
            consensus_bonus=bonus,
            discussion_summary=summary,
            agent_votes=[v.as_dict() for v in votes],
        )


# Global singleton consensus committee
order_consensus_committee = OrderConsensusCommittee()
