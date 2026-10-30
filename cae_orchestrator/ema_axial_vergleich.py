# -*- coding: utf-8 -*-
"""Paarvergleich fuer den SCHEIBENLAEUFER -- die Entscheidungen VOR der Zeichnung.

Warum ein eigenes Modul und keine Achsen in ``ema_paarvergleich``
-----------------------------------------------------------------
Zwei Gruende, und beide sind inhaltlich:

* **Die Achsen sind andere.** Der radiale Paarvergleich stellt Magnetanordnung,
  Taschenoeffnung, V-Oeffnungswinkel, Wellenverbindung und Wuchtverschraubung
  gegenueber -- eine Scheibe hat davon nichts. Ihre Entscheidungen heissen
  Bauform (wo sich der Anzug aufhebt), ``lambda = Ri/Ro`` (die eine Groesse, die
  es radial gar nicht gibt), Zahnform und Rueckenblech.
* **Der Bewerter ist ein anderer.** ``ema_paarvergleich`` rechnet ueber
  ``ema_optimize._eval_geom``, und das ist der radiale Weg -- Zylinderringe mal
  Blechpaketlaenge. Hier wird ``ema_axial`` gerufen, also Kreisringscheiben mal
  ihrer axialen Dicke.

Beides zusammen heisst: eine axiale Achse im radialen Satz waere eine Zeile, die
richtig aussieht und eine andere Maschine meint. Das Verb bleibt dasselbe
(``cae_cli.py paarvergleich``), der Weg dahinter nicht -- dieselbe Trennung wie
``feld2d``, das sich nach ``ema_maschinenart.Art.feldweg`` verzweigt.

Was hier gerechnet wird -- und was ausdruecklich nicht
-------------------------------------------------------
**Stufe 1, analytisch, Millisekunden.** Kein Feldlauf, keine FEM, keine
Thermiksimulation -- genau wie der radiale Paarvergleich und aus demselben
Grund: das hier ist die Stufe, auf der man *entscheidet*, nicht die, auf der man
*nachweist*. Jede Zahl kommt aus einer Funktion, die es schon gibt
(``ema_axial.auslegung``/``anzug``/``ruecken``/``bandage``/``zahnform``/
``lambda_grenze``, ``ema_thermal.rated_torque``, ``ema_axial_thermik.masse``);
dieses Modul rechnet **keine eigene Physik**.

``B_gap`` kommt aus der **Arbeitsgeraden** (``ema_axial_fdm.eichung_magnet``),
nicht aus einem Feldlauf. Das hat eine Folge, die hier ausgesprochen wird,
damit niemand sie fuer einen Mangel haelt: **YASA und TORUS-NN bekommen auf
dieser Stufe dasselbe B_gap**. Sie unterscheiden sich im Stapel (Joch oder
nicht), in der Masse und darin, wo sich der Anzug aufhebt -- im FELD
unterscheiden sie sich ebenfalls, aber das sagt erst ``axial --stufe feld``
(gemessen am Vorgabe-Payload: YASA 1,1234 T, TORUS-NN 0,9733 T, AFIR 1,1105 T,
einseitig 1,1011 T). Diese Spalte steht deshalb als Hinweis unter der
Bauform-Achse und nicht als Zahl in der Tabelle.

Was der erste Lauf gefunden hat
-------------------------------
Drei der vierzehn Achsen bewegten gar nichts, und **zwei davon zu Unrecht**
-- keiner der Fehler lag in diesem Modul (alle drei in ``BEFUNDE.md``,
16.10.2026):

* **Magnetwerkstoff:** viermal dasselbe ``B_gap``, von N35 bis Ferrit. Er
  wirkt ueber die MODUL-GLOBALEN ``ema_analysis.Br_NdFeB``/``MU_R_MAG``
  (Muster ``run_pipeline``), nicht ueber den Payload -- s. ``bewerte``.
* **Blechsorte:** sie wirkt AUSSCHLIESSLICH ueber ``B_sat_T``, und niemand
  uebergab es; ``ema_axial.zahnform`` fiel auf seine Modulvorgabe 1,70 T.
* **Bauform:** Masse und Bauhoehe standen still, weil ``ema_axial_thermik``
  Zahn, Joch und Ruecken selbst fuehrte statt aus ``ema_axial_fdm``.

Daraus die Regel, die ``vergleiche`` jetzt anwendet: **eine Achse, die bei
mindestens zwei baubaren Optionen keine gezaehlte Kennzahl bewegt, wird
BENANNT** (``wirkungslos`` + ``wirkungslos_grund``, dieselbe Haltung wie
``ema_paramstudy.wirkungslos_grund``). Eine Tabelle mit sechs gleichen
Zeilen sieht nach einem Rechenfehler aus und ist meistens keiner -- und wo
doch, soll es auffallen. Steht kein Grund da, ist das selbst die Auskunft.
Der Grund darf eine FUNKTION des Payloads sein: die Nutzahl ist nur flach,
solange die Nutbreite abgeleitet wird, und ein fester Satz waere im anderen
Fall eine Behauptung gegen die Messung.
"""

