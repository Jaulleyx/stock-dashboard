"""Stock Dashboard — inserisci il nome o il ticker di un titolo e visualizza
i dati principali per valutarne l'acquisto. Dati da Yahoo Finance (yfinance)."""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Stock Dashboard", page_icon="📈", layout="wide")


# ---------------------------------------------------------------- helpers

def is_num(v):
    return isinstance(v, (int, float, np.number)) and not (isinstance(v, float) and math.isnan(v))


def fmt_num(v, dec=2):
    return f"{v:,.{dec}f}" if is_num(v) else "—"


def fmt_pct(v, dec=1, already_pct=False):
    if not is_num(v):
        return "—"
    return f"{v if already_pct else v * 100:.{dec}f}%"


def fmt_big(v, cur=""):
    if not is_num(v):
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= div:
            return f"{sign}{v / div:.2f}{unit} {cur}".strip()
    return f"{sign}{v:.0f} {cur}".strip()


def get_row(df, *names):
    """Prima riga trovata in un DataFrame di bilancio (le etichette cambiano tra aziende)."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


# ---------------------------------------------------------------- data

@st.cache_data(ttl=3600, show_spinner=False)
def search_symbol(query):
    """Accetta un ticker (AAPL, ENI.MI) o un nome (Apple, Ferrari)."""
    try:
        quotes = yf.Search(query, max_results=8).quotes
        return [
            (q["symbol"], q.get("shortname") or q.get("longname") or q["symbol"], q.get("exchange", ""))
            for q in quotes if q.get("quoteType") in ("EQUITY", "ETF")
        ]
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def load(symbol):
    t = yf.Ticker(symbol)
    info = t.info or {}
    hist = t.history(period="5y", auto_adjust=True)
    try:
        fin, bs, cf = t.financials, t.balance_sheet, t.cashflow
    except Exception:
        fin = bs = cf = pd.DataFrame()
    try:
        divs = t.dividends
    except Exception:
        divs = pd.Series(dtype=float)
    return info, hist, fin, bs, cf, divs


# ---------------------------------------------------------------- scorecard

def scorecard(info, tech):
    """Controlli euristici semplici. Non è un consiglio d'investimento."""
    checks = []

    def add(name, ok, detail):
        if ok is not None:
            checks.append((name, ok, detail))

    pe = info.get("trailingPE")
    add("P/E ragionevole (< 25)", pe < 25 if is_num(pe) and pe > 0 else None, fmt_num(pe))
    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    add("PEG < 1.5", peg < 1.5 if is_num(peg) and peg > 0 else None, fmt_num(peg))
    roe = info.get("returnOnEquity")
    add("ROE > 15%", roe > 0.15 if is_num(roe) else None, fmt_pct(roe))
    pm = info.get("profitMargins")
    add("Margine netto > 10%", pm > 0.10 if is_num(pm) else None, fmt_pct(pm))
    rg = info.get("revenueGrowth")
    add("Ricavi in crescita", rg > 0 if is_num(rg) else None, fmt_pct(rg))
    de = info.get("debtToEquity")
    add("Debito/Equity < 100%", de < 100 if is_num(de) else None, fmt_num(de))
    cr = info.get("currentRatio")
    add("Current ratio > 1", cr > 1 if is_num(cr) else None, fmt_num(cr))
    fcf = info.get("freeCashflow")
    add("Free cash flow positivo", fcf > 0 if is_num(fcf) else None, fmt_big(fcf))
    up = tech.get("upside")
    add("Upside target analisti > 10%", up > 0.10 if is_num(up) else None, fmt_pct(up))
    add("Prezzo sopra MA200", tech["price"] > tech["ma200"] if is_num(tech.get("ma200")) else None,
        f"MA200 {fmt_num(tech.get('ma200'))}")
    return checks


# ---------------------------------------------------------------- UI

st.title("📈 Stock Dashboard")
st.caption("Inserisci un ticker (es. `AAPL`, `ENI.MI`, `RACE`) o il nome di un'azienda.")

query = st.text_input("Titolo", value=st.session_state.get("last_query", "AAPL"))
if not query.strip():
    st.stop()
st.session_state["last_query"] = query

