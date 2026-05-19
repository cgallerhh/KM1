from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from km1_common import KASSENARTEN, PROCESSED_DIR, REPORTS_DIR, ROOT, ensure_dirs, format_int, format_pct, read_json

MONTH_LABELS = {
    1: "Januar",
    2: "Februar",
    3: "Maerz",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}


def run_all() -> None:
    for script in ["download_km1.py", "extract_km1.py", "normalize_km1.py", "analyze_km1.py"]:
        subprocess.run([sys.executable, str(ROOT / "src" / script)], check=True, cwd=ROOT)


def load_normalized() -> list[dict]:
    path = PROCESSED_DIR / "km1_normalized.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["jahr"] = int(row["jahr"])
        row["monat"] = int(row["monat"])
        row["wert"] = float(row["wert"])
    return rows


def find_target_lists() -> list[Path]:
    patterns = ["*top*31*", "*ziel*kassen*", "*krankenkassen*", "*kassenliste*"]
    hits: list[Path] = []
    for pattern in patterns:
        hits.extend(ROOT.glob(pattern))
        hits.extend((ROOT / "data").glob(f"**/{pattern}"))
    return sorted({p for p in hits if p.is_file()})


def value(rows: list[dict], kassenart: str, code: str) -> float | None:
    for row in rows:
        if row["kassenart"] == kassenart and row["kennzahl_code"] == code and row["geschlecht"] == "Zu":
            return row["wert"]
    return None


def source(rows: list[dict], kassenart: str, code: str) -> str:
    for row in rows:
        if row["kassenart"] == kassenart and row["kennzahl_code"] == code and row["geschlecht"] == "Zu":
            return f"{row['quelle_datei']}, S. {row['quelle_seite']}"
    return "Quelle nicht extrahiert"


def fmt_value(code: str, val: float | None) -> str:
    return format_pct(val) if code.endswith("prozent") else format_int(val)


def delta_text(delta: dict | None, code: str) -> str:
    if not delta or delta.get("abs") is None:
        return "n/a"
    abs_part = format_pct(delta["abs"]) if code.endswith("prozent") else format_int(delta["abs"])
    pct_part = format_pct(delta.get("pct"))
    return f"{abs_part} ({pct_part})"


def strongest(analysis: dict, code: str) -> str:
    item = analysis["kennzahlen"].get(code, {}).get("staerkste_kassenart")
    if not item:
        return "n/a"
    return f"{item['kassenart']} ({fmt_value(code, item['wert'])})"


def weakest(analysis: dict, code: str) -> str:
    item = analysis["kennzahlen"].get(code, {}).get("schwaechste_kassenart")
    if not item:
        return "n/a"
    return f"{item['kassenart']} ({fmt_value(code, item['wert'])})"


def ranking_md(analysis: dict, code: str) -> str:
    ranking = analysis["kennzahlen"].get(code, {}).get("ranking", [])
    if not ranking:
        return "- Keine belastbaren Werte extrahiert."
    return "\n".join(f"- {item['kassenart']}: {fmt_value(code, item['wert'])}" for item in ranking)


def assessment_for_code(code: str, has_previous: bool) -> str:
    if code == "krankenstand_prozent":
        return "Hoher Krankenstand ist ein direkter Trigger fuer AU-, Krankengeld- und Fallsteuerungsprozesse."
    if code == "familienversicherte":
        return "Relevant fuer Service-, Stammdaten- und Familienversicherungsprozesse."
    if code == "rentner_kvdr":
        return "Demografie- und Leistungsdruck; relevant fuer Versorgung, Pflege- und Kommunikationsprozesse."
    if code.startswith("freiwillige"):
        return "Wettbewerbs- und Beitragsnahe Zielgruppe mit Beratungs- und Bindungsrelevanz."
    if not has_previous:
        return "Statuswert; echter Trendvergleich entsteht nach weiteren Monatslaeufen."
    return "Trendwert fuer Markt- und Wettbewerbsdynamik."


