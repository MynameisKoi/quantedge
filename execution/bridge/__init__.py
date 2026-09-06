from execution.bridge.facade import ensure_bridge, get_bridge
from execution.bridge.file_bridge import FileBridge, file_bridge
from execution.bridge.server import BridgeServer, bridge_server, ensure_bridge_server
from execution.bridge.zeromq_adapter import ZeroMQAdapter

# Primary: Exness MT4 file bridge (see bridge/mt4/).
# Optional: MT5 TCP EA under bridge/mt5/ with BRIDGE_TRANSPORT=tcp.

__all__ = [
    "BridgeServer",
    "bridge_server",
    "ensure_bridge_server",
    "FileBridge",
    "file_bridge",
    "get_bridge",
    "ensure_bridge",
    "ZeroMQAdapter",
]
