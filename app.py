"""Stock Dashboard — lista dei preferiti e scheda di analisi per ogni titolo.
Dati da Yahoo Finance (yfinance) e Google News."""

import math
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data

st.set_page_config(page_title="Stock Dashboard", page_icon="📈", layout="wide")


# ---------------------------------------------------------------- formattazione

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


def table(rows):
    st.dataframe(pd.DataFrame(rows, columns=["Indicatore", "Valore", "Cosa indica"]), hide_index=True, width="stretch")


def get_row(df, *names):
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


def clean_company_name(name):
    """'Amazon.com, Inc.' -> 'Amazon', utile per cercare notizie."""
    name = re.sub(r"\b(Holding|Holdings|Group|Inc|Corp|Corporation|Ltd|Limited|plc|S\.p\.A|SpA|N\.V|AG|SE|Co)\b\.?",
                  "", name or "", flags=re.I)
    return re.sub(r"\.com\b|[,.]+\s*$", "", name).strip(" ,.") or name


def open_stock(ticker):
    st.query_params["t"] = ticker


def go_home():
    st.query_params.clear()


# ---------------------------------------------------------------- pagina preferiti

def add_favorite_form(favs, key, preset=None):
    """Form per aggiungere un titolo ai preferiti scegliendo la categoria."""
    if preset:
        symbol, name = preset
    else:
        q = st.text_input("Cerca per nome o ticker", key=f"{key}_q", placeholder="es. Ferrari, NVDA, ENI.MI")
        if not q.strip():
            return
        matches = data.search_symbol(q.strip()) or [(q.strip().upper(), q.strip().upper(), "")]
        labels = [f"{s} — {n} ({e})" if e else f"{s} — {n}" for s, n, e in matches]
        symbol, name, _ = matches[labels.index(st.selectbox("Risultati", labels, key=f"{key}_sel"))]
    cat = st.radio("Categoria", list(data.CATEGORIES), format_func=data.CATEGORIES.get,
                   horizontal=True, key=f"{key}_cat")
    if st.button("Aggiungi ai preferiti", key=f"{key}_btn", type="primary"):
        if data.find_favorite(favs, symbol):
            st.warning(f"{symbol} è già nei preferiti.")
            return
        favs[cat].append({"ticker": symbol, "nome": clean_company_name(name)})
        persisted = data.save_favorites(favs)
        st.toast(f"{symbol} aggiunto" + ("" if persisted else " (salvataggio solo temporaneo)"))
        st.rerun()


def favorites_table(cat, items, quotes):
    if not items:
        st.caption("Nessun titolo in questa categoria. Aggiungine uno qui sotto.")
        return
    rows = []
    for it in items:
        q = quotes.get(it["ticker"]) or {}
        rows.append({"Nome": it["nome"], "Ticker": it["ticker"], "Prezzo": q.get("price"),
                     "Oggi": q.get("day", np.nan) * 100 if q else np.nan,
                     "3 mesi": q.get("3m", np.nan) * 100 if q else np.nan,
                     "Andamento 3 mesi": q.get("trend", [])})
    event = st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun",
        selection_mode="single-row", key=f"tbl_{cat}",
        column_config={
            "Prezzo": st.column_config.NumberColumn(format="%.2f"),
            "Oggi": st.column_config.NumberColumn(format="%+.2f%%"),
            "3 mesi": st.column_config.NumberColumn(format="%+.1f%%"),
            "Andamento 3 mesi": st.column_config.LineChartColumn(),
        })
    if event.selection.rows:
        open_stock(rows[event.selection.rows[0]]["Ticker"])
        st.rerun()


