from fastapi import APIRouter

from config.settings import settings
from execution.bridge.facade import ensure_bridge
from execution.bridge.paths import default_bridge_dir

router = APIRouter()


@router.get("/bridge/status")
async def bridge_status():
    bridge = await ensure_bridge()
    return {
        "transport": settings.bridge_transport,
        "file_dir": str(default_bridge_dir()),
        "host": settings.zmq_host,
        "port": settings.zmq_req_port,
        "ea_connected": bridge.connected,
        "ea_info": bridge.ea_info,
        "enable_live_trading": settings.enable_live_trading,
        "exness_account_type": settings.exness_account_type,
    }
