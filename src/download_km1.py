from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from pypdf import PdfReader

from km1_common import (
    BASE_URL,
    PROCESSED_DIR,
    RAW_DIR,
    Period,
    candidate_urls,
    ensure_dirs,
    latest_candidate_periods,
    now_iso,
    sha256_file,
    write_json,
)


def encoded_url(filename: str) -> str:
    return BASE_URL + quote(filename)


def probe_url(url: str, timeout: int = 20) -> bool:
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        if response.status_code == 200:
            return True
        if response.status_code in {403, 405}:
            response = requests.get(url, stream=True, timeout=timeout)
            return response.status_code == 200
    except requests.RequestException:
        return False
    return False


def find_latest(today: date | None = None) -> tuple[Period, str, str]:
    for period in latest_candidate_periods(today=today, max_back=6):
        for filename, _ in candidate_urls(period):
            url = encoded_url(filename)
            if probe_url(url):
                canonical = f"KM1_Januar_bis_{period.month_name}_{period.year}.pdf"
                return period, canonical, url
    raise RuntimeError("Keine KM1-Datei in den letzten 6 Rueckwaertsversuchen gefunden.")


def download_file(url: str, output_path: Path) -> None:
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"Download ist keine PDF-Datei: {url}")
    output_path.write_bytes(response.content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Laedt die aktuellste KM1-PDF-Datei.")
    parser.add_argument("--year", type=int, help="Berichtsjahr erzwingen")
    parser.add_argument("--month", type=int, help="Berichtsmonat erzwingen, 1-12")
    args = parser.parse_args()

    ensure_dirs()

    if args.year and args.month:
        period = Period(args.year, args.month)
        filename = f"KM1_Januar_bis_{period.month_name}_{period.year}.pdf"
        url = encoded_url(filename)
        if not probe_url(url):
            raise SystemExit(f"Datei nicht gefunden: {url}")
    else:
        period, filename, url = find_latest()

    output_path = RAW_DIR / filename
    if not output_path.exists():
        download_file(url, output_path)

    reader = PdfReader(str(output_path))
    first_page_text = reader.pages[0].extract_text() or ""
    stand = None
    for line in first_page_text.splitlines():
        if line.strip().lower().startswith("stand:"):
            stand = line.strip().split(":", 1)[1].strip()
            break
    metadata = {
        "quell_url": url,
        "dateiname": filename,
        "download_datum": now_iso(),
        "berichtszeitraum": f"Januar bis {period.month_name} {period.year}",
        "stand_laut_deckblatt": stand,
        "seitenzahl": len(reader.pages),
        "hash_sha256": sha256_file(output_path),
        "erkannter_neuester_monat": period.month_name,
        "jahr": period.year,
        "monat": period.month,
        "lokaler_pfad": str(output_path.relative_to(Path.cwd())),
    }
    write_json(PROCESSED_DIR / "km1_metadata.json", metadata)
    print(f"OK: {filename} gespeichert ({metadata['seitenzahl']} Seiten).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER beim KM1-Download: {exc}", file=sys.stderr)
        raise SystemExit(1)
