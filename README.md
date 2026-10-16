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

## Ricerca automatica con Claude

Quando si apre un titolo senza dati, il sito lo mette in coda creando `requests/<TICKER>.json` nel repository.
Un'attività pianificata di Claude (lun–ven, ogni ora dalle 8 alle 23, ora italiana) legge la coda, cerca sul web
segmenti, partecipazioni, categoria, sintesi e rischi seguendo `RESEARCH_SPEC.md`, e salva il risultato in
`research/<TICKER>.json`. I dati sono condivisi da tutti gli utenti del sito. Usa l'abbonamento Claude: nessuna
chiave API a pagamento.

Configurazione (Streamlit Cloud -> App settings -> Secrets), vedi `.streamlit/secrets.toml.example`:
- `github_token`: token GitHub con permesso Contents read/write, per la coda, le ricerche e i preferiti