def home_page():
    st.title("📈 I miei titoli")
    favs = data.load_favorites()

    q = st.text_input("🔎 Apri un titolo", placeholder="Nome o ticker, es. Apple, RACE, ENI.MI")
    if q.strip():
        matches = data.search_symbol(q.strip())
        if matches:
            labels = [f"{s} — {n} ({e})" for s, n, e in matches]
            pick = st.selectbox("Risultati", labels)
            if st.button("Apri scheda", type="primary"):
                open_stock(matches[labels.index(pick)][0])
                st.rerun()
        elif st.button(f"Apri {q.strip().upper()}", type="primary"):
            open_stock(q.strip().upper())
            st.rerun()

    all_tickers = tuple(i["ticker"] for items in favs.values() for i in items)
    with st.spinner("Aggiorno le quotazioni…"):
        quotes = data.quotes_overview(all_tickers)

    st.caption("Clicca su una riga per aprire la scheda del titolo.")
    for cat, label in data.CATEGORIES.items():
        st.subheader(label)
        favorites_table(cat, favs[cat], quotes)

    with st.expander("➕ Aggiungi ai preferiti"):
        add_favorite_form(favs, "home")


# ---------------------------------------------------------------- scheda titolo: sezioni comuni

def price_chart(close, cur):
    ma50, ma200 = close.rolling(50).mean(), close.rolling(200).mean()
    period = st.radio("Periodo", ["1M", "6M", "1A", "3A", "5A"], index=2, horizontal=True, label_visibility="collapsed")
    since = close.index[-1] - pd.Timedelta(days={"1M": 31, "6M": 183, "1A": 365, "3A": 1095, "5A": 1830}[period])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=close[since:].index, y=close[since:], name="Prezzo", line=dict(width=2)))
    fig.add_trace(go.Scatter(x=ma50[since:].index, y=ma50[since:], name="MA50", line=dict(width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=ma200[since:].index, y=ma200[since:], name="MA200", line=dict(width=1, dash="dash")))
    fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified",
                      legend=dict(orientation="h", y=1.05), yaxis_title=cur)
    st.plotly_chart(fig, width="stretch")


def analysts_section(d, price, cur):
    info = d["info"]
    big = data.big_firm_targets(d["upgrades"])
    big_t = big["Target"].dropna() if not big.empty else pd.Series(dtype=float)
    big_s = big["Punteggio"].dropna() if not big.empty else pd.Series(dtype=float)
    mean_t = info.get("targetMeanPrice")

    st.markdown("##### Media delle grandi banche d'affari (ultimi 12 mesi)")
    c = st.columns(4)
    if len(big_t):
        c[0].metric("Target medio", f"{big_t.mean():,.2f} {cur}", fmt_pct(big_t.mean() / price - 1))
        c[1].metric("Range target", f"{big_t.min():,.0f} – {big_t.max():,.0f}")
    else:
        c[0].metric("Target medio", "—")
        c[1].metric("Range target", "—")
    c[2].metric("Giudizio medio", data.score_label(big_s.mean()) if len(big_s) else "—",
                f"{big_s.mean():.1f} / 5" if len(big_s) else None, delta_color="off")
    c[3].metric("Banche considerate", len(big))

    if not big.empty:
        show = big.copy()
        show["Upside"] = (show["Target"] / price - 1) * 100
        st.dataframe(show.drop(columns="Punteggio"), hide_index=True, width="stretch", column_config={
            "Target": st.column_config.NumberColumn(format="%.2f"),
            "Upside": st.column_config.NumberColumn(format="%+.1f%%")})
    else:
        st.caption("Nessun giudizio recente delle grandi banche disponibile per questo titolo.")

    st.markdown("##### Consenso di tutti gli analisti")
    c = st.columns(4)
    c[0].metric("Target medio", f"{fmt_num(mean_t)} {cur}" if is_num(mean_t) else "—",
                fmt_pct(mean_t / price - 1) if is_num(mean_t) else None)
    c[1].metric("Target min / max", f"{fmt_num(info.get('targetLowPrice'), 0)} – {fmt_num(info.get('targetHighPrice'), 0)}")
    rec = info.get("recommendationKey")
    c[2].metric("Consenso", rec.replace("_", " ").title() if rec and rec != "none" else "—")
    c[3].metric("N. analisti", info.get("numberOfAnalystOpinions") or "—")

    recs = d["recs"]
    if recs is not None and not recs.empty and "period" in recs.columns:
        now = recs[recs["period"] == "0m"]
        if not now.empty:
            r = now.iloc[0]
            cols = {"Strong Buy": "strongBuy", "Buy": "buy", "Hold": "hold", "Sell": "sell", "Strong Sell": "strongSell"}
            fig = go.Figure(go.Bar(x=[int(r.get(v, 0)) for v in cols.values()], y=list(cols), orientation="h",
                                   marker_color=["#1a7f37", "#4caf50", "#9e9e9e", "#e57373", "#c62828"]))
            fig.update_layout(height=200, margin=dict(l=0, r=0, t=0, b=0), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, width="stretch")

    st.markdown("##### Stime su utili e ricavi")
    rows = []
    labels = {"0y": "Anno in corso", "+1y": "Prossimo anno", "0q": "Trimestre in corso", "+1q": "Prossimo trimestre"}
    for est, name in ((d["eps_est"], "EPS"), (d["rev_est"], "Ricavi")):
        if est is None or est.empty:
            continue
        for p in ("0q", "0y", "+1y"):
            if p in est.index:
                r = est.loc[p]
                fmt = (lambda v: fmt_num(v)) if name == "EPS" else (lambda v: fmt_big(v))
                rows.append({"Stima": f"{name} — {labels[p]}", "Media": fmt(r.get("avg")),
                             "Min": fmt(r.get("low")), "Max": fmt(r.get("high")),
                             "Crescita attesa": fmt_pct(r.get("growth")), "Analisti": r.get("numberOfAnalysts")})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("Stime non disponibili.")


