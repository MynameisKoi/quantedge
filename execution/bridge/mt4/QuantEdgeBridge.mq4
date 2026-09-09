//+------------------------------------------------------------------+
//|                                          QuantEdgeBridge.mq4     |
//| File-based JSON bridge for QuantEdge AI (Exness MT4 Demo)        |
//| No Socket* APIs / no DLL — uses Common\Files\quantedge\          |
//+------------------------------------------------------------------+
#property copyright "QuantEdge AI"
#property version   "1.10"
#property strict

input int    InpTimerMs        = 250;
input int    InpHeartbeatSec   = 2;
input int    InpMagic          = 20260322;
input int    InpSlippage       = 30;
input string InpSymbolMap      = "USOIL:USOILm,XAUUSD:XAUUSDm,BTCUSD:BTCUSDm,EURUSD:EURUSDm";

#define MASTER_VAR       "QuantEdge_Master_Chart"
#define MASTER_PING_VAR  "QuantEdge_Master_Ping"

datetime g_last_heartbeat = 0;
string   g_processed_ids[64];
int      g_processed_count = 0;

//+------------------------------------------------------------------+
bool IsMasterChart()
  {
   datetime now = TimeLocal();
   if(!GlobalVariableCheck(MASTER_VAR))
     {
      GlobalVariableSet(MASTER_VAR, (double)ChartID());
      GlobalVariableSet(MASTER_PING_VAR, (double)now);
      return true;
     }
   double master_id = GlobalVariableGet(MASTER_VAR);
   if(master_id == (double)ChartID())
     {
      GlobalVariableSet(MASTER_PING_VAR, (double)now);
      return true;
     }
   double last_ping = GlobalVariableGet(MASTER_PING_VAR);
   if(now - (datetime)last_ping > 5)
     {
      // Previous master chart closed or timed out — elect current chart
      GlobalVariableSet(MASTER_VAR, (double)ChartID());
      GlobalVariableSet(MASTER_PING_VAR, (double)now);
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
bool IsIdProcessed(const string id)
  {
   for(int i=0; i<g_processed_count; i++)
     {
      if(g_processed_ids[i] == id)
         return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
void MarkIdProcessed(const string id)
  {
   if(g_processed_count >= 64)
     {
      for(int i=0; i<63; i++)
         g_processed_ids[i] = g_processed_ids[i+1];
      g_processed_ids[63] = id;
     }
   else
     {
      g_processed_ids[g_processed_count++] = id;
     }
  }

//+------------------------------------------------------------------+
string MapSymbol(const string sym)
  {
   string parts[];
   int n = StringSplit(InpSymbolMap, ',', parts);
   for(int i=0; i<n; i++)
     {
      string kv[];
      if(StringSplit(parts[i], ':', kv) == 2)
        {
         StringTrimLeft(kv[0]); StringTrimRight(kv[0]);
         StringTrimLeft(kv[1]); StringTrimRight(kv[1]);
         if(kv[0] == sym)
            return kv[1];
        }
     }
   return sym;
  }

//+------------------------------------------------------------------+
string JsonEscape(const string s)
  {
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   return out;
  }

//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
bool WriteCommon(const string relpath, const string content)
  {
   int h = FileOpen(relpath, FILE_BIN|FILE_WRITE|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON);
   if(h == INVALID_HANDLE)
     {
      Print("QuantEdgeBridge: FileOpen write failed ", relpath, " err=", GetLastError());
      return false;
     }
   int n = StringLen(content);
   uchar bytes[];
   ArrayResize(bytes, n);
   for(int i=0; i<n; i++)
      bytes[i] = (uchar)StringGetChar(content, i);
   FileWriteArray(h, bytes, 0, n);
   FileClose(h);
   return true;
  }

//+------------------------------------------------------------------+
string ReadCommon(const string relpath)
  {
   if(!FileIsExist(relpath, FILE_COMMON))
      return "";
   int h = FileOpen(relpath, FILE_BIN|FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return "";
   int size = (int)FileSize(h);
   if(size <= 0)
     {
      FileClose(h);
      return "";
     }
   uchar bytes[];
   ArrayResize(bytes, size);
   FileReadArray(h, bytes, 0, size);
   FileClose(h);
   string out = "";
   for(int i=0; i<size; i++)
      out += CharToStr(bytes[i]);
   return out;
  }

//+------------------------------------------------------------------+
void DeleteCommon(const string relpath)
  {
   if(FileIsExist(relpath, FILE_COMMON))
      FileDelete(relpath, FILE_COMMON);
  }

//+------------------------------------------------------------------+
string ExtractString(const string json, const string key)
  {
   string pattern = "\"" + key + "\":\"";
   int start = StringFind(json, pattern);
   if(start < 0)
      return "";
   start += StringLen(pattern);
   int end = StringFind(json, "\"", start);
   if(end < 0)
      return "";
   return StringSubstr(json, start, end - start);
  }

//+------------------------------------------------------------------+
double ExtractNumber(const string json, const string key, const double def_value=0.0)
  {
   string pattern = "\"" + key + "\":";
   int start = StringFind(json, pattern);
   if(start < 0)
      return def_value;
   start += StringLen(pattern);
   while(start < StringLen(json) && StringGetChar(json, start) == ' ')
      start++;
   string num = "";
   for(int i=start; i<StringLen(json); i++)
     {
      int c = StringGetChar(json, i);
      if((c>='0' && c<='9') || c=='.' || c=='-')
         num += CharToStr(c);
      else
         break;
     }
   if(num == "")
      return def_value;
   return StrToDouble(num);
  }

//+------------------------------------------------------------------+
void ReplyOk(const string id, const string payload_json)
  {
   string msg = StringFormat("{\"type\":\"reply\",\"id\":\"%s\",\"ok\":true,\"payload\":%s}",
                             JsonEscape(id), payload_json);
   WriteCommon("quantedge\\reply\\" + id + ".json", msg);
  }

//+------------------------------------------------------------------+
void ReplyErr(const string id, const string err)
  {
   string msg = StringFormat(
      "{\"type\":\"reply\",\"id\":\"%s\",\"ok\":false,\"error\":\"%s\",\"payload\":{}}",
      JsonEscape(id), JsonEscape(err));
   WriteCommon("quantedge\\reply\\" + id + ".json", msg);
  }

//+------------------------------------------------------------------+
void WriteHello()
  {
   string mode = IsDemo() ? "Demo" : "Real";
   string hello = StringFormat(
      "{\"type\":\"hello\",\"payload\":{\"account\":%d,\"server\":\"%s\",\"trade_mode\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"platform\":\"MT4\",\"chart_symbol\":\"%s\"}}",
      AccountNumber(), JsonEscape(AccountServer()), mode, AccountBalance(), AccountEquity(), JsonEscape(Symbol()));
   WriteCommon("quantedge\\hello.json", hello);
  }

//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
string ResolveMarketSymbol(const string base)
  {
   string mapped = MapSymbol(base);
   if(MarketInfo(mapped, MODE_BID) > 0.0)
      return mapped;
   if(MarketInfo(base, MODE_BID) > 0.0)
      return base;
   string suffixes[5] = {"m", "m.", ".", ".a", "pro"};
   for(int i=0; i<5; i++)
     {
      string s = base + suffixes[i];
      if(MarketInfo(s, MODE_BID) > 0.0)
         return s;
     }
   string cur = Symbol();
   if(StringFind(cur, base) >= 0 && MarketInfo(cur, MODE_BID) > 0.0)
      return cur;
   return "";
  }

//+------------------------------------------------------------------+
void WriteMT4Stats()
  {
   if(!IsConnected())
      return;
   datetime now = TimeCurrent();
   if(now <= 0)
      return;

   string sym_xau = ResolveMarketSymbol("XAUUSD");
   string sym_oil = ResolveMarketSymbol("USOIL");
   string sym_eur = ResolveMarketSymbol("EURUSD");
   string sym_btc = ResolveMarketSymbol("BTCUSD");

   double bid_xau = (sym_xau != "") ? MarketInfo(sym_xau, MODE_BID) : 0.0;
   double ask_xau = (sym_xau != "") ? MarketInfo(sym_xau, MODE_ASK) : 0.0;
   double bid_oil = (sym_oil != "") ? MarketInfo(sym_oil, MODE_BID) : 0.0;
   double ask_oil = (sym_oil != "") ? MarketInfo(sym_oil, MODE_ASK) : 0.0;
   double bid_eur = (sym_eur != "") ? MarketInfo(sym_eur, MODE_BID) : 0.0;
   double ask_eur = (sym_eur != "") ? MarketInfo(sym_eur, MODE_ASK) : 0.0;
   double bid_btc = (sym_btc != "") ? MarketInfo(sym_btc, MODE_BID) : 0.0;
   double ask_btc = (sym_btc != "") ? MarketInfo(sym_btc, MODE_ASK) : 0.0;

   // 1. Live Quotes JSON
   string quotes_json = StringFormat(
      "{\"time\":%d,\"quotes\":{\"XAUUSD\":{\"bid\":%.2f,\"ask\":%.2f},\"USOIL\":{\"bid\":%.2f,\"ask\":%.2f},\"EURUSD\":{\"bid\":%.5f,\"ask\":%.5f},\"BTCUSD\":{\"bid\":%.2f,\"ask\":%.2f}}}",
      now, bid_xau, ask_xau, bid_oil, ask_oil, bid_eur, ask_eur, bid_btc, ask_btc
   );
   WriteCommon("quantedge\\quotes.json", quotes_json);

   // 2. Gold M15 Institutional Indicators
   string xau_stats = "";
   if(sym_xau != "" && bid_xau > 0.0 && iBars(sym_xau, PERIOD_M15) >= 20)
     {
      double x_ema9  = iMA(sym_xau, PERIOD_M15, 9, 0, MODE_EMA, PRICE_CLOSE, 0);
      double x_ema21 = iMA(sym_xau, PERIOD_M15, 21, 0, MODE_EMA, PRICE_CLOSE, 0);
      double x_ema50 = iMA(sym_xau, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE, 0);
      double x_atr   = iATR(sym_xau, PERIOD_M15, 14, 0);
      double x_adx   = iADX(sym_xau, PERIOD_M15, 14, PRICE_CLOSE, MODE_MAIN, 0);
      double x_crange = iHigh(sym_xau, PERIOD_M15, 0) - iLow(sym_xau, PERIOD_M15, 0);
      double x_cbody  = MathAbs(iClose(sym_xau, PERIOD_M15, 0) - iOpen(sym_xau, PERIOD_M15, 0));
      xau_stats = StringFormat(
         "{\"symbol\":\"XAUUSD\",\"mt4_symbol\":\"%s\",\"price\":%.2f,\"bid\":%.2f,\"ask\":%.2f,\"ema9\":%.2f,\"ema21\":%.2f,\"ema50\":%.2f,\"atr\":%.2f,\"adx\":%.1f,\"candle_range\":%.2f,\"candle_body\":%.2f,\"time\":%d}",
         JsonEscape(sym_xau), bid_xau, bid_xau, ask_xau, x_ema9, x_ema21, x_ema50, x_atr, x_adx, x_crange, x_cbody, now
      );
      WriteCommon("quantedge\\stats_XAUUSD.json", xau_stats);
     }

   // 3. Crude Oil M15 Volatility Breakout & Donchian Indicators
   string oil_stats = "";
   if(sym_oil != "" && bid_oil > 0.0 && iBars(sym_oil, PERIOD_M15) >= 25)
     {
      double o_ema20 = iMA(sym_oil, PERIOD_M15, 20, 0, MODE_EMA, PRICE_CLOSE, 0);
      double o_ema50 = iMA(sym_oil, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE, 0);
      double o_atr   = iATR(sym_oil, PERIOD_M15, 14, 0);
      double o_adx   = iADX(sym_oil, PERIOD_M15, 14, PRICE_CLOSE, MODE_MAIN, 0);
      int hi_bar = iHighest(sym_oil, PERIOD_M15, MODE_HIGH, 20, 1);
      int lo_bar = iLowest(sym_oil, PERIOD_M15, MODE_LOW, 20, 1);
      double o_dh = (hi_bar >= 0) ? iHigh(sym_oil, PERIOD_M15, hi_bar) : (bid_oil + o_atr);
      double o_dl = (lo_bar >= 0) ? iLow(sym_oil, PERIOD_M15, lo_bar) : (bid_oil - o_atr);
      double o_crange = iHigh(sym_oil, PERIOD_M15, 0) - iLow(sym_oil, PERIOD_M15, 0);
      double o_cbody  = MathAbs(iClose(sym_oil, PERIOD_M15, 0) - iOpen(sym_oil, PERIOD_M15, 0));
      oil_stats = StringFormat(
         "{\"symbol\":\"USOIL\",\"mt4_symbol\":\"%s\",\"price\":%.2f,\"bid\":%.2f,\"ask\":%.2f,\"ema20\":%.2f,\"ema50\":%.2f,\"atr\":%.2f,\"adx\":%.1f,\"donchian_high\":%.2f,\"donchian_low\":%.2f,\"candle_range\":%.2f,\"candle_body\":%.2f,\"time\":%d}",
         JsonEscape(sym_oil), bid_oil, bid_oil, ask_oil, o_ema20, o_ema50, o_atr, o_adx, o_dh, o_dl, o_crange, o_cbody, now
      );
      WriteCommon("quantedge\\stats_USOIL.json", oil_stats);
     }

   // 4. EURUSD M15 Bollinger & RSI Indicators
   string eur_stats = "";
   if(sym_eur != "" && bid_eur > 0.0 && iBars(sym_eur, PERIOD_M15) >= 25)
     {
      double e_up  = iBands(sym_eur, PERIOD_M15, 20, 2, 0, PRICE_CLOSE, MODE_UPPER, 0);
      double e_mid = iBands(sym_eur, PERIOD_M15, 20, 2, 0, PRICE_CLOSE, MODE_MAIN, 0);
      double e_low = iBands(sym_eur, PERIOD_M15, 20, 2, 0, PRICE_CLOSE, MODE_LOWER, 0);
      double e_rsi = iRSI(sym_eur, PERIOD_M15, 14, PRICE_CLOSE, 0);
      double e_atr = iATR(sym_eur, PERIOD_M15, 14, 0);
      double e_adx = iADX(sym_eur, PERIOD_M15, 14, PRICE_CLOSE, MODE_MAIN, 0);
      double e_crange = iHigh(sym_eur, PERIOD_M15, 0) - iLow(sym_eur, PERIOD_M15, 0);
      double e_cbody  = MathAbs(iClose(sym_eur, PERIOD_M15, 0) - iOpen(sym_eur, PERIOD_M15, 0));
      eur_stats = StringFormat(
         "{\"symbol\":\"EURUSD\",\"mt4_symbol\":\"%s\",\"price\":%.5f,\"bid\":%.5f,\"ask\":%.5f,\"bb_upper\":%.5f,\"bb_middle\":%.5f,\"bb_lower\":%.5f,\"rsi\":%.1f,\"atr\":%.5f,\"adx\":%.1f,\"candle_range\":%.5f,\"candle_body\":%.5f,\"time\":%d}",
         JsonEscape(sym_eur), bid_eur, bid_eur, ask_eur, e_up, e_mid, e_low, e_rsi, e_atr, e_adx, e_crange, e_cbody, now
      );
      WriteCommon("quantedge\\stats_EURUSD.json", eur_stats);
     }

   // 5. BTCUSD M15 Indicators & Volatility Expansion
   string btc_stats = "";
   if(sym_btc != "" && bid_btc > 0.0 && iBars(sym_btc, PERIOD_M15) >= 20)
     {
      double b_ema9  = iMA(sym_btc, PERIOD_M15, 9, 0, MODE_EMA, PRICE_CLOSE, 0);
      double b_ema21 = iMA(sym_btc, PERIOD_M15, 21, 0, MODE_EMA, PRICE_CLOSE, 0);
      double b_ema50 = iMA(sym_btc, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE, 0);
      double b_atr   = iATR(sym_btc, PERIOD_M15, 14, 0);
      double b_adx   = iADX(sym_btc, PERIOD_M15, 14, PRICE_CLOSE, MODE_MAIN, 0);
      double b_rsi   = iRSI(sym_btc, PERIOD_M15, 14, PRICE_CLOSE, 0);
      int b_hi_bar   = iHighest(sym_btc, PERIOD_M15, MODE_HIGH, 20, 1);
      int b_lo_bar   = iLowest(sym_btc, PERIOD_M15, MODE_LOW, 20, 1);
      double b_dh    = (b_hi_bar >= 0) ? iHigh(sym_btc, PERIOD_M15, b_hi_bar) : (bid_btc + 2.0*b_atr);
      double b_dl    = (b_lo_bar >= 0) ? iLow(sym_btc, PERIOD_M15, b_lo_bar) : (bid_btc - 2.0*b_atr);
      double b_crange = iHigh(sym_btc, PERIOD_M15, 0) - iLow(sym_btc, PERIOD_M15, 0);
      double b_cbody  = MathAbs(iClose(sym_btc, PERIOD_M15, 0) - iOpen(sym_btc, PERIOD_M15, 0));
      btc_stats = StringFormat(
         "{\"symbol\":\"BTCUSD\",\"mt4_symbol\":\"%s\",\"price\":%.2f,\"bid\":%.2f,\"ask\":%.2f,\"ema9\":%.2f,\"ema21\":%.2f,\"ema50\":%.2f,\"atr\":%.2f,\"adx\":%.1f,\"rsi\":%.1f,\"donchian_high\":%.2f,\"donchian_low\":%.2f,\"candle_range\":%.2f,\"candle_body\":%.2f,\"time\":%d}",
         JsonEscape(sym_btc), bid_btc, bid_btc, ask_btc, b_ema9, b_ema21, b_ema50, b_atr, b_adx, b_rsi, b_dh, b_dl, b_crange, b_cbody, now
      );
      WriteCommon("quantedge\\stats_BTCUSD.json", btc_stats);
     }

   // 6. Aggregate Unified MT4 Stats
   string parts = "";
   if(xau_stats != "") parts += "\"XAUUSD\":" + xau_stats;
   if(oil_stats != "") { if(parts != "") parts += ","; parts += "\"USOIL\":" + oil_stats; }
   if(eur_stats != "") { if(parts != "") parts += ","; parts += "\"EURUSD\":" + eur_stats; }
   if(btc_stats != "") { if(parts != "") parts += ","; parts += "\"BTCUSD\":" + btc_stats; }

   string combined = StringFormat("{\"time\":%d,\"stats\":{%s}}", now, parts);
   WriteCommon("quantedge\\mt4_stats.json", combined);
  }

//+------------------------------------------------------------------+
void WriteHistory()
  {
   int hist_total = OrdersHistoryTotal();
   string items = "";
   int count = 0;

   for(int i=hist_total-1; i>=0 && count < 100; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY))
         continue;
      if(OrderType() > OP_SELL)
         continue;
      string side = (OrderType() == OP_BUY) ? "long" : "short";
      double net_pnl = OrderProfit() + OrderSwap() + OrderCommission();
      string item = StringFormat(
         "{\"ticket\":%d,\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":%.2f,\"open_price\":%.5f,\"close_price\":%.5f,\"open_time\":%d,\"close_time\":%d,\"profit\":%.2f,\"net_pnl\":%.2f,\"magic\":%d}",
         OrderTicket(), JsonEscape(OrderSymbol()), side, OrderLots(), OrderOpenPrice(), OrderClosePrice(),
         (int)OrderOpenTime(), (int)OrderCloseTime(), OrderProfit(), net_pnl, OrderMagicNumber());
      if(items != "")
         items += ",";
      items += item;
      count++;
     }
   string json = StringFormat("{\"time\":%d,\"total_closed\":%d,\"trades\":[%s]}", (int)TimeCurrent(), count, items);
   WriteCommon("quantedge\\history.json", json);
  }

//+------------------------------------------------------------------+
void WriteHeartbeat()
  {
   if(!IsMasterChart())
     {
      // Non-master charts still update quotes & indicators for their respective symbol
      WriteMT4Stats();
      return;
     }

   if(TimeCurrent() - g_last_heartbeat < InpHeartbeatSec)
      return;
   int open_count = 0;
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderMagicNumber() == InpMagic && OrderType() <= OP_SELL)
         open_count++;
     }
   string mode = IsDemo() ? "Demo" : "Real";
   string hb = StringFormat(
      "{\"type\":\"heartbeat\",\"payload\":{\"account\":%d,\"server\":\"%s\",\"trade_mode\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"positions\":%d,\"platform\":\"MT4\",\"chart_symbol\":\"%s\"}}",
      AccountNumber(), JsonEscape(AccountServer()), mode, AccountBalance(), AccountEquity(), open_count, JsonEscape(Symbol()));
   WriteCommon("quantedge\\heartbeat.json", hb);

   // Export real-time MT4 market quotes and native M15 indicators
   WriteMT4Stats();

   // Export real-time MT4 closed trade history
   WriteHistory();

   g_last_heartbeat = TimeCurrent();
  }

//+------------------------------------------------------------------+
void HandlePing(const string id)
  {
   ReplyOk(id, "{\"pong\":true,\"platform\":\"MT4\"}");
  }

//+------------------------------------------------------------------+
void HandleAccount(const string id)
  {
   string mode = IsDemo() ? "Demo" : "Real";
   string payload = StringFormat(
      "{\"account\":%d,\"server\":\"%s\",\"trade_mode\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"currency\":\"%s\",\"leverage\":%d,\"platform\":\"MT4\"}",
      AccountNumber(), JsonEscape(AccountServer()), mode,
      AccountBalance(), AccountEquity(), AccountCurrency(), AccountLeverage());
   ReplyOk(id, payload);
  }

//+------------------------------------------------------------------+
void HandlePositions(const string id)
  {
   string items = "";
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderType() > OP_SELL)
         continue;
      if(OrderMagicNumber() != InpMagic)
         continue;
      string side = (OrderType() == OP_BUY) ? "long" : "short";
      string item = StringFormat(
         "{\"ticket\":%d,\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":%.2f,\"entry_price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"open_time\":%d,\"unrealized_pnl\":%.2f}",
         OrderTicket(), JsonEscape(OrderSymbol()), side, OrderLots(), OrderOpenPrice(),
         OrderStopLoss(), OrderTakeProfit(), (int)OrderOpenTime(),
         OrderProfit()+OrderSwap()+OrderCommission());
      if(items != "")
         items += ",";
      items += item;
     }
   ReplyOk(id, "{\"positions\":[" + items + "]}");
  }