matches = search_symbol(query.strip())
if matches:
    labels = [f"{s} — {n} ({e})" for s, n, e in matches]
    symbol = matches[labels.index(st.selectbox("Risultati", labels))][0] if len(matches) > 1 else matches[0][0]
else:
    symbol = query.strip().upper()

with st.spinner(f"Carico i dati di {symbol}…"):
    try:
        info, hist, fin, bs, cf, divs = load(symbol)
    except Exception as e:
        st.error(f"Errore nel recupero dati per {symbol}: {e}")
        st.stop()

if hist.empty:
    st.error(f"Nessun dato trovato per **{symbol}**. Controlla il ticker (per Borsa Italiana aggiungi `.MI`).")
    st.stop()

cur = info.get("currency", "")
close = hist["Close"]
price = info.get("currentPrice") or info.get("regularMarketPrice") or float(close.iloc[-1])
prev = info.get("previousClose") or (float(close.iloc[-2]) if len(close) > 1 else price)

# indicatori tecnici
ma50 = close.rolling(50).mean()
ma200 = close.rolling(200).mean()
returns = close.pct_change().dropna()
target = info.get("targetMeanPrice")
tech = {
    "price": price,
    "ma50": float(ma50.iloc[-1]) if len(close) >= 50 else None,
    "ma200": float(ma200.iloc[-1]) if len(close) >= 200 else None,
    "rsi": float(rsi(close).iloc[-1]) if len(close) > 15 else None,
    "vol": float(returns[-252:].std() * np.sqrt(252)) if len(returns) > 20 else None,
    "upside": target / price - 1 if is_num(target) and price else None,
}


def perf(days):
    return float(close.iloc[-1] / close.iloc[-days - 1] - 1) if len(close) > days else None


ytd = close[close.index.year == close.index[-1].year]
perfs = {"1M": perf(21), "3M": perf(63), "YTD": float(close.iloc[-1] / ytd.iloc[0] - 1) if len(ytd) else None,
         "1A": perf(252), "3A": perf(756), "5A": perf(len(close) - 2)}

# ---- header
st.header(f"{info.get('longName') or info.get('shortName') or symbol}  ·  {symbol}")
st.caption(" · ".join(x for x in (info.get("sector"), info.get("industry"), info.get("country"),
                                   info.get("exchange")) if x))

c = st.columns(5)
c[0].metric("Prezzo", f"{fmt_num(price)} {cur}", fmt_pct(price / prev - 1, 2) if prev else None)
c[1].metric("Capitalizzazione", fmt_big(info.get("marketCap"), cur))
c[2].metric("Min/Max 52 sett.", f"{fmt_num(info.get('fiftyTwoWeekLow'))} / {fmt_num(info.get('fiftyTwoWeekHigh'))}")
c[3].metric("Target medio analisti", f"{fmt_num(target)} {cur}" if is_num(target) else "—",
            fmt_pct(tech["upside"]) if is_num(tech["upside"]) else None)
rec = info.get("recommendationKey")
c[4].metric("Consenso", rec.replace("_", " ").title() if rec else "—",
            f"{info.get('numberOfAnalystOpinions')} analisti" if info.get("numberOfAnalystOpinions") else None,
            delta_color="off")

# ---- grafico prezzo
period = st.radio("Periodo", ["1M", "6M", "1A", "3A", "5A"], index=2, horizontal=True)
days = {"1M": 31, "6M": 183, "1A": 365, "3A": 1095, "5A": 1830}[period]
since = close.index[-1] - pd.Timedelta(days=days)
fig = go.Figure()
fig.add_trace(go.Scatter(x=close[since:].index, y=close[since:], name="Prezzo", line=dict(width=2)))
fig.add_trace(go.Scatter(x=ma50[since:].index, y=ma50[since:], name="MA50", line=dict(width=1, dash="dot")))
fig.add_trace(go.Scatter(x=ma200[since:].index, y=ma200[since:], name="MA200", line=dict(width=1, dash="dash")))
fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified",
                  legend=dict(orientation="h", y=1.05), yaxis_title=cur)
st.plotly_chart(fig, width="stretch")

st.markdown("**Performance:** " + "  ·  ".join(f"{k} **{fmt_pct(v)}**" for k, v in perfs.items()))

