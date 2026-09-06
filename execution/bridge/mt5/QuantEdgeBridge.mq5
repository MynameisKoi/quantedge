//+------------------------------------------------------------------+
//|                                          QuantEdgeBridge.mq5     |
//| TCP JSON bridge client for QuantEdge AI (Exness MT5 Demo/Real)   |
//| Python binds 127.0.0.1:5555 — this EA connects outbound.         |
//+------------------------------------------------------------------+
#property copyright "QuantEdge AI"
#property version   "1.00"

input string InpHost           = "127.0.0.1";
input int    InpPort           = 5555;
input int    InpTimerMs        = 250;
input int    InpHeartbeatSec   = 2;
input int    InpMagic          = 20260322;
input string InpSymbolMap      = "USOIL:USOIL,XAUUSD:XAUUSD,BTCUSD:BTCUSD,EURUSD:EURUSD";

int      g_socket = INVALID_HANDLE;
bool     g_connected = false;
string   g_rx_buf = "";
datetime g_last_heartbeat = 0;

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
bool SendLine(const string line)
  {
   if(!g_connected || g_socket == INVALID_HANDLE)
      return false;
   string msg = line + "\n";
   uchar data[];
   int len = StringToCharArray(msg, data, 0, WHOLE_ARRAY, CP_UTF8);
   // StringToCharArray includes trailing '\0' — do not send it
   if(len <= 1)
      return false;
   int sent = SocketSend(g_socket, data, len - 1);
   return sent == len - 1;
  }

//+------------------------------------------------------------------+
bool ConnectBridge()
  {
   if(g_socket != INVALID_HANDLE)
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
     }
   g_connected = false;
   g_rx_buf = "";

   g_socket = SocketCreate();
   if(g_socket == INVALID_HANDLE)
     {
      Print("QuantEdgeBridge: SocketCreate failed ", GetLastError());
      return false;
     }

   if(!SocketConnect(g_socket, InpHost, InpPort, 3000))
     {
      Print("QuantEdgeBridge: connect ", InpHost, ":", InpPort, " failed err=", GetLastError());
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
      return false;
     }

   g_connected = true;
   Print("QuantEdgeBridge: connected to ", InpHost, ":", InpPort);

   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string server = AccountInfoString(ACCOUNT_SERVER);
   long trade_mode = AccountInfoInteger(ACCOUNT_TRADE_MODE); // 0=demo 1=contest 2=real
   string mode = (trade_mode == ACCOUNT_TRADE_MODE_DEMO) ? "Demo" : "Real";
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   string hello = StringFormat(
      "{\"type\":\"hello\",\"payload\":{\"account\":%s,\"server\":\"%s\",\"trade_mode\":\"%s\",\"balance\":%.2f,\"equity\":%.2f}}",
      IntegerToString(login), JsonEscape(server), mode, bal, eq);
   SendLine(hello);
   g_last_heartbeat = TimeCurrent();
   return true;
  }

