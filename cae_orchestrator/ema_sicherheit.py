"""Sicherheitskriterien eines gerechneten Laufs — deterministisch, an einer Stelle.

Warum
-----

Die Pipeline **meldet** ihre Grenzwertverletzungen im Laufprotokoll, aber sie
haelt den Lauf nicht an, und das Ergebnis traegt sie nur verstreut: die
stationaeren Temperaturen in ``summary``, die je Zyklus in
``drivecycle*.thermal``, die Festigkeit in ``summary.safety_factor_fem`` — und ob
ueberhaupt eine FEM lief, steht in ``structural_basis``. Wer den Lauf nur ansieht,
liest „✅ Analyse abgeschlossen" und uebersieht darueber, dass der Magnet im
Zyklus 210 °C erreicht, wo 80 °C die Grenze waeren.

Dieses Modul zieht die Kriterien zusammen und faellt ein **hartes** Urteil:
bestanden oder nicht, je Kriterium mit Wert, Grenze und Herkunft.

Zwei Dinge, die hier anders sind als in der frueheren verstreuten Logik
-----------------------------------------------------------------------

* **Die Magnetgrenze kommt aus der Werkstofftabelle**, nicht aus einer festen
  Zahl. ``ema_report._variant_verdict`` prueft(e) gegen 150 °C — fuer NdFeB N35
  liegt die Dauergrenze aber bei **80 °C** (``ema_pipeline.MAGNETS``), und genau
  davor warnt die Thermikstufe auch. Ein Lauf mit 118 °C Magnettemperatur waere
  in der Berichtstabelle als „einsetzbar" durchgegangen, waehrend das
  Laufprotokoll daneben „irreversible Entmagnetisierung" schrieb.
* **Eine fehlende FEM ist ein eigener Befund**, kein bestandenes Kriterium.
  ``safety_factor_fem = null`` heisst nicht „sicher", sondern „nicht gerechnet";
  die Festigkeitsaussage ruht dann allein auf der analytischen Ringformel, die
  die Spannungsspitzen an den duennen Stegen ueber den Magnettaschen nicht kennt.
"""

from __future__ import annotations

# Isolierstoffklasse H — dieselbe Grenze, die ``ema_thermal`` im Laufprotokoll
# nennt. Eine zweite Zahl an dieser Stelle waere eine zweite Wahrheit.
ISOLIERKLASSE_C = 180.0
WICKLUNG_SPITZE_C = 200.0
SF_ZIEL = 1.5          # geforderter Sicherheitsfaktor
SF_VERSAGEN = 1.0      # darunter fliesst der Rotor


def _k(name, ok, text, wert=None, grenze=None, einheit="", schwere="verletzt",
       quelle=""):
    return {"name": name, "ok": bool(ok), "text": text, "wert": wert,
            "grenze": grenze, "einheit": einheit,
            "schwere": ("" if ok else schwere), "quelle": quelle}


def _magnetgrenze(magnet: str) -> tuple:
    """(Grenztemperatur, Bezeichnung) aus der Werkstofftabelle.

    Nimmt den Schluessel (``ndfeb_n35``) ODER die Bezeichnung (``NdFeB N35``):
    der Payload fuehrt den Schluessel, die Kennwertzeile des Vergleichsberichts
    die Bezeichnung. Ist beides unbekannt, gilt der strengste Wert der Tabelle —
    lieber ein Fehlalarm als eine uebersehene Entmagnetisierung.
    """
    try:
        from ema_pipeline import MAGNETS
    except Exception:                                        # noqa: BLE001
        return 80.0, str(magnet)
    m = MAGNETS.get(str(magnet))
    if m is None:
        m = next((v for v in MAGNETS.values()
                  if v["label"].lower() == str(magnet).strip().lower()), None)
    if m is None:
        m = min(MAGNETS.values(), key=lambda v: v["T_op_max"])
        return float(m["T_op_max"]), f"{m['label']} (Werkstoff unbekannt, konservativ)"
    return float(m["T_op_max"]), str(m["label"])


def _zyklus_temperaturen(results: dict) -> list:
    """Je Fahrzyklus die Dauer- und Spitzentemperaturen, sofern gerechnet."""
    aus = []
    for key, res in (results or {}).items():
        if not key.startswith("drivecycle") or not isinstance(res, dict):
            continue
        th = res.get("thermal") or {}
        avg, peak = th.get("avg") or {}, th.get("peak") or {}
        if not avg and not peak:
            continue
        aus.append({"zyklus": res.get("cycle_name") or key,
                    "T_w_dauer": avg.get("T_winding"), "T_m_dauer": avg.get("T_magnet"),
                    "T_w_peak": peak.get("T_winding"), "T_m_peak": peak.get("T_magnet")})
    return aus


