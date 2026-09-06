from pathlib import Path

from core.rl.trade_learner import TradeRLPolicy
from core.rl.trade_memory import TradeExperience, TradeMemory


def test_trade_memory_lifecycle(tmp_path: Path):
    mem_file = tmp_path / "test_memory.json"
    mem = TradeMemory(persistence_path=str(mem_file))

    # Record entry
    exp = mem.record_entry(
        trade_id="t1",
        asset="XAUUSD",
        strategy="intraday_mtf_scalper",
        state_key="XAUUSD|risk-on|bullish|pullback_ema|m5_bull_shift",
        action="execute_full",
        side="long",
        entry_price=2350.0,
        spread_cost=0.25,
    )
    assert exp.trade_id == "t1"
    assert len(mem._active_trades) == 1

    # Record exit with profit (+2.5R)
    closed_exp = mem.record_exit(
        trade_id="t1",
        exit_price=2360.0,
        realized_pnl=250.0,
        risk_amount=100.0,
    )
    assert closed_exp is not None
    assert closed_exp.closed is True
    assert closed_exp.reward > 2.0
    assert len(mem.experiences) == 1

    # Check persistence
    assert mem_file.exists()
    mem2 = TradeMemory(persistence_path=str(mem_file))
    assert len(mem2.experiences) == 1
    assert mem2.summary()["win_rate"] == 100.0


def test_rl_policy_learning():
    policy = TradeRLPolicy(learning_rate=0.5, exploration_rate=0.0)
    state_key = policy.build_state_key("EURUSD", "risk-on", "bullish", "pullback_ema", "m5_bull_shift")

    # Initial evaluation
    init_eval = policy.evaluate_setup("EURUSD", "risk-on", "bullish", "pullback_ema", "m5_bull_shift", explore=False)
    assert init_eval["approved"] is True
    initial_q = init_eval["q_value"]

    # Learn from big loss
    loss_exp = TradeExperience(
        trade_id="loss_1",
        asset="EURUSD",
        strategy="scalper",
        state_key=state_key,
        action="execute_full",
        side="long",
        entry_price=1.0850,
        exit_price=1.0800,
        realized_pnl=-100.0,
        reward=-1.5,
        closed=True,
    )
    policy.learn_from_trade(loss_exp)

    post_loss_eval = policy.evaluate_setup("EURUSD", "risk-on", "bullish", "pullback_ema", "m5_bull_shift", explore=False)
    assert post_loss_eval["q_value"] < initial_q

    # Learn from multiple big wins
    for i in range(5):
        win_exp = TradeExperience(
            trade_id=f"win_{i}",
            asset="EURUSD",
            strategy="scalper",
            state_key=state_key,
            action="execute_full",
            side="long",
            entry_price=1.0850,
            exit_price=1.0900,
            realized_pnl=200.0,
            reward=2.5,
            closed=True,
        )
        policy.learn_from_trade(win_exp)

    post_win_eval = policy.evaluate_setup("EURUSD", "risk-on", "bullish", "pullback_ema", "m5_bull_shift", explore=False)
    assert post_win_eval["q_value"] > 1.0
    assert post_win_eval["action"] == "execute_full"
