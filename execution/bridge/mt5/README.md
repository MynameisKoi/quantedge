# QuantEdge MT5 Bridge (optional)

> **Prefer MT4 for Exness experiments** — see [`../mt4/README.md`](../mt4/README.md).

Python binds a TCP JSON server on `ZMQ_HOST:ZMQ_REQ_PORT` (default `127.0.0.1:5555`).  
The MT5 EA **connects outbound** — no ZeroMQ DLL required in MetaTrader.

## 1. Exness Demo + MT5

1. Create an [Exness Demo](https://www.exness.com/) account.
2. Install **MetaTrader 5** and log into the **Demo** server.
3. In MT5: **Tools → Options → Expert Advisors**
   - Enable **Allow algorithmic trading**
   - Enable **Allow DLL imports** (not required for this EA, safe default)
4. Turn **AutoTrading** ON (toolbar button).

## 2. Install the EA

1. Copy `QuantEdgeBridge.mq5` to your MT5 data folder:
   - File → Open Data Folder → `MQL5/Experts/`
2. In MetaEditor, compile `QuantEdgeBridge.mq5` (F7). Fix any compile errors if your build differs.
3. In MT5 Navigator → Experts, drag **QuantEdgeBridge** onto any chart (e.g. EURUSD).
4. Inputs (defaults are fine for local demo):
   - `InpHost` = `127.0.0.1`
   - `InpPort` = `5555`
   - `InpSymbolMap` — map QuantEdge names to Exness symbols if needed  
     (example: `USOIL:USOILm,BTCUSD:BTCUSD`)

## 3. Allow local socket (Windows / MT5)

MT5 must be allowed to connect to localhost. If the EA logs connect failures:

- Windows Firewall: allow MetaTrader 5
- MT5 **Tools → Options → Expert Advisors → Allow WebRequest** is for HTTP; sockets use terminal network permissions — usually work on `127.0.0.1` once AutoTrading is on

## 4. Handshake from Python

```powershell
cd c:\Users\khoid\code\quantedge
.\.venv\Scripts\Activate.ps1

# Terminal A — wait for EA (start this BEFORE or AFTER attaching the EA)
python -m execution.bridge_test --wait --ping --account
```

You should see EA `hello` with account/server/balance, then `PING ok` and account JSON.

## 5. Min-lot demo order (explicit)

```powershell
# Caps at 0.02 lots; requires Demo EXNESS_ACCOUNT_TYPE; requires confirmation flag
python -m execution.bridge_test --wait --order --symbol EURUSD --side buy --volume 0.01 --i-understand-demo
```

The EA **refuses non-demo** accounts for `OPEN`.

## 6. Engine live routing (later)

In `.env`:

```env
EXNESS_ACCOUNT_TYPE=Demo
ENABLE_LIVE_TRADING=true
ZMQ_HOST=127.0.0.1
ZMQ_REQ_PORT=5555
```

1. Start bridge wait / attach EA  
2. `python -m core.engine`  
3. Kill switch: `POST /api/v1/config/emergency-stop`

Keep `ENABLE_LIVE_TRADING=false` until handshake + one manual min-lot order succeed.
