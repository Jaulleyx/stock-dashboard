# Stock Dashboard

Inserisci il nome o il ticker di un titolo e visualizza i dati utili per valutarne l'acquisto.

## Avvio

```bash
pip install -r requirements.txt
streamlit run app.py
```

Si apre su http://localhost:8501.

## Cosa mostra

- **Header**: prezzo e variazione, capitalizzazione, min/max 52 settimane, target e consenso analisti
- **Grafico** prezzo con medie mobili 50/200 e performance 1M / 3M / YTD / 1A / 3A / 5A
- **Valutazione**: P/E, PEG, P/S, P/B, EV/EBITDA, FCF yield, EPS
- **Redditività & crescita**: margini, ROE, ROA, crescita ricavi/utili
- **Solidità finanziaria**: cassa, debito, debito netto, D/E, current/quick ratio, free cash flow
- **Dividendi**: rendimento, payout, storico annuo
- **Tecnica & rischio**: beta, volatilità, RSI, distanza dai massimi, max drawdown
- **Bilanci storici**: ricavi, utile, FCF, debito degli ultimi anni
- **Scorecard**: 10 controlli rapidi pass/fail (soglie modificabili in `scorecard()`)

Ticker italiani: aggiungi `.MI` (es. `ENI.MI`, `RACE.MI`). Puoi anche scrivere il nome ("Ferrari").

Dati da Yahoo Finance tramite `yfinance`: gratuiti, senza API key, ma non ufficiali e talvolta incompleti.