def news_section(d, company):
    news = data.all_news(d["yf_news"], company)
    if not news:
        st.info("Nessuna notizia trovata.")
        return
    for n in news:
        when = n["data"].tz_convert("Europe/Rome").strftime("%d/%m/%Y %H:%M") if n["data"] is not None else ""
        st.markdown(f"**[{n['titolo']}]({n['url']})**  \n"
                    f"<small>{n['fonte']} · {when}</small>", unsafe_allow_html=True)
        if n["riassunto"]:
            st.caption(n["riassunto"][:280])


def risk_section(info, close, price):
    returns = close.pct_change().dropna()
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
    table([
        ("Beta", fmt_num(info.get("beta")), ">1 più volatile del mercato"),
        ("Volatilità annua", fmt_pct(float(returns[-252:].std() * np.sqrt(252))), ""),
        ("RSI (14)", fmt_num(float(rsi(close).iloc[-1]), 1), ">70 ipercomprato, <30 ipervenduto"),
        ("Media mobile 50 gg", fmt_num(ma50), "Prezzo sopra" if is_num(ma50) and price > ma50 else "Prezzo sotto"),
        ("Media mobile 200 gg", fmt_num(ma200), "Prezzo sopra" if is_num(ma200) and price > ma200 else "Prezzo sotto"),
        ("Distanza dal max 52 sett.", fmt_pct(price / info["fiftyTwoWeekHigh"] - 1)
         if is_num(info.get("fiftyTwoWeekHigh")) else "—", ""),
        ("Max drawdown 5 anni", fmt_pct(float((close / close.cummax() - 1).min())), "Peggior calo dal massimo"),
        ("Short % del flottante", fmt_pct(info.get("shortPercentOfFloat")), ""),
    ])


# ---------------------------------------------------------------- scheda titolo: azienda singola

