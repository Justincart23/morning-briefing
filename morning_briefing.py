#!/usr/bin/env python3
"""
Morning Briefing — JPMorgan Private Bank Edition
Sends a daily 6:30 AM email built for a wealth management / private bank analyst.

SETUP:
  pip install requests yfinance --break-system-packages
  Create .env in this folder:  export GMAIL_PASS="your-app-password"
  Cron: 30 6 * * * source ~/Documents/Claude/Projects/JPMorgan\ Internship/.env && python3 ~/Documents/Claude/Projects/JPMorgan\ Internship/morning_briefing.py

"""

import os, smtplib, datetime, re, xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# ── CONFIG ───────────────────────────────────────────────────────────────────
GMAIL_USER = os.environ.get("GMAIL_USER", "justincartagenova@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "")
TO_EMAIL   = os.environ.get("TO_EMAIL",   "justincartagenova@gmail.com")

NOW      = datetime.datetime.now()
DATE_STR = NOW.strftime("%A, %B %d, %Y")
WEEKDAY  = NOW.strftime("%A")
TIME_STR = NOW.strftime("%I:%M %p")

FUTURES = {
    "ES=F":      ("S&P 500",    "equity"),
    "NQ=F":      ("Nasdaq",     "equity"),
    "YM=F":      ("Dow",        "equity"),
    "RTY=F":     ("Russell 2000","equity"),
    "^VIX":      ("VIX",        "vix"),
    "^TNX":      ("10-Yr Yield","rate"),
    "^TYX":      ("30-Yr Yield","rate"),
    "GC=F":      ("Gold",       "commodity"),
    "CL=F":      ("Oil (WTI)",  "commodity"),
    "DX-Y.NYB":  ("USD Index",  "fx"),
}

# Yield curve tickers
YIELD_2Y  = "^IRX"   # 13-week proxy; use ^FVX for 5yr, ^IRX for short end
YIELD_2Y_TICKER = "2YY=F"   # 2-yr Treasury futures (best yfinance proxy)
YIELD_10Y = "^TNX"
YIELD_30Y = "^TYX"
AGG_TICKER = "AGG"   # iShares Core US Aggregate Bond ETF

FINANCIALS = {
    "JPM":  "JPMorgan Chase",
    "GS":   "Goldman Sachs",
    "MS":   "Morgan Stanley",
    "BLK":  "BlackRock",
    "BAC":  "Bank of America",
    "C":    "Citigroup",
    "WFC":  "Wells Fargo",
}

SECTORS = {
    "XLF":  "Financials",
    "XLK":  "Technology",
    "XLE":  "Energy",
    "XLV":  "Healthcare",
    "XLI":  "Industrials",
    "XLC":  "Comm. Services",
    "XLY":  "Cons. Discretionary",
    "XLP":  "Cons. Staples",
    "XLRE": "Real Estate",
    "XLU":  "Utilities",
    "XLB":  "Materials",
}

# Market ripple effects — keyword → plain-English implication
RIPPLE = {
    "tariff":    ("Trade", "Tariff move → XLI, XLB, global supply chains"),
    "china":     ("China", "China risk → semis, XLK, supply chain names"),
    "iran":      ("Iran/Oil", "Iran tension → oil spike, XLE, gold bid"),
    "oil":       ("Energy", "Oil move → XLE, inflation outlook, airlines"),
    "fed":       ("Fed", "Fed signal → rates, TLT, XLF duration sensitivity"),
    "rate":      ("Rates", "Rate move → bond prices, XLF, REITs (XLRE)"),
    "inflation": ("CPI/PCE", "Inflation data → rate path, TLT, TIPS"),
    "bank":      ("Banking", "Bank news → XLF, KRE, direct JPM exposure"),
    "sanctions": ("Sanctions", "Sanctions → XLF compliance, energy names"),
    "recession": ("Growth", "Recession fear → defensives (XLP, XLU), credit spreads"),
    "ukraine":   ("Ukraine", "Conflict → XLE, wheat, defense (LMT, RTX)"),
    "debt":      ("Debt/Credit", "Debt news → Treasury yields, IG/HY spreads"),
    "default":   ("Default", "Default risk → credit spreads, risk-off move"),
    "ecb":       ("ECB", "ECB policy → EUR/USD, European cross-asset exposure"),
    "earnings":  ("Earnings", "Earnings beat/miss → sector read-through"),
    "ai":        ("AI/Tech", "AI story → semis (NVDA, AVGO), XLK broadly"),
    "crypto":    ("Crypto", "Crypto move → risk sentiment barometer"),
    "gdp":       ("Growth", "GDP data → rate path, cyclicals vs. defensives"),
    "jobs":      ("Jobs/NFP", "Jobs data → Fed reaction, consumer spending names"),
}


# ── UTILITIES ────────────────────────────────────────────────────────────────
def fetch_rss(url, max_items=6):
    if not REQUESTS_OK:
        return []
    try:
        r = requests.get(url, timeout=9, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items = []
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            desc  = item.findtext("description", "").strip()
            desc  = re.sub(r"<[^>]+>", "", desc)[:300].strip()
            pub   = item.findtext("pubDate", "").strip()
            if title:
                items.append({"title": title, "link": link, "desc": desc, "pub": pub})
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []

def get_quote(ticker):
    """Returns (price, prev_close, chg_pct) or None."""
    try:
        info = yf.Ticker(ticker).fast_info
        p = getattr(info, "last_price", None)
        c = getattr(info, "previous_close", None)
        if p and c:
            return p, c, ((p - c) / c) * 100
    except Exception:
        pass
    return None

def chg_color(chg):
    return "#16a34a" if chg >= 0 else "#dc2626"

def chg_arrow(chg):
    return "▲" if chg >= 0 else "▼"

def source_badge(url):
    mapping = [
        ("reuters",     "Reuters",     "#e05c00", "#fff4ee"),
        ("bbc",         "BBC",         "#b91c1c", "#fef2f2"),
        ("cnbc",        "CNBC",        "#0066cc", "#eff6ff"),
        ("marketwatch", "MarketWatch", "#006B3C", "#f0fdf4"),
        ("yahoo",       "Yahoo Fin",   "#6001d2", "#f5f3ff"),
        ("espn",        "ESPN",        "#cc0000", "#fff0f0"),
        ("ft.com",      "FT",          "#c8531c", "#fff7ed"),
        ("bloomberg",   "Bloomberg",   "#1a1a1a", "#f8fafc"),
        ("wsj",         "WSJ",         "#1c4b8a", "#eff6ff"),
    ]
    u = url.lower()
    for key, label, color, bg in mapping:
        if key in u:
            return f'<span style="font-size:10px;font-weight:700;color:{color};background:{bg};padding:2px 6px;border-radius:3px;margin-right:6px;letter-spacing:.03em">{label}</span>'
    return ''

def ripple_tag(title_lower):
    for kw, (label, note) in RIPPLE.items():
        if kw in title_lower:
            return f'<span style="display:inline-block;font-size:10px;font-weight:600;color:#854d0e;background:#fef9c3;padding:2px 7px;border-radius:3px;margin-top:4px">⚡ {label}: {note}</span>'
    return ""

def divider():
    return '<div style="height:1px;background:#f1f5f9;margin:2px 0"></div>'

def card(title, subtitle, content, accent="#2563eb"):
    return f"""
<div style="background:#ffffff;border-radius:0;border-top:3px solid {accent};margin-bottom:3px;padding:20px 24px">
  <div style="margin-bottom:14px">
    <div style="font-size:15px;font-weight:800;color:#0f172a;letter-spacing:-.2px">{title}</div>
    <div style="font-size:11px;color:#94a3b8;margin-top:2px;font-weight:500">{subtitle}</div>
  </div>
  {content}
</div>"""


# ── SECTION 1: MARKET INTELLIGENCE BRIEF ─────────────────────────────────────
def market_intelligence():
    """Top-of-email: regime + WM take + what to know before walking in."""
    if not YFINANCE_OK:
        return ""

    es = get_quote("ES=F")
    vix = get_quote("^VIX")
    tnx = get_quote("^TNX")
    oil = get_quote("CL=F")
    gold = get_quote("GC=F")
    btc = get_quote("BTC-USD")

    # Market regime
    if es:
        chg = es[2]
        if chg > 1:      regime, rc, rbg = "RISK-ON", "#166534", "#dcfce7"
        elif chg > 0.3:  regime, rc, rbg = "LEANING GREEN", "#166534", "#f0fdf4"
        elif chg > -0.3: regime, rc, rbg = "FLAT OPEN", "#78716c", "#fafaf9"
        elif chg > -1:   regime, rc, rbg = "LEANING RED", "#991b1b", "#fff7f7"
        else:            regime, rc, rbg = "RISK-OFF", "#991b1b", "#fee2e2"
        es_line = f'S&P futures <strong>{chg:+.2f}%</strong>'
    else:
        regime, rc, rbg = "PENDING", "#64748b", "#f8fafc"
        es_line = "Futures data loading"

    # Signal chips
    chips = []
    if vix:
        v = vix[0]
        if v > 30:   chips.append(("EXTREME FEAR", "#991b1b", "#fee2e2"))
        elif v > 25: chips.append((f"VIX {v:.0f} — Elevated Fear", "#9a3412", "#ffedd5"))
        elif v > 20: chips.append((f"VIX {v:.0f} — Caution", "#854d0e", "#fef9c3"))
        else:        chips.append((f"VIX {v:.0f} — Calm", "#166534", "#dcfce7"))
    if tnx:
        td = tnx[2]
        dir_ = "Rising" if td > 0 else "Falling"
        if abs(td) > 0.5:
            chips.append((f"Yields {dir_} Fast ({tnx[0]:.2f}%)", "#1e40af", "#dbeafe"))
        elif abs(td) > 0.1:
            chips.append((f"Yields {dir_} ({tnx[0]:.2f}%)", "#374151", "#f1f5f9"))
    if oil:
        od = oil[2]
        if abs(od) > 1.5:
            chips.append((f"Oil {'Surging' if od > 0 else 'Falling'} {od:+.1f}%", "#92400e", "#fef3c7"))
    if btc:
        bc = btc[2]
        chips.append((f"BTC ${btc[0]:,.0f} {bc:+.1f}%", "#7c3aed" if bc >= 0 else "#6b21a8", "#f5f3ff"))

    chips_html = " ".join(
        f'<span style="display:inline-block;font-size:11px;font-weight:700;color:{c};background:{bg};padding:3px 9px;border-radius:4px">{t}</span>'
        for t, c, bg in chips
    )

    # What this means — specific to JPM Private Bank context
    wm_takes = []
    if es and es[2] < -0.5:
        wm_takes.append("📉 Down open expected — if clients reach out, lead with long-term allocation and avoid reacting to daily moves. HNW clients in alternatives are naturally cushioned.")
    if vix and vix[0] > 22:
        wm_takes.append("🛡 Elevated VIX creates structured products conversations — protected notes, collars on concentrated equity, or cash management for anxious clients.")
    if tnx and tnx[2] > 0.08:
        wm_takes.append("📈 Yields rising — bond prices falling. Fixed income clients need context on duration. Short-duration and floating rate now look attractive vs. long bonds.")
    if tnx and tnx[0] and tnx[0] > 4.5:
        wm_takes.append(f"💰 10-yr at {tnx[0]:.2f}% — cash and T-bills are genuinely competitive. This is a legitimate yield story for clients sitting in money markets.")
    if oil and abs(oil[2]) > 2:
        if oil[2] > 0:
            wm_takes.append("⛽ Oil spike — watch XLE (energy sector). Iran/geopolitical tension driving it. Energy names in client portfolios may be cushioning broader losses.")
        else:
            wm_takes.append("⛽ Oil falling — good for inflation outlook, bad for energy sector allocations. Potential catalyst to revisit overweight energy positions.")
    if not wm_takes:
        wm_takes.append("✅ Steady open — good day for proactive client outreach. No fires to put out. Use the calm to build relationships and prep for Q3 strategy conversations.")

    takes_html = "".join(
        f'<div style="padding:7px 0;border-bottom:1px solid #f8fafc;font-size:13px;color:#1e293b;line-height:1.5">{t}</div>'
        for t in wm_takes
    )

    return f"""
<div style="background:#0f172a;padding:20px 24px 0;border-radius:12px 12px 0 0">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
    <div>
      <div style="font-size:22px;font-weight:900;color:#fff;letter-spacing:-.5px">Good morning, Justin ☀️</div>
      <div style="font-size:12px;color:#64748b;margin-top:3px">{DATE_STR} &nbsp;·&nbsp; {TIME_STR} &nbsp;·&nbsp; Market opens in ~3 hours</div>
    </div>
    <div style="background:#1e293b;padding:8px 14px;border-radius:8px;text-align:right">
      <div style="font-size:10px;font-weight:700;color:#3b82f6;letter-spacing:.05em">JPM PRIVATE BANK</div>
      <div style="font-size:10px;color:#64748b;margin-top:1px">Morning Intelligence Brief</div>
    </div>
  </div>
  <div style="height:4px;background:linear-gradient(90deg,#2563eb,#7c3aed,#db2777,#ea580c);margin:16px -24px 0;border-radius:0"></div>
</div>
<div style="background:#fff;padding:18px 24px 14px;margin-bottom:3px">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap">
    <span style="font-size:18px;font-weight:900;color:{rc};background:{rbg};padding:5px 14px;border-radius:6px;letter-spacing:.02em">{regime}</span>
    <span style="font-size:13px;color:#475569">{es_line}</span>
  </div>
  <div style="margin-bottom:14px">{chips_html}</div>
  <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px">💡 What This Means for You Today</div>
  {takes_html}
</div>"""


# ── SECTION 2: PREMARKET TABLE ────────────────────────────────────────────────
def premarket_table():
    if not YFINANCE_OK:
        return card("📊 Premarket Snapshot", "Futures + macro — before the 9:30 bell",
                    "<p style='color:#94a3b8;font-size:13px'>Install yfinance: pip install yfinance</p>")

    # Futures rows
    fut_rows = ""
    for ticker, (label, kind) in FUTURES.items():
        q = get_quote(ticker)
        if not q:
            continue
        price, prev, chg = q
        color = chg_color(chg)
        arrow = chg_arrow(chg)
        if kind == "rate":
            disp = f"{price:.3f}%"
        elif kind == "vix":
            disp = f"{price:.2f}"
        elif kind == "fx":
            disp = f"{price:.2f}"

        else:
            disp = f"${price:,.2f}" if price > 10 else f"{price:.4f}"

        # highlight big moves
        bg = ""
        if abs(chg) > 1.5:
            bg = f"background:{'#f0fdf4' if chg > 0 else '#fff7f7'};"

        fut_rows += f"""<tr style="{bg}">
          <td style="padding:6px 10px;font-size:13px;font-weight:700;color:#0f172a">{label}</td>
          <td style="padding:6px 10px;font-size:13px;color:#475569;text-align:right">{disp}</td>
          <td style="padding:6px 10px;font-size:13px;font-weight:800;color:{color};text-align:right">{arrow} {chg:+.2f}%</td>
        </tr>"""

    # Financials rows
    fin_rows = ""
    for ticker, label in FINANCIALS.items():
        q = get_quote(ticker)
        if not q:
            continue
        price, prev, chg = q
        color = chg_color(chg)
        arrow = chg_arrow(chg)
        jpm_flag = ' <span style="font-size:9px;background:#dbeafe;color:#1e40af;padding:1px 5px;border-radius:3px;font-weight:700">YOUR FIRM</span>' if ticker == "JPM" else ""
        fin_rows += f"""<tr>
          <td style="padding:5px 10px;font-size:13px;font-weight:600;color:#0f172a">{label}{jpm_flag}</td>
          <td style="padding:5px 10px;font-size:13px;color:#475569;text-align:right">${price:,.2f}</td>
          <td style="padding:5px 10px;font-size:13px;font-weight:800;color:{color};text-align:right">{arrow} {chg:+.2f}%</td>
        </tr>"""

    content = f"""
    <div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">Futures &amp; Macro</div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px">{fut_rows}</table>
    <div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">Financials — Prior Close &amp; Peer Context</div>
    <table style="width:100%;border-collapse:collapse">{fin_rows}</table>
    <div style="margin-top:8px;font-size:10px;color:#94a3b8">Data: Yahoo Finance · Futures = live premarket · Stocks = prior close · Market opens 9:30 AM ET</div>"""

    return card("📊 Premarket Snapshot", "What the market expects before the bell", content, "#2563eb")


# ── SECTION 3: SECTOR ROTATION ───────────────────────────────────────────────
def sector_rotation():
    if not YFINANCE_OK:
        return card("🔥 Sector Rotation", "Yesterday's close — sets the tone",
                    "<p style='color:#94a3b8;font-size:13px'>Data unavailable</p>")

    sectors = []
    for etf, name in SECTORS.items():
        q = get_quote(etf)
        if q:
            sectors.append((name, etf, q[2]))

    if not sectors:
        return card("🔥 Sector Rotation", "Yesterday's close",
                    "<p style='color:#94a3b8;font-size:13px'>Data unavailable</p>")

    sectors.sort(key=lambda x: x[2], reverse=True)
    max_abs = max(abs(c) for _, _, c in sectors) or 1

    rows = ""
    for name, etf, chg in sectors:
        color  = chg_color(chg)
        bg     = "#dcfce7" if chg >= 0 else "#fee2e2"
        arrow  = chg_arrow(chg)
        bar_w  = int((abs(chg) / max_abs) * 80)
        bar_dir = "left" if chg >= 0 else "right"
        jpm_note = " ← your sector" if etf == "XLF" else ""
        rows += f"""
        <tr>
          <td style="padding:5px 8px;font-size:12px;font-weight:700;color:#1e293b;width:150px">{name}<span style="font-size:10px;color:#3b82f6">{jpm_note}</span></td>
          <td style="padding:5px 8px;width:40px;font-size:10px;color:#94a3b8">{etf}</td>
          <td style="padding:5px 8px">
            <div style="height:8px;width:{bar_w}%;background:{color};border-radius:3px;opacity:.65;min-width:3px"></div>
          </td>
          <td style="padding:5px 8px;font-size:13px;font-weight:800;color:{color};text-align:right;white-space:nowrap">{arrow} {chg:+.2f}%</td>
        </tr>"""

    # Rotation narrative
    top = sectors[0]
    bot = sectors[-1]
    xlf_chg = next((c for n, e, c in sectors if e == "XLF"), None)

    narr = f"<strong>{top[0]}</strong> led, <strong>{bot[0]}</strong> lagged. "
    if "Utilities" in top[0] or "Staples" in top[0] or "Healthcare" in top[0]:
        narr += "Defensive rotation — money moving to safety. Markets cautious under the surface even if indices look flat."
    elif "Technology" in top[0]:
        narr += "Tech leading = risk appetite healthy. Growth and AI names in favor. Watch for breadth — is it all NVDA or broad-based?"
    elif "Financials" in top[0]:
        narr += "Financials leading — positive rate/earnings sentiment. Direct tailwind for JPM and the sector."
    elif "Energy" in top[0]:
        narr += "Energy leading — likely oil/geopolitical driver. Watch XLE and commodity-linked names in client portfolios."
    else:
        narr += "Monitor whether this is a single-day move or a trend establishing itself."

    if xlf_chg is not None:
        xlf_color = chg_color(xlf_chg)
        narr += f' <strong style="color:{xlf_color}">XLF (Financials) {chg_arrow(xlf_chg)} {xlf_chg:+.2f}%</strong> — direct context for JPM conversations today.'

    content = f"""
    <table style="width:100%;border-collapse:collapse">{rows}</table>
    <div style="margin-top:12px;padding:10px 12px;background:#f8fafc;border-left:3px solid #f59e0b;border-radius:4px;font-size:12px;color:#1e293b;line-height:1.6">
      📌 <strong>Rotation Read:</strong> {narr}
    </div>
    <div style="margin-top:6px;font-size:10px;color:#94a3b8">Prior close · Yahoo Finance · All 11 S&amp;P 500 sectors</div>"""

    return card("🔥 Sector Rotation", "All 11 sectors ranked — where money moved yesterday", content, "#f59e0b")


# ── SECTION 4: MARKET HEADLINES (full, with context) ─────────────────────────
def market_headlines():
    feeds = [
        ("https://feeds.reuters.com/reuters/businessNews",       "https://reuters.com"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/","https://marketwatch.com"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "https://cnbc.com"),
        ("https://finance.yahoo.com/news/rssindex",              "https://yahoo.com"),
    ]
    all_items = []
    for url, domain in feeds:
        items = fetch_rss(url, max_items=4)
        for it in items:
            it["domain"] = domain
        all_items.extend(items)

    if not all_items:
        return card("📰 Market Headlines", "Top finance news", "<p style='color:#94a3b8'>Unavailable</p>")

    rows = ""
    for item in all_items[:8]:
        title  = item["title"]
        link   = item.get("link", "#")
        desc   = item.get("desc", "")
        domain = item.get("domain", link)
        badge  = source_badge(domain)
        rt     = ripple_tag(title.lower())
        desc_html = f'<div style="font-size:12px;color:#64748b;margin-top:3px;line-height:1.5">{desc}</div>' if desc else ""

        rows += f"""
        <div style="padding:11px 0;border-bottom:1px solid #f1f5f9">
          <div style="margin-bottom:4px">{badge}<a href="{link}" style="font-size:13px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.5">{title}</a></div>
          {desc_html}
          {f'<div style="margin-top:5px">{rt}</div>' if rt else ""}
        </div>"""

    content = rows + '<div style="margin-top:8px;font-size:10px;color:#94a3b8">Sources: Reuters · MarketWatch · CNBC · Yahoo Finance</div>'
    return card("📰 Market Headlines", "Full stories — click to read · market impact tagged", content, "#0f172a")


# ── SECTION 5: GEO PULSE ─────────────────────────────────────────────────────
def geo_pulse():
    feeds = [
        ("https://feeds.reuters.com/reuters/worldNews",  "https://reuters.com"),
        ("https://feeds.bbci.co.uk/news/world/rss.xml",  "https://bbc.com"),
    ]
    all_items = []
    for url, domain in feeds:
        items = fetch_rss(url, max_items=5)
        for it in items:
            it["domain"] = domain
        all_items.extend(items)

    if not all_items:
        return card("🌍 Geo Pulse", "Global events with market implications", "<p style='color:#94a3b8'>Unavailable</p>")

    rows = ""
    for item in all_items[:6]:
        title  = item["title"]
        link   = item.get("link", "#")
        desc   = item.get("desc", "")
        domain = item.get("domain", link)
        badge  = source_badge(domain)
        rt     = ripple_tag(title.lower())
        desc_html = f'<div style="font-size:12px;color:#64748b;margin-top:3px;line-height:1.5">{desc}</div>' if desc else ""

        rows += f"""
        <div style="padding:11px 0;border-bottom:1px solid #f1f5f9">
          <div style="margin-bottom:4px">{badge}<a href="{link}" style="font-size:13px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.5">{title}</a></div>
          {desc_html}
          {f'<div style="margin-top:5px">{rt}</div>' if rt else ""}
        </div>"""

    content = rows + '<div style="margin-top:8px;font-size:10px;color:#94a3b8">Sources: Reuters World · BBC World</div>'
    return card("🌍 Geo Pulse", "Global developments — tagged by market impact", content, "#7c3aed")


# ── SECTION 6: ANALYST LENS ──────────────────────────────────────────────────
def analyst_lens():
    """
    Private bank analyst prep — what to know, what to ask, what to watch.
    This section is fixed + contextual based on market data.
    """
    tnx = get_quote("^TNX") if YFINANCE_OK else None
    vix = get_quote("^VIX") if YFINANCE_OK else None
    es  = get_quote("ES=F") if YFINANCE_OK else None

    items = []

    # Always-on private bank context
    items.append(("🏦", "Private Bank Lens",
        "JPM Private Bank serves clients with $10M+ in investable assets. Your job is to understand their total picture — not just investments, but estate planning, lending (Lombard loans, mortgages), tax strategy, and next-gen wealth transfer. Every market move connects to one of those pillars."))

    items.append(("📐", "Portfolio Construction Today",
        "At 6:30 AM your advisors are already thinking: <strong>Should I rebalance? Do I need to call any clients?</strong> Know your sector rotation (above) and be ready to explain <em>why</em> a sector moved — not just that it did."))

    # Yield-specific
    if tnx and tnx[0] > 4.3:
        items.append(("💵", f"Fixed Income Opportunity — Yields at {tnx[0]:.2f}%",
            f"With the 10-yr at {tnx[0]:.2f}%, cash and short-duration fixed income are genuinely attractive. HNW clients holding excess liquidity can lock in real yield. This is a conversation worth having proactively — not waiting for clients to ask."))
    elif tnx:
        items.append(("📉", f"Rates — 10-Yr at {tnx[0]:.2f}%",
            "Rates are the backbone of every fixed income conversation. Know the direction and velocity — is this a trend or a blip? Rising yields hurt bond prices but help new buyers. Falling yields support equity valuations."))

    # VIX-specific
    if vix and vix[0] > 20:
        items.append(("🛡", "Volatility — Structured Products Moment",
            f"VIX at {vix[0]:.1f} means options are expensive. That's bad if you're buying protection, but it opens conversations around <strong>structured notes</strong> (principal-protected, buffered notes), or reviewing whether client equity exposure is sized appropriately for their risk tolerance."))

    # Analyst fundamentals
    items.append(("🔍", "Equity Research Mindset",
        "As an analyst in the private bank, you're not just reporting prices — you're synthesizing what sector moves mean for client portfolios. If Financials are lagging, that's a story about rate compression, credit quality, or regulatory headwinds. Connect the dots before anyone asks you to."))

    items.append(("💬", "Client Conversation Prep",
        "HNW clients ask two types of questions: <em>\"Is my money safe?\"</em> and <em>\"Am I missing something?\"</em>. Today's briefing gives you the data to answer both. Lead with context, not just numbers. 'The market is flat but there's rotation into defensives' is more useful than 'S&P is up 0.1%.'"))

    items.append(("📋", "What Smart Interns Ask",
        "Questions that signal you understand the business: <em>\"How does today's rate move affect the duration positioning in client fixed income sleeves?\"</em> or <em>\"Is the XLF move driven by rate sensitivity or earnings expectations?\"</em> Connect macro to portfolio — that's what senior advisors do."))

    rows = "".join(f"""
    <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
      <div style="display:flex;gap:10px;align-items:flex-start">
        <span style="font-size:18px;line-height:1">{icon}</span>
        <div>
          <div style="font-size:13px;font-weight:800;color:#0f172a;margin-bottom:3px">{title}</div>
          <div style="font-size:12px;color:#475569;line-height:1.6">{body}</div>
        </div>
      </div>
    </div>""" for icon, title, body in items)

    return card("🧠 Analyst Lens — Private Bank Prep", "How to think about today · what to know · what to ask", rows, "#0f172a")


# ── SECTION 7: SPORTS & SMALL TALK ───────────────────────────────────────────
def sports_brief():
    # ESPN sport-specific RSS feeds — most reliable from cloud servers
    # Philly teams: Phillies (MLB), Eagles (NFL), 76ers (NBA), Flyers (NHL)
    month = NOW.month

    sport_feeds = [
        # ESPN RSS feeds work reliably from server environments
        ("⚾ MLB / Phillies",  "https://www.espn.com/espn/rss/mlb/news",    "phillies"),
        ("🏀 NBA",             "https://www.espn.com/espn/rss/nba/news",    "76ers"),
        ("🏈 NFL / Eagles",    "https://www.espn.com/espn/rss/nfl/news",    "eagles"),
        ("🏒 NHL / Flyers",    "https://www.espn.com/espn/rss/nhl/news",    "flyers"),
    ]

    # Season context so hooks are accurate
    season_context = {}
    if month in [4, 5, 6, 7, 8, 9, 10]:
        season_context["mlb"] = "in season"
    if month in [10, 11, 12, 1, 2, 3, 4, 5, 6]:
        season_context["nba"] = "in season" if month in [10, 11, 12, 1, 2, 3, 4, 5, 6] else "offseason"
    if month in [6, 7, 8, 9]:
        season_context["nfl"] = "offseason/training camp"
    elif month in [9, 10, 11, 12, 1]:
        season_context["nfl"] = "in season"
    if month in [10, 11, 12, 1, 2, 3, 4, 5, 6]:
        season_context["nhl"] = "in season/playoffs"

    sport_html = ""
    total_items = 0

    for label, url, philly_team in sport_feeds:
        items = fetch_rss(url, max_items=4)
        if not items:
            continue

        # Prioritize Philly team stories, then fill with top news
        philly = [i for i in items if philly_team.lower() in i["title"].lower() or philly_team.lower() in i.get("desc","").lower()]
        others = [i for i in items if i not in philly]
        show = (philly + others)[:2]

        sport_html += f'<div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid #f1f5f9">{label}</div>'
        for item in show:
            title = item["title"]
            desc  = item.get("desc", "")
            # Highlight if Philly team mentioned
            is_philly = philly_team.lower() in title.lower() or philly_team.lower() in desc.lower()
            title_style = "font-size:13px;font-weight:700;color:#0f172a;text-decoration:none"
            philly_badge = f' <span style="font-size:9px;font-weight:800;background:#003f8f;color:#fff;padding:1px 5px;border-radius:3px">PHILLY</span>' if is_philly else ""
            desc_html = f'<div style="font-size:11px;color:#64748b;margin-top:2px;line-height:1.4">{desc[:140]}{"…" if len(desc) > 140 else ""}</div>' if desc else ""
            sport_html += f'<div style="padding:5px 0"><a href="{item["link"]}" style="{title_style}">{title}</a>{philly_badge}{desc_html}</div>'
            total_items += 1

    # Fallback: NYT Sports if ESPN feeds all fail
    if total_items == 0:
        for fb_url in [
            "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
            "https://feeds.reuters.com/reuters/sportsNews",
        ]:
            fallback = fetch_rss(fb_url, max_items=6)
            if fallback:
                sport_html += '<div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid #f1f5f9">🏆 Top Sports</div>'
                for item in fallback:
                    desc = item.get("desc", "")
                    desc_html = f'<div style="font-size:11px;color:#64748b;margin-top:2px;line-height:1.4">{desc[:140]}{"…" if len(desc) > 140 else ""}</div>' if desc else ""
                    sport_html += f'<div style="padding:5px 0"><a href="{item["link"]}" style="font-size:13px;font-weight:700;color:#0f172a;text-decoration:none">{item["title"]}</a>{desc_html}</div>'
                break
        else:
            sport_html = "<p style='color:#94a3b8;font-size:13px'>Sports data unavailable</p>"

    # Philly teams context block
    philly_block = """
    <div style="margin-top:14px;padding:10px 12px;background:#f0f4ff;border-left:3px solid #003f8f;border-radius:4px">
      <div style="font-size:10px;font-weight:800;color:#1e3a8a;text-transform:uppercase;margin-bottom:5px">🦅 Philadelphia Teams</div>
      <div style="font-size:12px;color:#1e293b;line-height:1.7">
        <strong>Phillies</strong> (MLB) · <strong>Eagles</strong> (NFL) · <strong>76ers</strong> (NBA) · <strong>Flyers</strong> (NHL)<br>
        <span style="font-size:11px;color:#64748b">Philly stories are highlighted above. Great small-talk with any PA client or colleague.</span>
      </div>
    </div>"""

    hooks = {
        "Monday":    "Did you catch any of the games this weekend?",
        "Tuesday":   "Big game last night — did you see how it ended?",
        "Wednesday": "Midweek check — how are your teams looking right now?",
        "Thursday":  "Almost the weekend. Any games you're watching?",
        "Friday":    "Big sports weekend coming up. Got plans around any of the games?",
        "Saturday":  "So much going on today in sports — anything you're locked in on?",
        "Sunday":    "Great Sunday for sports. Watching anything later?",
    }
    hook = hooks.get(WEEKDAY, "Anything in sports you're following right now?")

    footer = f"""
    <div style="margin-top:12px;padding:12px 14px;background:#f0fdf4;border-left:3px solid #22c55e;border-radius:4px">
      <div style="font-size:10px;font-weight:800;color:#15803d;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">💬 {WEEKDAY} Opener</div>
      <div style="font-size:13px;color:#1c1917;font-style:italic">{hook}</div>
      <div style="font-size:11px;color:#64748b;margin-top:4px">Philly teams highlighted above — instant common ground in PA. Sports = rapport with any banker or client.</div>
    </div>"""

    content = sport_html + philly_block + footer + '<div style="margin-top:8px;font-size:10px;color:#94a3b8">Source: ESPN · NYT Sports · Reuters Sports</div>'
    return card("🏆 Sports & Small Talk", "Know the story · own the room", content, "#16a34a")


# ── SECTION: RATES, BONDS & MACRO DASHBOARD ──────────────────────────────────
def rates_and_macro():
    if not YFINANCE_OK:
        return card("📐 Rates & Macro Dashboard", "Yield curve · S&P · Oil · AGG",
                    "<p style='color:#94a3b8;font-size:13px'>Data unavailable</p>")

    # ── S&P 500: yesterday close + today futures ──────────────────────────────
    spy  = get_quote("SPY")   # prior close proxy
    es   = get_quote("ES=F")  # futures = today's implied open

    # ── Yields ────────────────────────────────────────────────────────────────
    q2y  = get_quote("2YY=F")   # 2-yr Treasury
    q10y = get_quote("^TNX")    # 10-yr Treasury
    q30y = get_quote("^TYX")    # 30-yr Treasury

    # ── AGG ───────────────────────────────────────────────────────────────────
    agg  = get_quote("AGG")

    # ── Oil ───────────────────────────────────────────────────────────────────
    oil  = get_quote("CL=F")

    rows = ""

    # S&P block
    if spy and es:
        spy_close = spy[0]
        es_price  = es[0]
        es_chg    = es[2]
        # ES futures are in full S&P index points (~10x SPY price).
        # Use ES day-change % directly — it's already the correct market move.
        implied_open_chg = es_chg
        color = chg_color(implied_open_chg)
        arrow = chg_arrow(implied_open_chg)
        rows += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">S&P 500</div>
          <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div><div style="font-size:11px;color:#94a3b8">Yesterday Close (SPY)</div><div style="font-size:16px;font-weight:800;color:#0f172a">${spy_close:,.2f}</div></div>
            <div><div style="font-size:11px;color:#94a3b8">Futures Implied Move (ES=F)</div><div style="font-size:16px;font-weight:800;color:{color}">{arrow} {implied_open_chg:+.2f}% &nbsp;<span style="font-size:13px;color:#475569">(ES {es_price:,.2f})</span></div></div>
          </div>
        </div>"""
    elif spy:
        rows += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">S&P 500</div>
          <div style="font-size:16px;font-weight:800;color:#0f172a">SPY Prior Close: ${spy[0]:,.2f}</div>
        </div>"""

    # Yield curve block
    y2  = q2y[0]  if q2y  else None
    y10 = q10y[0] if q10y else None
    y30 = q30y[0] if q30y else None

    if y2 and y10:
        spread = y10 - y2
        spread_color = "#16a34a" if spread > 0 else "#dc2626"
        if spread > 0.5:
            curve_shape = "Normal (steepening) — growth expected, risk appetite supported"
        elif spread > 0:
            curve_shape = "Flat-ish — market uncertain on growth outlook"
        elif spread > -0.25:
            curve_shape = "Mildly inverted — mild recession signal, watch credit"
        else:
            curve_shape = "Inverted — recession warning, historically reliable signal"

        y2_chg  = q2y[2]  if q2y  else 0
        y10_chg = q10y[2] if q10y else 0

        rows += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">Yield Curve</div>
          <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px">
            <div><div style="font-size:11px;color:#94a3b8">2-Year</div><div style="font-size:15px;font-weight:800;color:#0f172a">{y2:.3f}% <span style="font-size:12px;color:{chg_color(y2_chg)}">{chg_arrow(y2_chg)}{y2_chg:+.1f}bp</span></div></div>
            <div><div style="font-size:11px;color:#94a3b8">10-Year</div><div style="font-size:15px;font-weight:800;color:#0f172a">{y10:.3f}% <span style="font-size:12px;color:{chg_color(y10_chg)}">{chg_arrow(y10_chg)}{y10_chg:+.1f}bp</span></div></div>
            {"<div><div style='font-size:11px;color:#94a3b8'>30-Year</div><div style='font-size:15px;font-weight:800;color:#0f172a'>" + f"{y30:.3f}%" + "</div></div>" if y30 else ""}
            <div><div style="font-size:11px;color:#94a3b8">2s10s Spread</div><div style="font-size:15px;font-weight:800;color:{spread_color}">{spread:+.0f}bps</div></div>
          </div>
          <div style="font-size:12px;color:#475569;padding:7px 10px;background:#f8fafc;border-left:3px solid {spread_color};border-radius:3px">
            📐 <strong>Curve Shape:</strong> {curve_shape}
          </div>
        </div>"""

    # VIX block
    vix = get_quote("^VIX")
    if vix:
        vix_val = vix[0]
        vix_chg = vix[2]
        if vix_val > 30:
            vix_label, vix_color, vix_bg = "EXTREME FEAR", "#991b1b", "#fee2e2"
            vix_note = "Market in panic mode. Clients may call. Lead with long-term allocation and stay calm."
        elif vix_val > 25:
            vix_label, vix_color, vix_bg = "HIGH FEAR", "#9a3412", "#ffedd5"
            vix_note = "Elevated anxiety. Structured products conversations are relevant — protected notes, collars."
        elif vix_val > 20:
            vix_label, vix_color, vix_bg = "CAUTION", "#854d0e", "#fef9c3"
            vix_note = "Above normal volatility. Options pricing is rich. Watch for positioning shifts."
        elif vix_val > 15:
            vix_label, vix_color, vix_bg = "NORMAL", "#166534", "#dcfce7"
            vix_note = "Calm market. Good environment for risk assets. Complacency risk if sustained."
        else:
            vix_label, vix_color, vix_bg = "VERY CALM", "#166534", "#f0fdf4"
            vix_note = "Extremely low volatility. Markets pricing in near-zero risk — historically precedes spikes."

        rows += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">VIX — Fear Gauge</div>
          <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:6px">
            <div style="font-size:22px;font-weight:900;color:{vix_color};background:{vix_bg};padding:4px 14px;border-radius:6px">{vix_val:.2f}</div>
            <div><span style="font-size:13px;font-weight:800;color:{vix_color}">{vix_label}</span> &nbsp;<span style="font-size:12px;color:{chg_color(vix_chg)}">{chg_arrow(vix_chg)} {vix_chg:+.2f}%</span></div>
          </div>
          <div style="font-size:11px;color:#475569">{vix_note}</div>
        </div>"""

    # AGG block
    if agg:
        agg_color = chg_color(agg[2])
        agg_arrow = chg_arrow(agg[2])
        rows += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">AGG — Bloomberg US Aggregate Bond Index (ETF Proxy)</div>
          <div style="display:flex;gap:24px;flex-wrap:wrap">
            <div><div style="font-size:11px;color:#94a3b8">Price</div><div style="font-size:16px;font-weight:800;color:#0f172a">${agg[0]:,.2f}</div></div>
            <div><div style="font-size:11px;color:#94a3b8">Change</div><div style="font-size:16px;font-weight:800;color:{agg_color}">{agg_arrow} {agg[2]:+.2f}%</div></div>
          </div>
          <div style="font-size:11px;color:#64748b;margin-top:5px">AGG tracks investment-grade US bonds (Treasuries, MBS, corporates). Rising AGG = falling yields / risk-off. Falling AGG = rising yields / inflation pressure.</div>
        </div>"""

    # Oil block
    if oil:
        oil_color = chg_color(oil[2])
        oil_arrow = chg_arrow(oil[2])
        oil_note = ""
        if oil[2] > 2:
            oil_note = "Significant spike — watch XLE, inflation expectations, airline costs."
        elif oil[2] < -2:
            oil_note = "Sharp drop — positive for inflation, negative for energy sector."
        elif oil[2] > 0.5:
            oil_note = "Moderate rise — energy names may outperform today."
        else:
            oil_note = "Relatively stable — no major energy catalyst overnight."

        rows += f"""
        <div style="padding:12px 0;border-bottom:1px solid #f1f5f9">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px">WTI Crude Oil</div>
          <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:6px">
            <div><div style="font-size:11px;color:#94a3b8">Price</div><div style="font-size:16px;font-weight:800;color:#0f172a">${oil[0]:,.2f}/bbl</div></div>
            <div><div style="font-size:11px;color:#94a3b8">Change</div><div style="font-size:16px;font-weight:800;color:{oil_color}">{oil_arrow} {oil[2]:+.2f}%</div></div>
          </div>
          <div style="font-size:11px;color:#475569">{oil_note}</div>
        </div>"""

    # Macro narrative from overnight headlines
    feeds = [
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "CNBC"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
    ]
    all_headlines = []
    for url, source in feeds:
        items = fetch_rss(url, max_items=4)
        for it in items:
            it["source"] = source
        all_headlines.extend(items)

    if all_headlines:
        macro_items = all_headlines[:6]
        macro_rows = ""
        macro_themes = set()
        for item in macro_items:
            tl = item["title"].lower()
            for kw, (label, _) in RIPPLE.items():
                if kw in tl:
                    macro_themes.add(label)
            rt = ripple_tag(tl)
            macro_rows += f"""
            <div style="padding:8px 0;border-bottom:1px solid #f8fafc">
              <div style="font-size:12px;font-weight:700;color:#1e293b">{item['title']}</div>
              {f'<div style="margin-top:4px">{rt}</div>' if rt else ''}
            </div>"""

        if macro_themes:
            themes_html = " ".join(
                f'<span style="font-size:11px;font-weight:700;color:#1e40af;background:#dbeafe;padding:2px 8px;border-radius:3px">{t}</span>'
                for t in macro_themes
            )
            themes_line = f'<div style="margin-bottom:10px"><strong style="font-size:11px;color:#64748b">Active themes: </strong>{themes_html}</div>'
        else:
            themes_line = ""

        rows += f"""
        <div style="padding:12px 0">
          <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px">🌐 Overnight Macro Pulse</div>
          {themes_line}
          {macro_rows}
          <div style="margin-top:10px;padding:10px 12px;background:#f0f9ff;border-left:3px solid #2563eb;border-radius:4px;font-size:12px;color:#1e293b;line-height:1.6">
            💡 <strong>Big Picture:</strong> Read the headlines above through this lens — how do they affect the Fed's rate path, credit spreads, or equity risk premium? That's the question your advisors are asking at 8 AM.
          </div>
        </div>"""

    return card("📐 Rates, Bonds & Macro", "S&P · Yield Curve · AGG · Oil · Overnight Headlines", rows, "#2563eb")


# ── EMAIL ASSEMBLY ────────────────────────────────────────────────────────────
def build_email():
    header    = market_intelligence()
    markets   = premarket_table()
    rates     = rates_and_macro()
    sectors   = sector_rotation()
    headlines = market_headlines()
    geo       = geo_pulse()
    analyst   = analyst_lens()
    sports    = sports_brief()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Morning Briefing — {DATE_STR}</title>
</head>
<body style="margin:0;padding:0;background:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:16px 10px">

  {header}
  {markets}
  {rates}
  {sectors}
  {headlines}
  {geo}
  {analyst}
  {sports}

  <!-- FOOTER -->
  <div style="background:#0f172a;padding:14px 24px;border-radius:0 0 12px 12px">
    <div style="font-size:11px;color:#475569;line-height:1.7">
      Market data: Yahoo Finance &nbsp;·&nbsp; News: Reuters, BBC, CNBC, MarketWatch, Yahoo Finance &nbsp;·&nbsp; Sports: ESPN<br>
      Delivered at 6:30 AM daily &nbsp;·&nbsp; justincartagenova@gmail.com &nbsp;·&nbsp; <strong style="color:#3b82f6">JPMorgan Asset &amp; Wealth Management</strong>
    </div>
  </div>

</div>
</body>
</html>"""


# ── SEND ──────────────────────────────────────────────────────────────────────
def send():
    if not GMAIL_PASS:
        print("❌  GMAIL_PASS not set.")
        return
    subject = f"☀️ Morning Brief — {DATE_STR}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(build_email(), "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
        print(f"✅  Sent to {TO_EMAIL}")
    except smtplib.SMTPAuthenticationError:
        print("❌  Auth failed — use a Gmail App Password.")
        print("    https://myaccount.google.com/apppasswords")
    except Exception as e:
        print(f"❌  {e}")

if __name__ == "__main__":
    send()