from __future__ import annotations

import ema_axial
import ema_axial_fdm as AF
import ema_axial_thermik as AT
import ema_fluss
import ema_pipeline
import ema_thermal

#: Preise je kg -- dieselbe Tabelle wie radial (``ema_screen.PREISE_EUR_KG``),
#: importiert und nicht abgeschrieben: zwei Preislisten waeren zwei verschieden
#: teure Maschinen aus derselben Zeichnung.
from ema_screen import PREISE_EUR_KG

# ── Die eine Bewertung ───────────────────────────────────────────────────────

def _mat(geom: dict) -> tuple:
    """Die vier Werkstoffdicts, wie ``ema_thermal`` sie an ``masse`` reicht."""
    g = geom or {}
    lam = ema_pipeline.LAMINATES
    hp = ema_pipeline.HAIRPIN_MATS
    mg = ema_pipeline.MAGNETS
    return (lam.get(g.get("rotor_lam") or g.get("rotorLam") or "m270_35a",
                    lam["m270_35a"]),
            lam.get(g.get("stator_lam") or g.get("statorLam") or "m270_35a",
                    lam["m270_35a"]),
            hp.get(g.get("hairpin_mat") or g.get("hairpinMat") or "cu_etp",
                   hp["cu_etp"]),
            mg.get(g.get("magnet") or "ndfeb_n35", mg["ndfeb_n35"]))