def kassenart_section(rows: list[dict], kassenart: str) -> str:
    insured = value(rows, kassenart, "versicherte_insgesamt")
    members = value(rows, kassenart, "mitglieder_gkv_gesamt")
    pensioners = value(rows, kassenart, "rentner_kvdr")
    family = value(rows, kassenart, "familienversicherte")
    sick = value(rows, kassenart, "krankenstand_prozent")
    facts = (
        f"Versicherte {format_int(insured)}, Mitglieder {format_int(members)}, "
        f"Rentner/KVdR {format_int(pensioners)}, Familienversicherte {format_int(family)}, "
        f"Krankenstand {format_pct(sick)}."
    )
    return (
        f"### {kassenart}\n\n"
        f"- Relevante Kennzahlen: {facts}\n"
        f"- Auffaellige Entwicklung: Ohne Vorperiode aktuell als Statusbild zu lesen; nach naechstem Lauf werden Delta-Werte automatisch ausgewiesen.\n"
        f"- Wahrscheinliche fachliche Herausforderung: Segmentgerechte Bearbeitung von Mitgliedern, Rentnern, Familienversicherten und AU-Faellen.\n"
        f"- Wahrscheinlicher IT-Bedarf: BI, Prozessmonitoring, Inputmanagement, Automatisierung in Service- und Leistungsprozessen.\n"
        f"- Moeglicher Gespraechsanlass: Welche Kennzahlengruppe erzeugt aktuell den groessten operativen Druck in Service, Leistung oder Finanzen?\n"
    )


