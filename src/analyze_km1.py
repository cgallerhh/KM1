from __future__ import annotations

import csv
import sys
from collections import defaultdict

from km1_common import KASSENARTEN, PROCESSED_DIR, format_int, format_pct, read_json, write_json

CORE_CODES = [
    "versicherte_insgesamt",
    "mitglieder_gkv_gesamt",
    "pflichtmitglieder_akv",
    "freiwillige_mitglieder_mit_kg",
    "freiwillige_mitglieder_ohne_kg",
    "rentner_kvdr",
    "familienversicherte",
    "krankenstand_prozent",
]


def load_rows() -> list[dict]:
    path = PROCESSED_DIR / "km1_normalized.csv"
    if not path.exists():
        raise RuntimeError("Keine normalisierte CSV gefunden. Bitte zuerst src/normalize_km1.py ausfuehren.")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["jahr"] = int(row["jahr"])
        row["monat"] = int(row["monat"])
        row["wert"] = float(row["wert"])
    return rows


def index(rows: list[dict]) -> dict[tuple, dict]:
    return {(r["jahr"], r["monat"], r["kassenart"], r["kennzahl_code"], r["geschlecht"]): r for r in rows}


def value(idx: dict[tuple, dict], year: int, month: int, kassenart: str, code: str) -> float | None:
    row = idx.get((year, month, kassenart, code, "Zu"))
    return None if not row else row["wert"]


def previous_period(year: int, month: int) -> tuple[int, int]:
    month -= 1
    if month == 0:
        month = 12
        year -= 1
    return year, month


def delta(current: float | None, previous: float | None) -> dict:
    if current is None or previous is None:
        return {"abs": None, "pct": None}
    abs_delta = current - previous
    pct_delta = None if previous == 0 else abs_delta / previous * 100
    return {"abs": abs_delta, "pct": pct_delta}


def rank(idx: dict[tuple, dict], year: int, month: int, code: str) -> list[dict]:
    rows = []
    for kassenart in KASSENARTEN:
        if kassenart == "Insgesamt":
            continue
        current = value(idx, year, month, kassenart, code)
        if current is not None:
            rows.append({"kassenart": kassenart, "wert": current})
    return sorted(rows, key=lambda item: item["wert"], reverse=True)


def analyze() -> dict:
    rows = load_rows()
    metadata = read_json(PROCESSED_DIR / "km1_metadata.json", {})
    idx = index(rows)
    year, month = int(metadata["jahr"]), int(metadata["monat"])
    prev_year, prev_month = previous_period(year, month)
    has_previous = any(r["jahr"] == prev_year and r["monat"] == prev_month for r in rows)

    kennzahlen = defaultdict(dict)
    for code in CORE_CODES:
        ranking = rank(idx, year, month, code)
        strongest = ranking[0] if ranking else None
        weakest = ranking[-1] if ranking else None
        current_total = value(idx, year, month, "Insgesamt", code)
        previous_total = value(idx, prev_year, prev_month, "Insgesamt", code)
        kennzahlen[code] = {
            "name": next((r["kennzahl_name"] for r in rows if r["kennzahl_code"] == code), code),
            "gesamtwert": current_total,
            "gesamtwert_formatiert": format_pct(current_total) if code.endswith("prozent") else format_int(current_total),
            "staerkste_kassenart": strongest,
            "schwaechste_kassenart": weakest,
            "veraenderung_vormonat": delta(current_total, previous_total),
            "ranking": ranking,
        }

    shares = {}
    total_insured = value(idx, year, month, "Insgesamt", "versicherte_insgesamt")
    if total_insured:
        for kassenart in KASSENARTEN:
            v = value(idx, year, month, kassenart, "versicherte_insgesamt")
            if v is not None:
                shares[kassenart] = v / total_insured * 100

    analysis = {
        "metadata": metadata,
        "has_previous_period": has_previous,
        "period": {"year": year, "month": month},
        "previous_period": {"year": prev_year, "month": prev_month},
        "kennzahlen": kennzahlen,
        "anteile_versicherte": shares,
        "row_count": len(rows),
        "coverage_note": "Trendvergleich nur verfuegbar, wenn normalisierte Vorperioden im selben CSV-Bestand vorhanden sind.",
    }
    write_json(PROCESSED_DIR / "km1_analysis.json", analysis)
    print(f"OK: Analyse fuer {year}-{month:02d} erstellt.")
    return analysis


def main() -> int:
    analyze()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER bei KM1-Analyse: {exc}", file=sys.stderr)
        raise SystemExit(1)
