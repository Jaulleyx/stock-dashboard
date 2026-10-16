"""Ricerca dei dati che Yahoo Finance non fornisce (segmenti, partecipazioni, sintesi).

Il sito mette i titoli in coda creando requests/<TICKER>.json nel repository GitHub.
Un'attività pianificata di Claude (giorni feriali) legge la coda, fa la ricerca seguendo
RESEARCH_SPEC.md e salva il risultato in research/<TICKER>.json."""

import json
from datetime import date, datetime

import requests
import streamlit as st

import data

RESEARCH_DIR = data.ROOT / "research"
REQUESTS_DIR = data.ROOT / "requests"
RAW_URL = f"https://raw.githubusercontent.com/{data.GITHUB_REPO}/main"


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_remote(path):
    """Legge un file direttamente da GitHub: i risultati compaiono anche prima che l'app si aggiorni."""
    try:
        r = requests.get(f"{RAW_URL}/{path}", timeout=10)
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def _read(local_path, remote_path):
    try:
        return json.loads(local_path.read_text())
    except Exception:
        return _fetch_remote(remote_path)


def load(ticker):
    return _read(RESEARCH_DIR / f"{ticker}.json", f"research/{ticker}.json")


def queued(ticker):
    return _read(REQUESTS_DIR / f"{ticker}.json", f"requests/{ticker}.json")


def enqueue(ticker, company, info, refresh=False):
    """Mette il titolo in coda. Restituisce False se non è possibile salvare su GitHub."""
    req = {"ticker": ticker, "nome": company, "richiesta": datetime.now().isoformat(timespec="minutes"),
           "aggiornamento": refresh,
           "contesto": {k: info.get(k) for k in ("longName", "sector", "industry", "country", "exchange",
                                                 "financialCurrency", "website") if info.get(k)}}
    content = json.dumps(req, indent=2, ensure_ascii=False) + "\n"
    if not data.github_put(f"requests/{ticker}.json", content, f"Richiesta ricerca: {ticker}"):
        return False
    REQUESTS_DIR.mkdir(exist_ok=True)
    (REQUESTS_DIR / f"{ticker}.json").write_text(content)
    _fetch_remote.clear()
    return True


def is_stale(result, days=90):
    try:
        return (date.today() - date.fromisoformat(result["data_ricerca"])).days > days
    except Exception:
        return True
