from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from km1_common import GESCHLECHTER, KASSENARTEN, MONTHS, PROCESSED_DIR, ensure_dirs, parse_number, read_json

KEYWORDS = {
    "anzahl_kassen": ["anzahl der kassen", "krankenkassen"],
    "pflichtmitglieder_akv": ["pflichtmitglieder", "akv"],
    "freiwillige_mitglieder_mit_kg": ["freiwillige mitglieder", "anspruch auf krankengeld"],
    "freiwillige_mitglieder_ohne_kg": ["freiwillige mitglieder", "ohne anspruch auf krankengeld"],
    "mitglieder_akv_gesamt": ["mitglieder", "allgemeine krankenversicherung"],
    "rentner_kvdr": ["rentner", "kvdr"],
    "mitglieder_gkv_gesamt": ["mitglieder", "insgesamt"],
    "familienversicherte": ["familienversicherte"],
    "versicherte_insgesamt": ["versicherte", "insgesamt"],
    "auszubildende": ["auszubildende"],
    "alg_sgb_iii": ["arbeitslosengeld", "sgb iii"],
    "buergergeld": ["buergergeld", "bürgergeld"],
    "studierende_praktikanten": ["studenten", "praktikanten"],
    "kuenstler_publizisten": ["kuenstler", "künstler", "publizisten"],
    "hauptberuflich_selbstaendige": ["hauptberuflich", "selbstaendige", "selbständige"],
    "freiwillige_arbeitnehmer": ["freiwillig versicherte arbeitnehmer", "freiwillige arbeitnehmer"],
    "au_krankengeldberechtigte": ["arbeitsunfaehige", "arbeitsunfähige", "krankengeldberechtigte"],
    "krankenstand_prozent": ["krankenstand"],
}

CODE_MAP = {
    "10015": ("auszubildende", "Auszubildende"),
    "10030": ("alg_sgb_iii", "Arbeitslosengeldempfaenger nach SGB III"),
    "10031": ("buergergeld", "Buergergeld-Beziehende"),
    "10090": ("studierende_praktikanten", "Studierende / Praktikanten / Auszubildende ohne Entgelt"),
    "10130": ("kuenstler_publizisten", "Selbstaendige Kuenstler und Publizisten"),
    "10199": ("pflichtmitglieder_akv", "Pflichtmitglieder AKV gesamt"),
    "10210": ("freiwillige_mitglieder_mit_kg", "Freiwillige Mitglieder mit Anspruch auf Krankengeld"),
    "10212": ("freiwillige_mitglieder_ohne_kg", "Freiwillige Mitglieder ohne Anspruch auf Krankengeld"),
    "10217": ("freiwillige_arbeitnehmer", "Freiwillige Arbeitnehmer"),
    "10218": ("hauptberuflich_selbstaendige", "Hauptberuflich Selbstaendige"),
    "10399": ("mitglieder_akv_gesamt", "Mitglieder AKV gesamt"),
    "10499": ("rentner_kvdr", "Rentner / KVdR"),
    "10999": ("mitglieder_gkv_gesamt", "Mitglieder GKV gesamt"),
    "11099": ("familienversicherte", "Familienversicherte"),
    "12099": ("versicherte_insgesamt", "Versicherte insgesamt"),
    "15010": ("au_krankengeldberechtigte", "Arbeitsunfaehige krankengeldberechtigte Mitglieder"),
    "15030": ("krankenstand_prozent", "Krankenstand in Prozent"),
}

STRUCTURE_ROWS = {
    "Kassen insgesamt": "anzahl_kassen",
    "landesunmittelbar": "landesunmittelbar",
    "bundesunmittelbar": "bundesunmittelbar",
    "regional geöffnet": "regional_geoeffnet",
    "regional geoeffnet": "regional_geoeffnet",
    "bundesweit geöffnet": "bundesweit_geoeffnet",
    "bundesweit geoeffnet": "bundesweit_geoeffnet",
    "nicht geöffnet": "nicht_geoeffnet",
    "nicht geoeffnet": "nicht_geoeffnet",
}

