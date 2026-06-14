#!/usr/bin/env python3
"""
Morning Briefing — JPMorgan Private Bank Edition
Sends a daily 6:30 AM email built for a wealth management / private bank analyst.
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

GMAIL_USER = os.environ.get("GMAIL_USER", "justincartagenova@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "")
TO_EMAIL   = os.environ.get("TO_EMAIL",   "justincartagenova@gmail.com")

NOW      = datetime.datetime.now()
DATE_STR = NOW.strftime("%A, %B %d, %Y")
WEEKDAY  = NOW.strftime("%A")
TIME_STR = NOW.strftime("%I:%M %p")

FUTURES = {
    "ES=F":      ("S&P 500",     "equity"),
    "NQ=F":      ("Nasdaq",      "equity"),
    "YM=F":      ("Dow",         "equity"),
    "RTY=F":     ("Russell 2000","equity"),
    "^VIX":      ("VIX",         "vix"),
    "^TNX":      ("10-Yr Yield", "rate"),
    "^TYX":      ("30-Yr Yield", "rate"),
    "GC=F":      ("Gold",        "commodity"),
    "CL=F":      ("Oil (WTI)",   "commodity"),
    "DX-Y.NYB":  ("USD Index",   "fx"),
}

FINANCIALS = {
    "JPM": "JPMorgan Chase",
    "GS":  "Goldman Sachs",
    "MS":  "Morgan Stanley",
    "BLK": "BlackRock",
    "BAC": "Bank of America",
    "C":   "Citigroup",
    "WFC": "Wells Fargo",
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

RIPPLE = {
    "tariff":    ("Trade",      "Tariff move -> XLI, XLB, global supply chains"),
    "china":     ("China",      "China risk -> semis, XLK, supply chain names"),
    "iran":      ("Iran/Oil",   "Iran tension -> oil spike, XLE, gold bid"),
    "oil":       ("Energy",     "Oil move -> XLE, inflation outlook, airlines"),
    "fed":       ("Fed",        "Fed signal -> rates, TLT, XLF duration sensitivity"),
    "rate":      ("Rates",      "Rate move -> bond prices, XLF, REITs (XLRE)"),
    "inflation": ("CPI/PCE",    "Inflation data -> rate path, TLT, TIPS"),
    "bank":      ("Banking",    "Bank news -> XLF, KRE, direct JPM exposure"),
    "sanctions": ("Sanctions",  "Sanctions -> XLF compliance, energy names"),
    "recession": ("Growth",     "Recession fear -> defensives (XLP, XLU), credit spreads"),
    "ukraine":   ("Ukraine",    "Conflict -> XLE, wheat, defense (LMT, RTX)"),
    "debt":      ("Debt/Credit","Debt news -> Treasury yields, IG/HY spreads"),
    "default":   ("Default",    "Default risk -> credit spreads, risk-off move"),
    "ecb":       ("ECB",        "ECB policy -> EUR/USD, European cross-asset exposure"),
    "earnings":  ("Earnings",   "Earnings beat/miss -> sector read-through"),
    "ai":        ("AI/Tech",    "AI story -> semis (NVDA, AVGO), XLK broadly"),
    "crypto":    ("Crypto",     "Crypto move -> risk sentiment barometer"),
    "gdp":       ("Growth",     "GDP data -> rate path, cyclicals vs. defensives"),
    "jobs":      ("Jobs/NFP",   "Jobs data -> Fed reaction, consumer spending names"),
}


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
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300].strip()
            if title:
                items.append({"title": title, "link": link, "desc": desc})
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []

def get_quote(ticker):
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
        ("ft.com",      "FT",          "#c8531c", "#fff7ed"),
        ("bloomberg",   "Bloomberg",   "#1a1a1a", "#f8fafc"),
        ("wsj",         "WSJ",         "#1c4b8a", "#eff6ff"),
    ]
    for key, label, color, bg in mapping:
        if key in url.lower():
            return f'<span style="font-size:10px;font-weight:700;color:{color};background:{bg};padding:2px 6px;border-radius:3px;margin-right:6px">{label}</span>'
    return ""

def ripple_tag(title_lower):
    for kw, (label, note) in RIPPLE.items():
        if kw in title_lower:
            return f'<span style="display:inline-block;font-size:10px;font-weight:600;color:#854d0e;background:#fef9c3;padding:2px 7px;border-radius:3px;margin-top:4px">&#9889; {label}: {note}</span>'
    return ""

def card(title, subtitle, content, accent="#2563eb"):
    return f"""
