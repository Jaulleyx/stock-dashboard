"""Dati macroeconomici: inflazione al consumo (prezzi al cliente), inflazione alla produzione
(costi di produzione) e disoccupazione. Fonti: FRED (Stati Uniti) ed Eurostat (area euro e paesi UE).
Nessuna chiave API necessaria. Ogni serie restituisce una pd.Series mensile in % oppure None."""

import io

import pandas as pd
import requests
import streamlit as st

START = "2018-01-01"

# Paesi dell'area euro: nome Yahoo Finance -> codice Eurostat
EUROZONE = {
    "Italy": "IT", "Germany": "DE", "France": "FR", "Spain": "ES", "Netherlands": "NL", "Belgium": "BE",
    "Austria": "AT", "Ireland": "IE", "Finland": "FI", "Portugal": "PT", "Greece": "EL", "Luxembourg": "LU",
    "Slovakia": "SK", "Slovenia": "SI", "Lithuania": "LT", "Latvia": "LV", "Estonia": "EE", "Croatia": "HR",
    "Cyprus": "CY", "Malta": "MT",
}

SERIES = {
    "cpi": "Inflazione al consumo (prezzi al cliente)",
    "ppi": "Inflazione alla produzione (costi di produzione)",
    "unemp": "Disoccupazione",
}


# ---------------------------------------------------------------- FRED (Stati Uniti)

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _fred(series_id):
    try:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                         params={"id": series_id, "cosd": "2016-01-01"}, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
                      index=pd.to_datetime(df.iloc[:, 0])).dropna()
        return s if len(s) else None
    except Exception:
        return None


def _yoy(index_series):
    return None if index_series is None else (index_series.pct_change(12) * 100).dropna()


def us_series():
    return {
        "cpi": _yoy(_fred("CPIAUCSL")),   # indice prezzi al consumo
        "ppi": _yoy(_fred("PPIFIS")),     # indice prezzi alla produzione, domanda finale
        "unemp": _fred("UNRATE"),         # tasso di disoccupazione
    }


# ---------------------------------------------------------------- Eurostat (area euro e paesi UE)

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _eurostat(dataset, geos, **filters):
    """Prima serie disponibile tra i codici geografici indicati (formato JSON-stat)."""
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
    for geo in geos:
        try:
            r = requests.get(url, params={"geo": geo, "sinceTimePeriod": "2016-01", **filters}, timeout=20)
            if not r.ok:
                continue
            j = r.json()
            times = j["dimension"]["time"]["category"]["index"]
            values = j.get("value", {})
            s = pd.Series({pd.Timestamp(t): values.get(str(i)) for t, i in times.items()}, dtype=float).dropna()
            if len(s):
                return s.sort_index()
        except Exception:
            continue
    return None


def eu_series(code):
    """code: codice paese Eurostat (IT, DE...) oppure 'EA' per l'area euro."""
    geos = ["EA", "EA20", "EA19"] if code == "EA" else [code]
    une_geos = ["EA20", "EA19", "EA"] if code == "EA" else [code]
    return {
        "cpi": _eurostat("prc_hicp_manr", geos, coicop="CP00", unit="RCH_A"),
        "ppi": _eurostat("sts_inppd_m", une_geos, indic_bt="PRC_PRR_DOM", nace_r2="B-E36",
                         s_adj="NSA", unit="PCH_SM"),
        "unemp": _eurostat("une_rt_m", une_geos, s_adj="SA", age="TOTAL", sex="T", unit="PC_ACT"),
    }


# ---------------------------------------------------------------- selezione area

def areas_for(country):
    """Aree economiche da mostrare per il paese della società: [(nome, serie), ...]."""
    if country in EUROZONE:
        return [(country_it(country), eu_series(EUROZONE[country])), ("Area euro", eu_series("EA"))], None
    if country == "United States":
        return [("Stati Uniti", us_series())], None
    note = (f"Dati macro per {country or 'questo paese'} non disponibili: mostro Stati Uniti e area euro "
            "come riferimento dei mercati globali.")
    return [("Stati Uniti", us_series()), ("Area euro", eu_series("EA"))], note


def country_it(country):
    names = {"Italy": "Italia", "Germany": "Germania", "France": "Francia", "Spain": "Spagna",
             "Netherlands": "Paesi Bassi", "Belgium": "Belgio", "Ireland": "Irlanda", "Portugal": "Portogallo",
             "Greece": "Grecia", "Finland": "Finlandia", "Austria": "Austria"}
    return names.get(country, country)


def annual_average(s):
    return None if s is None else s.groupby(s.index.year).mean()
