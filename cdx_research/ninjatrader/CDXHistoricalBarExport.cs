#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Text;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
#endregion

// CDX research-only historical 1-minute OHLCV export.
// NOT CRTBarBridge. No TCP. No orders. Do not add to the live Phase74 stack.

namespace NinjaTrader.NinjaScript.Indicators
{
    public class CDXHistoricalBarExport : Indicator
    {
        private StreamWriter _writer;
        private string _resolvedPath;
        private string _metaPath;
        private int _rows;
        private TimeZoneInfo _chartTz;
        private TimeZoneInfo _etTz;

        [NinjaScriptProperty]
        [Display(Name = "ExportPath", Order = 1, GroupName = "CDX")]
        public string ExportPath { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ChartTimeZoneId", Order = 2, GroupName = "CDX")]
        public string ChartTimeZoneId { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "CDX research-only 1m historical export. No orders. Isolated from CRTBarBridge.";
                Name = "CDXHistoricalBarExport";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                DrawOnPricePanel = false;
                IsSuspendedWhileInactive = false;
                BarsRequiredToPlot = 1;
                ExportPath = "";
                ChartTimeZoneId = "Eastern Standard Time";
            }
            else if (State == State.DataLoaded)
            {
                OpenWriter();
            }
            else if (State == State.Terminated)
            {
                CloseWriter();
            }
        }

        protected override void OnBarUpdate()
        {
            if (_writer == null || CurrentBar < 0)
                return;
            WriteBar();
        }

        private void OpenWriter()
        {
            try
            {
                _chartTz = ResolveTz(ChartTimeZoneId, "Eastern Standard Time");
                _etTz = ResolveTz("Eastern Standard Time", "UTC");

                string dest = ExportPath;
                if (string.IsNullOrWhiteSpace(dest))
                {
                    string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
                    dest = Path.Combine(docs, "NinjaTrader 8", "cdx_export", "nq_1m_ninjatrader_sep6_sep21.csv");
                }

                string dir = Path.GetDirectoryName(dest);
                if (!string.IsNullOrEmpty(dir))
                    Directory.CreateDirectory(dir);

                _resolvedPath = dest;
                _metaPath = Path.ChangeExtension(dest, ".meta.txt");
                _writer = new StreamWriter(dest, false, new UTF8Encoding(false));
                _writer.WriteLine("timestamp_raw,chart_timezone,timestamp_utc,timestamp_et,open,high,low,close,volume,instrument,source");
                WriteMeta();
                Print("CDXHistoricalBarExport writing " + dest + " chart_tz=" + _chartTz.Id);
            }
            catch (Exception ex)
            {
                Print("CDXHistoricalBarExport open failed: " + ex.Message);
                _writer = null;
            }
        }

        private void WriteBar()
        {
            DateTime raw = Time[0];
            DateTime unspecified = DateTime.SpecifyKind(raw, DateTimeKind.Unspecified);
            DateTime utc;
            try
            {
                utc = TimeZoneInfo.ConvertTimeToUtc(unspecified, _chartTz);
            }
            catch (Exception ex)
            {
                Print("CDXHistoricalBarExport tz convert failed: " + ex.Message);
                return;
            }
            DateTime et = TimeZoneInfo.ConvertTimeFromUtc(utc, _etTz);
            string instrument = Instrument != null ? Instrument.FullName : "UNKNOWN";

            _writer.WriteLine(string.Format(
                CultureInfo.InvariantCulture,
                "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},NINJATRADER",
                raw.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                Escape(ChartTimeZoneId),
                utc.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                et.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                Open[0],
                High[0],
                Low[0],
                Close[0],
                (long)Volume[0],
                Escape(instrument)
            ));
            _rows++;
            if (_rows % 2000 == 0)
            {
                _writer.Flush();
                Print("CDXHistoricalBarExport rows=" + _rows);
            }
        }

        private void WriteMeta()
        {
            try
            {
                string session = "UNKNOWN";
                try
                {
                    if (Bars != null && Bars.TradingHours != null)
                        session = Bars.TradingHours.Name;
                }
                catch
                {
                    session = "UNKNOWN";
                }

                string instrument = Instrument != null ? Instrument.FullName : "UNKNOWN";
                string master = (Instrument != null && Instrument.MasterInstrument != null)
                    ? Instrument.MasterInstrument.Name
                    : "UNKNOWN";
                string period = BarsPeriod != null ? BarsPeriod.ToString() : "UNKNOWN";

                File.WriteAllText(
                    _metaPath,
                    "source=NINJATRADER\r\n"
                    + "not=DATABENTO\r\n"
                    + "dataset=CDX_ALIGNMENT_NINJATRADER\r\n"
                    + "instrument=" + instrument + "\r\n"
                    + "master=" + master + "\r\n"
                    + "bar_type=" + period + "\r\n"
                    + "calculate=OnBarClose\r\n"
                    + "session=" + session + "\r\n"
                    + "chart_timezone=" + ChartTimeZoneId + "\r\n"
                    + "timestamp_semantics=bar_open_in_chart_timezone_converted_via_TimeZoneInfo\r\n"
                    + "adjustment=as_presented_by_ninjatrader_no_extra_back_adjust\r\n"
                    + "export_path=" + _resolvedPath + "\r\n"
                );
            }
            catch (Exception ex)
            {
                Print("CDXHistoricalBarExport meta failed: " + ex.Message);
            }
        }

        private void CloseWriter()
        {
            if (_writer == null)
                return;
            try
            {
                _writer.Flush();
                _writer.Dispose();
                Print("CDXHistoricalBarExport closed rows=" + _rows + " path=" + _resolvedPath);
            }
            catch (Exception ex)
            {
                Print("CDXHistoricalBarExport close failed: " + ex.Message);
            }
            _writer = null;
        }

        private static TimeZoneInfo ResolveTz(string id, string fallback)
        {
            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(id);
            }
            catch
            {
                return TimeZoneInfo.FindSystemTimeZoneById(fallback);
            }
        }

        private static string Escape(string value)
        {
            if (string.IsNullOrEmpty(value))
                return "";
            return value.Replace(",", " ").Replace("\r", " ").Replace("\n", " ");
        }
    }
}
