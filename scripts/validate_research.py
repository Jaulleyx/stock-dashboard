"""Controlla che un file research/<TICKER>.json rispetti il formato di RESEARCH_SPEC.md.

Uso: python3 scripts/validate_research.py research/AMZN.json"""

import json
import sys
from datetime import date

NUM = (int, float)


def check(d):
    errors = []

    def need(obj, key, types, where, nullable=False):
        if key not in obj:
            errors.append(f"{where}: manca '{key}'")
        elif not (isinstance(obj[key], types) or (nullable and obj[key] is None)) or isinstance(obj[key], bool):
            errors.append(f"{where}: '{key}' ha tipo errato ({type(obj[key]).__name__})")

    for k in ("ticker", "data_ricerca", "categoria", "motivazione_categoria", "sintesi", "periodo", "valuta",
              "misura_utile", "note"):
        need(d, k, str, "radice")
    for k in ("catalizzatori", "rischi", "segmenti", "partecipazioni", "fonti"):
        need(d, k, list, "radice")
    if errors:
        return errors

    if d["categoria"] not in ("singole", "suddivisioni"):
        errors.append("categoria deve essere 'singole' o 'suddivisioni'")
    try:
        date.fromisoformat(d["data_ricerca"])
    except ValueError:
        errors.append("data_ricerca deve essere AAAA-MM-GG")
    for i, s in enumerate(d["segmenti"]):
        w = f"segmenti[{i}]"
        need(s, "nome", str, w)
        need(s, "descrizione", str, w)
        for k in ("ricavi", "utile", "crescita_ricavi_pct"):
            need(s, k, NUM, w, nullable=True)
        need(s, "multiplo", NUM, w)
        if s.get("metodo") not in ("EV/EBIT", "EV/Sales"):
            errors.append(f"{w}: metodo deve essere 'EV/EBIT' o 'EV/Sales'")
    for i, p in enumerate(d["partecipazioni"]):
        w = f"partecipazioni[{i}]"
        need(p, "nome", str, w)
        need(p, "ticker_yahoo", str, w, nullable=True)
        need(p, "quota_pct", NUM, w, nullable=True)
        need(p, "valore_mln", NUM, w, nullable=True)
        need(p, "note", str, w)
    for i, f in enumerate(d["fonti"]):
        need(f, "titolo", str, f"fonti[{i}]")
        need(f, "url", str, f"fonti[{i}]")
    return errors


if __name__ == "__main__":
    path = sys.argv[1]
    try:
        errs = check(json.load(open(path)))
    except json.JSONDecodeError as e:
        errs = [f"JSON non valido: {e}"]
    if errs:
        print("ERRORI:\n- " + "\n- ".join(errs))
        sys.exit(1)
    print(f"OK: {path}")