STRUCTURE_NAMES = {
    "anzahl_kassen": "Anzahl der Kassen insgesamt",
    "landesunmittelbar": "Landesunmittelbare Kassen",
    "bundesunmittelbar": "Bundesunmittelbare Kassen",
    "regional_geoeffnet": "Regional geoeffnete Kassen",
    "bundesweit_geoeffnet": "Bundesweit geoeffnete Kassen",
    "nicht_geoeffnet": "Nicht geoeffnete Kassen",
}

NAMES = {
    "anzahl_kassen": "Anzahl der Kassen insgesamt",
    "pflichtmitglieder_akv": "Pflichtmitglieder AKV gesamt",
    "freiwillige_mitglieder_mit_kg": "Freiwillige Mitglieder mit Anspruch auf Krankengeld",
    "freiwillige_mitglieder_ohne_kg": "Freiwillige Mitglieder ohne Anspruch auf Krankengeld",
    "mitglieder_akv_gesamt": "Mitglieder AKV gesamt",
    "rentner_kvdr": "Rentner / KVdR",
    "mitglieder_gkv_gesamt": "Mitglieder GKV gesamt",
    "familienversicherte": "Familienversicherte",
    "versicherte_insgesamt": "Versicherte insgesamt",
    "auszubildende": "Auszubildende",
    "alg_sgb_iii": "Arbeitslosengeldempfaenger nach SGB III",
    "buergergeld": "Buergergeld-Beziehende",
    "studierende_praktikanten": "Studierende / Praktikanten / Auszubildende ohne Entgelt",
    "kuenstler_publizisten": "Selbstaendige Kuenstler und Publizisten",
    "hauptberuflich_selbstaendige": "Hauptberuflich Selbstaendige",
    "freiwillige_arbeitnehmer": "Freiwillige Arbeitnehmer",
    "au_krankengeldberechtigte": "Arbeitsunfaehige krankengeldberechtigte Mitglieder",
    "krankenstand_prozent": "Krankenstand in Prozent",
}


def clean(text: str) -> str:
    text = (text or "").replace("\n", " ").replace("\u00a0", " ")
    text = text.replace("ü", "ue").replace("ä", "ae").replace("ö", "oe").replace("ß", "ss")
    return re.sub(r"\s+", " ", text.lower()).strip()


def classify(label: str) -> tuple[str, str] | None:
    normalized = clean(label)
    for code, words in KEYWORDS.items():
        hits = [word for word in words if clean(word) in normalized]
        if len(hits) == len(words) or (code in {"familienversicherte", "auszubildende", "krankenstand_prozent"} and hits):
            return code, NAMES[code]
    return None


def row_numbers(row: list[str]) -> list[float | None]:
    return [parse_number(cell) for cell in row]


def find_kassenart_table(table: list[list[str]]) -> list[str] | None:
    for row in table[:8]:
        joined = " ".join(row)
        found = [k for k in KASSENARTEN if re.search(rf"\b{re.escape(k)}\b", joined, flags=re.I)]
        if len(found) >= 4:
            return found
    return None


def infer_stichtag(text: str, fallback_year: int, fallback_month: int) -> str:
    match = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if match:
        day, month, year = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return f"{fallback_year:04d}-{fallback_month:02d}-01"


def infer_period(page: dict, metadata: dict) -> tuple[int, int]:
    sheet_name = page.get("sheet_name", "")
    text = f"{sheet_name}\n{page.get('text', '')}"
    for month, (canonical, variants) in MONTHS.items():
        if clean(sheet_name) in {clean(canonical), *(clean(variant) for variant in variants)}:
            return int(metadata["jahr"]), month
        for variant in [canonical, *variants]:
            match = re.search(rf"\b{re.escape(variant)}\s+(\d{{4}})\b", text, flags=re.I)
            if match:
                return int(match.group(1)), month
    return int(metadata["jahr"]), int(metadata["monat"])