<div style="background:#ffffff;border-top:3px solid {accent};margin-bottom:3px;padding:20px 24px">
  <div style="margin-bottom:14px">
    <div style="font-size:15px;font-weight:800;color:#0f172a">{title}</div>
    <div style="font-size:11px;color:#94a3b8;margin-top:2px">{subtitle}</div>
  </div>
  {content}
</div>"""


def market_intelligence():
    if not YFINANCE_OK:
        return ""
    es   = get_quote("ES=F")
    vix  = get_quote("^VIX")
    tnx  = get_quote("^TNX")
    oil  = get_quote("CL=F")
    gold = get_quote("GC=F")
    btc  = get_quote("BTC-USD")

    if es:
        chg = es[2]
        if chg > 1:      regime, rc, rbg = "RISK-ON",      "#166534", "#dcfce7"
        elif chg > 0.3:  regime, rc, rbg = "LEANING GREEN","#166534", "#f0fdf4"
        elif chg > -0.3: regime, rc, rbg = "FLAT OPEN",    "#78716c", "#fafaf9"
        elif chg > -1:   regime, rc, rbg = "LEANING RED",  "#991b1b", "#fff7f7"
        else:            regime, rc, rbg = "RISK-OFF",     "#991b1b", "#fee2e2"
        es_line = f"S&P futures <strong>{chg:+.2f}%</strong>"
    else:
        regime, rc, rbg = "PENDING", "#64748b", "#f8fafc"
        es_line = "Futures data loading"

    chips = []
    if vix:
        v = vix[0]
        if v > 30:   chips.append(("EXTREME FEAR", "#991b1b", "#fee2e2"))
        elif v > 25: chips.append((f"VIX {v:.0f} - Elevated Fear", "#9a3412", "#ffedd5"))
        elif v > 20: chips.append((f"VIX {v:.0f} - Caution", "#854d0e", "#fef9c3"))
        else:        chips.append((f"VIX {v:.0f} - Calm", "#166534", "#dcfce7"))
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

    wm_takes = []
    if es and es[2] < -0.5:
        wm_takes.append("Down open expected - lead with long-term allocation, avoid reacting to daily moves.")
    if vix and vix[0] > 22:
        wm_takes.append("Elevated VIX - structured products conversations are relevant: protected notes, collars.")
    if tnx and tnx[2] > 0.08:
        wm_takes.append("Yields rising - bond prices falling. Short-duration and floating rate look attractive.")
    if tnx and tnx[0] and tnx[0] > 4.5:
        wm_takes.append(f"10-yr at {tnx[0]:.2f}% - cash and T-bills are genuinely competitive yield story.")
    if oil and abs(oil[2]) > 2:
        wm_takes.append(f"Oil {'spike' if oil[2] > 0 else 'drop'} - watch XLE and inflation outlook.")
    if not wm_takes:
        wm_takes.append("Steady open - good day for proactive client outreach. No fires to put out.")

    takes_html = "".join(
        f'<div style="padding:7px 0;border-bottom:1px solid #f8fafc;font-size:13px;color:#1e293b;line-height:1.5">{t}</div>'
        for t in wm_takes
    )

    return f"""
