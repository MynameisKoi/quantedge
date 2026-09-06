from risk.manager import RiskManager
from risk.position_sizer import atr_position_size


def test_atr_position_size_positive():
    sizing = atr_position_size(price=2350.0, atr=18.0)
    assert sizing["volume"] > 0
    assert sizing["risk_amount"] > 0


def test_risk_manager_approves_clean_trade():
    rm = RiskManager()
    decision = rm.evaluate(
        asset="EURUSD",
        side="long",
        score=70,
        atr=0.004,
        price=1.085,
    )
    assert decision["approved"] is True