def values_to_kassenarten(numbers: list[float]) -> list[tuple[str, float]]:
    if len(numbers) == 7:
        return list(zip(KASSENARTEN, numbers))
    if len(numbers) == 6:
        # In a few rows the LKK column is visually blank and disappears in text extraction.
        total, aok, bkk, ikk, kbs, vdek = numbers
        if abs(total - (aok + bkk + ikk + kbs + vdek)) < max(2.0, total * 0.0001):
            return list(zip(KASSENARTEN, [total, aok, bkk, ikk, 0.0, kbs, vdek]))
    return list(zip(KASSENARTEN[: len(numbers)], numbers))


def parse_text_page(page: dict, metadata: dict) -> list[dict]:
    out: list[dict] = []
    page_no = page["page"]
    text = page.get("text") or ""
    page_year, page_month = infer_period(page, metadata)
    stichtag = infer_stichtag(text, page_year, page_month)
    current_code: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        for label, code in STRUCTURE_ROWS.items():
            if clean(line).startswith(clean(label)):
                numbers = [n for n in (parse_number(part) for part in re.findall(r"\d[\d.,]*", line)) if n is not None]
                if numbers:
                    for kassenart, number in values_to_kassenarten(numbers):
                        out.append(make_row(metadata, stichtag, kassenart, code, STRUCTURE_NAMES[code], "Zu", number, page_no, page_year, page_month))

        row_match = re.search(r"\b(Mä|Fr|Zu)\b\s+(.+)$", line)
        if row_match:
            before_gender = line[: row_match.start()]
            raw_candidates = re.findall(r"\b([0-9]{5}[A-Z]?)\b", before_gender)
            if raw_candidates:
                last_code = raw_candidates[-1]
                current_code = last_code if last_code in CODE_MAP else None
        if not row_match or not current_code:
            continue
        geschlecht = row_match.group(1)
        numbers = [n for n in (parse_number(part) for part in re.findall(r"\d[\d.,]*", row_match.group(2))) if n is not None]
        if not numbers:
            continue
        code, name = CODE_MAP[current_code]
        for kassenart, number in values_to_kassenarten(numbers):
            out.append(make_row(metadata, stichtag, kassenart, code, name, geschlecht, number, page_no, page_year, page_month))
        if geschlecht == "Zu":
            current_code = None
    return out


def parse_xlsx_page(page: dict, metadata: dict) -> list[dict]:
    out: list[dict] = []
    page_no = page["page"]
    page_year, page_month = infer_period(page, metadata)
    stichtag = infer_stichtag(page.get("text", ""), page_year, page_month)
    current: tuple[str, str, str] | None = None
    rows = page.get("tables", [[]])[0]

    for cells in rows:
        cells = ["" if cell is None else str(cell).strip() for cell in cells]
        if not any(cells):
            continue

        label = cells[0] if cells else ""
        label_clean = clean(label)
        for structure_label, structure_code in STRUCTURE_ROWS.items():
            if label_clean == clean(structure_label):
                numbers = [parse_number(cell) for cell in cells[1:8]]
                present = [number for number in numbers if number is not None]
                for kassenart, number in values_to_kassenarten(present):
                    out.append(
                        make_row(
                            metadata,
                            stichtag,
                            kassenart,
                            structure_code,
                            STRUCTURE_NAMES[structure_code],
                            "Zu",
                            number,
                            page_no,
                            page_year,
                            page_month,
                        )
                    )

        code = next((cell for cell in cells if re.fullmatch(r"[0-9]{5}[A-Z]?", cell or "")), None)
        if code in CODE_MAP:
            current = (code, *CODE_MAP[code])

        gender_index = next((idx for idx, cell in enumerate(cells) if cell in GESCHLECHTER), None)
        if gender_index is None or current is None:
            continue

        _, kennzahl_code, kennzahl_name = current
        numbers = [parse_number(cell) for cell in cells[gender_index + 1 : gender_index + 8]]
        present = [number for number in numbers if number is not None]
        if not present:
            continue
        for kassenart, number in values_to_kassenarten(present):
            out.append(make_row(metadata, stichtag, kassenart, kennzahl_code, kennzahl_name, cells[gender_index], number, page_no, page_year, page_month))
        if cells[gender_index] == "Zu":
            current = None
    return out


