from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

BASE_URL = "https://www.bundesgesundheitsministerium.de/fileadmin/Dateien/3_Downloads/Statistiken/GKV/Mitglieder_Versicherte/"

MONTHS = {
    1: ("Januar", ["Januar"]),
    2: ("Februar", ["Februar"]),
    3: ("Maerz", ["Maerz", "März", "Marz"]),
    4: ("April", ["April"]),
    5: ("Mai", ["Mai"]),
    6: ("Juni", ["Juni"]),
    7: ("Juli", ["Juli"]),
    8: ("August", ["August"]),
    9: ("September", ["September"]),
    10: ("Oktober", ["Oktober"]),
    11: ("November", ["November"]),
    12: ("Dezember", ["Dezember"]),
}

KASSENARTEN = ["Insgesamt", "AOK", "BKK", "IKK", "LKK", "KBS", "vdek"]
GESCHLECHTER = ["Mä", "Fr", "Zu"]


@dataclass(frozen=True)
class Period:
    year: int
    month: int

    @property
    def month_name(self) -> str:
        return MONTHS[self.month][0]

    @property
    def label(self) -> str:
        return f"{self.month_name} {self.year}"

    @property
    def yyyymm(self) -> str:
        return f"{self.year}_{self.month:02d}"


def ensure_dirs() -> None:
    for directory in (RAW_DIR, PROCESSED_DIR, REPORTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def latest_candidate_periods(today: date | None = None, max_back: int = 6) -> list[Period]:
    today = today or date.today()
    start_month = today.month - 1
    start_year = today.year
    if start_month == 0:
        start_month = 12
        start_year -= 1

    periods: list[Period] = []
    year, month = start_year, start_month
    for _ in range(max_back + 1):
        periods.append(Period(year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return periods


def filename_for(period: Period, month_variant: str | None = None) -> str:
    month_name = month_variant or period.month_name
    return f"KM1_Januar_bis_{month_name}_{period.year}.pdf"


def candidate_urls(period: Period) -> list[tuple[str, str]]:
    urls = []
    for variant in MONTHS[period.month][1]:
        filename = filename_for(period, variant)
        urls.append((filename, BASE_URL + filename))
    return urls


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_number(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "x"}:
        return None
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    else:
        parts = text.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            text = "".join(parts)
    try:
        return float(text)
    except ValueError:
        return None


def format_int(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{int(round(value)):,}".replace(",", ".")


def format_pct(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}".replace(".", ",") + " %"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
