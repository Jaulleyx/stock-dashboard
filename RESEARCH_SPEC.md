# Istruzioni per la ricerca automatica

Queste istruzioni le segue l'attività pianificata di Claude (lun–ven, 8–23) che elabora la coda delle ricerche.

## Procedura

1. `git pull origin main`, poi elenca i file in `requests/`. **Se la cartella è vuota o non esiste, termina subito**
   senza fare altro.
2. Elabora al massimo **3 richieste** per esecuzione, dalla più vecchia (campo `richiesta`).
3. Per ogni richiesta `requests/<TICKER>.json`:
   1. Fai la ricerca descritta sotto e scrivi il risultato in `research/<TICKER>.json`.
   2. Esegui `python3 scripts/validate_research.py research/<TICKER>.json` e correggi finché non passa.
   3. Elimina `requests/<TICKER>.json`.
   4. Fai commit (`Ricerca Claude: <TICKER>`) e `git pull --rebase origin main && git push origin main`.
      Un commit per titolo, così il lavoro fatto non si perde se un titolo successivo fallisce.
4. Se per un titolo non trovi dati affidabili, salva comunque il file con quello che hai trovato
   (campi mancanti a `null`, liste vuote) e spiega il problema in `note`.

## Cosa cercare

Lo scopo è dare i dati che Yahoo Finance non fornisce, per valutare l'acquisto del titolo.

- **Fonti:** ultimi risultati annuali dalle fonti ufficiali: investor relations, comunicati sui risultati,
  SEC (10-K / 20-F), relazioni annuali. Usa la ricerca web; preferisci i comunicati ufficiali agli articoli.
- **Segmenti:** ricavi e utile operativo (o la misura usata dalla società, es. Adjusted EBITA) di ogni segmento,
  esattamente come li riporta la società, in **milioni nella valuta di bilancio**.
- **Partecipazioni:** per holding o società con partecipazioni importanti, elenca le partecipate con quota
  posseduta in % e ticker Yahoo Finance se quotate (es. `RACE`, `STLAM.MI`, `PHIA.AS`).
- **Categoria:** `suddivisioni` se ci sono più divisioni con economie molto diverse (es. Amazon: e-commerce +
  cloud) o se è una holding; altrimenti `singole`.
- **Multipli:** per ogni segmento un multiplo ragionevole basato su concorrenti comparabili:
  `EV/EBIT` per segmenti in utile e maturi, `EV/Sales` per segmenti in perdita o in forte crescita.
- **Sintesi, catalizzatori, rischi:** in italiano, concreti e aggiornati alle ultime notizie.
- **Inflazione e disoccupazione (`macro`):** valuta come l'azienda è esposta a:
  - *inflazione al consumo*: riesce ad aumentare i prezzi ai clienti senza perdere vendite (potere di prezzo)?
    I suoi prodotti sono essenziali o rinviabili? Cosa è successo a volumi e prezzi nel 2021–2023?
  - *inflazione alla produzione*: peso di materie prime, energia, trasporti e salari sui costi; contratti di
    copertura; andamento dei margini lordi quando i costi sono saliti.
  - *disoccupazione*: quanto i ricavi dipendono dai consumi delle famiglie o dalla spesa delle imprese
    (prodotti ciclici o difensivi); effetto sul costo e sulla disponibilità di manodopera.
  - *mercati principali*: in quali paesi/aree genera i ricavi, con le percentuali se riportate.
  Basati su dati concreti (commenti del management, margini storici, mix di prodotti), non su frasi generiche.

Regole: usa solo numeri trovati nelle fonti, mai inventati (`null` se mancano). Se un numero è ricavato per
differenza o stimato, scrivilo in `note`. Tutti i testi in italiano.

## Formato di `research/<TICKER>.json`

```json
{
  "ticker": "AMZN",
  "data_ricerca": "2026-10-16",
  "categoria": "suddivisioni",
  "motivazione_categoria": "Tre segmenti con margini e crescita molto diversi: e-commerce e cloud.",
  "sintesi": "4-6 frasi: cosa fa, come guadagna, situazione attuale.",
  "catalizzatori": ["3-5 possibili driver positivi"],
  "rischi": ["3-5 rischi principali"],
  "periodo": "FY2025 (chiuso il 31/12/2025)",
  "valuta": "USD",
  "misura_utile": "Utile operativo",
  "segmenti": [
    {
      "nome": "AWS",
      "descrizione": "Servizi cloud",
      "ricavi": 128700,
      "utile": 45600,
      "crescita_ricavi_pct": 20.0,
      "metodo": "EV/EBIT",
      "multiplo": 30
    }
  ],
  "partecipazioni": [
    {"nome": "Esempio S.p.A.", "ticker_yahoo": "ESEMPIO.MI", "quota_pct": 25.0, "valore_mln": null, "note": "Quotata"}
  ],
  "macro": {
    "potere_prezzo": "alto",
    "sensibilita_inflazione": "media",
    "sensibilita_disoccupazione": "media",
    "impatto_prezzi_consumo": "2-4 frasi su come l'inflazione al consumo influisce su prezzi e domanda.",
    "impatto_costi_produzione": "2-4 frasi su costi di produzione, materie prime, salari e margini.",
    "impatto_disoccupazione": "2-4 frasi su quanto domanda e costi dipendono dal mercato del lavoro.",
    "mercati_principali": "Nord America 61%, Europa 25%, resto del mondo 14%"
  },
  "fonti": [{"titolo": "Amazon Q4 2025 earnings release", "url": "https://..."}],
  "note": "Avvertenze sui dati."
}
```

Tipi: `ricavi`, `utile`, `crescita_ricavi_pct`, `quota_pct`, `valore_mln` sono numeri o `null`;
`ticker_yahoo` è stringa o `null`; `metodo` è `EV/EBIT` o `EV/Sales`; `categoria` è `singole` o `suddivisioni`;
`potere_prezzo` è `alto`, `medio` o `basso`; `sensibilita_inflazione` e `sensibilita_disoccupazione` sono
`alta`, `media` o `bassa`.