def single_company_section(d, price, cur):
    info = d["info"]
    fcf, mcap = info.get("freeCashflow"), info.get("marketCap")
    t_val, t_prof, t_health, t_div, t_hist, t_score = st.tabs(
        ["Valutazione", "Redditività & crescita", "Solidità", "Dividendi", "Bilanci storici", "Scorecard"])
    with t_val:
        table([
            ("P/E (trailing)", fmt_num(info.get("trailingPE")), "Prezzo / utile ultimi 12 mesi"),
            ("P/E (forward)", fmt_num(info.get("forwardPE")), "Prezzo / utile atteso"),
            ("PEG", fmt_num(info.get("trailingPegRatio") or info.get("pegRatio")), "P/E corretto per la crescita (<1 economico)"),
            ("Prezzo / Vendite", fmt_num(info.get("priceToSalesTrailing12Months")), ""),
            ("Prezzo / Valore contabile", fmt_num(info.get("priceToBook")), ""),
            ("EV / EBITDA", fmt_num(info.get("enterpriseToEbitda")), ""),
            ("FCF yield", fmt_pct(fcf / mcap) if is_num(fcf) and is_num(mcap) and mcap else "—", "Free cash flow / capitalizzazione"),
            ("EPS (trailing / forward)", f"{fmt_num(info.get('trailingEps'))} / {fmt_num(info.get('forwardEps'))}", ""),
        ])
    with t_prof:
        table([
            ("Margine lordo", fmt_pct(info.get("grossMargins")), ""),
            ("Margine operativo", fmt_pct(info.get("operatingMargins")), ""),
            ("Margine netto", fmt_pct(info.get("profitMargins")), ""),
            ("ROE", fmt_pct(info.get("returnOnEquity")), "Rendimento sul capitale proprio"),
            ("ROA", fmt_pct(info.get("returnOnAssets")), "Rendimento sugli attivi"),
            ("Crescita ricavi (YoY)", fmt_pct(info.get("revenueGrowth")), ""),
            ("Crescita utili (YoY)", fmt_pct(info.get("earningsGrowth")), ""),
            ("Ricavi (12 mesi)", fmt_big(info.get("totalRevenue"), info.get("financialCurrency", cur)), ""),
        ])
    with t_health:
        fcur = info.get("financialCurrency", cur)
        table([
            ("Liquidità totale", fmt_big(info.get("totalCash"), fcur), ""),
            ("Debito totale", fmt_big(info.get("totalDebt"), fcur), ""),
            ("Debito / Equity", fmt_num(info.get("debtToEquity")), "In %, sotto 100 è prudente"),
            ("Current ratio", fmt_num(info.get("currentRatio")), "Attività / passività correnti (>1 ok)"),
            ("Free cash flow", fmt_big(fcf, fcur), ""),
        ])
    with t_div:
        dy = info.get("dividendYield")
        table([
            ("Rendimento dividendo", fmt_pct(dy, 2, already_pct=is_num(dy) and dy > 0.5), ""),
            ("Dividendo annuo", fmt_num(info.get("dividendRate")), cur),
            ("Payout ratio", fmt_pct(info.get("payoutRatio")), "Quota di utili distribuita (<70% sostenibile)"),
        ])
        divs = d["divs"]
        if divs is not None and len(divs):
            yearly = divs.groupby(divs.index.year).sum().tail(15)
            st.bar_chart(yearly[yearly.index < pd.Timestamp.now().year], height=240)
        else:
            st.info("Questo titolo non distribuisce dividendi.")
    with t_hist:
        historical_financials(d, info.get("financialCurrency", cur))
    with t_score:
        scorecard(info, price)


def historical_financials(d, cur):
    series = {k: v for k, v in {
        "Ricavi": get_row(d["fin"], "Total Revenue", "Operating Revenue"),
        "Utile netto": get_row(d["fin"], "Net Income", "Net Income Common Stockholders"),
        "Free cash flow": get_row(d["cf"], "Free Cash Flow"),
        "Debito totale": get_row(d["bs"], "Total Debt")}.items() if v is not None}
    if not series:
        st.info("Bilanci storici non disponibili.")
        return
    df = pd.DataFrame(series).sort_index()
    df.index = df.index.year
    fig = go.Figure([go.Bar(x=df.index, y=df[c], name=c) for c in df.columns])
    fig.update_layout(barmode="group", height=360, margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=1.08), yaxis_title=cur)
    st.plotly_chart(fig, width="stretch")


