"""
Muffett Investments — Nasdaq 100 RS & Volume Scanner
Vercel serverless endpoint
"""

from http.server import BaseHTTPRequestHandler
import yfinance as yf
import pandas as pd
from datetime import datetime

# ── Nasdaq 100 Universe ───────────────────────────────────────────────────────
NASDAQ_100 = {
    "AAPL":  "Apple",          "MSFT":  "Microsoft",      "NVDA":  "NVIDIA",
    "AMZN":  "Amazon",         "META":  "Meta",            "GOOGL": "Alphabet A",
    "GOOG":  "Alphabet C",     "TSLA":  "Tesla",           "AVGO":  "Broadcom",
    "COST":  "Costco",         "NFLX":  "Netflix",         "AMD":   "AMD",
    "ADBE":  "Adobe",          "QCOM":  "Qualcomm",        "PEP":   "PepsiCo",
    "CSCO":  "Cisco",          "TMUS":  "T-Mobile",        "TXN":   "Texas Instruments",
    "AMAT":  "Applied Materials","INTU": "Intuit",          "AMGN":  "Amgen",
    "SBUX":  "Starbucks",      "ISRG":  "Intuitive Surgical","BKNG": "Booking Holdings",
    "VRTX":  "Vertex Pharma",  "LRCX":  "Lam Research",    "REGN":  "Regeneron",
    "MU":    "Micron",         "GILD":  "Gilead",          "ADI":   "Analog Devices",
    "MRVL":  "Marvell Tech",   "PANW":  "Palo Alto",       "KLAC":  "KLA Corp",
    "ADP":   "ADP",            "INTC":  "Intel",           "SNPS":  "Synopsys",
    "CDNS":  "Cadence Design", "MDLZ":  "Mondelez",        "PYPL":  "PayPal",
    "CEG":   "Constellation Energy","CTAS":"Cintas",        "ABNB":  "Airbnb",
    "FTNT":  "Fortinet",       "MAR":   "Marriott",        "MCHP":  "Microchip Tech",
    "NXPI":  "NXP Semi",       "ORLY":  "O'Reilly Auto",   "CSX":   "CSX Corp",
    "PCAR":  "PACCAR",         "WDAY":  "Workday",         "KHC":   "Kraft Heinz",
    "DXCM":  "Dexcom",         "ROST":  "Ross Stores",     "ODFL":  "Old Dominion",
    "BIIB":  "Biogen",         "IDXX":  "IDEXX Labs",      "FANG":  "Diamondback Energy",
    "GEHC":  "GE Healthcare",  "EXC":   "Exelon",          "MRNA":  "Moderna",
    "ON":    "ON Semiconductor","TTD":  "Trade Desk",      "MNST":  "Monster Beverage",
    "PAYX":  "Paychex",        "ROP":   "Roper Tech",      "KDP":   "Keurig Dr Pepper",
    "TEAM":  "Atlassian",      "FAST":  "Fastenal",        "CPRT":  "Copart",
    "DLTR":  "Dollar Tree",    "EA":    "Electronic Arts",  "CRWD":  "CrowdStrike",
    "DDOG":  "Datadog",        "ZS":    "Zscaler",         "VRSK":  "Verisk",
    "CTSH":  "Cognizant",      "LULU":  "Lululemon",       "MELI":  "MercadoLibre",
    "ILMN":  "Illumina",       "CSGP":  "CoStar",          "SMCI":  "Super Micro",
    "ARM":   "ARM Holdings",   "UBER":  "Uber",            "DASH":  "DoorDash",
    "CDW":   "CDW Corp",       "CHTR":  "Charter Comm",    "CMCSA": "Comcast",
    "APP":   "AppLovin",       "PLTR":  "Palantir",        "ZM":    "Zoom",
    "ALGN":  "Align Tech",     "MTCH":  "Match Group",     "HOOD":  "Robinhood",
    "COIN":  "Coinbase",       "WBD":   "Warner Bros",     "RIVN":  "Rivian",
    "LCID":  "Lucid Motors",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_vol(v):
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    elif v >= 1_000:   return f"{v/1_000:.0f}K"
    return str(int(v))

def ret_html(val):
    color = "#4caf50" if val > 0 else "#ef5350" if val < 0 else "#888"
    sign  = "+" if val > 0 else ""
    return f"<span style='color:{color};font-weight:600'>{sign}{val}%</span>"

def rs_badge(rs):
    if rs >= 10:   label, c = "Top RS",  "#0d47a1"
    elif rs >= 5:  label, c = "Strong",  "#1b5e20"
    elif rs >= 2:  label, c = "Rising",  "#2e7d32"
    elif rs >= 0:  label, c = "Neutral", "#37474f"
    elif rs >= -3: label, c = "Weak",    "#b71c1c"
    else:          label, c = "Lagging", "#7f0000"
    return f"<span style='background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:.72rem;white-space:nowrap'>{label}</span>"

def vol_bar(ratio):
    pct   = min(ratio * 50, 100)
    color = "#4caf50" if ratio >= 1.3 else "#ef5350" if ratio < 0.7 else "#888"
    return (f"<div style='display:flex;align-items:center;gap:6px'>"
            f"<div style='width:60px;height:6px;background:#1e1e28;border-radius:3px'>"
            f"<div style='width:{pct:.0f}%;height:6px;background:{color};border-radius:3px'></div></div>"
            f"<span style='color:{color};font-size:.82rem'>{ratio:.1f}x</span></div>")

def vol_trend_html(t):
    if t >= 1.2:   return "<span style='color:#4caf50;font-size:.82rem'>&#9650; Rising</span>"
    elif t <= 0.8: return "<span style='color:#ef5350;font-size:.82rem'>&#9660; Falling</span>"
    else:          return "<span style='color:#888;font-size:.82rem'>&#8212; Flat</span>"

def ma_check(above):
    return "<span style='color:#4caf50'>&#10003;</span>" if above else "<span style='color:#ef5350'>&#10007;</span>"

# ── Data & Calculation ────────────────────────────────────────────────────────
def run_scan():
    all_tickers = list(NASDAQ_100.keys()) + ["QQQ"]
    raw = yf.download(all_tickers, period="1y", interval="1d",
                      auto_adjust=True, progress=False)
    close  = raw["Close"]
    volume = raw["Volume"]

    if isinstance(close,  pd.Series): close  = close.to_frame(name=all_tickers[0])
    if isinstance(volume, pd.Series): volume = volume.to_frame(name=all_tickers[0])

    # Retry missing
    missing = [t for t in all_tickers if t not in close.columns or close[t].dropna().empty]
    for t in missing:
        try:
            s = yf.download(t, period="1y", interval="1d", auto_adjust=True, progress=False)
            close[t]  = s["Close"]
            volume[t] = s["Volume"]
        except Exception:
            pass

    qqq = close["QQQ"].dropna()
    qqq_now   = float(qqq.iloc[-1])
    qqq_ret_1w = round((qqq_now / float(qqq.iloc[-6])  - 1)*100, 1) if len(qqq)>=6  else 0
    qqq_ret_1m = round((qqq_now / float(qqq.iloc[-22]) - 1)*100, 1) if len(qqq)>=22 else 0
    qqq_ret_1q = round((qqq_now / float(qqq.iloc[-63]) - 1)*100, 1) if len(qqq)>=63 else 0

    rows = []
    for ticker, name in NASDAQ_100.items():
        try:
            c = close[ticker].dropna()
            v = volume[ticker].dropna()
            if len(c) < 22 or len(v) < 22: continue

            p_now = float(c.iloc[-1])
            p_1w  = float(c.iloc[-6])  if len(c)>=6  else float(c.iloc[0])
            p_1m  = float(c.iloc[-22]) if len(c)>=22 else float(c.iloc[0])
            p_1q  = float(c.iloc[-63]) if len(c)>=63 else float(c.iloc[0])

            ret_1w = round((p_now/p_1w - 1)*100, 1)
            ret_1m = round((p_now/p_1m - 1)*100, 1)
            ret_1q = round((p_now/p_1q - 1)*100, 1)
            rs_1w  = round(ret_1w - qqq_ret_1w, 1)
            rs_1q  = round(ret_1q - qqq_ret_1q, 1)
            rs_score = round(0.4*rs_1w + 0.6*rs_1q, 1)

            vol_today   = int(v.iloc[-1])
            vol_avg_20d = float(v.iloc[-21:-1].mean()) if len(v)>=21 else float(v.mean())
            vol_5d_avg  = float(v.iloc[-6:-1].mean())  if len(v)>=6  else float(v.mean())
            vol_ratio   = round(vol_today/vol_avg_20d, 2) if vol_avg_20d>0 else 1.0
            vol_trend   = round(vol_5d_avg/vol_avg_20d, 2) if vol_avg_20d>0 else 1.0

            ma50  = float(c.iloc[-50:].mean())  if len(c)>=50  else float(c.mean())
            ma200 = float(c.iloc[-200:].mean()) if len(c)>=200 else float(c.mean())
            above_50  = p_now > ma50
            above_200 = p_now > ma200
            inst_flag = above_50 and above_200 and vol_ratio>=1.3 and rs_score>=3

            rows.append({"ticker":ticker,"name":name,"price":round(p_now,2),
                         "ret_1w":ret_1w,"ret_1m":ret_1m,"ret_1q":ret_1q,
                         "rs_1w":rs_1w,"rs_1q":rs_1q,"rs_score":rs_score,
                         "vol_today":vol_today,"vol_ratio":vol_ratio,"vol_trend":vol_trend,
                         "above_50":above_50,"above_200":above_200,"inst_flag":inst_flag})
        except Exception:
            continue

    df = pd.DataFrame(rows).sort_values("rs_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df)+1))
    bm = {"qqq_1w":qqq_ret_1w,"qqq_1m":qqq_ret_1m,"qqq_1q":qqq_ret_1q}
    return df, bm

# ── HTML Page ─────────────────────────────────────────────────────────────────
def build_page(df, bm):
    now    = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    top20  = df.head(20)
    inst_c = int(top20["inst_flag"].sum())
    ab200  = int(top20["above_200"].sum())

    bench = (f"<span style='margin-right:20px'>QQQ 1W: {ret_html(bm['qqq_1w'])}</span>"
             f"<span style='margin-right:20px'>QQQ 1M: {ret_html(bm['qqq_1m'])}</span>"
             f"<span>QQQ 1Q: {ret_html(bm['qqq_1q'])}</span>")

    rows_html = ""
    for _, r in top20.iterrows():
        flag = ""
        if r["inst_flag"]:
            flag = (" <span style='background:#0d47a1;color:#fff;padding:1px 6px;"
                    "border-radius:8px;font-size:.65rem;vertical-align:middle'>"
                    "&#128200; INST</span>")
        rows_html += f"""
        <tr>
          <td class="muted">{int(r['rank'])}</td>
          <td><strong>{r['ticker']}</strong>{flag}</td>
          <td class="muted">{r['name']}</td>
          <td class="mono">${r['price']}</td>
          <td>{ret_html(r['ret_1w'])}</td>
          <td>{ret_html(r['ret_1m'])}</td>
          <td>{ret_html(r['ret_1q'])}</td>
          <td>{rs_badge(r['rs_score'])}&nbsp;<span class='mono muted'>{r['rs_score']:+.1f}</span></td>
          <td class='mono'>{fmt_vol(r['vol_today'])}</td>
          <td>{vol_bar(r['vol_ratio'])}</td>
          <td>{vol_trend_html(r['vol_trend'])}</td>
          <td style='text-align:center'>{ma_check(r['above_50'])}</td>
          <td style='text-align:center'>{ma_check(r['above_200'])}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nasdaq 100 RS Scanner — Muffett Investments</title>
<style>
  :root{{--bg:#0b0b0f;--card:#111116;--border:#1e1e28;--text:#e2e2e8;--muted:#55556a}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       padding:32px 20px;font-size:14px}}
  .header{{margin-bottom:22px}}
  .header h1{{font-size:1.6rem;color:#fff;font-weight:700}}
  .header p{{color:var(--muted);font-size:.8rem;margin-top:5px}}
  .benchmark{{display:inline-flex;align-items:center;background:var(--card);
              border:1px solid var(--border);border-radius:10px;
              padding:10px 16px;margin-bottom:18px;font-size:.82rem}}
  .stats-row{{display:flex;gap:14px;margin-bottom:22px;flex-wrap:wrap}}
  .stat-card{{background:var(--card);border:1px solid var(--border);
              border-radius:10px;padding:12px 18px;min-width:140px}}
  .stat-card .label{{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px}}
  .stat-card .value{{font-size:1.4rem;font-weight:700;color:#fff;margin-top:4px}}
  .section-title{{font-size:.7rem;text-transform:uppercase;letter-spacing:2px;
                  color:var(--muted);margin-bottom:14px;font-weight:600}}
  .table-wrap{{overflow-x:auto;margin-bottom:40px}}
  table{{width:100%;border-collapse:collapse;min-width:900px}}
  th{{text-align:left;padding:9px 12px;color:var(--muted);
      border-bottom:1px solid var(--border);font-weight:500;
      font-size:.78rem;white-space:nowrap}}
  td{{padding:9px 12px;border-bottom:1px solid #0f0f15;white-space:nowrap}}
  tr:hover td{{background:#13131a}}
  .muted{{color:var(--muted)}}
  .mono{{font-family:'SF Mono',monospace;font-size:.85rem}}
  .legend{{margin-top:36px;padding-top:16px;border-top:1px solid var(--border);
           color:var(--muted);font-size:.76rem;line-height:2.2}}
  .legend strong{{color:#aaa}}
</style>
</head>
<body>

<div class="header">
  <h1>&#128202; Nasdaq 100 — Relative Strength Scanner</h1>
  <p>Muffett Investments &nbsp;&middot;&nbsp; {now} &nbsp;&middot;&nbsp; Top 20 vs QQQ benchmark &nbsp;&middot;&nbsp; Source: Yahoo Finance</p>
</div>

<div class="benchmark">
  <span style="color:var(--muted);margin-right:10px">Benchmark (QQQ):</span>
  {bench}
</div>

<div class="stats-row">
  <div class="stat-card">
    <div class="label">Stocks Scanned</div>
    <div class="value">{len(df)}</div>
  </div>
  <div class="stat-card">
    <div class="label">Above 200MA (Top 20)</div>
    <div class="value" style="color:#4caf50">{ab200}<span style="font-size:.9rem;color:var(--muted)"> / 20</span></div>
  </div>
  <div class="stat-card">
    <div class="label">Inst. Buying Signals</div>
    <div class="value" style="color:#7c6af7">{inst_c}</div>
  </div>
</div>

<div class="section-title">Top 20 by Relative Strength vs QQQ</div>
<div class="table-wrap">
<table>
  <thead><tr>
    <th>#</th><th>Ticker</th><th>Company</th><th>Price</th>
    <th>1W %</th><th>1M %</th><th>1Q %</th>
    <th>RS Score</th>
    <th>Vol Today</th><th>vs 20d Avg</th><th>Vol Trend</th>
    <th>50MA</th><th>200MA</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</div>

<div class="legend">
  <strong>RS Score</strong> = 40% &times; (stock 1W &minus; QQQ 1W) + 60% &times; (stock 1Q &minus; QQQ 1Q) &nbsp;&middot;&nbsp;
  <strong>vs 20d Avg</strong> = today's volume &divide; 20-day average volume &nbsp;&middot;&nbsp;
  <strong>Vol Trend</strong> = 5-day avg &divide; 20-day avg &nbsp;&middot;&nbsp;
  <strong>&#128200; INST</strong> = above both MAs + vol &ge;1.3&times; + RS &ge;3
</div>

</body>
</html>"""

# ── Vercel Handler ────────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            df, bm = run_scan()
            html   = build_page(df, bm)
            body   = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            msg = f"Error: {e}".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, format, *args):
        pass
