# Exness Historical Data Folder

Place your exported historical CSV files here to backtest with real Exness price action.

### Accepted Filenames
- `XAUUSD_M5.csv` or `XAUUSDm_M5.csv` or `XAUUSD_M1.csv` or `XAUUSD.csv`
- `EURUSD_M5.csv` or `EURUSDm_M5.csv` or `EURUSD_M1.csv` or `EURUSD.csv`
- `BTCUSD_M5.csv` or `BTCUSDm_M5.csv` or `BTCUSD_M1.csv` or `BTCUSD.csv`
- `USOIL_M5.csv` or `USOILm_M5.csv` or `USOIL_M1.csv` or `USOIL.csv`

---

### How to Export from MetaTrader 4 (Exness)

1. Open MetaTrader 4.
2. Press **`F2`** (or go to **Tools ➔ History Center**).
3. On the left navigation pane, expand your instrument:
   - For example: **Exness-Trial / Forex ➔ EURUSDm** or **Commodities ➔ XAUUSDm**.
4. Double-click the timeframe (e.g. **5 Minutes (M5)** or **1 Minute (M1)**).
5. Click **Download** to pull all historical broker records from Exness servers.
6. Click **Export** and save the file into this folder:
   `c:\Users\khoid\code\quantedge\data\historical\XAUUSD_M5.csv` (or `EURUSD_M5.csv`).

The engine will automatically detect, parse, and resample the M5 data into M15 and H4 timeframes for multi-timeframe analysis.