def scorecard(info, price):
    checks = []

    def add(name, value, ok):
        if ok is not None:
            checks.append((name, ok, value))

    pe, roe, pm, rg = info.get("trailingPE"), info.get("returnOnEquity"), info.get("profitMargins"), info.get("revenueGrowth")
    de, cr, fcf, tgt = info.get("debtToEquity"), info.get("currentRatio"), info.get("freeCashflow"), info.get("targetMeanPrice")
    add("P/E ragionevole (< 25)", fmt_num(pe), pe < 25 if is_num(pe) and pe > 0 else None)
    add("ROE > 15%", fmt_pct(roe), roe > 0.15 if is_num(roe) else None)
    add("Margine netto > 10%", fmt_pct(pm), pm > 0.10 if is_num(pm) else None)
    add("Ricavi in crescita", fmt_pct(rg), rg > 0 if is_num(rg) else None)
    add("Debito/Equity < 100%", fmt_num(de), de < 100 if is_num(de) else None)
    add("Current ratio > 1", fmt_num(cr), cr > 1 if is_num(cr) else None)
    add("Free cash flow positivo", fmt_big(fcf), fcf > 0 if is_num(fcf) else None)
    add("Upside analisti > 10%", fmt_pct(tgt / price - 1) if is_num(tgt) else "—", tgt / price > 1.1 if is_num(tgt) else None)
    if checks:
        passed = sum(ok for _, ok, _ in checks)
        st.subheader(f"{passed} / {len(checks)} controlli superati")
        st.progress(passed / len(checks))
        for name, ok, value in checks:
            st.markdown(f"{'✅' if ok else '❌'} **{name}** — {value}")
    st.caption("Soglie indicative, da adattare al settore. Non è un consiglio d'investimento.")


# ---------------------------------------------------------------- scheda titolo: azienda con suddivisioni

def conglomerate_section(d, symbol, price, cur):
    info = d["info"]
    seg = data.load_segments().get(symbol)
    t_seg, t_sotp, t_cons, t_hist = st.tabs(["Segmenti", "Somma delle parti", "Dati consolidati", "Bilanci storici"])

    with t_seg:
        if not seg:
            st.info(f"Dati per segmento non ancora presenti per {symbol}. Chiedi a Claude di aggiungerli "
                    "(file `segments.json`).")
        else:
            df = pd.DataFrame(seg["segmenti"])
            df["margine"] = df["utile"] / df["ricavi"]
            st.caption(f"{seg['periodo']} · valori in milioni {seg['valuta']} · fonte: {seg['fonte']}")
            c1, c2 = st.columns(2)
            pie = go.Figure(go.Pie(labels=df["nome"], values=df["ricavi"], hole=0.5, sort=False))
            pie.update_layout(height=320, margin=dict(l=0, r=0, t=30, b=0), title="Ricavi per segmento",
                              legend=dict(orientation="h"))
            c1.plotly_chart(pie, width="stretch")
            bar = go.Figure(go.Bar(x=df["nome"], y=df["utile"],
                                   marker_color=["#1a7f37" if v >= 0 else "#c62828" for v in df["utile"]]))
            bar.update_layout(height=320, margin=dict(l=0, r=0, t=30, b=0), title=seg["misura_utile"] + " per segmento")
            c2.plotly_chart(bar, width="stretch")
            tot_r, tot_u = df["ricavi"].sum(), df["utile"].sum()
            st.dataframe(pd.DataFrame({
                "Segmento": df["nome"], "Ricavi": df["ricavi"], "% ricavi": df["ricavi"] / tot_r * 100,
                seg["misura_utile"]: df["utile"], "% utile": df["utile"] / tot_u * 100, "Margine": df["margine"] * 100,
            }), hide_index=True, width="stretch", column_config={
                "Ricavi": st.column_config.NumberColumn(format="%,.0f"),
                seg["misura_utile"]: st.column_config.NumberColumn(format="%,.0f"),
                "% ricavi": st.column_config.NumberColumn(format="%.1f%%"),
                "% utile": st.column_config.NumberColumn(format="%.1f%%"),
                "Margine": st.column_config.NumberColumn(format="%.1f%%")})
            if seg.get("note"):
                st.caption(seg["note"])

    with t_sotp:
        if seg:
            sum_of_parts(seg, info, price, cur)
        else:
            st.info("Servono i dati per segmento per calcolare la somma delle parti.")

    with t_cons:
        fcur = info.get("financialCurrency", cur)
        net_debt = info["totalDebt"] - info["totalCash"] if is_num(info.get("totalDebt")) and is_num(info.get("totalCash")) else None
        fcf, mcap = info.get("freeCashflow"), info.get("marketCap")
        rate = data.fx_rate(fcur, cur)
        table([
            ("Capitalizzazione", fmt_big(mcap, cur), ""),
            ("Enterprise value", fmt_big(info.get("enterpriseValue"), cur), "Capitalizzazione + debito netto"),
            ("EV / EBITDA", fmt_num(info.get("enterpriseToEbitda")), "Multiplo più adatto ai gruppi diversificati"),
            ("EV / Ricavi", fmt_num(info.get("enterpriseToRevenue")), ""),
            ("P/E forward", fmt_num(info.get("forwardPE")), ""),
            ("FCF yield", fmt_pct(fcf * rate / mcap) if is_num(fcf) and is_num(mcap) and rate else "—", ""),
            ("Ricavi (12 mesi)", fmt_big(info.get("totalRevenue"), fcur), ""),
            ("Crescita ricavi (YoY)", fmt_pct(info.get("revenueGrowth")), ""),
            ("Margine operativo", fmt_pct(info.get("operatingMargins")), ""),
            ("Free cash flow", fmt_big(fcf, fcur), ""),
            ("Debito netto", fmt_big(net_debt, fcur), "Negativo = cassa netta"),
            ("ROE", fmt_pct(info.get("returnOnEquity")), ""),
        ])

    with t_hist:
        historical_financials(d, info.get("financialCurrency", cur))


