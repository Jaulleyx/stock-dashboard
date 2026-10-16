"""Ricerca automatica con Claude: quando si apre un titolo, Claude cerca sul web i dati che
Yahoo Finance non fornisce (segmenti, partecipazioni, sintesi) e li salva in research/<TICKER>.json.
I risultati vengono salvati anche su GitHub, così sono condivisi tra tutti gli utenti del sito."""

import json
from datetime import date
from pathlib import Path

import anthropic
import streamlit as st

import data

RESEARCH_DIR = data.ROOT / "research"
MODEL = "claude-opus-5-5"
MAX_ROUNDS = 6  # massimo numero di ripartenze su pause_turn

NULL_NUM = {"type": ["number", "null"]}
NULL_STR = {"type": ["string", "null"]}

SUBMIT_TOOL = {
    "name": "salva_ricerca",
    "description": "Salva i risultati della ricerca sul titolo. Chiamalo una sola volta, alla fine.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["categoria", "motivazione_categoria", "sintesi", "catalizzatori", "rischi", "periodo",
                     "valuta", "misura_utile", "segmenti", "partecipazioni", "fonti", "note"],
        "properties": {
            "categoria": {"type": "string", "enum": ["singole", "suddivisioni"],
                          "description": "singole = un business principale; suddivisioni = più divisioni/segmenti "
                                         "rilevanti con economie diverse, conglomerati o holding."},
            "motivazione_categoria": {"type": "string"},
            "sintesi": {"type": "string", "description": "4-6 frasi in italiano: cosa fa, come guadagna, situazione attuale."},
            "catalizzatori": {"type": "array", "items": {"type": "string"}, "description": "3-5 possibili driver positivi"},
            "rischi": {"type": "array", "items": {"type": "string"}, "description": "3-5 rischi principali"},
            "periodo": {"type": "string", "description": "Periodo dei dati per segmento, es. 'FY2025 (chiuso 31/12/2025)'"},
            "valuta": {"type": "string", "description": "Valuta di bilancio, codice ISO (USD, EUR, CNY...)"},
            "misura_utile": {"type": "string", "description": "Misura di utile per segmento usata, es. 'Utile operativo', 'Adjusted EBITA'"},
            "segmenti": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["nome", "descrizione", "ricavi", "utile", "crescita_ricavi_pct", "metodo", "multiplo"],
                    "properties": {
                        "nome": {"type": "string"},
                        "descrizione": {"type": "string"},
                        "ricavi": {**NULL_NUM, "description": "Milioni nella valuta di bilancio"},
                        "utile": {**NULL_NUM, "description": "Milioni nella valuta di bilancio (negativo se in perdita)"},
                        "crescita_ricavi_pct": {**NULL_NUM, "description": "Crescita annua dei ricavi in %, es. 12.5"},
                        "metodo": {"type": "string", "enum": ["EV/EBIT", "EV/Sales"]},
                        "multiplo": {"type": "number", "description": "Multiplo ragionevole basato su concorrenti comparabili"},
                    },
                },
            },
            "partecipazioni": {
                "type": "array",
                "description": "Partecipazioni rilevanti in altre società (soprattutto per holding). Vuoto se non rilevanti.",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["nome", "ticker_yahoo", "quota_pct", "valore_mln", "note"],
                    "properties": {
                        "nome": {"type": "string"},
                        "ticker_yahoo": {**NULL_STR, "description": "Ticker Yahoo Finance se quotata (es. 'RACE', 'STLAM.MI'), altrimenti null"},
                        "quota_pct": {**NULL_NUM, "description": "Percentuale posseduta, es. 24.5"},
                        "valore_mln": {**NULL_NUM, "description": "Valore stimato in milioni nella valuta di bilancio, se non quotata"},
                        "note": {"type": "string"},
                    },
                },
            },
            "fonti": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False, "required": ["titolo", "url"],
                          "properties": {"titolo": {"type": "string"}, "url": {"type": "string"}}},
            },
            "note": {"type": "string", "description": "Avvertenze sui dati (stime, dati ricavati per differenza, ecc.)"},
        },
    },
}