def normalize() -> list[dict]:
    metadata = read_json(PROCESSED_DIR / "km1_metadata.json", {})
    raw_pages = read_json(PROCESSED_DIR / "km1_raw_tables.json", [])
    if not raw_pages:
        raise RuntimeError("Keine Rohdaten gefunden. Bitte zuerst src/extract_km1.py ausfuehren.")

    rows: list[dict] = []
    for page in raw_pages:
        if page.get("source_type") == "xlsx":
            rows.extend(parse_xlsx_page(page, metadata))
            continue
        page_no = page["page"]
        page_year, page_month = infer_period(page, metadata)
        stichtag = infer_stichtag(page.get("text", ""), page_year, page_month)
        rows.extend(parse_text_page(page, metadata))
        for table in page.get("tables", []):
            if not table:
                continue
            kassenarten = find_kassenart_table(table)
            for table_row in table:
                cells = ["" if cell is None else str(cell).strip() for cell in table_row]
                label = " ".join(cells[:3])
                classified = classify(label)
                if not classified:
                    continue
                code, name = classified
                values = row_numbers(cells)
                numeric_positions = [(idx, val) for idx, val in enumerate(values) if val is not None]
                if code == "krankenstand_prozent":
                    numeric_positions = [(idx, val) for idx, val in numeric_positions if val < 100]
                if not numeric_positions:
                    continue

                if kassenarten and len(numeric_positions) >= len(kassenarten):
                    selected = numeric_positions[-len(kassenarten) :]
                    for kassenart, (_, value) in zip(kassenarten, selected):
                        rows.append(make_row(metadata, stichtag, kassenart, code, name, "Zu", value, page_no, page_year, page_month))
                elif len(numeric_positions) >= len(KASSENARTEN) * 3:
                    selected = numeric_positions[-len(KASSENARTEN) * 3 :]
                    pos = 0
                    for kassenart in KASSENARTEN:
                        for geschlecht in GESCHLECHTER:
                            rows.append(make_row(metadata, stichtag, kassenart, code, name, geschlecht, selected[pos][1], page_no, page_year, page_month))
                            pos += 1
                else:
                    for _, value in numeric_positions[-1:]:
                        rows.append(make_row(metadata, stichtag, "Insgesamt", code, name, "Zu", value, page_no, page_year, page_month))

    deduped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["jahr"], row["monat"], row["kassenart"], row["kennzahl_code"], row["geschlecht"])
        deduped[key] = row
    return list(deduped.values())


def make_row(
    metadata: dict,
    stichtag: str,
    kassenart: str,
    code: str,
    name: str,
    geschlecht: str,
    value: float,
    page_no: int,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    return {
        "jahr": year if year is not None else metadata["jahr"],
        "monat": month if month is not None else metadata["monat"],
        "stichtag": stichtag,
        "kassenart": kassenart,
        "kennzahl_code": code,
        "kennzahl_name": name,
        "geschlecht": geschlecht,
        "wert": value,
        "quelle_datei": metadata["dateiname"],
        "quelle_seite": page_no,
    }


def write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "jahr",
        "monat",
        "stichtag",
        "kassenart",
        "kennzahl_code",
        "kennzahl_name",
        "geschlecht",
        "wert",
        "quelle_datei",
        "quelle_seite",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ensure_dirs()
    rows = normalize()
    write_csv(rows, PROCESSED_DIR / "km1_normalized.csv")
    print(f"OK: {len(rows)} normalisierte Kennzahl-Zeilen geschrieben.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER bei KM1-Normalisierung: {exc}", file=sys.stderr)
        raise SystemExit(1)