def bewerte(payload: dict, rpm: float) -> dict:
    """Eine Option: Kennzahlen plus das Urteil, ob sie ueberhaupt baubar ist.

    Die Tore sind **die vorhandenen** und keine zweite Pruefung daneben:
    ``lambda_grenze`` (traegt der Innenrand noch eine Nut?), ``zahnform``
    (saettigt der Zahn?) und ``ruecken`` (ist die Steifigkeit ueberhaupt
    erreichbar?). Reisst eines, steht die Option mit Grund da statt mit Zahlen.
    """
    import ema_analysis

    geom = dict(payload.get("geom") or {})
    axial_mm = payload.get("axial_len") or geom.get("axialLen")
    lam_r, lam_s, _hp, mag = _mat(payload)

    # **Der Magnetwerkstoff wirkt ueber MODUL-GLOBALE, nicht ueber den
    # Payload.** ``ema_axial_fdm.eichung_magnet_spitze`` rechnet
    # ``EA.Br_NdFeB * hm/(hm + EA.MU_R_MAG*kc*g)`` -- genau dasselbe Muster wie
    # ``run_pipeline`` und ``ema_paarvergleich._setz_magnet``. Ohne das
    # Umsetzen lieferte die Achse Magnetwerkstoff gemessen **viermal dieselben
    # 0,8137 T**, von N35 bis Ferrit Y30, und eine Tabelle mit ueberall
    # gleichem B_gap sieht nach einem Befund ueber die Scheibe aus. Gesetzt
    # wird eng um den Aufruf und im ``finally`` zurueck.
    br_alt, mu_alt = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
    try:
        ema_analysis.Br_NdFeB = float(mag.get("Br", br_alt))
        ema_analysis.MU_R_MAG = float(mag.get("mu_r", mu_alt))
        a = ema_axial.auslegung(geom, axial_mm)
        b_gap = AF.eichung_magnet(geom)
        # Die Saettigungsgrenze kommt aus der gewaehlten BLECHSORTE
        # (``LAMINATES[...]["B_sat_T"]``, 1,65..2,00 T). Ohne sie fiel
        # ``zahnform`` auf seine Modulvorgabe 1,70 T zurueck, und die Achse
        # Blechsorte bewegte nichts -- obwohl gerade sie nur ueber diese eine
        # Zahl wirkt. Dasselbe fuer die Platte des Rueckenblechs: ``ruecken``
        # nimmt E und nu aus dem LAEUFERblech.
        zf = ema_axial.zahnform(geom, b_gap,
                                float(lam_s.get("B_sat_T", 0) or 0) or None)
        lam = ema_axial.lambda_grenze(geom)
        an = ema_axial.anzug(geom, b_gap)
        ru = ema_axial.ruecken(geom, b_gap, None, lam_r)
        ba = ema_axial.bandage(geom, rpm)
        nb = ema_axial.nutbreite_befund(geom)
    except Exception as e:                                         # noqa: BLE001
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}
    finally:
        ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG = br_alt, mu_alt

    gruende = []
    if not lam.get("lambda_haelt", True):
        gruende.append(
            f"lambda {lam['lambda_ist']:.3f} unter lambda_min "
            f"{lam['lambda_min']:.3f} — am Innenrand bindet die "
            f"{lam.get('bindet', '?')}")
    if not zf.get("haelt", True):
        gruende.append(
            f"Zahn saettigt: {zf['b_zahn_innen_t']:.3f} T gegen "
            f"B_sat {zf['b_sat_t']:.2f} T ({zf.get('bindende_stelle', '')})")
    if not ru.get("steifigkeit_erreichbar", True):
        gruende.append("Rueckenblech: die geforderte Steifigkeit ist mit "
                       "keiner Dicke erreichbar (Nabe zu klein)")

    kuehl = (payload.get("cooling") or geom.get("cooling") or "water")
    t_dauer = ema_thermal.rated_torque(geom, float(axial_mm or 0.0) or None,
                                       kuehl) if axial_mm else \
        ema_thermal.rated_torque(geom, None, kuehl)

    m = AT.masse(geom, lam_r, lam_s, _hp, mag)
    m_mag = float(m.get("magnet", 0.0))
    m_fe = float(m.get("rotoreisen", 0.0)) + float(m.get("statoreisen", 0.0))
    m_cu = float(m.get("kupfer", 0.0))
    masse = sum(v for v in m.values() if isinstance(v, (int, float)))
    import ema_screen as _scr
    kosten = (m_mag * _scr.preis(payload, "magnet") + m_cu * _scr.preis(payload, "kupfer")
              + float(m.get("rotoreisen", 0.0)) * _scr.preis(payload, "stahl_rotor")
              + float(m.get("statoreisen", 0.0)) * _scr.preis(payload, "stahl_stator"))

    return {
        "ok": not gruende,
        "grund": " · ".join(gruende),
        "bauform": a["bauform"],
        "n_spalte": a["n_spalte"],
        "poles": a["poles"],
        "slots": a["slots"],
        "lambda": a["lambda"],
        "B_gap_T": b_gap,
        "T_dauer_Nm": float(t_dauer or 0.0),
        "anzug_kN": an["kraft_je_spalt_N"] / 1e3,
        "anzug_hebt_auf": bool(an["hebt_sich_auf"]),
        "ruecken_soll_mm": ru["t_soll_m"] * 1000.0,
        "ruecken_bindet": ru.get("bindet", "?"),
        "w_anteil_spalt_pct": ru["w_anteil_spalt"] * 100.0,
        "B_zahn_T": zf["b_zahn_innen_t"],
        "zahn_ausnutzung_pct": zf["b_zahn_innen_t"] / max(zf["b_sat_t"], 1e-9) * 100.0,
        "magnetkraft_kN": ba["kraft_gesamt_N"] / 1e3,
        "klebescher_MPa": ba["klebescherspannung_pa"] / 1e6,
        "b_nut_aussen_mm": nb["b_nut_aussen_mm"],
        "masse_kg": masse,
        "magnet_kg": m_mag,
        "kosten_EUR": kosten,
    }


# ── Die Achsen ───────────────────────────────────────────────────────────────

#: Wohin ein Achsenwert gehoert. Ausdruecklich benannt und nicht an der
#: Funktion abgelesen: `ema_text2ema.SCHEMA` fuehrt dieselbe Unterscheidung
#: (`geom: True/False`), und wer sie raet, schreibt den Wert in einen toten
#: Schluessel -- genau der Fehler, gegen den `cae_cli._ALIAS` gebaut ist.
EBENE_GEOM, EBENE_OBEN = "geom", "payload"


def _setzen(payload: dict, achse: dict, wert) -> None:
    ziel = payload["geom"] if achse.get("ebene", EBENE_GEOM) == EBENE_GEOM \
        else payload
    ziel[achse["schluessel"]] = wert