SYSTEM = """Sei un analista finanziario. Ricevi un titolo azionario e devi raccogliere dal web i dati
necessari per valutarlo, in particolare quelli che Yahoo Finance non fornisce.

Procedura:
1. Cerca l'ultimo bilancio annuale (o i risultati annuali più recenti) dalle fonti ufficiali:
   investor relations della società, comunicati stampa sui risultati, SEC (10-K/20-F), relazioni annuali.
2. Estrai i ricavi e l'utile operativo (o la misura usata dalla società) per ogni segmento riportato.
   Usa esattamente i segmenti come li riporta la società, in milioni nella valuta di bilancio.
3. Per le holding o le società con partecipazioni importanti, elenca le partecipazioni con quota posseduta
   e ticker Yahoo Finance, se quotate.
4. Decidi la categoria: "suddivisioni" se ci sono più divisioni con economie molto diverse (es. Amazon:
   e-commerce + cloud) o se è una holding; altrimenti "singole".
5. Per ogni segmento suggerisci un multiplo ragionevole basato su concorrenti comparabili: EV/EBIT per
   segmenti in utile e maturi, EV/Sales per segmenti in perdita o in forte crescita.

Regole:
- Usa solo numeri trovati nelle fonti. Se un dato non c'è, metti null: non inventare.
- Se ricavi un numero per differenza o lo stimi, scrivilo in "note".
- Scrivi tutti i testi in italiano.
- Quando hai finito, chiama lo strumento salva_ricerca una sola volta."""


def api_key():
    try:
        return st.secrets.get("anthropic_api_key")
    except Exception:
        return None


def load(ticker):
    path = RESEARCH_DIR / f"{ticker}.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save(ticker, result):
    content = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    RESEARCH_DIR.mkdir(exist_ok=True)
    (RESEARCH_DIR / f"{ticker}.json").write_text(content)
    return data.github_put(f"research/{ticker}.json", content, f"Ricerca Claude: {ticker}")


def run(ticker, company, info, progress=None):
    """Esegue la ricerca con web search e restituisce il dizionario dei risultati."""
    client = anthropic.Anthropic(api_key=api_key())
    context = {k: info.get(k) for k in ("longName", "sector", "industry", "country", "exchange",
                                        "financialCurrency", "website") if info.get(k)}
    user = (f"Data di oggi: {date.today().isoformat()}.\nTitolo: {ticker} ({company}).\n"
            f"Dati di contesto da Yahoo Finance: {json.dumps(context, ensure_ascii=False)}")
    messages = [{"role": "user", "content": user}]
    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5},
        SUBMIT_TOOL,
    ]

    for _ in range(MAX_ROUNDS):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=messages,
            tools=tools,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if progress:
            searches = [b for b in response.content if b.type == "server_tool_use"]
            for b in searches:
                q = (b.input or {}).get("query") or (b.input or {}).get("url")
                if q:
                    progress(q)

        submit = next((b for b in response.content if b.type == "tool_use" and b.name == "salva_ricerca"), None)
        if submit:
            result = dict(submit.input)
            result.update({"ticker": ticker, "data_ricerca": date.today().isoformat(), "modello": MODEL})
            return result
        if response.stop_reason == "refusal":
            raise RuntimeError("La richiesta è stata rifiutata dal modello.")
        if response.stop_reason in ("pause_turn", "end_turn", "max_tokens"):
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "pause_turn":
                messages.append({"role": "user", "content": "Ora chiama salva_ricerca con i dati raccolti."})
            continue
        raise RuntimeError(f"Risposta inattesa (stop_reason={response.stop_reason}).")
    raise RuntimeError("La ricerca non si è conclusa: troppi passaggi.")


def is_stale(result, days=90):
    try:
        return (date.today() - date.fromisoformat(result["data_ricerca"])).days > days
    except Exception:
        return True
