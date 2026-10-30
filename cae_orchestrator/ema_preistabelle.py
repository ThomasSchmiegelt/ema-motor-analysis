"""Die Preisvariante des Paarvergleichs: EINE grosse Tabelle, billig gegen teuer.

Der Paarvergleich stellt je Achse die Optionen gegeneinander und fuehrt die Kosten als
eine Spalte unter vielen. Wer nur fragt „was kostet mich was", muss sich die Zeilen aus
neun Achsen zusammensuchen. Hier steht alles in einer Tabelle, nach Kosten sortiert:

* **teurer / billiger** gegen die Grundgeometrie, in Prozent -- nur die Rangfolge zaehlt,
  die Preise sind Platzhalter (``ema_screen.PREISE_EUR_KG`` mal ``PREIS_FAKTOR``);
* die Kosten nach **Magnet / Leiter / Eisen**, damit man sieht, WOHER ein Unterschied
  kommt;
* was man dafuer bekommt: Kt, Dauermoment, **EUR je Nm Dauermoment** -- eine billige
  Option, die nichts leistet, ist nicht billig;
* ob die Zeile **gilt**: ist das Eisen ueber ``ema_entscheidung.SAETTIGUNG_ABWEISEN``
  hinaus ausgelastet, sind Kt und Moment zu optimistisch, und die Zeile wird als nicht
  vergleichbar markiert. Dieselbe Regel wie in ``entscheide`` -- zwei Regeln waeren zwei
  Antworten auf dieselbe Frage.

Alle Maschinenarten stehen in der Tabelle (Achse ``maschinenart``): PSM, ASM, SynRM,
EESM, GSM. Die PSM ist der Hauptweg; die anderen Arten rechnen ihre eigenen Massen und
Kosten (Kaefig, Erregerwicklung, Anker) und teilen die Werkstoffpreise.
**Axialfluss:** nicht hier -- sein Paarvergleich (``ema_axial_vergleich``) fuehrt die
Kosten schon, in anderen Achsen.
"""
from __future__ import annotations

import ema_paarvergleich as PV
from ema_entscheidung import SAETTIGUNG_ABWEISEN

#: Achsen, die Material oder Bauart und damit den Preis bewegen. Geometrieachsen
#: (Nutbreite, Schraegung, ...) gehoeren in den normalen Paarvergleich.
PREIS_ACHSEN = ("maschinenart", "anordnung", "magnetwerkstoff", "blech",
                "leiterwerkstoff", "kaefigwerkstoff", "wicklungsart", "hairpins",
                "bauform")

#: Unter dieser Abweichung gilt eine Zeile als „gleich teuer" -- die Preise sind
#: auf ±25-30 % genau, alles darunter ist Rauschen.
GLEICH_PROZENT = 5.0


def _urteil(delta_pct: float | None) -> str:
    if delta_pct is None:
        return "—"
    if abs(delta_pct) < GLEICH_PROZENT:
        return "gleich"
    return "teurer" if delta_pct > 0 else "billiger"


def tabelle(erg: dict, basis: dict) -> dict:
    """Aus einem ``vergleiche``-Ergebnis die flache Preistabelle bauen."""
    b = PV._bewerte(basis, erg["n_max"], erg["rpm_betriebspunkt"], erg["last_nm"])
    if not b.get("ok"):
        return {"ok": False, "grund": f"Grundgeometrie nicht bewertbar: {b.get('grund', '')}",
                "zeilen": [], "abgelehnt": []}
    k0 = float(b["kosten_EUR"])
    zeilen, abgelehnt, ohne_wirkung = [], [], []
    for achse, a in erg["achsen"].items():
        # Eine Achse, die den Preis nicht bewegt, fuellt die Tabelle mit Zeilen, die
        # nichts sagen (Kaefigwerkstoff an einer PSM, Leiterzahl): sie wird genannt,
        # nicht aufgefuehrt.
        preise = [float(o["kosten_EUR"]) for o in a["optionen"] if o.get("ok")]
        if preise and (max(preise) - min(preise)) < 0.005 * max(max(preise), 1.0):
            ohne_wirkung.append(a["titel"])
            continue
        for o in a["optionen"]:
            if not o.get("ok"):
                abgelehnt.append({"achse": achse, "option": o["name"],
                                  "grund": str(o.get("grund", ""))[:90]})
                continue
            k = float(o["kosten_EUR"])
            delta = (k - k0) / k0 * 100.0 if k0 > 0 else None
            sat = o.get("saett_pct")
            # None = nicht geprueft (die GSM fuehrt keine Eisenausnutzung). Das ist
            # weder „gilt" noch „gilt nicht" und wird auch nicht als eines gezeigt.
            gilt = (None if not isinstance(sat, (int, float))
                    else sat <= SAETTIGUNG_ABWEISEN * 100.0)
            t = float(o.get("T_dauer_Nm") or 0.0)
            zeilen.append({
                "achse": achse, "titel": a["titel"], "option": o["name"],
                "magnet_EUR": o.get("kosten_magnet_EUR"),
                "leiter_EUR": o.get("kosten_leiter_EUR"),
                "eisen_EUR": o.get("kosten_eisen_EUR"),
                "kosten_EUR": k, "delta_pct": round(delta, 1) if delta is not None else None,
                "urteil": _urteil(delta),
                "gesamt_kg": o.get("gesamt_kg"), "Kt_Nm_per_A": o.get("Kt_Nm_per_A"),
                "T_dauer_Nm": o.get("T_dauer_Nm"),
                "eur_je_Nm": round(k / t, 2) if t > 0 else None,
                "saett_pct": sat, "gilt": gilt,
                "sf_n_max": o.get("SF_n_max"),
                "strom_limit": bool(o.get("strom_limit")),
            })
    zeilen.sort(key=lambda z: z["kosten_EUR"])
    return {"ok": True, "basis_kosten_EUR": k0,
            "basis_T_dauer_Nm": b.get("T_dauer_Nm"),
            "basis_saett_pct": b.get("saett_pct"),
            "zeilen": zeilen, "abgelehnt": abgelehnt, "ohne_preiswirkung": ohne_wirkung,
            "betriebspunkt": f"{erg['last_nm']:.0f} Nm @ {erg['rpm_betriebspunkt']:.0f} 1/min"}


