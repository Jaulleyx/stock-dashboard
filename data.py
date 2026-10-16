"""Recupero dati (Yahoo Finance, Google News) e gestione dei preferiti."""

import base64
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

ROOT = Path(__file__).parent
FAV_FILE = ROOT / "favorites.json"
SEG_FILE = ROOT / "segments.json"
GITHUB_REPO = "jaulleyx/stock-dashboard"
CATEGORIES = {"singole": "Aziende singole", "suddivisioni": "Aziende con suddivisioni"}

# Banche d'affari e broker principali: usati per la media "big" delle aspettative
BIG_FIRMS = ["goldman", "morgan stanley", "jp morgan", "jpmorgan", "bank of america", "bofa", "citi",
             "wells fargo", "barclays", "ubs", "deutsche bank", "hsbc", "jefferies", "bernstein",
             "evercore", "bnp", "mizuho", "macquarie", "nomura", "rbc", "td cowen", "credit suisse"]

RATING_SCORE = {
    "strong buy": 5, "top pick": 5, "conviction buy": 5,
    "buy": 4, "outperform": 4, "overweight": 4, "positive": 4, "accumulate": 4, "sector outperform": 4,
    "market outperform": 4, "add": 4,
    "hold": 3, "neutral": 3, "equal-weight": 3, "equal weight": 3, "market perform": 3, "sector perform": 3,
    "peer perform": 3, "in-line": 3, "sector weight": 3, "mixed": 3,
    "underperform": 2, "underweight": 2, "reduce": 2, "sector underperform": 2, "negative": 2,
    "sell": 1, "strong sell": 1,
}
SCORE_LABEL = [(4.5, "Strong Buy"), (3.5, "Buy"), (2.5, "Hold"), (1.5, "Underperform"), (0, "Sell")]


def score_label(s):
    return next(label for threshold, label in SCORE_LABEL if s >= threshold)


# ---------------------------------------------------------------- preferiti

def load_favorites():
    try:
        data = json.loads(FAV_FILE.read_text())
    except Exception:
        data = {}
    return {k: data.get(k, []) for k in CATEGORIES}


def _github_token():
    try:
        return st.secrets.get("github_token")
    except Exception:
        return None


def save_favorites(favs):
    """Salva in locale e, se configurato il token, anche su GitHub (così non si perde al riavvio)."""
    content = json.dumps(favs, indent=2, ensure_ascii=False) + "\n"
    FAV_FILE.write_text(content)
    token = _github_token()
    if not token:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/favorites.json"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    sha = requests.get(url, headers=headers, timeout=10).json().get("sha")
    r = requests.put(url, headers=headers, timeout=10, json={
        "message": "Aggiorna preferiti", "sha": sha,
        "content": base64.b64encode(content.encode()).decode()})
    return r.ok


def find_favorite(favs, ticker):
    for cat, items in favs.items():
        if any(i["ticker"] == ticker for i in items):
            return cat
    return None


def load_segments():
    try:
        return {k: v for k, v in json.loads(SEG_FILE.read_text()).items() if not k.startswith("_")}
    except Exception:
        return {}


# ---------------------------------------------------------------- Yahoo Finance

@st.cache_data(ttl=3600, show_spinner=False)
def search_symbol(query):
    """Accetta un ticker (AAPL, ENI.MI) o un nome (Apple, Ferrari)."""
    try:
        quotes = yf.Search(query, max_results=8, news_count=0).quotes
        return [(q["symbol"], q.get("shortname") or q.get("longname") or q["symbol"], q.get("exchange", ""))
                for q in quotes if q.get("quoteType") in ("EQUITY", "ETF")]
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def quotes_overview(tickers):
    """Prezzo, variazione giornaliera e andamento 3 mesi per la lista preferiti (una sola richiesta)."""
    if not tickers:
        return {}
    df = yf.download(list(tickers), period="3mo", auto_adjust=True, progress=False, group_by="ticker")
    out = {}
    for t in tickers:
        try:
            close = (df[t]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]).dropna()
            out[t] = {"price": float(close.iloc[-1]), "day": float(close.iloc[-1] / close.iloc[-2] - 1),
                      "3m": float(close.iloc[-1] / close.iloc[0] - 1), "trend": close.round(2).tolist()}
        except Exception:
            out[t] = None
    return out