//+------------------------------------------------------------------+
bool EnsureSymbol(const string sym)
  {
   // Refresh quotes if possible (build-dependent)
   double bid = MarketInfo(sym, MODE_BID);
   if(bid > 0.0)
      return true;
   // Some brokers need the symbol in Market Watch first — try chart symbol later
   return false;
  }

//+------------------------------------------------------------------+
string ResolveTradeSymbol(const string requested)
  {
   string mapped = MapSymbol(requested);
   if(EnsureSymbol(mapped))
      return mapped;

   // Common Exness MT4 suffixes
   string suffixes[6];
   suffixes[0] = "m";
   suffixes[1] = "m.";
   suffixes[2] = ".";
   suffixes[3] = ".a";
   suffixes[4] = "pro";
   suffixes[5] = "c";
   for(int i=0; i<6; i++)
     {
      string cand = mapped + suffixes[i];
      if(EnsureSymbol(cand))
         return cand;
     }

   // Fall back to the chart the EA is attached to
   string chart_sym = Symbol();
   if(EnsureSymbol(chart_sym))
      return chart_sym;

   return "";
  }

//+------------------------------------------------------------------+
int DigitsFor(const string sym)
  {
   return (int)MarketInfo(sym, MODE_DIGITS);
  }

//+------------------------------------------------------------------+
void HandleOpen(const string id, const string json)
  {
   if(id != "" && FileIsExist("quantedge\\reply\\" + id + ".json", FILE_COMMON))
     {
      Print("QuantEdgeBridge: Command ", id, " already replied. Suppressing duplicate HandleOpen.");
      return;
     }

   string requested = ExtractString(json, "symbol");
   string side = ExtractString(json, "side");
   double volume = ExtractNumber(json, "volume", 0.01);
   double sl = ExtractNumber(json, "sl", 0.0);
   double tp = ExtractNumber(json, "tp", 0.0);
   string symbol = ResolveTradeSymbol(requested);

   if(requested == "" || volume <= 0)
     {
      ReplyErr(id, "invalid_symbol_or_volume");
      return;
     }
   if(!IsTradeAllowed())
     {
      ReplyErr(id, "trade_not_allowed_enable_autotrading");
      return;
     }
   if(!IsDemo())
     {
      ReplyErr(id, "refusing_non_demo_account");
      return;
     }
   if(symbol == "")
     {
      ReplyErr(id, "symbol_not_available:" + requested + "|chart:" + Symbol());
      return;
     }

   int cmd = OP_BUY;
   double price = MarketInfo(symbol, MODE_ASK);
   if(side == "sell" || side == "short")
     {
      cmd = OP_SELL;
      price = MarketInfo(symbol, MODE_BID);
     }

   int digits = DigitsFor(symbol);
   price = NormalizeDouble(price, digits);
   if(sl > 0) sl = NormalizeDouble(sl, digits);
   if(tp > 0) tp = NormalizeDouble(tp, digits);

   ResetLastError();
   int ticket = OrderSend(symbol, cmd, volume, price, InpSlippage, sl, tp, "QuantEdge", InpMagic, 0, clrDodgerBlue);
   if(ticket < 0)
     {
      ReplyErr(id, StringFormat("OrderSend_failed_err_%d", GetLastError()));
      return;
     }

   double fill = price;
   if(OrderSelect(ticket, SELECT_BY_TICKET))
      fill = OrderOpenPrice();

   string payload = StringFormat(
      "{\"ticket\":%d,\"price\":%.5f,\"volume\":%.2f,\"symbol\":\"%s\",\"platform\":\"MT4\"}",
      ticket, fill, volume, JsonEscape(symbol));
   ReplyOk(id, payload);
  }