<div style="background:#0f172a;padding:20px 24px 0;border-radius:12px 12px 0 0">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
    <div>
      <div style="font-size:22px;font-weight:900;color:#fff">Good morning, Justin &#9728;</div>
      <div style="font-size:12px;color:#64748b;margin-top:3px">{DATE_STR} &nbsp;&#183;&nbsp; {TIME_STR}</div>
    </div>
    <div style="background:#1e293b;padding:8px 14px;border-radius:8px;text-align:right">
      <div style="font-size:10px;font-weight:700;color:#3b82f6">JPM PRIVATE BANK</div>
      <div style="font-size:10px;color:#64748b;margin-top:1px">Morning Intelligence Brief</div>
    </div>
  </div>
  <div style="height:4px;background:linear-gradient(90deg,#2563eb,#7c3aed,#db2777,#ea580c);margin:16px -24px 0"></div>
</div>
<div style="background:#fff;padding:18px 24px 14px;margin-bottom:3px">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap">
    <span style="font-size:18px;font-weight:900;color:{rc};background:{rbg};padding:5px 14px;border-radius:6px">{regime}</span>
    <span style="font-size:13px;color:#475569">{es_line}</span>
  </div>
  <div style="margin-bottom:14px">{chips_html}</div>
  <div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px">What This Means For You Today</div>
  {takes_html}