def sum_of_parts(seg, info, price, cur):
    st.caption("Valuta ogni segmento con un multiplo, somma i valori e confronta con la capitalizzazione attuale. "
               "Modifica metodo e multipli nella tabella: il risultato si aggiorna.")
    df = pd.DataFrame(seg["segmenti"])[["nome", "ricavi", "utile", "metodo", "multiplo"]]
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["nome", "ricavi", "utile"], column_config={
        "nome": "Segmento",
        "ricavi": st.column_config.NumberColumn("Ricavi (mln)", format="%,.0f"),
        "utile": st.column_config.NumberColumn(f"{seg['misura_utile']} (mln)", format="%,.0f"),
        "metodo": st.column_config.SelectboxColumn("Metodo", options=["EV/EBIT", "EV/Sales"], required=True),
        "multiplo": st.column_config.NumberColumn("Multiplo", min_value=0.0, step=0.5, format="%.1fx"),
    }, key=f"sotp_{seg['periodo']}")
    edited["valore"] = np.where(edited["metodo"] == "EV/EBIT", edited["utile"], edited["ricavi"]) * edited["multiplo"]

    fcur = seg["valuta"]
    rate = data.fx_rate(fcur, cur)
    net_debt = (info["totalDebt"] - info["totalCash"]) / 1e6 if is_num(info.get("totalDebt")) and is_num(info.get("totalCash")) else 0.0
    c1, c2 = st.columns(2)
    nd = c1.number_input(f"Debito netto (mln {fcur}, negativo = cassa)", value=float(round(net_debt)), step=1000.0)
    inv = c2.number_input(f"Partecipazioni / investimenti non nei segmenti (mln {fcur})", value=0.0, step=1000.0)

    ev = edited["valore"].sum()
    equity = ev - nd + inv
    mcap = info.get("marketCap")
    if not rate or not is_num(mcap):
        st.warning("Impossibile confrontare con la capitalizzazione (manca cambio valuta o market cap).")
        return
    equity_q = equity * 1e6 * rate
    implied_price = price * equity_q / mcap
    c = st.columns(3)
    c[0].metric("Valore equity stimato", fmt_big(equity_q, cur))
    c[1].metric("Capitalizzazione attuale", fmt_big(mcap, cur))
    c[2].metric("Prezzo implicito", f"{implied_price:,.2f} {cur}", fmt_pct(implied_price / price - 1))
    fig = go.Figure(go.Waterfall(
        x=list(edited["nome"]) + ["Debito netto", "Partecipazioni", "Equity"],
        y=list(edited["valore"]) + [-nd, inv, 0],
        measure=["relative"] * (len(edited) + 2) + ["total"]))
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=f"mln {fcur}")
    st.plotly_chart(fig, width="stretch")
    st.caption("Stima indicativa: dipende interamente dai multipli scelti. Non è un consiglio d'investimento.")