//+------------------------------------------------------------------+
void SendHeartbeat()
  {
   if(!g_connected)
      return;
   if(TimeCurrent() - g_last_heartbeat < InpHeartbeatSec)
      return;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   int pos = PositionsTotal();
   string hb = StringFormat(
      "{\"type\":\"heartbeat\",\"payload\":{\"balance\":%.2f,\"equity\":%.2f,\"positions\":%d}}",
      bal, eq, pos);
   SendLine(hb);
   g_last_heartbeat = TimeCurrent();
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
double ExtractNumber(const string json, const string key, const double def=0.0)
  {
   string pattern = "\"" + key + "\":";
   int start = StringFind(json, pattern);
   if(start < 0)
      return def;
   start += StringLen(pattern);
   while(start < StringLen(json) && (StringGetCharacter(json, start) == ' '))
      start++;
   string num = "";
   for(int i=start; i<StringLen(json); i++)
     {
      ushort c = StringGetCharacter(json, i);
      if((c>='0' && c<='9') || c=='.' || c=='-')
         num += ShortToString(c);
      else
         break;
     }
   if(num == "")
      return def;
   return StringToDouble(num);
  }

//+------------------------------------------------------------------+
void ReplyOk(const string id, const string payload_json)
  {
   string msg = StringFormat("{\"type\":\"reply\",\"id\":\"%s\",\"ok\":true,\"payload\":%s}",
                             JsonEscape(id), payload_json);
   SendLine(msg);
  }

//+------------------------------------------------------------------+
void ReplyErr(const string id, const string err)
  {
   string msg = StringFormat(
      "{\"type\":\"reply\",\"id\":\"%s\",\"ok\":false,\"error\":\"%s\",\"payload\":{}}",
      JsonEscape(id), JsonEscape(err));
   SendLine(msg);
  }

//+------------------------------------------------------------------+
void HandlePing(const string id)
  {
   ReplyOk(id, "{\"pong\":true}");
  }

//+------------------------------------------------------------------+
void HandleAccount(const string id)
  {
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string server = AccountInfoString(ACCOUNT_SERVER);
   long trade_mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string mode = (trade_mode == ACCOUNT_TRADE_MODE_DEMO) ? "Demo" : "Real";
   string payload = StringFormat(
      "{\"account\":%s,\"server\":\"%s\",\"trade_mode\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"currency\":\"%s\",\"leverage\":%d}",
      IntegerToString(login), JsonEscape(server), mode,
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoString(ACCOUNT_CURRENCY),
      (int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   ReplyOk(id, payload);
  }

//+------------------------------------------------------------------+
void HandlePositions(const string id)
  {
   string items = "";
   int total = PositionsTotal();
   for(int i=0; i<total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic && InpMagic != 0)
        {
         // Still report all, or only magic? Report QuantEdge magic only when set.
         // Skip non-magic when magic filter active — actually report only our magic:
         if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
            continue;
        }
      string sym = PositionGetString(POSITION_SYMBOL);
      long type = PositionGetInteger(POSITION_TYPE);
      string side = (type == POSITION_TYPE_BUY) ? "long" : "short";
      double vol = PositionGetDouble(POSITION_VOLUME);
      double price = PositionGetDouble(POSITION_PRICE_OPEN);
      double profit = PositionGetDouble(POSITION_PROFIT);
      string item = StringFormat(
         "{\"ticket\":%s,\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":%.2f,\"entry_price\":%.5f,\"unrealized_pnl\":%.2f}",
         IntegerToString(ticket), JsonEscape(sym), side, vol, price, profit);
      if(items != "")
         items += ",";
      items += item;
     }
   ReplyOk(id, "{\"positions\":[" + items + "]}");
  }

//+------------------------------------------------------------------+
bool EnsureSymbol(const string sym)
  {
   if(!SymbolSelect(sym, true))
      return false;
   return true;
  }

//+------------------------------------------------------------------+
void HandleOpen(const string id, const string json)
  {
   string symbol = MapSymbol(ExtractString(json, "symbol"));
   string side = ExtractString(json, "side");
   double volume = ExtractNumber(json, "volume", 0.01);
   double sl = ExtractNumber(json, "sl", 0.0);
   double tp = ExtractNumber(json, "tp", 0.0);

   if(symbol == "" || volume <= 0)
     {
      ReplyErr(id, "invalid_symbol_or_volume");
      return;
     }
   if(!EnsureSymbol(symbol))
     {
      ReplyErr(id, "symbol_not_available:" + symbol);
      return;
     }

   // Safety: refuse Real accounts unless explicitly allowed via chart comment flag
   long trade_mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(trade_mode != ACCOUNT_TRADE_MODE_DEMO)
     {
      ReplyErr(id, "refusing_non_demo_account");
      return;
     }

   ENUM_ORDER_TYPE otype = ORDER_TYPE_BUY;
   double price = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(side == "sell" || side == "short")
     {
      otype = ORDER_TYPE_SELL;
      price = SymbolInfoDouble(symbol, SYMBOL_BID);
     }

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = symbol;
   req.volume   = volume;
   req.type     = otype;
   req.price    = price;
   req.deviation= 30;
   req.magic    = InpMagic;
   req.comment  = "QuantEdge";
   if(sl > 0)
      req.sl = sl;
   if(tp > 0)
      req.tp = tp;

   if(!OrderSend(req, res))
     {
      ReplyErr(id, StringFormat("OrderSend_failed_retcode_%d_err_%d", res.retcode, GetLastError()));
      return;
     }
   if(res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_DONE_PARTIAL)
     {
      ReplyErr(id, StringFormat("retcode_%d", res.retcode));
      return;
     }

   string payload = StringFormat(
      "{\"ticket\":%s,\"price\":%.5f,\"volume\":%.2f,\"symbol\":\"%s\",\"retcode\":%d}",
      IntegerToString(res.order), res.price, volume, JsonEscape(symbol), res.retcode);
   ReplyOk(id, payload);
  }

//+------------------------------------------------------------------+
void HandleCloseAll(const string id)
  {
   int closed = 0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      double volume = PositionGetDouble(POSITION_VOLUME);
      long type = PositionGetInteger(POSITION_TYPE);

      MqlTradeRequest req;
      MqlTradeResult  res;
      ZeroMemory(req);
      ZeroMemory(res);
      req.action = TRADE_ACTION_DEAL;
      req.position = ticket;
      req.symbol = symbol;
      req.volume = volume;
      req.deviation = 30;
      req.magic = InpMagic;
      if(type == POSITION_TYPE_BUY)
        {
         req.type = ORDER_TYPE_SELL;
         req.price = SymbolInfoDouble(symbol, SYMBOL_BID);
        }
      else
        {
         req.type = ORDER_TYPE_BUY;
         req.price = SymbolInfoDouble(symbol, SYMBOL_ASK);
        }
      if(OrderSend(req, res))
         closed++;
     }
   ReplyOk(id, StringFormat("{\"closed\":%d}", closed));
  }

//+------------------------------------------------------------------+
void HandleClose(const string id, const string json)
  {
   ulong ticket = (ulong)ExtractNumber(json, "ticket", 0);
   if(ticket == 0 || !PositionSelectByTicket(ticket))
     {
      ReplyErr(id, "position_not_found");
      return;
     }
   if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
     {
      ReplyErr(id, "magic_mismatch");
      return;
     }

   string symbol = PositionGetString(POSITION_SYMBOL);
   double volume = PositionGetDouble(POSITION_VOLUME);
   long type = PositionGetInteger(POSITION_TYPE);

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.position = ticket;
   req.symbol = symbol;
   req.volume = volume;
   req.deviation = 30;
   req.magic = InpMagic;
   if(type == POSITION_TYPE_BUY)
     {
      req.type = ORDER_TYPE_SELL;
      req.price = SymbolInfoDouble(symbol, SYMBOL_BID);
     }
   else
     {
      req.type = ORDER_TYPE_BUY;
      req.price = SymbolInfoDouble(symbol, SYMBOL_ASK);
     }
   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_DONE_PARTIAL))
     {
      ReplyErr(id, StringFormat("close_failed_%d", res.retcode));
      return;
     }
   ReplyOk(id, StringFormat("{\"ticket\":%s,\"closed\":true}", IntegerToString(ticket)));
  }