def _grund(w, basis: dict):
    """Der Grund fuer eine flache Achse -- fest oder aus dem Payload gerechnet.

    Manche Achsen sind immer flach (Blechsorte bewegt nur ``B_sat``), andere
    nur unter einer Bedingung (die Nutzahl, wenn die Nutbreite abgeleitet
    wird). Ein fester Satz waere im zweiten Fall eine Behauptung, die der
    Payload widerlegt.
    """
    return w(basis) if callable(w) else w


def _teiler(slots: int, kandidaten) -> list:
    """Polpaarzahlen, bei denen die Nutzahl aufgeht -- nichts anderes.

    Eine Polzahl, die die Nutzahl nicht teilt, ergibt eine Bruchlochwicklung;
    die gibt es, aber sie ist eine eigene Entscheidung und keine Nebenwirkung
    einer Vergleichsachse. Wer sie will, setzt sie ausdruecklich.
    """
    return [p for p in kandidaten if slots % (2 * int(p)) == 0]


ACHSEN = {
    # Die erste Entscheidung der Scheibe: wo hebt sich der Anzug auf. Sie steht
    # vorn, weil sie ueber Spaltzahl, Stapelhoehe und das halbe Gewicht
    # entscheidet -- und weil sie die einzige ist, die man nachtraeglich nicht
    # mehr aendern kann, ohne alles zu zeichnen.
    "bauform": {
        "titel": "Bauform (wo sich der axiale Anzug aufhebt)",
        "werte": lambda b: list(AF._BAUFORMEN),
        "beschriften": lambda w: {
            "yasa": "YASA — 2 Laeufer, jochloser Staender",
            "torus_nn": "TORUS-NN — 2 Laeufer, Staender mit Umfangsjoch",
            "afir": "AFIR — 2 Staender, 1 Laeufer",
            "einseitig": "einseitig — 1 Luftspalt",
        }.get(w, w),
        "schluessel": "axialBauform", "ebene": EBENE_GEOM,
        "notiz": "Stufe 1 gibt allen dasselbe B_gap (Arbeitsgerade). Im FELD "
                 "trennen sie sich — gemessen YASA 1,1234 · TORUS-NN 0,9733 · "
                 "AFIR 1,1105 · einseitig 1,1011 T; das sagt `axial --stufe "
                 "feld`, nicht diese Tabelle.",
    },
    # Die eine Groesse, die es radial gar nicht gibt.
    "lambda": {
        "titel": "lambda = Ri/Ro (Ringraum)",
        "werte": lambda b: [0.35, 0.45, 0.55, 0.65, 0.75],
        "beschriften": lambda w: f"lambda = {float(w):.2f}",
        "schluessel": "axialLambda", "ebene": EBENE_GEOM,
        "notiz": "Das Moment faellt MONOTON mit lambda (dT/dlambda = "
                 "-2*pi*sigma*Ro^3*lambda^2) — es gibt kein inneres Optimum. "
                 "Bindend ist die Zeichnung am Innenrand, und genau das misst "
                 "`lambda_grenze`.",
    },
    "polzahl": {
        "titel": "Polpaarzahl (Nutzahl muss aufgehen)",
        "werte": lambda b: _teiler(int((b.get("geom") or {}).get("slots", 54)),
                                   (1, 2, 3, 4, 6, 9)),
        "beschriften": lambda w: f"p = {int(w)} ({2 * int(w)} Pole)",
        "schluessel": "p", "ebene": EBENE_GEOM,
        "notiz": "Mehr Pole heisst weniger Fluss je Pol und damit ein duenneres "
                 "Rueckenblech — die Spalte „Ruecken soll“ ist hier die "
                 "eigentliche Aussage.",
        "wirkungslos_grund": "… und sie ist eine LAST, keine Guete, zaehlt also "
                       "nicht mit. Das ist kein Mangel der Achse, sondern "
                       "ihre Aussage: die Polzahl bewegt auf dieser Stufe "
                       "weder Feld noch Moment noch Masse, sondern die "
                       "ANFORDERUNG an das Rueckenblech — lies dazu die "
                       "Spalte „Ruecken soll“ in DIESER Tabelle (am "
                       "Vorgabe-Payload gemessen 74,2 → 11,1 mm von p = 1 "
                       "auf p = 9). Was sie sonst bewegt — "
                       "Ummagnetisierungsverluste, Umrichterfrequenz, "
                       "Wickelkopf — rechnet diese Stufe nicht.",
    },
    "nutzahl": {
        "titel": "Nutzahl",
        "werte": lambda b: [q for q in (24, 36, 48, 54, 60, 72)
                            if q % 3 == 0
                            and q % max(2 * int((b.get("geom") or {}).get("p", 3)), 1) == 0],
        "beschriften": lambda w: f"{int(w)} Nuten",
        "schluessel": "slots", "ebene": EBENE_GEOM,
        # **Ob sie wirkungslos ist, haengt am Payload** -- deshalb eine
        # Funktion und kein fester Satz. Steht `axialNutBreiteMm` auf 0, wird
        # die Nutbreite als ANTEIL der Teilung abgeleitet (`slotWidthRatio`),
        # dann kuerzt sich die Teilung heraus und die Achse bewegt nichts.
        # Steht dort ein Millimetermass, ist die Nut parallelflankig und von q
        # unabhaengig -- dann bewegt die Nutzahl sehr wohl den Zahn (gemessen
        # 1,211 bis 1,653 T ueber 24..54 Nuten). Ein fester Satz waere in
        # einem der beiden Faelle schlicht falsch gewesen.
        "wirkungslos_grund": lambda b: (
            "Die Nutteilung kuerzt sich heraus: `axialNutBreiteMm` steht auf "
            "0, die Nutbreite ist also ein ANTEIL der Teilung "
            "(`slotWidthRatio`), damit ist B_zahn = B_gap/((1-swr)*k_fe) "
            "nutzahlunabhaengig und im Kupfervolumen ist q*b_nut konstant. "
            "Der Hebel auf die Saettigung heisst dann `slotWidthRatio`. Mit "
            "einer Nutbreite in MILLIMETERN bewegt diese Achse den Zahn sehr "
            "wohl. Was sie in beiden Faellen NICHT zeigt — Wickelfaktor, "
            "Oberwellen, Rastmoment —, rechnet diese Stufe nicht."
            if not float((b.get("geom") or {}).get("axialNutBreiteMm", 0) or 0)
            else None),
    },
    "zahnform": {
        "titel": "Zahnform",
        "werte": lambda b: ["keil", "parallel"],
        "beschriften": lambda w: {"keil": "Keilzahn (b ~ r) — B_zahn ueber r konstant",
                                  "parallel": "parallelflankig — B_zahn steigt nach innen"
                                  }.get(w, w),
        "schluessel": "axialZahnform", "ebene": EBENE_GEOM,
    },
    "magnetwerkstoff": {
        "titel": "Magnetwerkstoff",
        "werte": lambda b: list(ema_pipeline.MAGNETS),
        "beschriften": lambda w: ema_pipeline.MAGNETS.get(w, {}).get("label", w),
        "schluessel": "magnet", "ebene": EBENE_OBEN,
        "notiz": "Der Preis je kg haengt seit dem 30.10.2026 an der Sorte "
                 "(`ema_screen.PREIS_FAKTOR`, Platzhalter zum Rangieren: Ferrit "
                 "rund ein Zehntel von NdFeB). Zahlen darueber hinaus: B_gap und "
                 "ob der Zahn dabei saettigt.",
    },
    "magnetdicke": {
        "titel": "Magnetdicke",
        "werte": lambda b: [3.0, 4.5, 6.0, 8.0, 10.0],
        "beschriften": lambda w: f"{float(w):.1f} mm",
        "schluessel": "axialMagnetDicke", "ebene": EBENE_GEOM,
    },
    "luftspalt": {
        "titel": "Luftspalt",
        "werte": lambda b: [0.5, 0.7, 1.0, 1.5, 2.0],
        "beschriften": lambda w: f"{float(w):.1f} mm",
        "schluessel": "axialSpaltMm", "ebene": EBENE_GEOM,
        "notiz": "Der Spalt bewegt hier zweierlei zugleich: das Feld ueber die "
                 "Arbeitsgerade UND den zulaessigen Durchbiegungsanteil, denn "
                 "der ist ein Anteil DES SPALTS.",
    },
    "polbedeckung": {
        "titel": "Polbedeckung",
        "werte": lambda b: [0.70, 0.80, 0.90, 1.00],
        "beschriften": lambda w: f"{float(w) * 100:.0f} %",
        "schluessel": "axialPolbedeckung", "ebene": EBENE_GEOM,
    },
    "zahnlaenge": {
        "titel": "Zahnlaenge (axial)",
        "werte": lambda b: [12.0, 18.0, 25.0, 35.0, 50.0],
        "beschriften": lambda w: f"{float(w):.0f} mm",
        "schluessel": "axialZahnLaengeMm", "ebene": EBENE_GEOM,
        "notiz": "Sie bewegt NUR Masse und Kosten. Das Moment der Scheibe "
                 "haengt am RINGRAUM (Ro, lambda), nicht an der axialen "
                 "Zahnlaenge — die ist der Platz fuer Kupfer und damit eine "
                 "Frage des Strombelags, den diese Stufe nicht rechnet.",
    },
    "rueckenblech": {
        "titel": "Rueckenblech des Laeufers (gezeichnet)",
        "werte": lambda b: [6.0, 10.0, 13.0, 20.0, 30.0],
        "beschriften": lambda w: f"{float(w):.0f} mm",
        "schluessel": "axialJochLaeuferMm", "ebene": EBENE_GEOM,
        "notiz": "Ob die gezeichnete Dicke REICHT, sagt die Spalte „Ruecken "
                 "soll“ daneben — sie ist die Anforderung, nicht die Zeichnung.",
    },
    "stapel": {
        "titel": "Gestapelte Teilmaschinen",
        "werte": lambda b: [1, 2, 3],
        "beschriften": lambda w: f"{int(w)} Stueck",
        "schluessel": "axialStapel", "ebene": EBENE_GEOM,
    },
    "kuehlung": {
        "titel": "Kuehlung",
        "werte": lambda b: list(ema_thermal.COOLING_PRESETS),
        "beschriften": lambda w: {"natural": "Natuerliche Konvektion",
                                  "forced": "Zwangsluft (Luefter)",
                                  "water": "Wassermantel",
                                  "oil": "Oelkuehlung"}.get(w, w),
        "schluessel": "cooling", "ebene": EBENE_OBEN,
        "notiz": "Wirkt hier NUR ueber die zulaessige Schubspannung in "
                 "`rated_torque` — kein Thermikmodell, keine Temperatur. Die "
                 "rechnet `run analyse`.",
    },
    "blech": {
        "titel": "Blechsorte (Saettigungsgrenze des Zahns)",
        "werte": lambda b: list(ema_pipeline.LAMINATES),
        "beschriften": lambda w: ema_pipeline.LAMINATES.get(w, {}).get("label", w),
        "schluessel": "stator_lam", "ebene": EBENE_OBEN,
        "notiz": "Wirkt hier NUR ueber `B_sat_T` (1,65 .. 2,00 T), also allein "
                 "ueber das Urteil „Zahn haelt“. Masse und Ummagnetisierungs"
                 "verluste bewegt sie nicht: `LAMINATES` fuehrt keine Dichte, "
                 "und Eisenverluste rechnet diese Stufe gar nicht.",
        "wirkungslos_grund": "… und genau deshalb steht in den Zahlenspalten "
                       "ueberall dasselbe: die Blechsorte entscheidet hier "
                       "nur, WELCHE Optionen uebrig bleiben, nicht wie gut "
                       "sie sind. Dass M250-35A als einzige ausfaellt, IST "
                       "das Ergebnis dieser Achse.",
    },
}