# ---------------------------------------------------------------- scheda titolo

def stock_page(symbol):
    if st.button("← I miei titoli"):
        go_home()
        st.rerun()

    with st.spinner(f"Carico i dati di {symbol}…"):
        try:
            d = data.load_stock(symbol)
        except Exception as e:
            st.error(f"Errore nel recupero dati per {symbol}: {e}")
            return
    info, hist = d["info"], d["hist"]
    if hist.empty:
        st.error(f"Nessun dato trovato per **{symbol}**. Controlla il ticker (per Borsa Italiana aggiungi `.MI`).")
        return

    favs = data.load_favorites()
    fav_cat = data.find_favorite(favs, symbol)
    cur = info.get("currency", "")
    close = hist["Close"]
    price = info.get("currentPrice") or info.get("regularMarketPrice") or float(close.iloc[-1])
    prev = info.get("previousClose") or float(close.iloc[-2])
    long_name = info.get("longName") or info.get("shortName") or symbol

    st.title(f"{long_name} · {symbol}")
    st.caption(" · ".join(x for x in (info.get("sector"), info.get("industry"), info.get("country")) if x))

    c = st.columns(4)
    c[0].metric("Prezzo", f"{fmt_num(price)} {cur}", fmt_pct(price / prev - 1, 2))
    c[1].metric("Capitalizzazione", fmt_big(info.get("marketCap"), cur))
    c[2].metric("Min / Max 52 sett.", f"{fmt_num(info.get('fiftyTwoWeekLow'))} / {fmt_num(info.get('fiftyTwoWeekHigh'))}")
    tgt = info.get("targetMeanPrice")
    c[3].metric("Target medio analisti", f"{fmt_num(tgt)} {cur}" if is_num(tgt) else "—",
                fmt_pct(tgt / price - 1) if is_num(tgt) else None)

    price_chart(close, cur)

    default_cat = fav_cat or ("suddivisioni" if symbol in data.load_segments() else "singole")
    cat = st.radio("Tipo di analisi", list(data.CATEGORIES), format_func=data.CATEGORIES.get, horizontal=True,
                   index=list(data.CATEGORIES).index(default_cat))

    t_an, t_news, t_fund, t_risk, t_prof = st.tabs(
        ["🎯 Aspettative analisti", "📰 Notizie", "📊 Fondamentali", "⚠️ Rischio", "🏢 Profilo"])
    with t_an:
        analysts_section(d, price, cur)
    with t_news:
        news_section(d, clean_company_name(info.get("shortName") or long_name))
    with t_fund:
        if cat == "singole":
            single_company_section(d, price, cur)
        else:
            conglomerate_section(d, symbol, price, cur)
    with t_risk:
        risk_section(info, close, price)
    with t_prof:
        if info.get("website"):
            st.markdown(f"🌐 [{info['website']}]({info['website']})")
        st.write(info.get("longBusinessSummary", "Descrizione non disponibile."))

    st.divider()
    if fav_cat:
        c1, c2 = st.columns(2)
        if fav_cat != cat and c1.button(f"Sposta in «{data.CATEGORIES[cat]}»"):
            favs[fav_cat] = [i for i in favs[fav_cat] if i["ticker"] != symbol]
            favs[cat].append({"ticker": symbol, "nome": clean_company_name(info.get("shortName") or long_name)})
            data.save_favorites(favs)
            st.rerun()
        if c2.button("Rimuovi dai preferiti"):
            favs[fav_cat] = [i for i in favs[fav_cat] if i["ticker"] != symbol]
            data.save_favorites(favs)
            st.rerun()
    else:
        with st.expander("⭐ Aggiungi ai preferiti"):
            add_favorite_form(favs, "detail", preset=(symbol, info.get("shortName") or long_name))

    st.caption("Dati: Yahoo Finance e Google News. Possono avere ritardi o lacune. Solo a scopo informativo.")


# ---------------------------------------------------------------- router

ticker = st.query_params.get("t")
if ticker:
    stock_page(ticker.upper())
else:
    home_page()
