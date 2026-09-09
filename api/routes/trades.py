from typing import Any
from fastapi import APIRouter, Body
from pydantic import BaseModel

from core.order_agent import order_decision_agent
from core.portfolio import portfolio
from strategies.strategy_allocator import strategy_allocator

router = APIRouter()


class OrderFireRequest(BaseModel):
    asset: str | None = None
    side: str | None = None
    price: float | None = None
    force: bool = False


@router.get("/trades/open")
async def open_trades():
    positions = []
    for key, pos in portfolio.positions.items():
        positions.append(
            {
                "key": key,
                "symbol": pos.symbol,
                "side": pos.side,
                "volume": pos.volume,
                "entry_price": pos.entry_price,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "unrealized_pnl": pos.unrealized_pnl,
                "ticket": pos.ticket,
                "opened_at": pos.opened_at.isoformat(),
            }
        )
    return {"count": len(positions), "positions": positions}


@router.get("/orders/decision/{asset}")
async def get_order_decision(asset: str, force: bool = False):
    """Preview the OrderDecisionAgent's trade requirements and risk sizing."""
    decision = order_decision_agent.decide_order(asset=asset, force=force)
    return decision


@router.post("/orders/fire")
@router.post("/trades/fire")
async def fire_order(req: OrderFireRequest = Body(...)):
    """
    Invoke OrderDecisionAgent to decide all requirements (size, symbol, price, s/l, t/p)
    and execute the trade directly in MT4 via QuantEdgeBridge.
    """
    target_asset = req.asset
    if not target_asset:
        # Scan all assets to find the first one meeting threshold
        allocations = strategy_allocator.allocate_all()
        for sym, alloc in allocations.items():
            if alloc.get("potential_order", {}).get("triggered") or alloc.get("score", 0) >= 65.0:
                target_asset = sym
                break
        if not target_asset:
            target_asset = "USOIL"  # fallback default

    result = await order_decision_agent.fire_order(
        asset=target_asset,
        side=req.side,
        price=req.price,
        force=req.force,
    )
    return result


class OrderActionRequest(BaseModel):
    ticket: str | int
    action: str = "CLOSE"


class OrderModifyRequest(BaseModel):
    ticket: str | int
    sl: float | None = None
    tp: float | None = None
    reason: str = "manual_mid_air_adjustment"


class ScaleInRequest(BaseModel):
    asset: str
    side: str | None = None


@router.get("/orders/lifecycle")
async def get_orders_lifecycle():
    """Concurrently evaluate all open positions and return lifecycle actions."""
    from core.order_lifecycle_agent import order_lifecycle_agent

    evaluations = await order_lifecycle_agent.evaluate_open_positions()
    return {
        "count": len(evaluations),
        "positions": evaluations,
    }


@router.post("/orders/close/{ticket}")
async def close_order_ticket(ticket: str):
    """Close a specific open order ticket in MT4 via OrderLifecycleAgent."""
    from core.order_lifecycle_agent import order_lifecycle_agent

    result = await order_lifecycle_agent.execute_action(ticket=ticket, action="CLOSE")
    return result


@router.post("/orders/action")
async def execute_order_action(req: OrderActionRequest = Body(...)):
    """Execute an agent-recommended lifecycle action on an open position."""
    from core.order_lifecycle_agent import order_lifecycle_agent

    result = await order_lifecycle_agent.execute_action(ticket=req.ticket, action=req.action)
    return result


@router.post("/orders/scale-in")
async def scale_in_order(req: ScaleInRequest = Body(...)):
    """Put more orders down (pyramid / scale-in) into an active winning trade."""
    from core.order_lifecycle_agent import order_lifecycle_agent

    analyses = await order_lifecycle_agent.evaluate_open_positions()
    matching = next((a for a in analyses if a["canonical_symbol"] == req.asset), None)
    side = req.side or (matching["side"] if matching else "long")
    ticket = matching["ticket"] if matching else 0

    result = await order_lifecycle_agent.execute_action(ticket=ticket, action="SCALE_IN")
    return result


@router.post("/orders/modify")
async def modify_order_ticket(req: OrderModifyRequest = Body(...)):
    """Interfere mid-air to modify Stop Loss and/or Take Profit for an open order ticket."""
    from core.order_lifecycle_agent import order_lifecycle_agent

    result = await order_lifecycle_agent.execute_action(
        ticket=req.ticket,
        action="MODIFY",
        new_sl=req.sl,
        new_tp=req.tp,
    )
    return result