# ── Durchspielen ─────────────────────────────────────────────────────────────

#: Was in der Tabelle steht. ``zaehlt`` sagt, ob die Groesse in die
#: Spannweiten-Rangliste eingeht: der Anzug und die Klebescherspannung tun es
#: NICHT -- sie sind Lasten, keine Guete, und „mehr Anzug“ ist weder besser
#: noch schlechter, sondern eine Anforderung an den Staender.
SPALTEN = (
    ("B_gap_T", "B_gap [T]", True),
    ("T_dauer_Nm", "T_dauer [Nm]", True),
    ("masse_kg", "Masse [kg]", True),
    ("magnet_kg", "Magnet [kg]", True),
    ("kosten_EUR", "Kosten [EUR]", True),
    ("B_zahn_T", "B_Zahn [T]", True),
    ("anzug_kN", "Anzug/Spalt [kN]", False),
    ("ruecken_soll_mm", "Ruecken soll [mm]", False),
    ("w_anteil_spalt_pct", "Durchbieg. [% Spalt]", False),
    ("magnetkraft_kN", "Magnetkraft [kN]", False),
    ("klebescher_MPa", "Kleber [MPa]", False),
)


def vergleiche(basis: dict, achsen: list | None = None,
               rpm: float | None = None) -> dict:
    """Jede Achse durchspielen, je Achse jede Option gegen jede."""
    if not basis.get("geom"):
        raise ValueError("Der Paarvergleich braucht einen Payload mit geom.")
    if ema_fluss.flussweg(basis["geom"]) != "axial":
        raise ValueError("Das hier ist der AXIALE Paarvergleich. Ein radialer "
                         "Payload gehoert nach ema_paarvergleich.")
    namen = achsen or list(ACHSEN)
    unbekannt = [n for n in namen if n not in ACHSEN]
    if unbekannt:
        raise ValueError(f"Unbekannte Achse(n): {', '.join(unbekannt)}. "
                         f"Bekannt: {', '.join(ACHSEN)}")
    rpm = float(rpm or basis.get("rpm_from") or 5000.0)

    aus = {}
    for name in namen:
        achse = ACHSEN[name]
        werte = achse["werte"](basis)
        if len(werte) < 2:
            # Dieselben Schluessel wie eine gerechnete Achse -- ein
            # JSON-Leser soll nicht je nach Ausgang ein anderes Dict bekommen.
            aus[name] = {"titel": achse["titel"], "uebersprungen":
                         "weniger als zwei Optionen bei dieser Grundgeometrie",
                         "schluessel": achse["schluessel"],
                         "notiz": achse.get("notiz"),
                         "optionen": [], "paare": [], "spannweite": {},
                         "wirkungslos": False, "wirkungslos_grund": None}
            continue
        optionen = []
        for w in werte:
            p = {k: (dict(v) if isinstance(v, dict) else v)
                 for k, v in basis.items()}
            p["geom"] = dict(basis["geom"])
            _setzen(p, achse, w)
            e = bewerte(p, rpm)
            e["wert"] = w
            e["label"] = achse["beschriften"](w)
            optionen.append(e)
        sp = _spannweite(optionen)
        aus[name] = {
            "titel": achse["titel"],
            "schluessel": achse["schluessel"],
            "notiz": achse.get("notiz"),
            "optionen": optionen,
            "paare": _paare(optionen),
            "spannweite": sp,
            # **Eine flache Achse wird BENANNT.** Dieselbe Regel wie
            # `ema_paramstudy.wirkungslos_grund` und aus demselben Grund: eine
            # Tabelle mit sechs gleichen Zeilen sieht nach einem Rechenfehler
            # aus und ist meistens keiner — und wo doch, soll es auffallen.
            # Steht kein Grund da, ist das selbst die Auskunft: dann ist offen,
            # warum nichts passiert.
            "wirkungslos": (not sp) and sum(1 for o in optionen
                                            if o.get("ok")) >= 2,
            "wirkungslos_grund": _grund(achse.get("wirkungslos_grund"), basis),
        }
    return {"achsen": aus, "rpm": rpm,
            "bauform": (basis.get("geom") or {}).get("axialBauform", "yasa")}