</div>"""


def premarket_table():
    if not YFINANCE_OK:
        return card("Premarket Snapshot", "Futures + macro", "<p style='color:#94a3b8'>Install yfinance</p>")

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
            disp = f"${price:,.2f}"
        bg = ""
        if abs(chg) > 1.5:
            bg = f"background:{'#f0fdf4' if chg > 0 else '#fff7f7'};"
        fut_rows += f'<tr style="{bg}"><td style="padding:6px 10px;font-size:13px;font-weight:700;color:#0f172a">{label}</td><td style="padding:6px 10px;font-size:13px;color:#475569;text-align:right">{disp}</td><td style="padding:6px 10px;font-size:13px;font-weight:800;color:{color};text-align:right">{arrow} {chg:+.2f}%</td></tr>'

    fin_rows = ""
    for ticker, label in FINANCIALS.items():
        q = get_quote(ticker)
        if not q:
            continue
        price, prev, chg = q
        color = chg_color(chg)
        arrow = chg_arrow(chg)
        flag = ' <span style="font-size:9px;background:#dbeafe;color:#1e40af;padding:1px 5px;border-radius:3px;font-weight:700">YOUR FIRM</span>' if ticker == "JPM" else ""
        fin_rows += f'<tr><td style="padding:5px 10px;font-size:13px;font-weight:600;color:#0f172a">{label}{flag}</td><td style="padding:5px 10px;font-size:13px;color:#475569;text-align:right">${price:,.2f}</td><td style="padding:5px 10px;font-size:13px;font-weight:800;color:{color};text-align:right">{arrow} {chg:+.2f}%</td></tr>'

    content = f'<div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">Futures &amp; Macro</div><table style="width:100%;border-collapse:collapse;margin-bottom:16px">{fut_rows}</table><div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">Financials</div><table style="width:100%;border-collapse:collapse">{fin_rows}</table>'
    return card("&#128202; Premarket Snapshot", "What the market expects before the bell", content, "#2563eb")


def rates_and_macro():
    if not YFINANCE_OK:
        return card("Rates &amp; Macro", "Yield curve · S&P · Oil · AGG · VIX", "<p style='color:#94a3b8'>Data unavailable</p>")

    spy  = get_quote("SPY")
    es   = get_quote("ES=F")
    q2y  = get_quote("2YY=F")
    q10y = get_quote("^TNX")
    q30y = get_quote("^TYX")
    agg  = get_quote("AGG")
    oil  = get_quote("CL=F")
    vix  = get_quote("^VIX")

    rows = ""

    if spy and es:
        implied_open_chg = es[2]
        color = chg_color(implied_open_chg)
        arrow = chg_arrow(implied_open_chg)
        rows += f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">S&P 500</div><div style="display:flex;gap:24px;flex-wrap:wrap"><div><div style="font-size:11px;color:#94a3b8">Yesterday Close (SPY)</div><div style="font-size:16px;font-weight:800;color:#0f172a">${spy[0]:,.2f}</div></div><div><div style="font-size:11px;color:#94a3b8">Futures Implied Move (ES=F)</div><div style="font-size:16px;font-weight:800;color:{color}">{arrow} {implied_open_chg:+.2f}% (ES {es[0]:,.2f})</div></div></div></div>'

    y2  = q2y[0]  if q2y  else None
    y10 = q10y[0] if q10y else None
    y30 = q30y[0] if q30y else None
    if y2 and y10:
        spread = y10 - y2
        sc = "#16a34a" if spread > 0 else "#dc2626"
        if spread > 0.5:   shape = "Normal (steepening) - growth expected, risk appetite supported"
        elif spread > 0:   shape = "Flat-ish - market uncertain on growth outlook"
        elif spread > -0.25: shape = "Mildly inverted - mild recession signal, watch credit"
        else:              shape = "Inverted - recession warning signal"
        y2c  = q2y[2]  if q2y  else 0
        y10c = q10y[2] if q10y else 0
        y30_html = f'<div><div style="font-size:11px;color:#94a3b8">30-Year</div><div style="font-size:15px;font-weight:800;color:#0f172a">{y30:.3f}%</div></div>' if y30 else ""
        rows += f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">Yield Curve</div><div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px"><div><div style="font-size:11px;color:#94a3b8">2-Year</div><div style="font-size:15px;font-weight:800;color:#0f172a">{y2:.3f}% <span style="font-size:12px;color:{chg_color(y2c)}">{chg_arrow(y2c)}{y2c:+.1f}bp</span></div></div><div><div style="font-size:11px;color:#94a3b8">10-Year</div><div style="font-size:15px;font-weight:800;color:#0f172a">{y10:.3f}% <span style="font-size:12px;color:{chg_color(y10c)}">{chg_arrow(y10c)}{y10c:+.1f}bp</span></div></div>{y30_html}<div><div style="font-size:11px;color:#94a3b8">2s10s Spread</div><div style="font-size:15px;font-weight:800;color:{sc}">{spread:+.0f}bps</div></div></div><div style="font-size:12px;color:#475569;padding:7px 10px;background:#f8fafc;border-left:3px solid {sc};border-radius:3px"><strong>Curve Shape:</strong> {shape}</div></div>'

    if vix:
        vv, vc = vix[0], vix[2]
        if vv > 30:   vl, vcol, vbg, vn = "EXTREME FEAR", "#991b1b", "#fee2e2", "Market in panic mode. Lead with long-term allocation."
        elif vv > 25: vl, vcol, vbg, vn = "HIGH FEAR",   "#9a3412", "#ffedd5", "Elevated anxiety. Structured products conversations relevant."
        elif vv > 20: vl, vcol, vbg, vn = "CAUTION",     "#854d0e", "#fef9c3", "Above normal volatility. Options pricing is rich."
        elif vv > 15: vl, vcol, vbg, vn = "NORMAL",      "#166534", "#dcfce7", "Calm market. Good environment for risk assets."
        else:         vl, vcol, vbg, vn = "VERY CALM",   "#166534", "#f0fdf4", "Extremely low volatility - historically precedes spikes."
        rows += f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">VIX - Fear Gauge</div><div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:6px"><div style="font-size:22px;font-weight:900;color:{vcol};background:{vbg};padding:4px 14px;border-radius:6px">{vv:.2f}</div><div><span style="font-size:13px;font-weight:800;color:{vcol}">{vl}</span> &nbsp;<span style="font-size:12px;color:{chg_color(vc)}">{chg_arrow(vc)} {vc:+.2f}%</span></div></div><div style="font-size:11px;color:#475569">{vn}</div></div>'

    if agg:
        ac, aa = chg_color(agg[2]), chg_arrow(agg[2])
        rows += f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">AGG - Bloomberg US Aggregate Bond ETF</div><div style="display:flex;gap:24px;flex-wrap:wrap"><div><div style="font-size:11px;color:#94a3b8">Price</div><div style="font-size:16px;font-weight:800;color:#0f172a">${agg[0]:,.2f}</div></div><div><div style="font-size:11px;color:#94a3b8">Change</div><div style="font-size:16px;font-weight:800;color:{ac}">{aa} {agg[2]:+.2f}%</div></div></div><div style="font-size:11px;color:#64748b;margin-top:5px">Rising AGG = falling yields / risk-off. Falling AGG = rising yields / inflation pressure.</div></div>'

    if oil:
        oc, oa = chg_color(oil[2]), chg_arrow(oil[2])
        if oil[2] > 2:    on = "Significant spike - watch XLE, inflation expectations, airline costs."
        elif oil[2] < -2: on = "Sharp drop - positive for inflation, negative for energy sector."
        elif oil[2] > 0.5: on = "Moderate rise - energy names may outperform today."
        else:             on = "Relatively stable - no major energy catalyst overnight."
        rows += f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:6px">WTI Crude Oil</div><div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:6px"><div><div style="font-size:11px;color:#94a3b8">Price</div><div style="font-size:16px;font-weight:800;color:#0f172a">${oil[0]:,.2f}/bbl</div></div><div><div style="font-size:11px;color:#94a3b8">Change</div><div style="font-size:16px;font-weight:800;color:{oc}">{oa} {oil[2]:+.2f}%</div></div></div><div style="font-size:11px;color:#475569">{on}</div></div>'

    feeds = [
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "CNBC"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
    ]
    all_hl = []
    for url, source in feeds:
        items = fetch_rss(url, max_items=4)
        for it in items:
            it["source"] = source
        all_hl.extend(items)

    if all_hl:
        macro_rows = ""
        macro_themes = set()
        for item in all_hl[:6]:
            tl = item["title"].lower()
            for kw, (label, _) in RIPPLE.items():
                if kw in tl:
                    macro_themes.add(label)
            rt = ripple_tag(tl)
            macro_rows += f'<div style="padding:8px 0;border-bottom:1px solid #f8fafc"><div style="font-size:12px;font-weight:700;color:#1e293b">{item["title"]}</div>{("<div style=margin-top:4px>" + rt + "</div>") if rt else ""}</div>'

        themes_line = ""
        if macro_themes:
            themes_html = " ".join(f'<span style="font-size:11px;font-weight:700;color:#1e40af;background:#dbeafe;padding:2px 8px;border-radius:3px">{t}</span>' for t in macro_themes)
            themes_line = f'<div style="margin-bottom:10px"><strong style="font-size:11px;color:#64748b">Active themes: </strong>{themes_html}</div>'

        rows += f'<div style="padding:12px 0"><div style="font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;margin-bottom:8px">Overnight Macro Pulse</div>{themes_line}{macro_rows}</div>'

    return card("&#128208; Rates, Bonds &amp; Macro", "S&P · Yield Curve · VIX · AGG · Oil · Overnight Headlines", rows, "#2563eb")


def sector_rotation():
    if not YFINANCE_OK:
        return card("Sector Rotation", "Yesterday's close", "<p style='color:#94a3b8'>Data unavailable</p>")
    sectors = []
    for etf, name in SECTORS.items():
        q = get_quote(etf)
        if q:
            sectors.append((name, etf, q[2]))
    if not sectors:
        return card("Sector Rotation", "Yesterday's close", "<p style='color:#94a3b8'>Data unavailable</p>")
    sectors.sort(key=lambda x: x[2], reverse=True)
    max_abs = max(abs(c) for _, _, c in sectors) or 1
    rows = ""
    for name, etf, chg in sectors:
        color = chg_color(chg)
        arrow = chg_arrow(chg)
        bar_w = int((abs(chg) / max_abs) * 80)
        jpm_note = " <- your sector" if etf == "XLF" else ""
        rows += f'<tr><td style="padding:5px 8px;font-size:12px;font-weight:700;color:#1e293b;width:150px">{name}<span style="font-size:10px;color:#3b82f6">{jpm_note}</span></td><td style="padding:5px 8px;width:40px;font-size:10px;color:#94a3b8">{etf}</td><td style="padding:5px 8px"><div style="height:8px;width:{bar_w}%;background:{color};border-radius:3px;opacity:.65;min-width:3px"></div></td><td style="padding:5px 8px;font-size:13px;font-weight:800;color:{color};text-align:right;white-space:nowrap">{arrow} {chg:+.2f}%</td></tr>'
    top, bot = sectors[0], sectors[-1]
    xlf_chg = next((c for n, e, c in sectors if e == "XLF"), None)
    narr = f"<strong>{top[0]}</strong> led, <strong>{bot[0]}</strong> lagged. "
    if "Utilities" in top[0] or "Staples" in top[0] or "Healthcare" in top[0]:
        narr += "Defensive rotation - money moving to safety."
    elif "Technology" in top[0]:
        narr += "Tech leading = risk appetite healthy."
    elif "Financials" in top[0]:
        narr += "Financials leading - positive tailwind for JPM."
    elif "Energy" in top[0]:
        narr += "Energy leading - likely oil/geopolitical driver."
    else:
        narr += "Monitor whether this is a single-day move or trend."
    if xlf_chg is not None:
        narr += f' <strong style="color:{chg_color(xlf_chg)}">XLF {chg_arrow(xlf_chg)} {xlf_chg:+.2f}%</strong> - direct context for JPM conversations.'
    content = f'<table style="width:100%;border-collapse:collapse">{rows}</table><div style="margin-top:12px;padding:10px 12px;background:#f8fafc;border-left:3px solid #f59e0b;border-radius:4px;font-size:12px;color:#1e293b;line-height:1.6"><strong>Rotation Read:</strong> {narr}</div>'
    return card("&#128293; Sector Rotation", "All 11 sectors ranked - where money moved yesterday", content, "#f59e0b")


def market_headlines():
    feeds = [
        ("https://feeds.reuters.com/reuters/businessNews",        "https://reuters.com"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "https://marketwatch.com"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "https://cnbc.com"),
        ("https://finance.yahoo.com/news/rssindex",               "https://yahoo.com"),
    ]
    all_items = []
    for url, domain in feeds:
        items = fetch_rss(url, max_items=4)
        for it in items:
            it["domain"] = domain
        all_items.extend(items)
    if not all_items:
        return card("Market Headlines", "Top finance news", "<p style='color:#94a3b8'>Unavailable</p>")
    rows = ""
    for item in all_items[:8]:
        badge = source_badge(item.get("domain", ""))
        rt    = ripple_tag(item["title"].lower())
        desc_html = f'<div style="font-size:12px;color:#64748b;margin-top:3px;line-height:1.5">{item["desc"]}</div>' if item.get("desc") else ""
        rows += f'<div style="padding:11px 0;border-bottom:1px solid #f1f5f9"><div style="margin-bottom:4px">{badge}<a href="{item.get("link","#")}" style="font-size:13px;font-weight:700;color:#0f172a;text-decoration:none">{item["title"]}</a></div>{desc_html}{("<div style=margin-top:5px>" + rt + "</div>") if rt else ""}</div>'
    content = rows + '<div style="margin-top:8px;font-size:10px;color:#94a3b8">Sources: Reuters · MarketWatch · CNBC · Yahoo Finance</div>'
    return card("&#128240; Market Headlines", "Full stories - market impact tagged", content, "#0f172a")


def geo_pulse():
    feeds = [
        ("https://feeds.reuters.com/reuters/worldNews", "https://reuters.com"),
        ("https://feeds.bbci.co.uk/news/world/rss.xml", "https://bbc.com"),
    ]
    all_items = []
    for url, domain in feeds:
        items = fetch_rss(url, max_items=5)
        for it in items:
            it["domain"] = domain
        all_items.extend(items)
    if not all_items:
        return card("Geo Pulse", "Global events", "<p style='color:#94a3b8'>Unavailable</p>")
    rows = ""
    for item in all_items[:6]:
        badge = source_badge(item.get("domain", ""))
        rt    = ripple_tag(item["title"].lower())
        desc_html = f'<div style="font-size:12px;color:#64748b;margin-top:3px;line-height:1.5">{item["desc"]}</div>' if item.get("desc") else ""
        rows += f'<div style="padding:11px 0;border-bottom:1px solid #f1f5f9"><div style="margin-bottom:4px">{badge}<a href="{item.get("link","#")}" style="font-size:13px;font-weight:700;color:#0f172a;text-decoration:none">{item["title"]}</a></div>{desc_html}{("<div style=margin-top:5px>" + rt + "</div>") if rt else ""}</div>'
    content = rows + '<div style="margin-top:8px;font-size:10px;color:#94a3b8">Sources: Reuters World · BBC World</div>'
    return card("&#127757; Geo Pulse", "Global developments - tagged by market impact", content, "#7c3aed")


def analyst_lens():
    tnx = get_quote("^TNX") if YFINANCE_OK else None
    vix = get_quote("^VIX") if YFINANCE_OK else None
    items = []
    items.append(("&#127970;", "Private Bank Lens", "JPM Private Bank serves clients with $10M+ in investable assets. Understand their total picture - investments, estate planning, lending (Lombard loans, mortgages), tax strategy, and next-gen wealth transfer."))
    items.append(("&#128208;", "Portfolio Construction Today", "At 6:30 AM your advisors are already thinking: Should I rebalance? Do I need to call any clients? Know your sector rotation and be ready to explain WHY a sector moved."))
    if tnx and tnx[0] > 4.3:
        items.append(("&#128181;", f"Fixed Income Opportunity - Yields at {tnx[0]:.2f}%", f"With the 10-yr at {tnx[0]:.2f}%, cash and short-duration fixed income are genuinely attractive. HNW clients holding excess liquidity can lock in real yield."))
    elif tnx:
        items.append(("&#128201;", f"Rates - 10-Yr at {tnx[0]:.2f}%", "Know the direction and velocity. Rising yields hurt bond prices but help new buyers. Falling yields support equity valuations."))
    if vix and vix[0] > 20:
        items.append(("&#128737;", "Volatility - Structured Products Moment", f"VIX at {vix[0]:.1f} means options are expensive. Opens conversations around structured notes, principal-protected or buffered notes."))
    items.append(("&#128269;", "Equity Research Mindset", "You are not just reporting prices - you are synthesizing what sector moves mean for client portfolios. Connect the dots before anyone asks you to."))
    items.append(("&#128203;", "What Smart Interns Ask", "How does today's rate move affect duration positioning in client fixed income sleeves? Is the XLF move driven by rate sensitivity or earnings expectations?"))
    rows = "".join(f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><div style="display:flex;gap:10px;align-items:flex-start"><span style="font-size:18px;line-height:1">{icon}</span><div><div style="font-size:13px;font-weight:800;color:#0f172a;margin-bottom:3px">{title}</div><div style="font-size:12px;color:#475569;line-height:1.6">{body}</div></div></div></div>' for icon, title, body in items)
    return card("&#129504; Analyst Lens - Private Bank Prep", "How to think about today · what to know · what to ask", rows, "#0f172a")


def sports_brief():
    sport_feeds = [
        ("&#9918; MLB", "https://www.mlb.com/feeds/news/rss.xml"),
        ("&#127936; NBA", "https://www.nba.com/news/rss.xml"),
        ("&#127944; NFL", "https://www.nfl.com/rss/rsslanding?searchString=news"),
        ("&#127944; NHL", "https://www.nhl.com/rss/news.xml"),
    ]
    sport_html = ""
    for label, url in sport_feeds:
        items = fetch_rss(url, max_items=2)
        if items:
            sport_html += f'<div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid #f1f5f9">{label}</div>'
            for item in items:
                desc = item.get("desc", "")
                desc_html = f'<div style="font-size:11px;color:#64748b;margin-top:2px;line-height:1.4">{desc[:120]}</div>' if desc else ""
                sport_html += f'<div style="padding:5px 0"><a href="{item["link"]}" style="font-size:13px;font-weight:600;color:#0f172a;text-decoration:none">{item["title"]}</a>{desc_html}</div>'

    if not sport_html:
        fallback = fetch_rss("https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml", max_items=5)
        if fallback:
            sport_html += '<div style="font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;margin:14px 0 6px">Top Sports</div>'
            for item in fallback:
                sport_html += f'<div style="padding:5px 0"><a href="{item["link"]}" style="font-size:13px;font-weight:600;color:#0f172a;text-decoration:none">{item["title"]}</a></div>'
        else:
            sport_html = "<p style='color:#94a3b8;font-size:13px'>Sports data unavailable</p>"

    hooks = {
        "Monday":    "Did you catch anything this weekend?",
        "Tuesday":   "Game last night - did you see the result?",
        "Wednesday": "Midweek - the standings are heating up.",
        "Thursday":  "Almost Friday - there is a game tonight. You watching?",
        "Friday":    "Big sports weekend coming up.",
        "Saturday":  "So much going on today.",
        "Sunday":    "Great Sunday for sports.",
    }
    hook = hooks.get(WEEKDAY, "Anything in sports you are following?")
    footer = f'<div style="margin-top:16px;padding:12px 14px;background:#f0fdf4;border-left:3px solid #22c55e;border-radius:4px"><div style="font-size:10px;font-weight:800;color:#15803d;text-transform:uppercase;margin-bottom:4px">{WEEKDAY} Opener</div><div style="font-size:13px;color:#1c1917;font-style:italic">{hook}</div></div>'
    content = sport_html + footer
    return card("&#127942; Sports &amp; Small Talk", "Know the story · own the room", content, "#16a34a")


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
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Morning Briefing</title></head>
<body style="margin:0;padding:0;background:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:16px 10px">
  {header}{markets}{rates}{sectors}{headlines}{geo}{analyst}{sports}
  <div style="background:#0f172a;padding:14px 24px;border-radius:0 0 12px 12px">
    <div style="font-size:11px;color:#475569;line-height:1.7">
      Market data: Yahoo Finance &nbsp;·&nbsp; News: Reuters, BBC, CNBC, MarketWatch<br>
      Delivered at 6:30 AM daily &nbsp;·&nbsp; justincartagenova@gmail.com &nbsp;·&nbsp; <strong style="color:#3b82f6">JPMorgan Asset &amp; Wealth Management</strong>
    </div>
  </div>
</div>
</body>
</html>"""


def send():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    gmail_user = os.environ.get("GMAIL_USER", "justincartagenova@gmail.com")
    gmail_pass = os.environ.get("GMAIL_PASS", "")
    to_email   = os.environ.get("TO_EMAIL",   "justincartagenova@gmail.com")

    if not gmail_pass:
        print("GMAIL_PASS not set.")
        return

    subject = f"Morning Brief - {DATE_STR}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = to_email
    msg.attach(MIMEText(build_email(), "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(gmail_user, gmail_pass)
            s.sendmail(gmail_user, to_email, msg.as_string())
        print(f"Sent to {to_email}")
    except smtplib.SMTPAuthenticationError:
        print("Auth failed - use a Gmail App Password.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    send()