//+------------------------------------------------------------------+
void HandleClose(const string id, const string json)
  {
   int ticket = (int)ExtractNumber(json, "ticket", 0);
   if(ticket <= 0 || !OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
     {
      ReplyErr(id, "position_not_found");
      return;
     }
   if(OrderMagicNumber() != InpMagic)
     {
      ReplyErr(id, "magic_mismatch");
      return;
     }
   if(OrderType() > OP_SELL)
     {
      ReplyErr(id, "not_a_market_position");
      return;
     }

   double close_price = (OrderType() == OP_BUY)
                        ? MarketInfo(OrderSymbol(), MODE_BID)
                        : MarketInfo(OrderSymbol(), MODE_ASK);
   close_price = NormalizeDouble(close_price, DigitsFor(OrderSymbol()));
   if(!OrderClose(ticket, OrderLots(), close_price, InpSlippage, clrRed))
     {
      ReplyErr(id, StringFormat("OrderClose_failed_err_%d", GetLastError()));
      return;
     }
   ReplyOk(id, StringFormat("{\"ticket\":%d,\"closed\":true,\"platform\":\"MT4\"}", ticket));
  }

//+------------------------------------------------------------------+
void HandleCloseAll(const string id)
  {
   int closed = 0;
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderMagicNumber() != InpMagic)
         continue;
      if(OrderType() > OP_SELL)
         continue;
      double close_price = (OrderType() == OP_BUY)
                           ? MarketInfo(OrderSymbol(), MODE_BID)
                           : MarketInfo(OrderSymbol(), MODE_ASK);
      close_price = NormalizeDouble(close_price, DigitsFor(OrderSymbol()));
      if(OrderClose(OrderTicket(), OrderLots(), close_price, InpSlippage, clrRed))
         closed++;
     }
   ReplyOk(id, StringFormat("{\"closed\":%d,\"platform\":\"MT4\"}", closed));
  }

