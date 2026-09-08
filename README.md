# 📈 QuantEdge AI — Autonomous Multi-Asset Trading System

> An AI-driven, macro-aware algorithmic trading engine for XAUUSD, USOIL, BTCUSD, EURUSD, and more. QuantEdge AI bridges deterministic quantitative execution with multi-agent cloud macro consensus (powered by Anthropic Claude Haiku & OpenAI APIs), institutional-grade Exness CFD backtesting, and dynamic risk management into a unified production-grade platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Real-World References & Lineage](#real-world-references--lineage)
3. [Architecture](#architecture)
4. [Core Upgrades & Enhancements](#core-upgrades--enhancements)
5. [Data Flow & Live vs. Backtest Decoupling](#data-flow--live-vs-backtest-decoupling)
6. [Strategy Allocator & Quantitative Reasoning](#strategy-allocator--quantitative-reasoning)
7. [How It Works (Regime-Gated Quants)](#how-it-works-regime-gated-quants)
8. [Risk Management & Order Fine-Tuning](#risk-management--order-fine-tuning)
9. [Assets Coverage & Idiosyncrasies](#assets-coverage--idiosyncrasies)
10. [Strategy Engine & ML Optimization](#strategy-engine--ml-optimization)
11. [Project Structure](#project-structure)
12. [API Endpoints](#api-endpoints)
13. [Environment Variables](#environment-variables)
14. [Setup & Running](#setup--running)
15. [Trade-offs & Algorithmic Paradigm](#trade-offs--algorithmic-paradigm)
16. [Roadmap](#roadmap)

---

## Overview

QuantEdge AI is a modular, event-driven algorithmic trading system designed around macroeconomic awareness and regime-gated execution. Operating on a **hybrid cloud-quant paradigm**, it utilizes high-speed Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) and OpenAI cloud APIs to run multi-agent debates, executing orders through the Exness brokerage platform via MT4/MT5 bridges.

- **Multi-Agent Cloud Macro Consensus**: Cloud-hosted LLM agent panels (Hawkish, Dovish, Commodity Specialist, Portfolio Manager — running on Anthropic Claude Haiku) debate macroeconomic prints to establish global macro regime bias.
- **Per-Asset Multi-Agent Macro Analysts**: Dedicated asset specialists (`AssetMacroAgent`) for XAUUSD, USOIL, EURUSD, and BTCUSD that evaluate breaking news, monetary policy, liquidity cycles, and asset-specific fundamentals.
- **Deterministic Quantitative Signals**: Multi-timeframe trend, breakout, and mean-reversion signals scored and gated by live MT4 indicators and the active macro regime.
- **Exness CFD Simulation & Execution**: Backtest engine and live execution router built specifically for Exness MT4/MT5 accounts, incorporating real-time variable spreads, slippage profiles, and daily overnight rollover swap rates.
- **Bayesian ML Optimization**: Automated hyperparameter tuning using `scikit-optimize` combined with walk-forward validation to eliminate over-fitting.
- **Natural Language Copilot Workspace**: Interactive LLM query interface allowing operators to audit portfolio heat, trigger backtests, and review signal reasoning via natural language.

---

## Real-World References & Lineage

QuantEdge AI synthesizes proven techniques from leading open-source quants and agentic AI frameworks:

| System / Framework | Architectural Influence & Key Takeaway |
|---|---|
| **TradingAgents** | Multi-agent consensus debate model for macro event classification. |
| **Freqtrade** | Modular strategy API, Telegram integration, and Bayesian hyperparameter optimization. |
| **QuantConnect (LEAN)** | Multi-asset execution modeling, margin checking, and realistic CFD swap/slippage simulation. |
| **Vibe-Trading** | Natural language copilot interface for real-time workspace interaction and strategy auditing. |
| **MetaApi / DWX Connect** | Low-latency ZeroMQ IPC bridge connecting Python AI pipelines to Exness MT4/MT5 terminals. |
| **Jesse** | High-speed vectorized backtesting patterns and clean Pythonic module architecture. |

---

## Architecture

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                        QuantEdge AI — System Architecture                  │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   ┌─────────────┐│
│  │  Data Layer  │    │ Intelligence │    │  Execution   │   │  Workspace  ││
│  │              │    │ (OpenAI API) │    │    Layer     │   │    Layer    ││
│  │ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │   │ ┌─────────┐ ││
│  │ │  Market  │ │───▶│ │  Signal  │ │───▶│ │  Order   │ │──▶│ │Dashboard│ ││
│  │ │   Feed   │ │    │ │  Engine  │ │    │ │ Manager  │ │   │ │  (Web)  │ ││
│  │ └──────────┘ │    │ └──────────┘ │    │ └──────────┘ │   │ └─────────┘ ││
│  │ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │   │ ┌─────────┐ ││
│  │ │  News /  │ │───▶│ │  OpenAI  │ │───▶│ │  Risk    │ │──▶│ │  Cloud  │ ││
│  │ │Sentiment │ │    │ │  Agents  │ │    │ │ Manager  │ │   │ │ Copilot │ ││
│  │ └──────────┘ │    │ └──────────┘ │    │ └──────────┘ │   │ └─────────┘ ││
│  │ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │   │ ┌─────────┐ ││
│  │ │  Econ    │ │───▶│ │Backtest  │ │    │ │ ZeroMQ   │ │   │ │ Alerts  │ ││
│  │ │ Calendar │ │    │ │& ML Opt. │ │    │ │  Bridge  │ │   │ │(Webhook)│ ││
│  │ └──────────┘ │    │ └──────────┘ │    │ │(Exness)  │ │   │ └─────────┘ ││
│  │              │    │              │    │ └──────────┘ │   │             ││
│  └──────────────┘    └──────────────┘    └──────────────┘   └─────────────┘│
└───────────────────────────────────────────────────────────────────────────┘
```

## Core Upgrades & Enhancements

### 1. Dynamic Strategy Selection via Reinforcement Learning & Agent Consensus
QuantEdge AI features a setup-aware, adaptive **Strategy Allocator** (`strategies/strategy_allocator.py`) paired with an online **Contextual Bandit Reinforcement Learning Policy** (`core/rl/trade_learner.py`):
- **Dynamic Archetypes**: Rather than locking each asset to a single rigid technical filter, the allocator dynamically scores 4 foundational market archetypes:
  1. `momentum_impulse`: Rides high-velocity trends hugging EMA 9/20 during ADX surges ($\ge 25$).
  2. `value_pullback`: Taps dynamic value support/resistance at the EMA 9–21 zone in steady trends.
  3. `volatility_breakout`: Capitalizes on Donchian channel expansions and volatility surges.
  4. `mean_revert`: Executes statistical exhaustion reversions at 2.0σ Bollinger boundaries.
- **Contextual Q-Learning**: Evaluates state signatures `(asset, regime, adx_tier, vol_tier)` with Upper Confidence Bound (UCB) exploration. Archetypes are rewarded on real execution and penalized when rigid filters cause missed high-probability market opportunities.
- **Full Transparency & Education UI**: Every strategy card on the live dashboard is clickable, opening a comprehensive modal with:
  - **Why Chosen Now**: Live indicator values, regime alignment, and RL state signature.
  - **Formulas & Rules**: Mathematical entry logic, dynamic ATR stop loss, and $+2.0\text{R}$ take-profit rules.
  - **Learn the Strategy**: Clear educational guide explaining the mechanics, ideal environments, and risk controls.
  - **Candidate Archetypes & Q-Scores**: Live comparison of alternative models with individual Q-values.

### 2. 24-Hour Missed Opportunity Post-Mortem & Learner
QuantEdge AI includes an autonomous **Missed Opportunity Analyzer** (`core/rl/missed_opportunity_analyzer.py`) that audits the market over 24-hour cycles to identify high-conviction moves that were left uncaptured due to overly strict entry parameters:
- **Bottlenecks Diagnosed**: Pullbacks too strict (e.g. Gold dropping $25 without a 14-pt bounce), extreme Donchian band lag (Oil moving $2.54 inside wide 20-bar channels), counter-trend filter mismatch (Euro trending down with RSI locked to extremes), and portfolio omissions (BTCUSD unlisted).
- **Autonomous RL Feedback**: Penalizes over-restrictive archetypes and updates Q-values so momentum impulse rides fast runners automatically.

### 3. Supermajority Consensus Protocol for MT4 Execution
QuantEdge AI enforces a multi-agent deliberation committee (`macro/order_consensus.py`) before any trade reaches Exness MetaTrader 4:
1. **Macro Regime Portfolio Manager (`RegimePM`)**: Verifies alignment with the prevailing macro regime (`risk-on`, `risk-off`, `stagflation`, `deflation`).
2. **Asset Macro Specialist Agent (`AssetSpecialist` - Claude Haiku 4.5)**: Verifies asset-specific breaking catalysts and directional conviction.
3. **Institutional Monetary & Liquidity Specialist (`LiquidityAgent`)**: Verifies central bank yield differentials, rate path, and institutional liquidity flows.
4. **Technical Alpha Reasoner (`TechnicalReasoner`)**: Confirms live Exness MT4 indicators (EMA impulse, Donchian breakout, Bollinger sweep, ADX/RSI).
5. **Capital Preservation & Risk Manager (`RiskGuard`)**: Verifies 1% account risk, ATR stop distance, and $+2.0\text{R}$ take-profit.

**The Supermajority Execution Gate Rule**:
> **Supermajority consensus ($\ge 4/5$ affirmative votes)** is required to trigger execution, **with mandatory RiskGuard approval** (RiskGuard holds absolute capital preservation veto power). When supermajority consensus is reached, the validation bonus ($+15.0$ pts) is awarded, the **Signal Threshold Gauge is met** ($\text{Score} \ge 65.0$), and the order is dispatched to Exness MT4 via `QuantEdgeBridge.mq4` (`orders.json`). If consensus is not reached, the trade is held in deliberation.

### 4. Live MT4 Ground Truth vs. Backtest CSV Decoupling
- **Historical CSV Data (`data/historical/*.csv`)**: Strictly reserved for offline backtesting, hyperparameter optimization, and walk-forward benchmarking. Backtest figures are never injected into live dashboard statistics.
- **Live Trading Execution & Daily Reports**: Real-time quotes, spreads, live indicators (`ema9`, `ema21`, `ema50`, `donchian_high`, `donchian_low`, `bb_upper`, `bb_lower`, `rsi`, `atr`, `adx`), account balance, floating equity, and closed trade history stream directly from the Exness MetaTrader 4 terminal (`FILE_COMMON\quantedge\mt4_stats.json`, `quotes.json`, `heartbeat.json`, and `history.json`).
- **Real Daily Performance Reporting**: The Daily Quantitative Trading Report (`/analytics/daily`) and overview metrics calculate realized PnL, win rate, and profit factor solely from actual MT4 closed orders. If 0 trades executed, win rate displays true `0.0%` and net PnL displays `$0.00` rather than misleading backtest constants.

### 5. Order Fine-Tuning & Strict Risk Gate (1% Rule)
Before any order reaches the Exness broker bridge:
- **Account Equity Sizing**: Strictly capped at 1% max risk per trade based on live MT4 account equity:
  $$\text{Volume} = \frac{\text{Equity} \times 0.01}{\text{ATR} \times \text{SL Multiplier} \times \text{Contract Size}}$$
- **Pre-set Take Profit (TP)**: Dynamically set at $+2.0\text{R}$ (or asset-specific target).
- **Dynamic Stop Loss (SL)**: Set at $\text{Entry Price} \pm (\text{ATR} \times \text{SL Multiplier})$.
- **Breakeven (BE) Trigger**: Placed at $+1.0\text{R}$ (or $+0.8\text{R}$ for FX) to eliminate risk once the position expands.

### 6. Anthropic Claude Haiku 4.5 Multi-Agent Engine & Per-Asset Analysis
- **Multi-Agent Consensus Layer**: Global regime debates run across Hawkish, Dovish, and Commodity agents, synthesized by the Portfolio Manager using Anthropic Claude Haiku (`claude-haiku-4-5-20251001`).
- **Per-Asset Specialist Agents (`AssetMacroAgent`)**: Evaluates real-time headlines, monetary policy pressures, liquidity cycles, and physical supply/demand for `XAUUSD`, `USOIL`, `EURUSD`, and `BTCUSD`.
- **24-Hour Persistence Cache (`macro/cache.py` & `data/asset_macro_cache.json`)**: Caches LLM outputs for 24 hours (with hourly refresh cycles) to prevent redundant API calls, slashing operational token expenses while maintaining razor-sharp macroeconomic awareness.
- **LangSmith & Observability**: Integrated tracing for API calls via LangSmith environment configuration.

---

## Data Flow & Live vs. Backtest Decoupling

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                    QuantEdge AI — Live vs. Backtest Data Flow                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [BACKTEST & BENCHMARKING ONLY]                                              │
│  data/historical/*.csv ──▶ [Backtest Engine] ──▶ Strategy-Asset Validation   │
│                                                                              │
│  [REAL LIVE TRADING PIPELINE]                                                │
│                                                                              │
│  Exness MT4 Terminal ──▶ FILE_COMMON\quantedge\                              │
│                          ├── quotes.json                                     │
│                          └── mt4_stats.json (EMAs, ATR, ADX, Bands, RSI)     │
│                                       │                                      │
│                                       ▼                                      │
│                            [Live Price Feed Normalizer]                      │
│                                       │                                      │
│  Hourly News RSS / Web ──▶ [Asset Macro Manager] (24h Cache)                 │
│  Economic Calendar     ──▶ [Macro Regime Classifier]                         │
│                                       │                                      │
│                                       ▼                                      │
│                           [Strategy Allocator Engine]                        │
│                           ├── XAUUSD: Trend & Chandelier Runner              │
│                           ├── USOIL:  NY Volatility Breakout (Donchian)      │
│                           ├── EURUSD: Liquidity Sweep Mean Reversion         │
│                           └── BTCUSD: Institutional Momentum Runner          │
│                                       │                                      │
│                                       ▼                                      │
│                    [Multi-Agent Order Discussion Committee]                  │
│                    ├── Regime PM: Macro cycle alignment                      │
│                    ├── Haiku 4.5 Specialist: Catalysts & sentiment           │
│                    ├── Liquidity Agent: Central bank policy & flows          │
│                    ├── Technical Reasoner: M15 Exness live geometry          │
│                    └── Risk Guard: 1% risk rule & asymmetric R:R             │
│                                       │                                      │
│                    [ALL AGENTS AGREE? (5/5 Consensus)]                       │
│                           ├── NO  ──▶ Agents Debating (Score < 65, Hold)     │
│                           └── YES ──▶ Signal Threshold Gauge Met (>= 65)     │
│                                       │                                      │
│                                       ▼                                      │
│                           [Risk Manager Order Fine-Tuning]                   │
│                           ├── 1% Max Account Equity Risk Sizing              │
│                           ├── Dynamic ATR Stop Loss                          │
│                           ├── Take Profit (+2.0R)                            │
│                           └── Breakeven Trigger (+1.0R)                      │
│                                       │                                      │
│                                       ▼                                      │
│                            [Exness MT4 File Bridge]                          │
│                            └── orders.json ──▶ QuantEdgeBridge EA            │
│                                       │                                      │
│                                       ▼                                      │
│                             [Live Responsive Dashboard]                      │
│                             └── 5-Second Real-Time Poll                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Strategy Allocator & Quantitative Reasoning

The **Strategy Allocator** combines real-time MT4 indicators with macro bias to reason over setup validity:

| Asset | Allocated Strategy | Primary Indicators | Macro Bias Factor | Risk Parameters |
|---|---|---|---|---|
| **XAUUSD** | Institutional Trend & Chandelier Runner | EMA 9, EMA 21, EMA 50, ATR(14), ADX(14) | Real yields & safe-haven geopolitical hedge | `sl_mult=1.5`, `be_r=1.0`, `partial_r=2.0` |
| **USOIL** | NY Volatility Breakout | Donchian High/Low (20), EMA 20, EMA 50 | OPEC+ policy & Middle East transit risk | `sl_mult=2.0`, `be_r=1.0`, `partial_r=2.0` |
| **EURUSD** | Liquidity Sweep Mean Revert | Bollinger Bands (20, 2.0σ), RSI(14) | Fed-ECB yield divergence | `sl_mult=1.2`, `be_r=0.8`, `partial_r=1.5` |
| **BTCUSD** | Institutional Momentum | EMA 20, EMA 50, ATR Bands, Volume | Risk-on liquidity & ETF demand | `sl_mult=1.5`, `be_r=1.0`, `partial_r=2.0` |

---

## How It Works (Regime-Gated Quants & Multi-Agent Consensus)

1. **Macro Intelligence & Caching**: Hourly RSS and financial headlines are digested by the cloud LLM layer and stored in `intelligence/model_cache.py` (24h TTL) to prevent repeated API expenses.
2. **Live Feed Ingestion**: The system continuously reads live quotes and M15 technical stats directly from the Exness MT4 terminal via the common files bridge.
3. **Multi-Agent Order Discussion**: When a setup condition is detected on MT4 indicators, the 5 specialized agents deliberate on the trade.
4. **Consensus & Threshold Gauge**: Only when all 5 agents unanimously agree is the signal threshold gauge satisfied ($\ge 65.0$).
5. **Deterministic Risk Routing**: The Risk Manager sizes the lot volume to risk precisely 1% of account balance, attaching an exact Stop Loss, $+2.0\text{R}$ Take Profit, and $+1.0\text{R}$ Breakeven trigger.
6. **Live Broker Execution**: The order JSON is written to `orders.json` where `QuantEdgeBridge.mq4` executes the order immediately on Exness MT4.
5. **Broker Execution**: Orders are written to `FILE_COMMON\quantedge\orders.json` and executed natively by the MT4 `QuantEdgeBridge` EA on Exness.

---

## Risk Management & Order Fine-Tuning

QuantEdge enforces strict non-negotiable risk constraints:
- **1% Equity Rule**: Under no circumstances will any order risk more than 1% of current account equity.
- **Dynamic ATR Sizing**: Stop loss distances adapt to current market volatility rather than fixed pips.
- **Automated Profit Extraction**: Orders include broker-ready Take Profit levels set to $+2.0\text{R}$ alongside automated Breakeven advancement when price moves $+1.0\text{R}$ into profit.
- **News Blackout Guard**: Trading is automatically suppressed 5 minutes before and after high-impact Tier-1 economic releases.

---

## Assets Coverage & Idiosyncrasies

| Asset Class | Key Drivers | Exness CFD / Execution Considerations |
|---|---|---|
| **XAUUSD** — Commodity / Safe Haven | Real yields, DXY, CPI, geopolitics | Extreme spread expansion during US market open; high overnight swap cost. |
| **USOIL** — Commodity / Energy | OPEC+ supply cuts, EIA inventories, global growth | Low liquidity during Asian sessions; strategy restricts trading to London/US sessions. |
| **BTCUSD** — Crypto / Risk Asset | Fed liquidity, ETF inflows, on-chain metrics | Trades 24/7; strategy accounts for weekend liquidity gaps and high beta volatility. |
| **EURUSD** — FX Major | ECB vs Fed policy divergence, macro prints | Tight Exness spreads; primary driver for macro trend-following models. |

---

## Strategy Engine & ML Optimization

### Base Strategy Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseStrategy(ABC):
    name: str
    assets: list[str]
    timeframes: list[str]

    @abstractmethod
    def compute_signals(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates quantitative composite signal score."""
        pass

    @abstractmethod
    def on_regime_change(self, regime: str) -> None:
        """Dynamically adjusts parameters when macro regime shifts."""
        pass
```

### Shipped Strategies

- **`gold_real_yield_reversal`**: Trades XAUUSD against real yield divergence in stagflationary regimes.
- **`oil_opec_momentum`**: Capitalizes on OPEC news breakouts and inventory drawdowns in USOIL.
- **`btc_liquidity_cycle`**: Aligns BTC longs with Fed balance sheet expansion and risk-on sentiment.
- **`ema_trend_universal`**: Multi-asset EMA crossover with ADX filter and ATR trailing stops.

---

## Project Structure

```text
quantedge-ai/
│
├── core/                       # Core event-driven loop
│   ├── engine.py                # Main 24/7 execution loop & tick processor
│   ├── portfolio.py             # Portfolio state management
│   └── events.py                # Internal event bus
│
├── intelligence/               # Macro & Live Ground-Truth Intelligence
│   ├── asset_macro.py           # Hourly breaking news & macro sentiment analyzer
│   ├── live_price_feed.py       # Exness MT4 quotes & technical indicator feed
│   ├── model_cache.py           # 24h LLM response cache & transparent logger
│   └── regime.py                # Macro regime classifier & economic blackout detector
│
├── strategies/                 # Strategy Layer & Reasoning Allocator
│   ├── strategy_allocator.py    # Reasoning engine mapping assets to fit strategies
│   ├── adaptive/
│   │   └── live_strategy.py     # Live trading strategy adapter (decoupled from CSVs)
│   ├── base.py                  # BaseStrategy interface
│   ├── trend/                   # Institutional trend & momentum models
│   └── optimizer.py             # Bayesian ML hyperparameter optimization
│
├── risk/                       # Risk Management Gate
│   ├── manager.py                # Core risk gate & dynamic order fine-tuning
│   ├── position_sizer.py         # ATR sizing (1% rule, TP @ +2.0R, BE trigger)
│   └── correlation_guard.py      # Cross-asset exposure limiters
│
├── execution/                  # Broker Execution Bridges
│   ├── order_manager.py          # Order lifecycle management
│   └── bridge/
│       ├── file_bridge.py        # High-reliability Exness MT4 File Bridge (FILE_COMMON)
│       └── zeromq_adapter.py     # ZeroMQ IPC Bridge
│
├── data/                       # Backtest Data & Offline Benchmarking
│   ├── historical/              # M15/H1 CSV datasets (used ONLY for backtesting)
│   └── feature_store.py         # Fast feature store
│
├── backtest/                   # Backtesting & Simulation
│   ├── engine.py                 # Vectorized & event-driven backtester
│   └── cfd_simulator.py          # Exness variable spreads, slippage, & swap fee models
│
├── api/                        # FastAPI Application
│   ├── main.py                   # App entrypoint
│   └── routes/                   # Analytics, Strategies, Macro, Copilot endpoints
│
├── dashboard/                  # Real-Time Responsive Web Dashboard
├── scripts/                    # 24/7 background services & launcher batch scripts
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

| Group | Method | Endpoint | Description |
|---|---|---|---|
| Strategy Intelligence | GET | `/analytics/strategies` | Live scores, MT4 indicators, qualitative reasoning, and execution triggers per asset. |
| Strategy Transparency | GET | `/analytics/strategy-details/{asset}` | Deep strategy transparency: RL Q-scores, mathematical formulas, live values, and educational guide. |
| Learning Post-Mortem | GET | `/analytics/missed-opportunities` | 24-hour forensic diagnostic of uncaptured moves and autonomous RL parameter adjustments. |
| Macro News | GET | `/analytics/macro/assets` | Hourly breaking news sentiment, stance, and quant impact per asset. |
| Macro News | POST | `/analytics/macro/assets/refresh` | Force an immediate news pull and macro re-analysis. |
| Performance | GET | `/analytics/daily` | Real-time Exness account balance, equity, win rate, and open positions (MT4 ground truth). |
| Reports | GET | `/analytics/reports` | Daily and weekly automated performance reports. |
| Signals | GET | `/signals` | Active technical and macro signal scores per asset. |
| Trades | GET | `/trades/open` | List of currently open Exness positions with live unrealized P&L. |
| Regime | GET | `/regime/current` | Macro Regime, confidence, and economic blackout calendar. |
| Copilot | POST | `/copilot/query` | Natural language query endpoint. |
| Emergency | POST | `/config/emergency-stop` | Immediate kill-switch: closes all Exness orders and pauses execution. |

---

## Environment Variables

Create a `.env` file in the root directory:

```env
# ─── Application Configuration ──────────────────────────────────────
APP_ENV=development
APP_PORT=8000
LOG_LEVEL=INFO
SECRET_KEY=your_jwt_secret_here

# ─── LLM Configuration (Anthropic Claude Haiku / OpenAI) ───────────
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key_here
PRIMARY_MACRO_MODEL=claude-haiku-4-5-20251001
FAST_SENTIMENT_MODEL=claude-haiku-4-5-20251001
OPENAI_API_KEY=your_openai_api_key_here

# ─── LLM Observability & Tracking (LangSmith / Helicone) ────────────
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=quantedge
HELICONE_API_KEY=your_helicone_api_key_here
MACRO_CACHE_TTL_HOURS=24.0

# ─── Database & Cache ────────────────────────────────────────────────
DATABASE_URL=postgresql://user:password@localhost:5432/quantedge
REDIS_URL=redis://localhost:6379/0

# ─── Exness MT4 / MT5 ZeroMQ & File Bridge ───────────────────────────
BRIDGE_TRANSPORT=file
EXNESS_ACCOUNT_TYPE=Demo  # Real | Demo
ZMQ_HOST=127.0.0.1
ZMQ_REQ_PORT=5555
ZMQ_SUB_PORT=5556

# ─── Data & News Provider Keys ─────────────────────────────────────────
MASSIVE_API_KEY=your_massive_api_key  # Formerly Polygon.io (api.massive.com)
POLYGON_API_KEY=                     # Backwards-compatible alias
NEWSAPI_KEY=your_newsapi_key

# ─── Risk Controls ────────────────────────────────────────────────────
RISK_PER_TRADE_PCT=1.0
MAX_PORTFOLIO_HEAT_PCT=5.0
MAX_DAILY_DRAWDOWN_PCT=3.0
ENABLE_LIVE_TRADING=false
```

---

## Setup & Running

### 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Exness MT4 or MT5 Terminal running on an active Exness Demo/Real account
- OpenAI API Key

### 2. Installation

```bash
# Clone repository
git clone https://github.com/MynameisKoi/quantedge.git
cd quantedge

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Infrastructure (PostgreSQL & Redis)
docker-compose up -d postgres redis

# Run Database Migrations
alembic upgrade head
```

### 3. Running Backtesting & Live Exness Engine

```bash
# Run a Backtest with Exness CFD Swap Simulation
python -m backtest.engine --strategy gold_real_yield_reversal --asset XAUUSD --from 2023-01-01

# Start FastAPI Server & Cloud Copilot
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Launch Live Execution Engine on Exness (Paper Mode)
python -m core.engine
```

---

## Trade-offs & Algorithmic Paradigm

1. **Latency vs. Signal Depth**: Multi-agent cloud consensus takes time (2–10 seconds). QuantEdge AI is intentionally designed for swing and trend-continuation strategies, deliberately ceding sub-second high-frequency scalping to avoid news-event latency slippage.
2. **Deterministic Risk vs. Stochastic Sentiment**: The OpenAI-powered agents provide macro context (stochastic bias), but execution math (1% risk rule, ATR sizing) is 100% hardcoded and deterministic. LLMs never touch trade execution sizing or order parameters directly.
3. **API Cost Management**: The pipeline utilizes a lightweight model (`gpt-4o-mini`) for routine sentiment filters, reserving the flagship model (`gpt-4o`) exclusively for major macroeconomic news events (NFP, FOMC, CPI) to optimize API operational expenses.
4. **Walk-Forward Validation vs. Over-fitting**: Automated ML optimization (`scikit-optimize`) is strictly gated behind out-of-sample walk-forward windows to ensure models do not memorize historical price curves.

---

## Roadmap

- [x] Multi-Agent Macro Consensus pipeline implementation (Cloud LLM API + Transparent Observability)
- [x] High-reliability Exness MT4 File Bridge (`FILE_COMMON\quantedge` quotes, stats, orders)
- [x] Strategy Allocator with reasoning-driven asset-to-strategy allocation & live indicator gating
- [x] Strict separation of Backtest Data (CSVs) vs. Real Live MT4 quotes and technical indicators
- [x] Deterministic Risk Gate (1% equity sizing, dynamic ATR stop loss, +2.0R Take Profit, Breakeven advancement)
- [x] Hourly Macro News & Sentiment Engine with 24-Hour cost-saving output cache
- [x] Live Real-Time Dashboard (5-second polling of MT4 stats, strategy intelligence, and account health)
- [x] ZeroMQ Exness MT4/MT5 secondary bridge integration
- [x] Exness CFD cost simulation engine (variable spreads + swap rates)
- [ ] Automated COT (Commitment of Traders) report integration
- [ ] Multi-broker failover cluster configuration

---

**Disclaimer**: QuantEdge AI is built for quantitative research and educational purposes. Algorithmic trading in leveraged financial markets carries substantial risk of capital loss.
