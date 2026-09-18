#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
#endregion

// Phase85 execution bridge — localhost JSON-lines, authenticated, allowlisted commands only.
// Separate from CRTBarBridge (market-data only). No shell, no HTTP, no dynamic code.

namespace NinjaTrader.NinjaScript.AddOns
{
    public class CRTExecutionBridge : AddOnBase
    {
        private const int ProtocolVersion = 1;
        private const int MaxQuantity = 1;
        private const string AllowedRoot = "MNQ";

        private TcpClient _client;
        private NetworkStream _stream;
        private StreamWriter _writer;
        private StreamReader _reader;
        private Thread _readerThread;
        private volatile bool _run;
        private bool _authenticated;
        private readonly object _ioLock = new object();
        private readonly object _idLock = new object();
        private readonly HashSet<string> _commandIds = new HashSet<string>(StringComparer.Ordinal);
        private Account _account;
        private string _side = "FLAT";
        private int _filledQty;
        private string _ocoId = "";

        [NinjaScriptProperty]
        [Display(Name = "Host", Order = 1, GroupName = "Bridge")]
        public string BridgeHost { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Port", Order = 2, GroupName = "Bridge")]
        public int BridgePort { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ExpectedAccount", Order = 3, GroupName = "Bridge")]
        public string ExpectedAccount { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ExpectedContract", Order = 4, GroupName = "Bridge")]
        public string ExpectedContract { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "CRT Phase85 execution bridge (localhost TCP, no generic broker passthrough)";
                Name = "CRTExecutionBridge";
                BridgeHost = "127.0.0.1";
                BridgePort = 8766;
                ExpectedAccount = "";
                ExpectedContract = "";
            }
            else if (State == State.Realtime || State == State.Configure)
            {
                LoadPersistedCommandIds();
                ConnectBridge();
            }
            else if (State == State.Terminated)
            {
                DisconnectBridge();
            }
        }

        private void ConnectBridge()
        {
            lock (_ioLock)
            {
                try
                {
                    DisconnectBridge();
                    if (BridgeHost != "127.0.0.1" && BridgeHost != "localhost")
                    {
                        Print("CRTExecutionBridge refuse non-local host");
                        return;
                    }

                    string token = ReadTokenFromFile();
                    if (string.IsNullOrEmpty(token))
                    {
                        Print("CRTExecutionBridge missing execution token file");
                        return;
                    }

                    _client = new TcpClient();
                    _client.Connect(IPAddress.Loopback, BridgePort);
                    _stream = _client.GetStream();
                    var utf8 = new UTF8Encoding(false);
                    _writer = new StreamWriter(_stream, utf8) { AutoFlush = true };
                    _reader = new StreamReader(_stream, utf8, false);

                    string hello = string.Format(
                        CultureInfo.InvariantCulture,
                        "{{\"type\":\"hello\",\"protocol_version\":{0},\"auth\":\"{1}\",\"account\":\"{2}\",\"instrument\":\"{3}\"}}\n",
                        ProtocolVersion,
                        EscapeJson(token),
                        EscapeJson(ExpectedAccount ?? ""),
                        EscapeJson(ExpectedContract ?? "")
                    );
                    _writer.Write(hello);
                    string ack = _reader.ReadLine();
                    if (ack == null || !(ack.Contains("\"ok\":true") || ack.Contains("\"ok\": true")))
                    {
                        Print("CRTExecutionBridge auth failed");
                        DisconnectBridge();
                        return;
                    }

                    if (!ResolveAccount())
                    {
                        Emit("EXECUTION_NOT_READY", "", "REJECT_ACCOUNT_NOT_ALLOWED", "", 0, 0);
                        DisconnectBridge();
                        return;
                    }

                    _authenticated = true;
                    _run = true;
                    SubscribeAccount();
                    Emit("EXECUTION_BRIDGE_READY", "", "OK", "", 0, 0);
                    Emit("ACCOUNT_STATE", "", "OK", "", 0, 0);
                    _readerThread = new Thread(ReadLoop) { IsBackground = true, Name = "CRTExecutionBridge" };
                    _readerThread.Start();
                    Print("CRTExecutionBridge authenticated");
                }
                catch (Exception ex)
                {
                    Print("CRTExecutionBridge connect error: " + ex.Message);
                    DisconnectBridge();
                }
            }
        }

        private void ReadLoop()
        {
            try
            {
                while (_run && _reader != null)
                {
                    string line = _reader.ReadLine();
                    if (line == null)
                        break;
                    if (string.IsNullOrWhiteSpace(line))
                        continue;
                    HandleCommandLine(line);
                }
            }
            catch (Exception ex)
            {
                Print("CRTExecutionBridge read: " + ex.Message);
            }
            finally
            {
                _authenticated = false;
                Emit("CONNECTION_STATE", "", "DISCONNECTED", "", 0, 0);
            }
        }

        private void HandleCommandLine(string line)
        {
            if (!_authenticated)
            {
                Emit("COMMAND_REJECTED", "", "NOT_AUTHENTICATED", "", 0, 0);
                return;
            }

            string command = JsonString(line, "command");
            string commandId = JsonString(line, "command_id");
            string account = JsonString(line, "account");
            string instrument = JsonString(line, "instrument");
            int quantity = JsonInt(line, "quantity", 1);
            int version = JsonInt(line, "protocol_version", 1);
            string signalId = JsonString(line, "signal_id");
            string eventId = JsonString(line, "event_id");

            if (version != ProtocolVersion)
            {
                Emit("COMMAND_REJECTED", commandId, "UNSUPPORTED_PROTOCOL", "", 0, 0);
                return;
            }
            if (!IsAllowedCommand(command))
            {
                Emit("COMMAND_REJECTED", commandId, "UNKNOWN_COMMAND", "", 0, 0);
                return;
            }
            if (string.IsNullOrEmpty(commandId))
            {
                Emit("COMMAND_REJECTED", commandId, "MALFORMED_JSON", "", 0, 0);
                return;
            }

            lock (_idLock)
            {
                if (_commandIds.Contains(commandId))
                {
                    Emit("DUPLICATE_COMMAND", commandId, "DUPLICATE_COMMAND", "", 0, 0);
                    return;
                }
                _commandIds.Add(commandId);
                PersistCommandId(commandId);
            }

            if (!string.IsNullOrEmpty(account) && account != ExpectedAccount)
            {
                Emit("COMMAND_REJECTED", commandId, "REJECT_ACCOUNT_NOT_ALLOWED", "", 0, 0);
                return;
            }
            if ((command == "ENTER_LONG" || command == "ENTER_SHORT" || command == "PLACE_PROTECTION") && quantity > MaxQuantity)
            {
                Emit("COMMAND_REJECTED", commandId, "REJECT_MAX_QUANTITY", "", 0, 0);
                return;
            }
            if ((command == "ENTER_LONG" || command == "ENTER_SHORT" || command == "PLACE_PROTECTION") && !InstrumentAllowed(instrument))
            {
                Emit("COMMAND_REJECTED", commandId, "REJECT_CONTRACT_MISMATCH", "", 0, 0);
                return;
            }

            if (command == "PING")
            {
                Emit("PONG", commandId, "OK", "", 0, 0);
                return;
            }
            if (command == "QUERY_POSITION" || command == "RECONCILE" || command == "QUERY_ORDERS")
            {
                EmitPosition(commandId);
                return;
            }
            if (command == "CANCEL_ENTRY")
            {
                CancelWorking("ENTRY");
                Emit("ORDER_CANCELLED", commandId, "OK", "", 0, 0);
                return;
            }
            if (command == "FLATTEN")
            {
                FlattenAccount(commandId);
                return;
            }
            if (command == "PLACE_PROTECTION")
            {
                PlaceProtection(line, commandId);
                return;
            }
            if (command == "ENTER_LONG" || command == "ENTER_SHORT")
            {
                Enter(command, commandId, quantity, signalId, eventId);
            }
        }

        private void Enter(string command, string commandId, int quantity, string signalId, string eventId)
        {
            if (_account == null || _account.Connection == null || _account.Connection.Status != ConnectionStatus.Connected)
            {
                Emit("COMMAND_REJECTED", commandId, "EXECUTION_NOT_READY", "", 0, 0);
                return;
            }
            if (!IsFlat())
            {
                Emit("COMMAND_REJECTED", commandId, "REJECT_POSITION_OPEN", "", 0, 0);
                return;
            }

            Instrument inst = Instrument.GetInstrument(ExpectedContract);
            if (inst == null)
            {
                Emit("COMMAND_REJECTED", commandId, "REJECT_CONTRACT_MISMATCH", "", 0, 0);
                return;
            }

            OrderAction action = command == "ENTER_LONG" ? OrderAction.Buy : OrderAction.Sell;
            // NT8 public API: Account.CreateOrder(Instrument, OrderAction, OrderType, OrderEntry, TimeInForce, qty, limit, stop, oco, name, gtd, text)
            Order order = _account.CreateOrder(
                inst,
                action,
                OrderType.Market,
                OrderEntry.Automated,
                TimeInForce.Day,
                quantity,
                0,
                0,
                "",
                "CRT85-ENTRY",
                DateTime.MaxValue,
                commandId
            );
            Emit("ORDER_RECEIVED", commandId, "OK", order != null ? order.OrderId : "", 0, 0);
            _account.Submit(new[] { order });
            Emit("ORDER_SUBMITTED", commandId, "OK", order != null ? order.OrderId : "", 0, 0);
        }

        private void PlaceProtection(string line, string commandId)
        {
            if (_filledQty < 1 || IsFlat())
            {
                Emit("PROTECTION_FAILURE", commandId, "NO_POSITION", "", 0, 0);
                return;
            }
            int qty = JsonInt(line, "quantity", _filledQty);
            if (qty > _filledQty || qty > MaxQuantity)
            {
                Emit("COMMAND_REJECTED", commandId, "INVALID_QUANTITY", "", 0, 0);
                return;
            }
            double stop = JsonDouble(line, "stop_price");
            double target = JsonDouble(line, "target_price");
            Instrument inst = Instrument.GetInstrument(ExpectedContract);
            if (inst == null || _account == null)
            {
                Emit("PROTECTION_FAILURE", commandId, "REJECT_CONTRACT_MISMATCH", "", 0, 0);
                return;
            }

            _ocoId = Guid.NewGuid().ToString("N");
            OrderAction exit = _side == "LONG" ? OrderAction.Sell : OrderAction.Buy;
            Order stopOrd = _account.CreateOrder(inst, exit, OrderType.StopMarket, OrderEntry.Automated, TimeInForce.Gtc, qty, 0, stop, _ocoId, "CRT85-STOP", DateTime.MaxValue, commandId);
            Order tgtOrd = _account.CreateOrder(inst, exit, OrderType.Limit, OrderEntry.Automated, TimeInForce.Gtc, qty, target, 0, _ocoId, "CRT85-TARGET", DateTime.MaxValue, commandId);
            try
            {
                _account.Submit(new[] { stopOrd, tgtOrd });
                Emit("STOP_WORKING", commandId, "OK", stopOrd != null ? stopOrd.OrderId : "", 0, 0);
                Emit("TARGET_WORKING", commandId, "OK", tgtOrd != null ? tgtOrd.OrderId : "", 0, 0);
            }
            catch (Exception ex)
            {
                Print("CRTExecutionBridge protection: " + ex.Message);
                Emit("PROTECTION_FAILURE", commandId, "PROTECTION_REJECT", "", 0, 0);
                FlattenAccount(commandId);
            }
        }

        private void FlattenAccount(string commandId)
        {
            if (_account == null)
            {
                Emit("COMMAND_REJECTED", commandId, "EXECUTION_NOT_READY", "", 0, 0);
                return;
            }
            Instrument inst = Instrument.GetInstrument(ExpectedContract);
            if (inst == null)
            {
                Emit("COMMAND_REJECTED", commandId, "REJECT_CONTRACT_MISMATCH", "", 0, 0);
                return;
            }
            try
            {
                CancelWorking("");
                _account.Flatten(new[] { inst });
            }
            catch (Exception ex)
            {
                Print("CRTExecutionBridge flatten: " + ex.Message);
            }
        }

        private void CancelWorking(string nameContains)
        {
            if (_account == null)
                return;
            List<Order> cancel = new List<Order>();
            foreach (Order o in _account.Orders)
            {
                if (o == null)
                    continue;
                if (o.OrderState != OrderState.Working && o.OrderState != OrderState.Accepted && o.OrderState != OrderState.Submitted)
                    continue;
                if (!string.IsNullOrEmpty(nameContains) && (o.Name == null || o.Name.IndexOf(nameContains, StringComparison.OrdinalIgnoreCase) < 0))
                    continue;
                cancel.Add(o);
            }
            if (cancel.Count > 0)
                _account.Cancel(cancel.ToArray());
        }

        private bool ResolveAccount()
        {
            if (string.IsNullOrWhiteSpace(ExpectedAccount))
                return false;
            Account match = null;
            int matches = 0;
            foreach (Account acct in Account.All)
            {
                if (acct == null || acct.Name != ExpectedAccount)
                    continue;
                matches++;
                match = acct;
            }
            if (matches != 1)
                return false;
            if (match.Connection == null || match.Connection.Status != ConnectionStatus.Connected)
                return false;
            _account = match;
            return true;
        }

        private void SubscribeAccount()
        {
            if (_account == null)
                return;
            _account.OrderUpdate += OnOrderUpdate;
            _account.ExecutionUpdate += OnExecutionUpdate;
            _account.PositionUpdate += OnPositionUpdate;
        }

        private void UnsubscribeAccount()
        {
            if (_account == null)
                return;
            _account.OrderUpdate -= OnOrderUpdate;
            _account.ExecutionUpdate -= OnExecutionUpdate;
            _account.PositionUpdate -= OnPositionUpdate;
        }

        private void OnOrderUpdate(object sender, OrderEventArgs e)
        {
            if (e == null || e.Order == null)
                return;
            Order o = e.Order;
            string commandId = o.CustomText ?? "";
            if (o.OrderState == OrderState.Accepted || o.OrderState == OrderState.Working)
                Emit("ORDER_ACCEPTED", commandId, "OK", o.OrderId, 0, 0);
            else if (o.OrderState == OrderState.Rejected)
                Emit("ORDER_REJECTED", commandId, "BROKER_REJECT", o.OrderId, 0, 0);
            else if (o.OrderState == OrderState.Cancelled)
                Emit("ORDER_CANCELLED", commandId, "OK", o.OrderId, 0, 0);
        }

        private void OnExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            if (e == null || e.Execution == null)
                return;
            Execution ex = e.Execution;
            string commandId = ex.Order != null ? (ex.Order.CustomText ?? "") : "";
            int remaining = 0;
            if (ex.Order != null)
                remaining = Math.Max(0, ex.Order.Quantity - ex.Order.Filled);
            if (ex.Order != null && ex.Order.OrderState == OrderState.PartFilled)
                Emit("PARTIAL_FILL", commandId, "OK", ex.Order.OrderId, ex.Price, ex.Quantity, remaining);
            else
                Emit("FILLED", commandId, "OK", ex.Order != null ? ex.Order.OrderId : "", ex.Price, ex.Quantity, remaining);

            if (ex.Order != null && ex.Order.Name == "CRT85-STOP")
                Emit("STOP_FILLED", commandId, "OK", ex.Order.OrderId, ex.Price, ex.Quantity, 0);
            if (ex.Order != null && ex.Order.Name == "CRT85-TARGET")
                Emit("TARGET_FILLED", commandId, "OK", ex.Order.OrderId, ex.Price, ex.Quantity, 0);
        }

        private void OnPositionUpdate(object sender, PositionEventArgs e)
        {
            if (e == null || e.Position == null)
                return;
            Position p = e.Position;
            if (p.MarketPosition == MarketPosition.Flat)
            {
                _side = "FLAT";
                _filledQty = 0;
                Emit("POSITION_FLAT", "", "OK", "", 0, 0);
            }
            else
            {
                _side = p.MarketPosition == MarketPosition.Long ? "LONG" : "SHORT";
                _filledQty = p.Quantity;
                Emit("POSITION_UPDATE", "", "OK", "", p.AveragePrice, p.Quantity);
            }
        }

        private bool IsFlat()
        {
            if (_account == null)
                return false;
            foreach (Position p in _account.Positions)
            {
                if (p == null || p.Instrument == null)
                    continue;
                if (!InstrumentAllowed(p.Instrument.FullName))
                    continue;
                if (p.MarketPosition != MarketPosition.Flat && p.Quantity != 0)
                    return false;
            }
            return true;
        }

        private void EmitPosition(string commandId)
        {
            string side = "FLAT";
            int qty = 0;
            if (_account != null)
            {
                foreach (Position p in _account.Positions)
                {
                    if (p == null || p.MarketPosition == MarketPosition.Flat)
                        continue;
                    if (!InstrumentAllowed(p.Instrument != null ? p.Instrument.FullName : ""))
                        continue;
                    side = p.MarketPosition == MarketPosition.Long ? "LONG" : "SHORT";
                    qty = p.Quantity;
                }
            }
            Emit(side == "FLAT" ? "POSITION_FLAT" : "POSITION_UPDATE", commandId, "OK", "", 0, qty);
            Emit("RECONCILIATION_RESULT", commandId, "OK", "", 0, qty);
        }

        private static bool IsAllowedCommand(string command)
        {
            return command == "ENTER_LONG" || command == "ENTER_SHORT" || command == "PLACE_PROTECTION"
                || command == "CANCEL_ENTRY" || command == "FLATTEN" || command == "QUERY_POSITION"
                || command == "QUERY_ORDERS" || command == "PING" || command == "RECONCILE";
        }

        private bool InstrumentAllowed(string instrument)
        {
            if (string.IsNullOrEmpty(instrument))
                instrument = ExpectedContract;
            if (string.IsNullOrEmpty(instrument))
                return false;
            string root = instrument.Trim();
            int space = root.IndexOf(' ');
            if (space > 0)
                root = root.Substring(0, space);
            if (root.Equals("NQ", StringComparison.OrdinalIgnoreCase))
                return false;
            if (!root.Equals(AllowedRoot, StringComparison.OrdinalIgnoreCase))
                return false;
            if (!string.IsNullOrEmpty(ExpectedContract) && instrument != ExpectedContract && instrument != AllowedRoot)
                return instrument.StartsWith(AllowedRoot, StringComparison.OrdinalIgnoreCase) && instrument == ExpectedContract;
            return true;
        }

        private void Emit(string ev, string commandId, string reason, string orderId, double fillPrice, int fillQty)
        {
            Emit(ev, commandId, reason, orderId, fillPrice, fillQty, 0);
        }

        private void Emit(string ev, string commandId, string reason, string orderId, double fillPrice, int fillQty, int remaining)
        {
            string ts = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
            string msg = string.Format(
                CultureInfo.InvariantCulture,
                "{{\"protocol_version\":{0},\"event\":\"{1}\",\"command_id\":\"{2}\",\"reason\":\"{3}\",\"order_id\":\"{4}\",\"fill_price\":{5},\"fill_quantity\":{6},\"remaining_quantity\":{7},\"account\":\"{8}\",\"instrument\":\"{9}\",\"created_at_utc\":\"{10}\"}}\n",
                ProtocolVersion,
                EscapeJson(ev),
                EscapeJson(commandId ?? ""),
                EscapeJson(reason ?? ""),
                EscapeJson(orderId ?? ""),
                fillPrice.ToString(CultureInfo.InvariantCulture),
                fillQty,
                remaining,
                EscapeJson(ExpectedAccount ?? ""),
                EscapeJson(ExpectedContract ?? ""),
                ts
            );
            lock (_ioLock)
            {
                if (_writer == null)
                    return;
                try { _writer.Write(msg); }
                catch { }
            }
        }

        private void LoadPersistedCommandIds()
        {
            try
            {
                string path = CommandIdPath();
                if (!File.Exists(path))
                    return;
                foreach (string line in File.ReadAllLines(path))
                {
                    if (!string.IsNullOrWhiteSpace(line))
                        _commandIds.Add(line.Trim());
                }
            }
            catch
            {
            }
        }

        private void PersistCommandId(string commandId)
        {
            try
            {
                File.AppendAllText(CommandIdPath(), commandId + Environment.NewLine);
            }
            catch
            {
            }
        }

        private static string CommandIdPath()
        {
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            return Path.Combine(docs, "NinjaTrader 8", "bin", "Custom", "crt_execution_command_ids.txt");
        }

        private static string ReadTokenFromFile()
        {
            foreach (string path in TokenFilePaths())
            {
                try
                {
                    if (!File.Exists(path))
                        continue;
                    string token = File.ReadAllText(path).Trim();
                    if (!string.IsNullOrEmpty(token))
                        return token;
                }
                catch
                {
                }
            }
            return "";
        }

        private static string[] TokenFilePaths()
        {
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string oneDrive = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "OneDrive", "Documents");
            return new[]
            {
                Path.Combine(docs, "NinjaTrader 8", "bin", "crt_execution_token.txt"),
                Path.Combine(oneDrive, "NinjaTrader 8", "bin", "crt_execution_token.txt"),
                Path.Combine(docs, "NinjaTrader 8", "bin", "Custom", "crt_execution_token.txt"),
                Path.Combine(oneDrive, "NinjaTrader 8", "bin", "Custom", "crt_execution_token.txt"),
            };
        }