//+------------------------------------------------------------------+
void HandleModify(const string id, const string json)
  {
   int ticket = (int)ExtractNumber(json, "ticket", 0);
   if(ticket <= 0 || !OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
     {
      ReplyErr(id, "position_not_found");
      return;
     }
   if(OrderMagicNumber() != InpMagic)
     {
      ReplyErr(id, "magic_mismatch");
      return;
     }
   if(OrderType() > OP_SELL)
     {
      ReplyErr(id, "not_a_market_position");
      return;
     }

   double new_sl = ExtractNumber(json, "sl", OrderStopLoss());
   double new_tp = ExtractNumber(json, "tp", OrderTakeProfit());

   int digits = DigitsFor(OrderSymbol());
   if(new_sl > 0) new_sl = NormalizeDouble(new_sl, digits);
   if(new_tp > 0) new_tp = NormalizeDouble(new_tp, digits);

   // Check if values actually changed to avoid err 1 (no changes)
   if(MathAbs(new_sl - OrderStopLoss()) < Point && MathAbs(new_tp - OrderTakeProfit()) < Point)
     {
      ReplyOk(id, StringFormat("{\"ticket\":%d,\"modified\":true,\"unchanged\":true,\"sl\":%.5f,\"tp\":%.5f}",
                               ticket, OrderStopLoss(), OrderTakeProfit()));
      return;
     }

   ResetLastError();
   if(!OrderModify(ticket, OrderOpenPrice(), new_sl, new_tp, 0, clrOrange))
     {
      int err = GetLastError();
      ReplyErr(id, StringFormat("OrderModify_failed_err_%d", err));
      return;
     }

   ReplyOk(id, StringFormat("{\"ticket\":%d,\"modified\":true,\"sl\":%.5f,\"tp\":%.5f,\"platform\":\"MT4\"}",
                            ticket, new_sl, new_tp));
  }

//+------------------------------------------------------------------+
void HandleCommand(const string json)
  {
   string id = ExtractString(json, "id");
   string action = ExtractString(json, "action");
   if(id == "" || action == "")
       return;

   if(action == "PING")
      HandlePing(id);
   else if(action == "ACCOUNT")
      HandleAccount(id);
   else if(action == "POSITIONS")
      HandlePositions(id);
   else if(action == "OPEN")
      HandleOpen(id, json);
   else if(action == "CLOSE")
      HandleClose(id, json);
   else if(action == "CLOSE_ALL")
      HandleCloseAll(id);
   else if(action == "MODIFY")
      HandleModify(id, json);
   else if(action == "HISTORY")
     {
      WriteHistory();
      string hist = ReadCommon("quantedge\\history.json");
      if(hist != "")
         ReplyOk(id, hist);
      else
         ReplyOk(id, "{\"trades\":[]}");
     }
   else if(action == "GET_STATS")
     {
      WriteMT4Stats();
      string st = ReadCommon("quantedge\\mt4_stats.json");
      if(st != "")
         ReplyOk(id, st);
      else
         ReplyOk(id, "{\"stats\":{}}");
     }
   else
      ReplyErr(id, "unknown_action");
  }

//+------------------------------------------------------------------+
void PollCommands()
  {
   if(!IsMasterChart())
      return;

   if(!FileIsExist("quantedge\\cmd\\pending.json", FILE_COMMON))
      return;

   string pending = ReadCommon("quantedge\\cmd\\pending.json");
   if(pending == "")
      return;
   if(StringFind(pending, "\"type\":\"cmd\"") < 0)
      return;

   string id = ExtractString(pending, "id");
   if(id == "")
      return;

   // Deduplication guard: ignore if already processed or reply already exists
   if(IsIdProcessed(id) || FileIsExist("quantedge\\reply\\" + id + ".json", FILE_COMMON))
     {
      DeleteCommon("quantedge\\cmd\\pending.json");
      return;
     }

   // ATOMIC INGESTION: Delete pending.json immediately BEFORE OrderSend/HandleCommand
   // so no parallel timer tick or secondary chart can ever read this command
   DeleteCommon("quantedge\\cmd\\pending.json");
   MarkIdProcessed(id);

   HandleCommand(pending);
   if(id != "")
      DeleteCommon("quantedge\\cmd\\" + id + ".json");
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(!IsTradeAllowed())
      Print("QuantEdgeBridge: enable AutoTrading in MT4 toolbar");
   if(!IsDemo())
      Print("QuantEdgeBridge: WARNING — not a Demo account; OPEN will be refused");

   // Ensure folder markers exist
   WriteCommon("quantedge\\cmd\\.keep", "1");
   WriteCommon("quantedge\\reply\\.keep", "1");
   WriteHello();
   Print("QuantEdgeBridge: file bridge active under Common\\\\Files\\\\quantedge\\\\");

   EventSetMillisecondTimer(InpTimerMs);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   DeleteCommon("quantedge\\heartbeat.json");
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   WriteHeartbeat();
   PollCommands();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
  }
//+------------------------------------------------------------------+
