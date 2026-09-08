#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Net.Sockets;
using System.Text;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
#endregion

// Read-only 1-minute closed-bar bridge for CRT Phase74 Python stack.
// NO order submission APIs — data feed only.

namespace NinjaTrader.NinjaScript.Indicators
{
    public class CRTBarBridge : Indicator
    {
        private TcpClient _client;
        private NetworkStream _stream;
        private StreamWriter _writer;
        private StreamReader _reader;
        private int _seq;
        private bool _authenticated;
        private readonly object _ioLock = new object();

        [NinjaScriptProperty]
        [Display(Name = "Host", Order = 1, GroupName = "Bridge")]
        public string BridgeHost { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Port", Order = 2, GroupName = "Bridge")]
        public int BridgePort { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "AuthToken", Order = 3, GroupName = "Bridge")]
        public string AuthToken { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "CRT read-only 1m bar bridge (localhost TCP, no orders)";
                Name = "CRTBarBridge";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                BridgeHost = "127.0.0.1";
                BridgePort = 8765;
                AuthToken = "";
            }
            else if (State == State.DataLoaded)
            {
                ConnectBridge();
            }
            else if (State == State.Terminated)
            {
                DisconnectBridge();
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1)
                return;

            if (!_authenticated)
            {
                ConnectBridge();
                if (!_authenticated)
                    return;
            }

            // Previous bar closed — send explicit UTC open timestamp + OHLCV.
            DateTime barOpenUtc = Time[1].ToUniversalTime();
            SendBar(
                barOpenUtc,
                Open[1],
                High[1],
                Low[1],
                Close[1],
                (long)Volume[1]
            );
        }

        private void ConnectBridge()
        {
            lock (_ioLock)
            {
                if (_authenticated)
                    return;

                try
                {
                    DisconnectBridge();
                    _client = new TcpClient();
                    _client.Connect(BridgeHost, BridgePort);
                    _stream = _client.GetStream();
                    _writer = new StreamWriter(_stream, new UTF8Encoding(false)) { AutoFlush = true };
                    _reader = new StreamReader(_stream, new UTF8Encoding(false), false);

                    string contract = Instrument != null ? Instrument.FullName : "UNKNOWN";
                    string hello = string.Format(
                        CultureInfo.InvariantCulture,
                        "{{\"type\":\"hello\",\"seq\":{0},\"auth\":\"{1}\",\"contract\":\"{2}\",\"instrument\":\"{3}\",\"chart_timezone\":\"UTC\"}}\n",
                        _seq,
                        EscapeJson(AuthToken ?? ""),
                        EscapeJson(contract),
                        EscapeJson(Instrument != null ? Instrument.MasterInstrument.Name : "UNKNOWN")
                    );
                    _writer.Write(hello);

                    string ackLine = _reader.ReadLine();
                    if (ackLine != null && ackLine.Contains("\"ok\":true"))
                    {
                        _authenticated = true;
                        Print("CRTBarBridge authenticated contract=" + contract);
                    }
                    else
                    {
                        Print("CRTBarBridge auth failed: " + ackLine);
                        DisconnectBridge();
                    }
                }
                catch (Exception ex)
                {
                    Print("CRTBarBridge connect error: " + ex.Message);
                    DisconnectBridge();
                }
            }
        }

        private void SendBar(DateTime barOpenUtc, double open, double high, double low, double close, long volume)
        {
            lock (_ioLock)
            {
                if (!_authenticated || _writer == null)
                    return;

                try
                {
                    _seq++;
                    string ts = barOpenUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
                    string contract = Instrument != null ? Instrument.FullName : "UNKNOWN";
                    string msg = string.Format(
                        CultureInfo.InvariantCulture,
                        "{{\"type\":\"bar\",\"seq\":{0},\"ts_utc\":\"{1}\",\"open\":{2},\"high\":{3},\"low\":{4},\"close\":{5},\"volume\":{6},\"contract\":\"{7}\"}}\n",
                        _seq,
                        ts,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        EscapeJson(contract)
                    );
                    _writer.Write(msg);
                }
                catch (Exception ex)
                {
                    Print("CRTBarBridge send error: " + ex.Message);
                    _authenticated = false;
                    DisconnectBridge();
                }
            }
        }

        private void DisconnectBridge()
        {
            _authenticated = false;
            try { if (_writer != null) _writer.Dispose(); } catch { }
            try { if (_reader != null) _reader.Dispose(); } catch { }
            try { if (_stream != null) _stream.Dispose(); } catch { }
            try { if (_client != null) _client.Close(); } catch { }
            _writer = null;
            _reader = null;
            _stream = null;
            _client = null;
        }

        private static string EscapeJson(string value)
        {
            if (string.IsNullOrEmpty(value))
                return "";
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private CRTBarBridge[] cacheCRTBarBridge;
        public CRTBarBridge CRTBarBridge(string bridgeHost, int bridgePort, string authToken)
        {
            return CRTBarBridge(Input, bridgeHost, bridgePort, authToken);
        }

        public CRTBarBridge CRTBarBridge(ISeries<double> input, string bridgeHost, int bridgePort, string authToken)
        {
            if (cacheCRTBarBridge != null)
                for (int idx = 0; idx < cacheCRTBarBridge.Length; idx++)
                    if (cacheCRTBarBridge[idx] != null && cacheCRTBarBridge[idx].BridgeHost == bridgeHost && cacheCRTBarBridge[idx].BridgePort == bridgePort && cacheCRTBarBridge[idx].AuthToken == authToken && cacheCRTBarBridge[idx].EqualsInput(input))
                        return cacheCRTBarBridge[idx];
            return CacheIndicator<CRTBarBridge>(new CRTBarBridge() { BridgeHost = bridgeHost, BridgePort = bridgePort, AuthToken = authToken }, input, ref cacheCRTBarBridge);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.CRTBarBridge CRTBarBridge(string bridgeHost, int bridgePort, string authToken)
        {
            return indicator.CRTBarBridge(Input, bridgeHost, bridgePort, authToken);
        }

        public Indicators.CRTBarBridge CRTBarBridge(ISeries<double> input, string bridgeHost, int bridgePort, string authToken)
        {
            return indicator.CRTBarBridge(input, bridgeHost, bridgePort, authToken);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.CRTBarBridge CRTBarBridge(string bridgeHost, int bridgePort, string authToken)
        {
            return indicator.CRTBarBridge(Input, bridgeHost, bridgePort, authToken);
        }

        public Indicators.CRTBarBridge CRTBarBridge(ISeries<double> input, string bridgeHost, int bridgePort, string authToken)
        {
            return indicator.CRTBarBridge(input, bridgeHost, bridgePort, authToken);
        }
    }
}

#endregion
