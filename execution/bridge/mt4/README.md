# QuantEdge MT4 Bridge (Exness Demo) — file IPC

Exness MT4 **does not expose** `SocketCreate` / `SocketConnect` (that caused your compile errors).  
This EA uses **Common Files** instead — no sockets, no DLL.

## 1. Install EA

1. Copy `QuantEdgeBridge.mq4` → MT4 **File → Open Data Folder → `MQL4/Experts/`**
2. Compile in MetaEditor (**F7**) — should be **0 errors**
3. Enable **AutoTrading**
4. Attach EA to a chart (EURUSD)
5. Experts log should show: `file bridge active under Common\Files\quantedge\`

## 2. Shared folder

EA writes / reads:

`%APPDATA%\MetaQuotes\Terminal\Common\Files\quantedge\`

Python uses the same path by default (`BRIDGE_TRANSPORT=file`).

## 3. Handshake

```powershell
cd c:\Users\khoid\code\quantedge
.\.venv\Scripts\Activate.ps1
python -m execution.bridge_test --wait --ping --account
```

## 4. Min-lot demo order

```powershell
python -m execution.bridge_test --wait --order --symbol EURUSD --side buy --volume 0.01 --i-understand-demo
```

Safety: EA refuses Real accounts; CLI caps at 0.02 lots.

## 5. .env

```env
EXNESS_ACCOUNT_TYPE=Demo
BRIDGE_TRANSPORT=file
ENABLE_LIVE_TRADING=false
```

Set `ENABLE_LIVE_TRADING=true` only after ping + one min-lot order succeed.

## Optional override

```env
BRIDGE_FILE_DIR=C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\Common\Files\quantedge
```