def build_report() -> Path:
    ensure_dirs()
    analysis = read_json(PROCESSED_DIR / "km1_analysis.json", {})
    if not analysis:
        raise RuntimeError("Keine Analyse gefunden. Bitte zuerst src/analyze_km1.py ausfuehren.")
    rows = load_normalized()
    metadata = analysis["metadata"]
    year = int(metadata["jahr"])
    month = int(metadata["monat"])
    month_label = MONTH_LABELS[month]
    report_path = REPORTS_DIR / f"KM1_Report_{year}_{month:02d}.md"
    has_previous = bool(analysis.get("has_previous_period"))
    target_lists = find_target_lists()

    key_codes = [
        "versicherte_insgesamt",
        "mitglieder_gkv_gesamt",
        "pflichtmitglieder_akv",
        "freiwillige_mitglieder_mit_kg",
        "freiwillige_mitglieder_ohne_kg",
        "rentner_kvdr",
        "familienversicherte",
        "krankenstand_prozent",
    ]

    lines: list[str] = []
    lines.append(f"# KM1-Auswertung {month_label} {year}\n")
    lines.append("## 1. Kurzbewertung für Account Management und Business Development\n")
    lines.extend(
        [
            f"- Datenbasis: {metadata['berichtszeitraum']} aus {metadata['dateiname']} ({metadata['seitenzahl']} Seiten).",
            "- Die KM1 liefert in dieser Auswertung belastbare Signale auf Ebene der Kassenarten, nicht auf Ebene einzelner Krankenkassen.",
            "- Größere Kassenarten mit hohem Versichertenbestand sind besonders relevant für skalierbare IT-Angebote in Service, BI, DMS und Automatisierung.",
            "- Krankenstandswerte sind ein konkreter Anlass für Gespräche zu AU, Krankengeld, Arbeitgeberkommunikation und Fallsteuerung.",
            "- Familienversicherte und Rentner/KVdR zeigen Prozesslast in Stammdaten, Leistung, Kommunikation und Versorgung.",
            "- Freiwillige Mitglieder sind vertrieblich interessant, weil Bindung, Servicequalität und Beitragssatzsensibilität zusammenfallen.",
            "- Ohne Vorperiode ist dieser erste Lauf als Marktstatus zu lesen; echte Monats- und Jahresvergleiche entstehen mit weiteren KM1-Dateien.",
            "- Jede Zahl ist über Datei und Seite in der normalisierten CSV rückverfolgbar.",
        ]
    )
    lines.append("\n## 2. Wichtigste Zahlen\n")
    lines.append("| Kennzahl | Gesamtwert | stärkste Kassenart | schwächste Kassenart | Veränderung ggü. Vormonat | Bewertung |")
    lines.append("|---|---:|---|---|---:|---|")
    for code in key_codes:
        item = analysis["kennzahlen"].get(code, {})
        lines.append(
            f"| {item.get('name', code)} | {item.get('gesamtwert_formatiert', 'n/a')} | "
            f"{strongest(analysis, code)} | {weakest(analysis, code)} | "
            f"{delta_text(item.get('veraenderung_vormonat'), code)} | {assessment_for_code(code, has_previous)} |"
        )

    lines.append("\n## 3. Größte und kleinste Marktsegmente\n")
    ranking_map = [
        ("Versicherte insgesamt", "versicherte_insgesamt"),
        ("Mitglieder insgesamt", "mitglieder_gkv_gesamt"),
        ("Pflichtmitglieder", "pflichtmitglieder_akv"),
        ("Freiwillige Mitglieder mit Krankengeldanspruch", "freiwillige_mitglieder_mit_kg"),
        ("Rentner / KVdR", "rentner_kvdr"),
        ("Familienversicherte", "familienversicherte"),
        ("Krankenstand", "krankenstand_prozent"),
    ]
    for title, code in ranking_map:
        lines.append(f"\n### {title}\n")
        lines.append(ranking_md(analysis, code))

    lines.append("\n## 4. Veränderungen und mögliche Ursachen\n")
    if has_previous:
        lines.append("- Direkt beobachtete Veränderung: Vorperiodenwerte wurden gefunden; die Deltas stehen in Abschnitt 2.")
    else:
        lines.append("- Direkt beobachtete Veränderung: Keine Vorperiode im Projektbestand gefunden. Dieser Bericht ist daher ein Statusbild.")
    lines.append("- Plausible Interpretation: Hohe Bestände bei Rentnern, Familienversicherten oder AU-Fällen deuten auf Prozesslast in Versorgung, Leistung, Kommunikation und Fallbearbeitung hin.")
    lines.append("- Noch zu validierende Hypothese: Beitragssatz- und Wettbewerbsdynamik, regionale Arbeitgeberstruktur, Demografie und mögliche Fusionen müssen mit externen Quellen geprüft werden.")

    lines.append("\n## 5. Herausforderungen je Kassenart\n")
    for kassenart in [k for k in KASSENARTEN if k != "Insgesamt"]:
        lines.append(kassenart_section(rows, kassenart))

    lines.append("\n## 6. Relevanz für meine Zielkassen\n")
    if target_lists:
        lines.append("Es wurden mögliche Zielkassenlisten gefunden, aber noch nicht automatisch strukturiert verknüpft:")
        lines.extend(f"- {path.relative_to(ROOT)}" for path in target_lists)
        lines.append("\nFür Einzelkassen gilt: konkrete Werte sind erst nach strukturierter Kassenart-Zuordnung ableitbar; KM1 selbst enthält hier keine Einzelkassenwerte.")
    else:
        lines.append("Keine Einzelkassenliste gefunden. Die KM1 erlaubt in dieser Form nur eine Auswertung nach Kassenarten.")

    lines.append("\n## 7. Konkrete Gesprächsanlässe\n")
    prompts = [
        ("Krankenstand und AU-Prozess", "Bereichsleitung Leistung", "Krankenstand aus KM1", "AU-/Krankengeld-Workflow, Fallsteuerung, Automatisierung", "Wo entstehen aktuell die größten Liegezeiten zwischen AU-Eingang, Prüfung und Krankengeldentscheidung?"),
        ("Familienversicherung", "Kundenservice", "Bestand Familienversicherte", "Inputmanagement, Dunkelverarbeitung, Stammdatenqualität", "Welche Familienversicherungsfälle verursachen im Service die meisten Rückfragen?"),
        ("Rentner/KVdR", "Bereichsleitung Versorgung", "Rentnerstruktur aus KM1", "Versorgungsdaten, Segmentierung, proaktive Kommunikation", "Wie steuern Sie Kommunikation und Services für ältere Versicherte datenbasiert?"),
        ("Freiwillige Mitglieder", "Markt/Vertrieb", "freiwillige Mitglieder aus KM1", "CRM, Kampagnensteuerung, Service-Analytics", "Welche Wechsel- oder Kündigungssignale sehen Sie bei freiwilligen Mitgliedern frühzeitig?"),
        ("Pflichtmitglieder", "Finanzen", "Pflichtmitgliederbestand aus KM1", "BI, Prognose, Beitragscontrolling", "Wie schnell können Sie Mitgliederbewegungen in Finanz- und Kapazitätsplanung übersetzen?"),
        ("Datenplattform", "CDO", "mehrere KM1-Struktursignale", "GKV-Datenplattform, KPI-Haus, Self-Service-BI", "Welche Kennzahlen fehlen Ihnen heute für eine monatliche operative Steuerung?"),
        ("Dokumentenlast", "CIO", "hohe Fallgruppen in Mitgliedschaft und Leistung", "DMS, OCR, Klassifikation, KI-Assistenz", "Welche Eingangskanäle und Dokumenttypen blockieren aktuell Automatisierung?"),
        ("Arbeitgeberkommunikation", "Bereich Markt/Arbeitgeber", "AU- und Pflichtmitgliederbezug", "Portale, Schnittstellen, Prozessintegration", "Wo ist der Arbeitgeberkontakt noch zu manuell oder medienbrüchig?"),
        ("Prozessbenchmark", "Vorstand/COO", "Kassenart-Rangfolge", "Prozess-Mining, Benchmarking, KPI-Steuerung", "Welche Prozesse würden Sie gern gegen ähnliche Kassenarten benchmarken?"),
        ("KI-gestützte Sachbearbeitung", "CIO/CDO", "Bearbeitungsdruck aus Strukturkennzahlen", "KI-Copilot, Wissenssuche, Vorgangszusammenfassung", "Welche Sachbearbeitungsentscheidungen sind häufig, regelnah und trotzdem noch manuell?"),
    ]
    for occasion, role, reason, solution, question in prompts:
        lines.append(f"- Anlass: {occasion}; Zielrolle: {role}; Begründung aus KM1: {reason}; mögliche IT-Lösung: {solution}; gute Einstiegsfrage: {question}")

    lines.append("\n## 8. Risiken und Grenzen der Analyse\n")
    lines.extend(
        [
            "- Es fehlen Einzelkassenwerte, sofern keine externe Zielkunden- oder Stammdatenliste verknüpft wird.",
            "- Aussagen zu Wachstum und Verlust sind nur belastbar, wenn Vorperioden im Projektbestand liegen.",
            "- Ursachen wie Demografie, Arbeitgeberstruktur, Beitragssatz, Fusionen oder regionale Effekte sind Hypothesen und extern zu validieren.",
            "- Sinnvolle Zusatzquellen: Top-31-Kassenliste, Beitragssatzdaten, Geschäftsberichte, Vergaben, Pressemitteilungen, LinkedIn-Signale und IT-Dienstleisterinformationen.",
        ]
    )

    lines.append("\n## 9. Nächste Schritte\n")
    lines.extend(
        [
            "- Datenqualität prüfen: Stichproben gegen PDF-Seiten und Tabellenlayout durchführen.",
            "- Vorperioden laden und normalisierte CSV historisieren.",
            "- Top-31-Kassenliste mit Kassenart verknüpfen.",
            "- Auffälligkeiten gegen Presse, Vergaben und LinkedIn prüfen.",
            "- Priorisierte Zielkundenliste aktualisieren und Gesprächsanlässe pro Account ausformulieren.",
        ]
    )
    lines.append("\n## Quellenhinweis\n")
    for code in key_codes:
        lines.append(f"- {analysis['kennzahlen'].get(code, {}).get('name', code)}: {source(rows, 'Insgesamt', code)}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Erzeugt den KM1-Marktanalysebericht.")
    parser.add_argument("--run-all", action="store_true", help="Fuehrt Download, Extraktion, Normalisierung und Analyse vorher aus.")
    args = parser.parse_args()
    if args.run_all:
        run_all()
    path = build_report()
    print(f"OK: Bericht geschrieben: {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER beim KM1-Bericht: {exc}", file=sys.stderr)
        raise SystemExit(1)