def _groesstes(werte):
    """Groesster Wert samt seiner Herkunft — ``(wert, woher)``, sonst (None, '')."""
    gefiltert = [(v, w) for v, w in werte if isinstance(v, (int, float))]
    if not gefiltert:
        return None, ""
    return max(gefiltert, key=lambda x: x[0])


def beurteile(row: dict) -> dict:
    """Die drei geteilten Kriterien auf einer FLACHEN Kennwertzeile.

    Von ``pruefen`` und von ``ema_report._variant_verdict`` benutzt, damit
    Bericht und Werkzeug nicht zwei verschiedene Urteile faellen.
    """
    warn, ok = [], True
    sf = row.get("safety_factor_fem")
    if isinstance(sf, (int, float)):
        if sf < SF_VERSAGEN:
            warn.append(f"MECHANISCHES VERSAGEN: FEM-Sicherheitsfaktor {sf:.2f} < "
                        f"{SF_VERSAGEN:.0f} (Rotor fliesst/berstet)")
            ok = False
        elif sf < SF_ZIEL:
            warn.append(f"Festigkeit unzureichend: FEM-Sicherheitsfaktor {sf:.2f} "
                        f"< {SF_ZIEL:.1f}")
            ok = False
    grenze, label = _magnetgrenze(row.get("magnet_key") or row.get("magnet") or "")
    tm = row.get("T_magnet_C")
    if isinstance(tm, (int, float)) and tm > grenze:
        warn.append(f"Magnettemperatur {tm:.0f} °C > Dauergrenze {grenze:.0f} °C "
                    f"({label}) — irreversible Entmagnetisierung")
        ok = False
    tw = row.get("T_winding_C")
    if isinstance(tw, (int, float)) and tw > ISOLIERKLASSE_C:
        warn.append(f"Wicklungstemperatur {tw:.0f} °C > {ISOLIERKLASSE_C:.0f} °C "
                    f"(Isolierklasse H)")
        ok = False
    return {"empfohlen": ok, "warnungen": warn}