//+------------------------------------------------------------------+
void HandleCommand(const string json)
  {
   string id = ExtractString(json, "id");
   string action = ExtractString(json, "action");
   if(id == "" || action == "")
      return;

   // payload may be nested; for simplicity re-parse fields from whole json
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
   else
      ReplyErr(id, "unknown_action");
  }

//+------------------------------------------------------------------+
void PollSocket()
  {
   if(!g_connected || g_socket == INVALID_HANDLE)
     {
      static datetime last_try = 0;
      if(TimeCurrent() - last_try >= 3)
        {
         last_try = TimeCurrent();
         ConnectBridge();
        }
      return;
     }

   uchar buf[];
   ArrayResize(buf, 4096);
   uint readable = SocketIsReadable(g_socket);
   if(readable > 0)
     {
      int got = SocketRead(g_socket, buf, MathMin(readable, 4096), 10);
      if(got > 0)
        {
         string chunk = CharArrayToString(buf, 0, got, CP_UTF8);
         g_rx_buf += chunk;
        }
      else if(got < 0)
        {
         Print("QuantEdgeBridge: read error ", GetLastError());
         g_connected = false;
         SocketClose(g_socket);
         g_socket = INVALID_HANDLE;
         return;
        }
     }

   // If peer closed
   if(!SocketIsConnected(g_socket))
     {
      Print("QuantEdgeBridge: socket disconnected");
      g_connected = false;
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
      return;
     }

   int nl;
   while((nl = StringFind(g_rx_buf, "\n")) >= 0)
     {
      string line = StringSubstr(g_rx_buf, 0, nl);
      g_rx_buf = StringSubstr(g_rx_buf, nl + 1);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0)
         continue;
      if(StringFind(line, "\"type\":\"cmd\"") >= 0 || StringFind(line, "\"type\": \"cmd\"") >= 0)
         HandleCommand(line);
     }

   SendHeartbeat();
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("QuantEdgeBridge: enable AutoTrading in MT5 toolbar");
   EventSetMillisecondTimer(InpTimerMs);
   ConnectBridge();
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_socket != INVALID_HANDLE)
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
     }
   g_connected = false;
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   PollSocket();
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   // Timer drives IO; tick kept for chart activity
  }
//+------------------------------------------------------------------+
