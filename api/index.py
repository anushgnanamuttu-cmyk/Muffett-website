"""
Muffett Investment — Sector Rotation Tracker
Deployed on Vercel, embedded via iframe on muffettinvestment.com
"""

from flask import Flask, Response
import yfinance as yf
import pandas as pd
from datetime import datetime
import time as time_mod

app = Flask(__name__)

# ── 1-hour data cache (avoids re-fetching on every page load) ────────────────
_cache = {"html": None, "ts": 0}
CACHE_TTL = 3600   # seconds

# ── ETF Universe ─────────────────────────────────────────────────────────────
SECTOR_ETFS = {
    "XLK":  "Technology",
    "XLC":  "Communication",
    "XLY":  "Consumer Disc",
    "XLP":  "Consumer Staples",
    "XLE":  "Energy",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLI":  "Industrials",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLU":  "Utilities",
}

TECH_ETFS = {
    "LIT":  "Battery",
    "XSD":  "Semis EW",
    "SMH":  "Semis",
    "SOXX": "Semis (SOXX)",
    "AIQ":  "AI Compute",
    "WTAI": "AI",
    "IGV":  "Software",
    "FDN":  "Internet",
    "CIBR": "Cyber",
    "QTUM": "Quantum",
    "CLOU": "Cloud",
    "DTCR": "Data Center",
    "GRID": "Grid",
    "NLR":  "Nuclear",
    "SHLD": "Defense",
    "FINX": "FinTech",
    "DAPP": "Blockchain",
    "ESPO": "Gaming",
    "SNSR": "IoT",
}

