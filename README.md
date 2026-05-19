# KM1-GKV-Analyse

Monatliche Auswertung der KM1-Statistik des Bundesministeriums fuer Gesundheit fuer Account Management und Business Development im GKV-IT-Markt.

## Zweck

Das Projekt laedt die jeweils aktuelle KM1-PDF-Datei, extrahiert Tabellen, normalisiert wichtige Kennzahlen nach Kassenart und erzeugt einen deutschsprachigen Markdown-Bericht fuer Vertrieb, Account Management und Business Development.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Monatslauf

```bash
python src/download_km1.py
python src/extract_km1.py
python src/normalize_km1.py
python src/analyze_km1.py
python src/report_km1.py
```

Oder in einem Schritt:

```bash
python src/report_km1.py --run-all
```

## Ergebnisse

- `data/raw/`: heruntergeladene KM1-PDFs
- `data/processed/km1_metadata.json`: Metadaten zur aktuellen Datei
- `data/processed/km1_raw_tables.csv`: roh extrahierte Tabellenzellen
- `data/processed/km1_raw_tables.json`: roh extrahierte Tabellen als JSON
- `data/processed/km1_normalized.csv`: normalisierte Kennzahlen
- `data/processed/km1_analysis.json`: berechnete Marktanalyse
- `reports/KM1_Report_YYYY_MM.md`: fertiger Bericht

## Hinweise zur Datenqualitaet

Die KM1 berichtet in dieser Form aggregiert nach Kassenarten. Einzelne Krankenkassen werden nur qualitativ bewertet, wenn eine Zielkundenliste mit Kassenart-Zuordnung vorhanden ist. Das Projekt erfindet keine Einzelkassenwerte.

Jede normalisierte Zahl enthaelt Quelle-Datei und Quelle-Seite. Interpretationen im Bericht sind von beobachteten Fakten getrennt.