def pruefen(results: dict, meta: dict | None = None) -> dict:
    """Alle Kriterien gegen einen gerechneten Lauf."""
    results = results or {}
    s = results.get("summary") or {}
    payload = (meta or {}).get("payload") or {}
    krit = []

    # ── Festigkeit ───────────────────────────────────────────────────────────
    sf = s.get("safety_factor_fem")
    basis = s.get("structural_basis") or ""
    if isinstance(sf, (int, float)):
        if sf < SF_VERSAGEN:
            krit.append(_k("festigkeit", False,
                           f"FEM-Sicherheitsfaktor {sf:.2f} — der Rotor fliesst bei "
                           f"{s.get('fem_rpm', '?')} U/min", sf, SF_VERSAGEN,
                           schwere="versagen", quelle="summary.safety_factor_fem"))
        else:
            krit.append(_k("festigkeit", sf >= SF_ZIEL,
                           f"FEM-Sicherheitsfaktor {sf:.2f} (gefordert {SF_ZIEL:.1f})",
                           sf, SF_ZIEL, quelle="summary.safety_factor_fem"))
    else:
        krit.append(_k("festigkeit", False,
                       f"KEINE Struktur-FEM gerechnet (Basis: {basis or 'unbekannt'}) — "
                       f"die Festigkeitsaussage ruht auf der Ringformel, die die "
                       f"Spannungsspitzen an den Stegen ueber den Magnettaschen nicht "
                       f"kennt", None, SF_ZIEL, schwere="hinweis",
                       quelle="summary.structural_basis"))

    # ── Drehzahlreserve ──────────────────────────────────────────────────────
    msr, rpm_to = s.get("max_safe_rpm"), payload.get("rpm_to")
    if isinstance(msr, (int, float)) and isinstance(rpm_to, (int, float)):
        krit.append(_k("drehzahl", msr >= rpm_to,
                       f"sichere Drehzahl {msr:.0f} 1/min gegen Betriebsmaximum "
                       f"{rpm_to:.0f} 1/min", msr, rpm_to, "1/min",
                       quelle="summary.max_safe_rpm"))

    # ── Temperaturen: stationaer UND in jedem gerechneten Zyklus ─────────────
    grenze, label = _magnetgrenze(payload.get("magnet") or "")
    zyk = _zyklus_temperaturen(results)
    tm, woher_m = _groesstes([(s.get("T_magnet_C"), "Auslegungspunkt")] +
                             [(z["T_m_dauer"], f"{z['zyklus']} (Dauer)") for z in zyk])
    if tm is not None:
        krit.append(_k("magnet_dauer", tm <= grenze,
                       f"Magnettemperatur {tm:.0f} °C ({woher_m}) gegen Dauergrenze "
                       f"{grenze:.0f} °C ({label})", tm, grenze, "°C",
                       quelle="thermal/drivecycle*.thermal.avg"))
    tmp, woher_mp = _groesstes([(z["T_m_peak"], z["zyklus"]) for z in zyk])
    if tmp is not None:
        krit.append(_k("magnet_spitze", tmp <= grenze,
                       f"Magnet-Spitzentemperatur {tmp:.0f} °C ({woher_mp}) gegen "
                       f"{grenze:.0f} °C — teilweise irreversibel", tmp, grenze, "°C",
                       quelle="drivecycle*.thermal.peak"))
    tw, woher_w = _groesstes([(s.get("T_winding_C"), "Auslegungspunkt")] +
                             [(z["T_w_dauer"], f"{z['zyklus']} (Dauer)") for z in zyk])
    if tw is not None:
        krit.append(_k("wicklung_dauer", tw <= ISOLIERKLASSE_C,
                       f"Wicklungstemperatur {tw:.0f} °C ({woher_w}) gegen "
                       f"{ISOLIERKLASSE_C:.0f} °C (Isolierklasse H)",
                       tw, ISOLIERKLASSE_C, "°C", quelle="thermal.steady"))
    twp, woher_wp = _groesstes([(z["T_w_peak"], z["zyklus"]) for z in zyk])
    if twp is not None:
        krit.append(_k("wicklung_spitze", twp <= WICKLUNG_SPITZE_C,
                       f"Wicklungs-Spitzentemperatur {twp:.0f} °C ({woher_wp}) gegen "
                       f"{WICKLUNG_SPITZE_C:.0f} °C", twp, WICKLUNG_SPITZE_C, "°C",
                       quelle="drivecycle*.thermal.peak"))

    # ── Entmagnetisierung durch Ankerrueckwirkung ────────────────────────────
    dem = (results.get("em_advanced") or {}).get("demag") or {}
    if dem:
        risk = bool(dem.get("risk"))
        krit.append(_k("entmagnetisierung", not risk,
                       f"Arbeitspunkt {dem.get('B_operating_T', '?')} T, Abstand zum "
                       f"Knie {dem.get('margin_T', '?')} T bei "
                       f"{dem.get('magnet_temp_C', '?')} °C",
                       dem.get("margin_T"), 0.0, "T", quelle="em_advanced.demag"))

    # ── Fahrzyklus und Fahrzeug ─────────────────────────────────────────────
    zyklus = payload.get("cycle")
    fahrzeug = payload.get("vehicle")
    if zyklus is None and fahrzeug is None:
        krit.append(_k("fahrprofil", False,
                       "Weder Fahrzyklus noch Fahrzeug im Payload — gerechnet wurde "
                       "mit der Vorgabe (WLTP + Autobahn-Volllast am 1600-kg-Pkw). "
                       "Das beschreibt ein Auto, unabhaengig von dieser Maschine",
                       None, None, schwere="verletzt", quelle="meta.payload"))
    elif zyklus and zyklus != "off":
        m = (fahrzeug or {}).get("mass_kg")
        krit.append(_k("fahrprofil", True,
                       f"Zyklus '{s.get('cycle_name') or zyklus}'"
                       + (f", Fahrzeug {m:.0f} kg" if isinstance(m, (int, float))
                          else ", Fahrzeug: Vorgabe (1600 kg Pkw)"),
                       quelle="meta.payload.cycle"))

    verletzt = [x for x in krit if not x["ok"]]
    return {"ok": not verletzt, "kriterien": krit,
            "n_verletzt": len(verletzt),
            "versagen": any(x["schwere"] == "versagen" for x in verletzt)}


def als_text(befund: dict) -> str:
    zeilen = []
    for k in befund["kriterien"]:
        marke = "✓" if k["ok"] else ("✗✗" if k["schwere"] == "versagen"
                                     else "⚠" if k["schwere"] == "hinweis" else "✗")
        zeilen.append(f"  {marke:2} {k['name']:18} {k['text']}")
    kopf = ("BESTANDEN" if befund["ok"]
            else f"{befund['n_verletzt']} Kriterium/Kriterien verletzt"
                 + (" — MECHANISCHES VERSAGEN" if befund["versagen"] else ""))
    return "Sicherheitskriterien: " + kopf + "\n" + "\n".join(zeilen)
