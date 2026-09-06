from fastapi import APIRouter

from core.events import Event, EventType, bus
from execution.order_manager import OrderManager

router = APIRouter()


@router.post("/config/emergency-stop")
async def emergency_stop():
    await bus.publish(
        Event(type=EventType.EMERGENCY_STOP, payload={}, source="api")
    )
    result = await OrderManager().emergency_flat()
    return {"status": "ok", **result}