        private void DisconnectBridge()
        {
            _run = false;
            _authenticated = false;
            UnsubscribeAccount();
            try { if (_writer != null) _writer.Dispose(); } catch { }
            try { if (_reader != null) _reader.Dispose(); } catch { }
            try { if (_stream != null) _stream.Dispose(); } catch { }
            try { if (_client != null) _client.Close(); } catch { }
            _writer = null;
            _reader = null;
            _stream = null;
            _client = null;
            _account = null;
        }

        private static string JsonString(string json, string key)
        {
            string needle = "\"" + key + "\"";
            int i = json.IndexOf(needle, StringComparison.Ordinal);
            if (i < 0)
                return "";
            int colon = json.IndexOf(':', i + needle.Length);
            if (colon < 0)
                return "";
            int q1 = json.IndexOf('"', colon + 1);
            if (q1 < 0)
                return "";
            int q2 = json.IndexOf('"', q1 + 1);
            if (q2 < 0)
                return "";
            return json.Substring(q1 + 1, q2 - q1 - 1);
        }

        private static int JsonInt(string json, string key, int fallback)
        {
            string needle = "\"" + key + "\"";
            int i = json.IndexOf(needle, StringComparison.Ordinal);
            if (i < 0)
                return fallback;
            int colon = json.IndexOf(':', i + needle.Length);
            if (colon < 0)
                return fallback;
            int end = colon + 1;
            while (end < json.Length && (json[end] == ' '))
                end++;
            int start = end;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '-'))
                end++;
            int value;
            if (int.TryParse(json.Substring(start, end - start), NumberStyles.Integer, CultureInfo.InvariantCulture, out value))
                return value;
            return fallback;
        }

        private static double JsonDouble(string json, string key)
        {
            string needle = "\"" + key + "\"";
            int i = json.IndexOf(needle, StringComparison.Ordinal);
            if (i < 0)
                return 0;
            int colon = json.IndexOf(':', i + needle.Length);
            if (colon < 0)
                return 0;
            int end = colon + 1;
            while (end < json.Length && json[end] == ' ')
                end++;
            int start = end;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '.' || json[end] == '-'))
                end++;
            double value;
            if (double.TryParse(json.Substring(start, end - start), NumberStyles.Float, CultureInfo.InvariantCulture, out value))
                return value;
            return 0;
        }

        private static string EscapeJson(string value)
        {
            if (string.IsNullOrEmpty(value))
                return "";
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }
    }
}
#endregion