def als_text(t: dict) -> str:
    if not t.get("ok"):
        return f"Preistabelle nicht moeglich: {t.get('grund', '')}"
    z = [f"Preisvergleich — Betriebspunkt {t['betriebspunkt']}; Grundgeometrie "
         f"{t['basis_kosten_EUR']:.0f} EUR, Dauermoment {t['basis_T_dauer_Nm']} Nm",
         "Nach Kosten sortiert, billigste zuerst. Preise sind Platzhalter (±25–30 %):",
         "nur teurer/billiger ist eine Aussage, kein Betrag.",
         "'x' = Eisen ueber der Grenze, Kt und Moment dort zu optimistisch: nicht vergleichbar; '?' = Eisen nicht geprueft.", "",
         f"  {'Achse':<15}{'Option':<26}{'Magnet':>7}{'Leiter':>7}{'Eisen':>7}{'Summe':>7}"
         f"{'Δ%':>7}  {'':<8}{'T_dauer':>8}{'EUR/Nm':>8}{'Eisen%':>7}  gilt"]
    for r in t["zeilen"]:
        def f(v, w, nd=0):
            return f"{v:>{w}.{nd}f}" if isinstance(v, (int, float)) else f"{'—':>{w}}"
        z.append(f"  {r['achse'][:14]:<15}{r['option'][:25]:<26}{f(r['magnet_EUR'], 7)}"
                 f"{f(r['leiter_EUR'], 7)}{f(r['eisen_EUR'], 7)}{f(r['kosten_EUR'], 7)}"
                 f"{f(r['delta_pct'], 7, 1)}  {r['urteil']:<8}{f(r['T_dauer_Nm'], 8, 1)}"
                 f"{f(r['eur_je_Nm'], 8, 1)}{f(r['saett_pct'], 7)}  "
                 f"{'?' if r['gilt'] is None else ('ja' if r['gilt'] else 'x')}{' (Strom am Limit)' if r['strom_limit'] else ''}")
    if t.get("ohne_preiswirkung"):
        z += ["", "Ohne Preiswirkung (nicht aufgefuehrt): " + "; ".join(t["ohne_preiswirkung"])]
    if t["abgelehnt"]:
        z += ["", "Nicht baubar / nicht bewertbar:"]
        z += [f"  {a['achse']}: {a['option']} — {a['grund']}" for a in t["abgelehnt"]]
    gut = [r for r in t["zeilen"] if r["gilt"]]
    if not gut:
        z += ["", "Keine Zeile ist gueltig: die Grundgeometrie sitzt im Eisen, und was nicht "
                  "vom Eisen abhaengt, ist billiger ohne leistungsfaehiger zu sein. Zuerst "
                  "die Saettigung beheben (Achse nutbreite, Joch), dann nach Preis waehlen."]
    if gut:
        z += ["", f"Billigste gueltige Zeile: {gut[0]['achse']} / {gut[0]['option']} "
                  f"({gut[0]['kosten_EUR']:.0f} EUR, {gut[0]['urteil']} gegen die Grundgeometrie). "
                  f"Je Nm Dauermoment am billigsten: "
                  + (lambda m: f"{m['achse']} / {m['option']} ({m['eur_je_Nm']} EUR/Nm)")(
                      min((r for r in gut if r["eur_je_Nm"]), key=lambda r: r["eur_je_Nm"]))
                  if any(r["eur_je_Nm"] for r in gut) else ""]
    return "\n".join(z)