@st.cache_data(ttl=900, show_spinner=False)
def load_stock(symbol):
    t = yf.Ticker(symbol)
    info = t.info or {}
    hist = t.history(period="5y", auto_adjust=True)

    def safe(fn, default=None):
        try:
            v = fn()
            return default if v is None else v
        except Exception:
            return default

    empty = pd.DataFrame()
    return {
        "info": info,
        "hist": hist,
        "fin": safe(lambda: t.financials, empty),
        "bs": safe(lambda: t.balance_sheet, empty),
        "cf": safe(lambda: t.cashflow, empty),
        "divs": safe(lambda: t.dividends, pd.Series(dtype=float)),
        "upgrades": safe(lambda: t.upgrades_downgrades, empty),
        "recs": safe(lambda: t.recommendations, empty),
        "eps_est": safe(lambda: t.earnings_estimate, empty),
        "rev_est": safe(lambda: t.revenue_estimate, empty),
        "yf_news": safe(lambda: t.news, []),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fx_rate(from_cur, to_cur):
    if not from_cur or not to_cur or from_cur == to_cur:
        return 1.0
    try:
        return float(yf.Ticker(f"{from_cur}{to_cur}=X").history(period="5d")["Close"].iloc[-1])
    except Exception:
        return None


# ---------------------------------------------------------------- analisti

def big_firm_targets(upgrades, months=12):
    """Ultimo giudizio e prezzo obiettivo di ogni grande banca negli ultimi `months` mesi."""
    if upgrades is None or upgrades.empty or "Firm" not in upgrades.columns:
        return pd.DataFrame()
    df = upgrades.copy()
    df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    df = df[df.index >= pd.Timestamp.now() - pd.DateOffset(months=months)].sort_index(ascending=False)
    df = df[df["Firm"].str.lower().apply(lambda f: any(b in f for b in BIG_FIRMS))]
    df = df.reset_index(names="Data").drop_duplicates("Firm")
    df["Punteggio"] = df["ToGrade"].str.lower().str.strip().map(RATING_SCORE)
    target = df["currentPriceTarget"] if "currentPriceTarget" in df else pd.Series(dtype=float)
    return pd.DataFrame({
        "Banca": df["Firm"], "Data": df["Data"].dt.date, "Giudizio": df["ToGrade"],
        "Punteggio": df["Punteggio"], "Target": target.where(target > 0),
    }).reset_index(drop=True)


# ---------------------------------------------------------------- notizie

def _yf_news(items):
    out = []
    for n in items or []:
        c = n.get("content", n)  # yfinance ha cambiato formato: gestisco entrambi
        url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link")
        date = c.get("pubDate") or c.get("providerPublishTime")
        try:
            date = pd.to_datetime(date, unit="s" if isinstance(date, (int, float)) else None, utc=True)
        except Exception:
            date = None
        if c.get("title") and url:
            out.append({"titolo": c["title"], "url": url, "data": date,
                        "fonte": (c.get("provider") or {}).get("displayName") or c.get("publisher", "Yahoo Finance"),
                        "riassunto": c.get("summary", "")})
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def google_news(query, lang="it"):
    region = {"it": ("IT", "it"), "en": ("US", "en-US")}[lang]
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
           + f"&hl={region[1]}&gl={region[0]}&ceid={region[0]}:{lang}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=10).read())
    except Exception:
        return []
    out = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        source = item.findtext("source", "")
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        try:
            date = pd.Timestamp(parsedate_to_datetime(item.findtext("pubDate"))).tz_convert("UTC")
        except Exception:
            date = None
        out.append({"titolo": title, "url": item.findtext("link"), "data": date, "fonte": source, "riassunto": ""})
    return out


def all_news(yf_items, company, limit=25):
    news = _yf_news(yf_items) + google_news(f'"{company}"', "it") + google_news(f"{company} stock", "en")
    seen, unique = set(), []
    for n in news:
        key = n["titolo"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(n)
    unique.sort(key=lambda n: n["data"] if n["data"] is not None else pd.Timestamp(0, tz="UTC"), reverse=True)
    return unique[:limit]