# ---- tabelle metriche
tab_val, tab_prof, tab_health, tab_div, tab_tech, tab_fin, tab_score, tab_info = st.tabs(
    ["Valutazione", "Redditività & crescita", "Solidità finanziaria", "Dividendi",
     "Tecnica & rischio", "Bilanci storici", "Scorecard", "Profilo"])


def table(rows):
    st.dataframe(pd.DataFrame(rows, columns=["Indicatore", "Valore", "Cosa indica"]),
                 hide_index=True, width="stretch")


fcf = info.get("freeCashflow")
mcap = info.get("marketCap")

with tab_val:
    table([
        ("P/E (trailing)", fmt_num(info.get("trailingPE")), "Prezzo / utile ultimi 12 mesi"),
        ("P/E (forward)", fmt_num(info.get("forwardPE")), "Prezzo / utile atteso"),
        ("PEG", fmt_num(info.get("trailingPegRatio") or info.get("pegRatio")), "P/E corretto per la crescita (<1 = economico)"),
        ("Prezzo / Vendite", fmt_num(info.get("priceToSalesTrailing12Months")), "Capitalizzazione / ricavi"),
        ("Prezzo / Valore contabile", fmt_num(info.get("priceToBook")), "Prezzo / patrimonio netto per azione"),
        ("EV / EBITDA", fmt_num(info.get("enterpriseToEbitda")), "Valore d'impresa / margine operativo lordo"),
        ("EV / Ricavi", fmt_num(info.get("enterpriseToRevenue")), ""),
        ("FCF yield", fmt_pct(fcf / mcap) if is_num(fcf) and is_num(mcap) and mcap else "—", "Free cash flow / capitalizzazione"),
        ("EPS (trailing)", fmt_num(info.get("trailingEps")), "Utile per azione"),
        ("EPS (forward)", fmt_num(info.get("forwardEps")), "Utile per azione atteso"),
        ("Enterprise value", fmt_big(info.get("enterpriseValue"), cur), ""),
    ])

with tab_prof:
    table([
        ("Margine lordo", fmt_pct(info.get("grossMargins")), ""),
        ("Margine operativo", fmt_pct(info.get("operatingMargins")), ""),
        ("Margine EBITDA", fmt_pct(info.get("ebitdaMargins")), ""),
        ("Margine netto", fmt_pct(info.get("profitMargins")), ""),
        ("ROE", fmt_pct(info.get("returnOnEquity")), "Rendimento sul capitale proprio"),
        ("ROA", fmt_pct(info.get("returnOnAssets")), "Rendimento sugli attivi"),
        ("Crescita ricavi (YoY)", fmt_pct(info.get("revenueGrowth")), "Ultimo trimestre vs anno prima"),
        ("Crescita utili (YoY)", fmt_pct(info.get("earningsGrowth")), "Ultimo trimestre vs anno prima"),
        ("Ricavi (12 mesi)", fmt_big(info.get("totalRevenue"), cur), ""),
        ("EBITDA", fmt_big(info.get("ebitda"), cur), ""),
        ("Utile netto", fmt_big(info.get("netIncomeToCommon"), cur), ""),
    ])

with tab_health:
    table([
        ("Liquidità totale", fmt_big(info.get("totalCash"), cur), ""),
        ("Debito totale", fmt_big(info.get("totalDebt"), cur), ""),
        ("Debito netto", fmt_big(info["totalDebt"] - info["totalCash"], cur)
         if is_num(info.get("totalDebt")) and is_num(info.get("totalCash")) else "—", "Debito − liquidità"),
        ("Debito / Equity", fmt_num(info.get("debtToEquity")), "In %, sotto 100 è prudente"),
        ("Current ratio", fmt_num(info.get("currentRatio")), "Attività / passività correnti (>1 ok)"),
        ("Quick ratio", fmt_num(info.get("quickRatio")), "Come sopra senza magazzino"),
        ("Free cash flow", fmt_big(fcf, cur), "Cassa generata dopo gli investimenti"),
        ("Cash flow operativo", fmt_big(info.get("operatingCashflow"), cur), ""),
    ])