def _paare(optionen: list) -> list:
    """Jede Option gegen jede -- aber nur die baubaren."""
    gut = [o for o in optionen if o.get("ok")]
    paare = []
    for i in range(len(gut)):
        for j in range(i + 1, len(gut)):
            a, b = gut[i], gut[j]
            fuer_a, fuer_b, still = [], [], []
            for sch, lab, zaehlt in SPALTEN:
                if not zaehlt:
                    continue
                va, vb = a.get(sch), b.get(sch)
                if va is None or vb is None:
                    continue
                if abs(va - vb) <= 1e-9 * max(abs(va), abs(vb), 1.0):
                    still.append(lab)
                    continue
                # Klein ist besser bei Masse, Magnetmasse, Kosten, B_Zahn.
                besser_klein = sch in ("masse_kg", "magnet_kg", "kosten_EUR",
                                       "B_zahn_T")
                a_gewinnt = (va < vb) if besser_klein else (va > vb)
                (fuer_a if a_gewinnt else fuer_b).append(lab)
            paare.append({"a": a["label"], "b": b["label"],
                          "fuer_a": fuer_a, "fuer_b": fuer_b,
                          "bewegt_nicht": still})
    return paare


def _spannweite(optionen: list) -> dict:
    gut = [o for o in optionen if o.get("ok")]
    aus = {}
    for sch, lab, zaehlt in SPALTEN:
        if not zaehlt:
            continue
        w = [o[sch] for o in gut if isinstance(o.get(sch), (int, float))]
        if len(w) < 2 or max(abs(x) for x in w) < 1e-12:
            continue
        lo, hi = min(w), max(w)
        sp = (hi - lo) / max(abs(lo), 1e-12) * 100.0
        # Eine Spanne von 0,0 % ist keine Spanne. Sie eingetragen zu lassen
        # fuellte die Rangliste mit Nullzeilen UND machte die Pruefung „bewegt
        # diese Achse ueberhaupt etwas“ blind: das Dict war dann nicht leer.
        if sp > 1e-6:
            aus[lab] = sp
    return aus