# ── Data Fetching ─────────────────────────────────────────────────────────────
def fetch_returns(tickers):
    all_tickers = list(tickers.keys())
    raw = yf.download(all_tickers, period="6mo", interval="1d",
                      auto_adjust=True, progress=False)["Close"]

    # Retry missing tickers individually
    if len(all_tickers) == 1:
        raw = raw.to_frame(name=all_tickers[0])
    missing = [t for t in all_tickers if t not in raw.columns or raw[t].dropna().empty]
    for t in missing:
        try:
            s = yf.download(t, period="6mo", interval="1d",
                            auto_adjust=True, progress=False)["Close"]
            raw[t] = s
        except Exception:
            pass

    rows = []
    for ticker, name in tickers.items():
        try:
            series = raw[ticker].dropna()
            if len(series) < 10:
                continue
            p_now  = float(series.iloc[-1])
            p_1w   = float(series.iloc[-6])   if len(series) >= 6   else float(series.iloc[0])
            p_1m   = float(series.iloc[-22])  if len(series) >= 22  else float(series.iloc[0])
            p_1q   = float(series.iloc[-63])  if len(series) >= 63  else float(series.iloc[0])
            # Previous period baselines (for delta arrows)
            p_prev_1w = float(series.iloc[-11]) if len(series) >= 11  else float(series.iloc[0])
            p_prev_1q = float(series.iloc[-126])if len(series) >= 126 else float(series.iloc[0])

            ret_1w  = round((p_now / p_1w  - 1) * 100, 1)
            ret_1m  = round((p_now / p_1m  - 1) * 100, 1)
            ret_1q  = round((p_now / p_1q  - 1) * 100, 1)
            prev_1w = round((p_1w  / p_prev_1w - 1) * 100, 1)
            prev_1q = round((p_1q  / p_prev_1q - 1) * 100, 1)
            vs_1w   = round(ret_1w - prev_1w, 1)
            vs_1q   = round(ret_1q - prev_1q, 1)
            rs      = round(0.4 * ret_1w + 0.6 * ret_1q, 1)

            rows.append({
                "ticker": ticker, "name": name,
                "price": round(p_now, 2),
                "ret_1w": ret_1w, "ret_1m": ret_1m, "ret_1q": ret_1q,
                "vs_1w": vs_1w,   "vs_1q": vs_1q,
                "rs": rs,
            })
        except Exception:
            continue

    df = pd.DataFrame(rows).sort_values("rs", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df

# ── HTML Helpers ──────────────────────────────────────────────────────────────
def heat_color(val, max_abs=8.0):
    """Map a % return to a background colour (green/red gradient)."""
    clamp = max(-max_abs, min(max_abs, val))
    ratio = clamp / max_abs
    if ratio >= 0:
        g = int(180 + 75 * ratio)
        return f"rgba(0,{g},80,{0.15 + 0.6 * ratio:.2f})"
    else:
        r = int(180 + 75 * (-ratio))
        return f"rgba({r},40,40,{0.15 + 0.6 * (-ratio):.2f})"

def ret_html(val):
    color = "#4caf50" if val > 0 else "#ef5350" if val < 0 else "#888"
    sign  = "+" if val > 0 else ""
    return f"<span style='color:{color};font-weight:600'>{sign}{val}%</span>"

def delta_html(val):
    if val > 0:   return f"<span style='color:#4caf50;font-size:.8rem'>▲ +{val}%</span>"
    elif val < 0: return f"<span style='color:#ef5350;font-size:.8rem'>▼ {val}%</span>"
    else:         return f"<span style='color:#666;font-size:.8rem'>─</span>"

def rs_badge(rs):
    if rs >= 5:    label, c = "Strong",  "#1b5e20"
    elif rs >= 2:  label, c = "Rising",  "#2e7d32"
    elif rs >= 0:  label, c = "Neutral", "#1a237e"
    elif rs >= -3: label, c = "Weak",    "#b71c1c"
    else:          label, c = "Lagging", "#7f0000"
    return f"<span style='background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:.72rem;white-space:nowrap'>{label}</span>"

def build_heatmap(df, title):
    tiles = ""
    for _, row in df.iterrows():
        bg    = heat_color(row["ret_1w"])
        arrow = "▲" if row["ret_1w"] > 0 else "▼" if row["ret_1w"] < 0 else "─"
        acol  = "#4caf50" if row["ret_1w"] > 0 else "#ef5350" if row["ret_1w"] < 0 else "#888"
        sign  = "+" if row["ret_1w"] > 0 else ""
        tiles += f"""
        <div class="tile" style="background:{bg}">
          <div class="tile-ticker">{row['ticker']}</div>
          <div class="tile-name">{row['name']}</div>
          <div class="tile-ret" style="color:{acol}">{sign}{row['ret_1w']}%</div>
          <div class="tile-sub">1W &nbsp;<span style='color:#aaa'>{arrow}</span>
            &nbsp;|&nbsp; 1Q: {'+' if row['ret_1q']>0 else ''}{row['ret_1q']}%</div>
        </div>"""
    return f"""
    <div class="section-title">{title}</div>
    <div class="heatmap">{tiles}</div>"""

def build_table(df, title):
    rows = ""
    for _, row in df.iterrows():
        rows += f"""
        <tr>
          <td class="muted">{int(row['rank'])}</td>
          <td><strong>{row['ticker']}</strong></td>
          <td class="muted">{row['name']}</td>
          <td class="mono">${row['price']}</td>
          <td>{ret_html(row['ret_1w'])}</td>
          <td>{delta_html(row['vs_1w'])}</td>
          <td>{ret_html(row['ret_1m'])}</td>
          <td>{ret_html(row['ret_1q'])}</td>
          <td>{delta_html(row['vs_1q'])}</td>
          <td>{rs_badge(row['rs'])}&nbsp;<span class="mono muted">{row['rs']:+.1f}</span></td>
        </tr>"""
    return f"""
    <div class="section-title" style="margin-top:40px">{title}</div>
    <div class="table-wrap">
    <table>
      <thead><tr>
        <th>#</th><th>Ticker</th><th>Name</th><th>Price</th>
        <th>1W</th><th>vs Prev Wk</th>
        <th>1M</th>
        <th>1Q</th><th>vs Prev Qtr</th>
        <th>RS Score</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>"""

# ── Full Page ─────────────────────────────────────────────────────────────────
def build_page(sector_df, tech_df):
    now  = datetime.now().strftime("%d %b %Y · %H:%M UTC")
    s_hm = build_heatmap(sector_df.sort_values("ret_1w", ascending=False), "S&amp;P 500 Sector Heatmap — Weekly Returns")
    t_hm = build_heatmap(tech_df.sort_values("ret_1w",   ascending=False), "Tech Thematic ETF Heatmap — Weekly Returns")
    s_tb = build_table(sector_df, "S&amp;P 500 Sector ETFs — Relative Strength Ranking")
    t_tb = build_table(tech_df,   "Tech Thematic ETFs — Relative Strength Ranking")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>Sector Rotation Tracker — Muffett Investment</title>
<style>
  :root {{
    --bg:     #0b0b0f;
    --card:   #111116;
    --border: #1e1e28;
    --text:   #e2e2e8;
    --muted:  #55556a;
    --accent: #7c6af7;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0 }}
  body {{
    background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    padding:32px 20px; font-size:14px;
  }}
  .header {{ margin-bottom:28px }}
  .header h1 {{ font-size:1.6rem; color:#fff; font-weight:700 }}
  .header p  {{ color:var(--muted); font-size:.8rem; margin-top:5px }}
  .section-title {{
    font-size:.7rem; text-transform:uppercase; letter-spacing:2px;
    color:var(--muted); margin-bottom:14px; font-weight:600;
  }}
  /* ── Heatmap ── */
  .heatmap {{
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(120px,1fr));
    gap:8px; margin-bottom:36px;
  }}
  .tile {{
    border:1px solid var(--border); border-radius:10px;
    padding:12px 10px; text-align:center; transition:.2s;
  }}
  .tile:hover {{ transform:translateY(-2px); border-color:#444 }}
  .tile-ticker {{ font-size:1rem; font-weight:700; color:#fff }}
  .tile-name   {{ font-size:.65rem; color:var(--muted); margin:2px 0 6px }}
  .tile-ret    {{ font-size:1.3rem; font-weight:700 }}
  .tile-sub    {{ font-size:.65rem; color:var(--muted); margin-top:4px }}
  /* ── Table ── */
  .table-wrap {{ overflow-x:auto; margin-bottom:40px }}
  table {{ width:100%; border-collapse:collapse; min-width:680px }}
  th {{
    text-align:left; padding:9px 12px; color:var(--muted);
    border-bottom:1px solid var(--border); font-weight:500;
    font-size:.78rem; white-space:nowrap;
  }}
  td {{ padding:9px 12px; border-bottom:1px solid #0f0f15; white-space:nowrap }}
  tr:hover td {{ background:#13131a }}
  .muted {{ color:var(--muted) }}
  .mono  {{ font-family:'SF Mono',monospace; font-size:.85rem }}
  /* ── Legend ── */
  .legend {{
    margin-top:36px; padding-top:16px;
    border-top:1px solid var(--border);
    color:var(--muted); font-size:.76rem; line-height:2;
  }}
  .legend strong {{ color:#aaa }}
  @media(max-width:500px) {{
    .heatmap {{ grid-template-columns:repeat(3,1fr) }}
    body {{ padding:16px 12px }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 Sector Rotation Tracker</h1>
  <p>Muffett Investment &nbsp;·&nbsp; Updated: {now} &nbsp;·&nbsp; Auto-refreshes hourly &nbsp;·&nbsp; Source: Yahoo Finance</p>
</div>

{s_hm}
{t_hm}
{s_tb}
{t_tb}

<div class="legend">
  <strong>RS Score</strong> = 40% weekly return + 60% quarterly return &nbsp;·&nbsp;
  <strong>vs Prev Wk/Qtr</strong> = change in return vs the prior equivalent period &nbsp;·&nbsp;
  Ranked strongest → weakest
</div>

</body>
</html>"""

# ── Flask Routes ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    now = time_mod.time()
    if _cache["html"] and (now - _cache["ts"]) < CACHE_TTL:
        return Response(_cache["html"], mimetype="text/html")

    sector_df = fetch_returns(SECTOR_ETFS)
    tech_df   = fetch_returns(TECH_ETFS)
    html      = build_page(sector_df, tech_df)

    _cache["html"] = html
    _cache["ts"]   = now
    return Response(html, mimetype="text/html")

@app.route("/health")
def health():
    return {"status": "ok", "cached": _cache["ts"] > 0}

if __name__ == "__main__":
    app.run(debug=True, port=5001)