with tab_div:
    dy = info.get("dividendYield")
    table([
        ("Rendimento dividendo", fmt_pct(dy, 2, already_pct=is_num(dy) and dy > 0.5), ""),
        ("Dividendo annuo", fmt_num(info.get("dividendRate")), cur),
        ("Payout ratio", fmt_pct(info.get("payoutRatio")), "Quota di utili distribuita (<70% sostenibile)"),
        ("Rendimento medio 5 anni", fmt_pct(info.get("fiveYearAvgDividendYield"), 2, already_pct=True), ""),
    ])
    if divs is not None and len(divs):
        yearly = divs.groupby(divs.index.year).sum().tail(15)
        if yearly.index[-1] == pd.Timestamp.now().year:
            yearly = yearly.iloc[:-1]  # anno in corso incompleto
        st.bar_chart(yearly, height=260)
        st.caption("Dividendi per azione per anno")
    else:
        st.info("Questo titolo non distribuisce dividendi.")

with tab_tech:
    table([
        ("Beta", fmt_num(info.get("beta")), ">1 più volatile del mercato"),
        ("Volatilità annua", fmt_pct(tech["vol"]), "Deviazione std rendimenti giornalieri × √252"),
        ("RSI (14)", fmt_num(tech["rsi"], 1), ">70 ipercomprato, <30 ipervenduto"),
        ("Media mobile 50 gg", fmt_num(tech["ma50"]), "Sopra" if is_num(tech["ma50"]) and price > tech["ma50"] else "Sotto"),
        ("Media mobile 200 gg", fmt_num(tech["ma200"]), "Sopra" if is_num(tech["ma200"]) and price > tech["ma200"] else "Sotto"),
        ("Distanza dal max 52 sett.", fmt_pct(price / info["fiftyTwoWeekHigh"] - 1)
         if is_num(info.get("fiftyTwoWeekHigh")) else "—", ""),
        ("Max drawdown 5 anni", fmt_pct(float((close / close.cummax() - 1).min())), "Peggior calo dal massimo"),
        ("Short % del flottante", fmt_pct(info.get("shortPercentOfFloat")), ""),
        ("Volume medio", fmt_big(info.get("averageVolume")), ""),
    ])

with tab_fin:
    rev = get_row(fin, "Total Revenue", "Operating Revenue")
    ni = get_row(fin, "Net Income", "Net Income Common Stockholders")
    fcf_hist = get_row(cf, "Free Cash Flow")
    debt_hist = get_row(bs, "Total Debt")
    series = {k: v for k, v in {"Ricavi": rev, "Utile netto": ni, "Free cash flow": fcf_hist,
                                "Debito totale": debt_hist}.items() if v is not None}
    if series:
        df = pd.DataFrame(series).sort_index()
        df.index = df.index.year
        fig2 = go.Figure([go.Bar(x=df.index, y=df[col], name=col) for col in df.columns])
        fig2.update_layout(barmode="group", height=380, margin=dict(l=0, r=0, t=10, b=0),
                           legend=dict(orientation="h", y=1.08), yaxis_title=cur)
        st.plotly_chart(fig2, width="stretch")
        st.dataframe(df.T.map(lambda v: fmt_big(v)), width="stretch")
    else:
        st.info("Bilanci storici non disponibili per questo titolo.")

with tab_score:
    checks = scorecard(info, tech)
    if checks:
        passed = sum(ok for _, ok, _ in checks)
        st.subheader(f"{passed} / {len(checks)} controlli superati")
        st.progress(passed / len(checks))
        for name, ok, detail in checks:
            st.markdown(f"{'✅' if ok else '❌'} **{name}** — {detail}")
    st.caption("Controlli euristici generici: soglie indicative, da adattare al settore. Non è un consiglio d'investimento.")

with tab_info:
    if info.get("website"):
        st.markdown(f"🌐 [{info['website']}]({info['website']})")
    if info.get("fullTimeEmployees"):
        st.markdown(f"👥 Dipendenti: **{info['fullTimeEmployees']:,}**")
    st.write(info.get("longBusinessSummary", "Descrizione non disponibile."))

st.divider()
st.caption("Dati: Yahoo Finance tramite yfinance (possono avere ritardi o lacune). Solo a scopo informativo.")