# ── Ausgabe ──────────────────────────────────────────────────────────────────

def als_text(erg: dict, paare: bool = True, max_paare: int = 8) -> str:
    z = []
    z.append(f"Axialfluss-Paarvergleich — Stufe 1 (analytisch), "
             f"{erg['rpm']:.0f} 1/min")
    z.append("")

    # Die Rangliste: welche Entscheidung bewegt was am staerksten.
    rang = {}
    for name, a in erg["achsen"].items():
        for lab, sp in (a.get("spannweite") or {}).items():
            if sp > rang.get(lab, (0.0, ""))[0]:
                rang[lab] = (sp, name)
    if rang:
        z.append("WAS BEWEGT WAS — Spannweite ueber die Optionen EINER Achse, in %.")
        z.append(f"  {'Kennzahl':<22}{'staerkste Achse':<22}{'Spanne':>10}")
        for lab, (sp, name) in sorted(rang.items(), key=lambda x: -x[1][0]):
            z.append(f"  {lab:<22}{name:<22}{sp:>9.0f} %")
        z.append("")

    for name, a in erg["achsen"].items():
        if a.get("uebersprungen"):
            z.append(f"── {a['titel']}  — uebersprungen: {a['uebersprungen']}")
            z.append("")
            continue
        gut = sum(1 for o in a["optionen"] if o.get("ok"))
        z.append(f"── {a['titel']}  ({gut} von {len(a['optionen'])} baubar)")
        if a.get("notiz"):
            z.append(f"    ⓘ {a['notiz']}")
        if a.get("wirkungslos"):
            z.append("    △ bewegt KEINE gezaehlte Kennzahl — "
                     + (a.get("wirkungslos_grund")
                        or "und warum, ist hier nicht geklaert. Eine flache "
                           "Achse ohne Begruendung ist kein Ergebnis."))
        kopf = f"  {'Option':<44}"
        for _, lab, _z in SPALTEN:
            kopf += f"{lab:>21}"
        z.append(kopf)
        for o in a["optionen"]:
            if not o.get("ok"):
                z.append(f"  {o['label'][:44]:<44}✗ {o.get('grund', '')[:110]}")
                continue
            zeile = f"  {o['label'][:44]:<44}"
            for sch, _lab, _z in SPALTEN:
                v = o.get(sch)
                zeile += f"{v:>21.4g}" if isinstance(v, (int, float)) else f"{'—':>21}"
            z.append(zeile)
            if not o.get("anzug_hebt_auf"):
                z.append("        ⚠ der Anzug hebt sich NICHT auf — er liegt "
                         "unausgeglichen am Lager")
            if a.get("schluessel") == "axialJochLaeuferMm":
                ist = float(o.get("wert") or 0.0)
                if ist and ist < o.get("ruecken_soll_mm", 0.0):
                    z.append(f"        ⚠ gezeichnet {ist:.0f} mm gegen "
                             f"{o['ruecken_soll_mm']:.1f} mm noetig "
                             f"(bindet: {o['ruecken_bindet']})")
        if paare and a["paare"]:
            z.append("")
            for p in a["paare"][:max_paare]:
                z.append(f"    {p['a'][:30]} GEGEN {p['b'][:30]}")
                if p["fuer_a"]:
                    z.append(f"      fuer links : {', '.join(p['fuer_a'])}")
                if p["fuer_b"]:
                    z.append(f"      fuer rechts: {', '.join(p['fuer_b'])}")
                if p["bewegt_nicht"]:
                    z.append(f"      bewegt NICHT: {', '.join(p['bewegt_nicht'])}")
        z.append("")

    z.append("Stufe 1, analytisch — kein Feldlauf, keine FEM, keine "
             "Thermiksimulation. B_gap kommt aus der ARBEITSGERADEN, die "
             "Kuehlung wirkt nur ueber die zulaessige Schubspannung, und die "
             "Spalten Anzug / Ruecken / Durchbiegung / Magnetkraft sind "
             "LASTEN und keine Guete — sie gehen in die Rangliste nicht ein. "
             "Was hier oben steht, rechnet danach `axial --stufe feld` und "
             "`run analyse` nach.")
    return "\n".join(z)
