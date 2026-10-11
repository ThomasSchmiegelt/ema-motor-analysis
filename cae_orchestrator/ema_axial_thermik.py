"""Thermik der Scheibenmaschine -- ein eigenes NETZ, nicht das radiale mit anderen Zahlen.

Warum ueberhaupt ein eigenes Modul
-----------------------------------
``ema_thermal.conductances`` ist ein Schalennetz von innen nach aussen: Welle ->
Laeufer -> Luftspalt -> Staender -> Gehaeuse, und jede Flaeche darin ist ein
Zylindermantel ``2*pi*R*L``. Das ist nicht die falsche Parametrierung einer
Scheibe, sondern die falsche TOPOLOGIE -- deshalb hat ``run_thermal_analysis``
den Axialfluss bisher ausdruecklich abgewiesen statt ihn durchzurechnen. Am
Vorgabe-Payload lief die radiale Rechnung naemlich klaglos durch und meldete
68,2 / 81,8 °C: plausible Zahlen fuer eine Maschine, die es nicht gibt.

Drei Dinge sind an der Scheibe wirklich anders, und sie sind der ganze Grund:

1. **Der Staender hat keinen langen Zylindermantel nach aussen.** Beim YASA
   sitzt er ZWISCHEN zwei Scheiben; nach aussen hat er nur ein schmales Band
   ``2*pi*Ro*(Zahn+Joch)``, und bei jochlosem Bau fast nichts. Der radiale
   Hauptweg Staendereisen -> Gehaeuse ist hier also der SCHWACHE.
2. **Dafuer liegt die WICKLUNG frei.** Die Wickelkoepfe stehen innen UND aussen
   am Ringraum und sind beim YASA vergossen -- das ist der Hauptweg, und er
   existiert radial so nicht. Wer ihn weglaesst, rechnet eine Scheibe, die sich
   nur durch ihr Eisen kuehlt.
3. **Die Laeuferscheiben sind hervorragende Konvektoren.** Ihre Rueckseite ist
   eine frei rotierende Scheibe; dafuer gibt es eine der bestbelegten
   Korrelationen ueberhaupt (Cobb/Saunders, Dorfman: ``Nu = 0,015*Re^0,8``).
   Radial gibt es diesen Pfad nicht, der Laeufer ist dort eingeschlossen --
   ``build_GA`` hatte deshalb gar keine Kante Laeufer->Gehaeuse.

Was GETEILT wird, ist der Loeser. ``build_GA``/``solve_steady``/
``solve_transient`` kennen nur Leitwerte und Kapazitaeten, keine Geometrie --
das ist die saubere Nahtstelle, und ein zweiter Loeser waere die Stelle, an der
die beiden Wege beim naechsten Fehlerbericht auseinanderlaufen.

Was das hier NICHT ist
-----------------------
Ein Netz aus KORRELATIONEN, kein geloestes Temperaturfeld -- genauso wie das
radiale. Die Zahlen unten sind benannt und einzeln nachschlagbar; wo eine
Annahme steht, steht das Wort. Insbesondere:

* ``H_VERGUSS`` ist eine Annahme und bewusst KLEINER als die 1500 W/m^2K, die
  ``ema_thermal`` fuer den Querpressverband Staender/Gehaeuse nimmt: ein
  vergossener Wickelkopf ist keine Metall-auf-Metall-Pressung.
* Der Luftspalt wird als Waermeleitung mit einem Drehzahlzuschlag gerechnet.
  Bei ``s/Ro = 0,008`` ist das Rotor-Stator-Spaltverhaeltnis klein (Couette),
  dort traegt die Leitung; die freie Scheibenkorrelation gilt fuer die
  RUECKSEITE, nicht fuer den Spalt.
* Eine Wicklung mit radialen Staeben hat ueber dem Radius eine veraenderliche
  Stromdichte, und der Zahn wird nach aussen breiter. Das Netz hat EINEN
  Wicklungsknoten und kennt diesen Verlauf nicht -- es sagt also nichts
  darueber, ob der Innenrand heisser ist als der Aussenrand, obwohl er es
  wegen der schmaleren Zaehne sein wird.
"""
from __future__ import annotations

import math

import ema_axial
import ema_fluss

#: Waermeleitfaehigkeit Luft [W/mK] und kinematische Zaehigkeit [m^2/s] bei ~60 °C.
K_LUFT = 0.028
NU_LUFT = 1.9e-5

#: Freie rotierende Scheibe, turbulent: ``Nu = C * Re^n`` (Cobb & Saunders 1956;
#: Dorfman, *Hydrodynamic Resistance and Heat Loss of Rotating Solids*).
#: ``Re = omega*Ro^2/nu``. Unter Re ~ 2,4e5 ist die Scheibe laminar
#: (``Nu = 0,36*Re^0,5``), darueber turbulent -- beide Aeste stehen in `_h_scheibe`.
SCHEIBE_C_TURB, SCHEIBE_N_TURB = 0.015, 0.8
SCHEIBE_C_LAM, SCHEIBE_N_LAM = 0.36, 0.5
SCHEIBE_RE_KRIT = 2.4e5

#: Kontaktleitwert vergossener Wickelkopf -> Gehaeuse [W/m^2K]. **Annahme.**
#: Kleiner als die 1500 des Querpressverbands in `ema_thermal.conductances`,
#: weil ein Verguss keine Metallpressung ist.
H_VERGUSS = 500.0

#: Kontaktleitwert Staenderrand -> Gehaeuse [W/m^2K] -- dieselbe Groesse und
#: derselbe Wert wie radial; sie wird hier nur ueber eine viel kleinere Flaeche
#: wirksam, und genau das ist die Aussage.
H_RAND = 1500.0

#: Klebespalt Magnet -> Laeuferscheibe.
K_KLEBER, T_KLEBER_M = 0.8, 0.15e-3

#: Zuschlag auf die Spaltleitung durch die Drehung. Bei kleinem Spaltverhaeltnis
#: (hier s/Ro ~ 0,008) bleibt die Stroemung couetteartig; der Zuschlag waechst
#: mild mit Re und wird gedeckelt, damit er nicht zur Hauptaussage wird.
SPALT_ZUSCHLAG_MAX = 3.0


def _h_scheibe(rpm: float, ro_m: float) -> tuple[float, float, str]:
    """Waermeuebergang auf der Rueckseite einer frei rotierenden Scheibe."""
    om = 2.0 * math.pi * max(rpm, 0.0) / 60.0
    re = om * ro_m * ro_m / NU_LUFT
    if re < 1.0:
        return 5.0, re, "ruhend (freie Konvektion angenommen)"
    if re < SCHEIBE_RE_KRIT:
        nu = SCHEIBE_C_LAM * re ** SCHEIBE_N_LAM
        art = "laminar"
    else:
        nu = SCHEIBE_C_TURB * re ** SCHEIBE_N_TURB
        art = "turbulent"
    return max(5.0, nu * K_LUFT / ro_m), re, art


def _zahl(geom: dict, schluessel: str, ersatz: float) -> float:
    """``geom[schluessel]`` als Zahl -- und ``None`` gilt als FEHLT.

    ``dict.get(k, ersatz)`` schuetzt nur gegen einen fehlenden Schluessel, nicht
    gegen einen vorhandenen mit dem Wert ``None`` -- und die Payloads dieses
    Werkzeugs tragen Nullen: ``ema_text2ema.SCHEMA`` hat fuer jeden axialen
    Schluessel ``default: None``, und wer einen Payload aus dem Schema
    aufbaut, bekommt sie. ``float(None)`` ist dann ein ``TypeError`` mitten in
    der Thermik, und die Meldung nennt den Schluessel nicht einmal (gemessen
    beim Bauen von ``test_axial_em3d.py``, 06.10.2026).
    """
    v = (geom or {}).get(schluessel)
    if v is None or v == "":
        return float(ersatz)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(ersatz)


def _geo(geom: dict) -> dict:
    """Die Masse der Scheibe in Metern -- einmal gerechnet, von beiden gelesen."""
    a = ema_axial.auslegung(geom, None)
    ro, ri = a["r_aussen_m"], a["r_innen_m"]
    # Nabe: die ausdrueckliche axiale Angabe gewinnt, sonst die Welle, sonst 60 mm.
    _nd = _zahl(geom, "axialNabeD", 0.0) or _zahl(geom, "shaftD", 60.0)
    r_nabe = max(_nd / 2000.0, 1e-3)
    h_wk = _zahl(geom, "axialWickelkopfMm", 14.0) / 1000.0
    return {
        "a": a, "ro": ro, "ri": ri,
        "A_ring_m2": math.pi * (ro * ro - ri * ri),
        "q": int(a["slots"]),
        "l_zahn": _zahl(geom, "axialZahnLaengeMm", 25.0) / 1000.0,
        "joch_s": _zahl(geom, "axialJochStaenderMm", 12.0) / 1000.0,
        "joch_r": _zahl(geom, "axialJochLaeuferMm", 13.0) / 1000.0,
        # **Nicht `axialNutBreiteMm` roh.** Dort ist 0 keine Nut von 0 mm,
        # sondern die Anweisung „aus `slotWidthRatio` ableiten" -- genau so
        # steht es in `AXIAL_VORGABE` und so liest es `ema_axial.nutbreite_mm`,
        # das sich selbst als **die EINE Quelle** der Nutbreite ausweist (und
        # dort steht auch, was zwei Quellen kosteten: 42 % Unterschied und ein
        # Saettigungsurteil ueber einen Zahn, den niemand gezeichnet hat).
        # Diese Zeile war die zweite Quelle, und sie hat nicht nur gerechnet:
        # mit `axialNutBreiteMm = 0` lief `ema_axial_em3d.baue_netz` in ein
        # nacktes `Exception: Degenerate box` aus Gmsh (ein Quader der Breite
        # null), also genau in das „auch geht es in Elmer nicht" vom
        # 09.10.2026. Der Wert gilt am AUSSENrand -- dort ist die Nut am
        # weitesten, und das Volumen unten rechnet mit der parallelflankigen
        # Nut, deren Breite nicht am Radius haengt.
        "b_nut": ema_axial.nutbreite_mm(
            geom, a["r_aussen_m"] * 1000.0) / 1000.0,
        "h_wk": h_wk,
        "d_mag": a["magnet_dicke_m"], "spalt": a["luftspalt_m"],
        "n_rotor": 2 if a["bauform"] in ("yasa", "torus_nn") else 1,
        "n_stator": 2 if a["bauform"] == "afir" else 1,
        "r_nabe_m": r_nabe, "r_geh_m": ro + h_wk + 0.008,
        "l_ges_m": stapelhoehe(geom),
    }


def masse(geom: dict, mat: dict, st_mat: dict, hp_mat: dict, mag: dict) -> dict:
    """Die Massen der Scheibe, aus ihrer eigenen Geometrie.

    Keine davon kommt aus dem radialen Modell: dort ist jedes Volumen ein
    Zylinderring mal Blechpaketlaenge, hier ist es eine KREISRINGSCHEIBE mal
    ihrer axialen Dicke.
    """
    G = _geo(geom)
    a, ro, ri, A_ring = G["a"], G["ro"], G["ri"], G["A_ring_m2"]
    q, l_zahn, joch_s = G["q"], G["l_zahn"], G["joch_s"]
    joch_r, b_nut, h_wk = G["joch_r"], G["b_nut"], G["h_wk"]
    d_mag, n_rot, n_st = G["d_mag"], G["n_rotor"], G["n_stator"]

    # Nutvolumen: die Nut ist parallelflankig, ihre Breite haengt also NICHT am
    # Radius -- das Volumen ist schlicht b*(ro-ri)*l_zahn je Nut.
    v_nut = q * b_nut * (ro - ri) * l_zahn
    # Wickelkopf innen UND aussen: zwei Toren um den Ringraum.
    v_wk = (2.0 * math.pi * ro * h_wk * l_zahn
            + 2.0 * math.pi * max(ri - h_wk, 1e-4) * h_wk * l_zahn)
    rho_cu = float(hp_mat.get("rho", 8960.0))
    m_cu = (v_nut * 0.45 + v_wk * 0.35) * rho_cu          # Fuellgrade als Annahme

    rho_fe = float(st_mat.get("rho", 7650.0))
    v_zahn = (A_ring * l_zahn - v_nut) * n_st
    v_joch_s = A_ring * joch_s * n_st
    m_st = (v_zahn + v_joch_s) * rho_fe

    rho_mag = float(mag.get("rho", 7500.0))
    m_mag = A_ring * d_mag * a["polbedeckung"] * rho_mag * n_rot

    rho_ri = float(mat.get("rho", 7650.0))
    r_nabe = G["r_nabe_m"]
    A_scheibe = math.pi * (ro * ro - r_nabe * r_nabe)
    m_ri = A_scheibe * joch_r * rho_ri * n_rot

    # Welle ueber die ganze Baulaenge; Gehaeuse als kurzer dicker Topf.
    l_ges = G["l_ges_m"]
    m_sh = math.pi * r_nabe ** 2 * (l_ges + 0.06) * rho_ri
    r_geh = G["r_geh_m"]
    v_geh = (2.0 * math.pi * r_geh * l_ges + 2.0 * math.pi * r_geh ** 2) * 0.006
    m_geh = v_geh * 2700.0
    return {"kupfer": m_cu, "staendereisen": m_st, "magnet": m_mag,
            "laeufereisen": m_ri, "welle": m_sh, "gehaeuse": m_geh,
            "A_ring_m2": A_ring, "n_rotor": n_rot, "n_stator": n_st,
            "l_ges_m": l_ges, "r_nabe_m": r_nabe, "r_geh_m": r_geh}


def stapelhoehe(geom: dict) -> float:
    """Axiale Baulaenge [m] -- dieselbe Schichtung, aus der die Seite zeichnet."""
    a = ema_axial.auslegung(geom, None)
    l_zahn = _zahl(geom, "axialZahnLaengeMm", 25.0) / 1000.0
    joch_s = _zahl(geom, "axialJochStaenderMm", 12.0) / 1000.0
    joch_r = _zahl(geom, "axialJochLaeuferMm", 13.0) / 1000.0
    d_mag = a["magnet_dicke_m"]
    g = a["luftspalt_m"]
    n_st = 2 if a["bauform"] == "afir" else 1
    n_rot = 2 if a["bauform"] in ("yasa", "torus_nn") else 1
    h = n_st * (l_zahn + joch_s) + n_rot * (d_mag + joch_r) + a["n_spalte"] * g
    return h * max(1, int(geom.get("axialStapel", 1)))


def kapazitaeten(geom: dict, mat: dict, st_mat: dict, hp_mat: dict,
                 mag: dict) -> dict:
    """Waermekapazitaeten -- dieselben Schluessel wie ``ema_thermal``."""
    import ema_thermal as TH
    m = masse(geom, mat, st_mat, hp_mat, mag)
    return {
        "C_winding": round(m["kupfer"] * TH.CP_CU, 1),
        "C_stator": round(m["staendereisen"] * TH.CP_FE, 1),
        "C_rotor": round(m["laeufereisen"] * TH.CP_FE, 1),
        "C_magnet": round(m["magnet"] * TH.CP_NDFEB, 1),
        "C_shaft": round(m["welle"] * TH.CP_FE, 1),
        "C_housing": round(m["gehaeuse"] * TH.CP_AL, 1),
        "_masses_g": {k: round(v * 1000, 1) for k, v in m.items()
                      if k in ("kupfer", "staendereisen", "magnet",
                               "laeufereisen", "welle", "gehaeuse")},
    }


def leitwerte(geom: dict, cooling: str, rpm: float,
              htc_oil: float = 0.0, wetted_area_m2: float = 0.0) -> dict:
    """Die Leitwerte des Scheibennetzes [W/K] -- Schluessel wie ``ema_thermal``.

    Neu gegenueber dem radialen Netz ist ``G_ri_h``: die Rueckseite der
    Laeuferscheibe gibt ihre Waerme direkt in den Gehaeuseraum ab. Radial gibt
    es diese Kante nicht (der Laeufer ist eingeschlossen), deshalb traegt
    ``ema_thermal.build_GA`` sie mit Vorgabe 0 -- dieselbe Bauform wie
    ``G_w_cool`` fuer die CFD-Kopplung, und damit bleibt der radiale Weg Ziffer
    fuer Ziffer derselbe.
    """
    import ema_thermal as TH
    m = _geo(geom)
    a, ro, ri, A_ring = m["a"], m["ro"], m["ri"], m["A_ring_m2"]
    q, l_zahn, joch_s = m["q"], m["l_zahn"], m["joch_s"]
    joch_r, h_wk, spalt = m["joch_r"], m["h_wk"], m["spalt"]
    n_sp, n_rot = a["n_spalte"], m["n_rotor"]

    # 1. Wicklung -> Staendereisen: Nutisolierung. Die Nut laeuft RADIAL, ihre
    #    Wand ist also (ro-ri) lang und l_zahn hoch -- zwei Flanken je Nut.
    A_nutwand = q * 2.0 * (ro - ri) * l_zahn
    G_w_si = min(TH.K_INS * A_nutwand / TH.T_INS_M, 100.0)

    # 2. Wicklung -> Gehaeuse ueber die freiliegenden WICKELKOEPFE. Der Weg, den
    #    es radial so nicht gibt, und beim YASA der Hauptweg.
    A_wk = (2.0 * math.pi * (ro + h_wk) * l_zahn
            + 2.0 * math.pi * max(ri - h_wk, 1e-3) * l_zahn)
    G_w_h = H_VERGUSS * A_wk

    # 3. Staendereisen -> Gehaeuse: nur das schmale Randband. Bei jochlosem
    #    YASA ist das fast nichts, und das ist die Aussage der Bauform.
    A_rand = 2.0 * math.pi * ro * (l_zahn + joch_s) * m["n_stator"]
    G_si_h = H_RAND * A_rand

    # 4. Ueber den Luftspalt auf die Magnete. Kleines Spaltverhaeltnis
    #    (s/Ro = {:.4f}) -> couetteartig, die LEITUNG traegt; der Drehzahl-
    #    zuschlag waechst mild und ist gedeckelt.
    om = 2.0 * math.pi * max(rpm, 0.0) / 60.0
    re_sp = om * ro * spalt / NU_LUFT
    zuschlag = min(SPALT_ZUSCHLAG_MAX, 1.0 + 0.012 * re_sp ** 0.5)
    G_si_m = K_LUFT * (A_ring * n_sp) / spalt * zuschlag

    # 5. Magnet -> Laeuferscheibe: Klebespalt ueber die GANZE Polflaeche. Viel
    #    besser als radial, wo der Magnet in einer Tasche mit Luftkappen sitzt.
    A_kleb = A_ring * a["polbedeckung"] * n_rot
    G_m_ri = K_KLEBER * A_kleb / T_KLEBER_M

    # 6. Laeuferscheibe -> Welle: Leitung in der Kreisringscheibe nach innen.
    r_nabe = m["r_nabe_m"]
    G_ri_sh = (2.0 * math.pi * TH.K_FE * joch_r * n_rot
               / max(math.log(max(ri / r_nabe, 1.0001)), 1e-3))

    # 7. Laeuferscheibe -> Gehaeuseraum: die frei rotierende RUECKSEITE.
    h_sch, re_sch, art = _h_scheibe(rpm, ro)
    A_rueck = A_ring * n_rot
    G_ri_h = h_sch * A_rueck

    # 8. Welle -> Gehaeuse ueber die Lager; 9. Gehaeuse -> Umgebung.
    G_sh_h = 2.0 * 1.2
    pres = TH.COOLING_PRESETS.get(cooling, TH.COOLING_PRESETS["natural"])
    r_geh, l_ges = m["r_geh_m"], m["l_ges_m"]
    A_geh = 2.0 * math.pi * r_geh * l_ges + 2.0 * math.pi * r_geh ** 2
    G_h_amb = float(pres["h_eff"]) * A_geh

    G_w_cool = 0.0
    if htc_oil > 0:
        G_w_cool = htc_oil * (wetted_area_m2 if wetted_area_m2 > 0 else A_wk)

    return {
        "G_w_si": G_w_si, "G_w_h": G_w_h, "G_si_h": G_si_h, "G_si_m": G_si_m,
        "G_w_m": 0.0, "G_m_ri": G_m_ri, "G_ri_sh": G_ri_sh, "G_ri_h": G_ri_h,
        "G_sh_h": G_sh_h, "G_h_amb": G_h_amb, "G_w_cool": G_w_cool,
        "_delta_T_coolant": float(pres["delta_T_coolant"]),
        "_label": pres["label"],
        "_axial": {
            "A_ring_m2": A_ring, "A_nutwand_m2": A_nutwand, "A_wickelkopf_m2": A_wk,
            "A_staenderrand_m2": A_rand, "A_rueckseite_m2": A_rueck,
            "A_gehaeuse_m2": A_geh, "Re_scheibe": re_sch, "h_scheibe_Wm2K": h_sch,
            "scheibe_art": art, "spalt_zuschlag": zuschlag,
            "spaltverhaeltnis": spalt / ro, "bauform": a["bauform"],
            "n_spalte": n_sp, "n_rotor": n_rot, "baulaenge_m": l_ges,
        },
    }


def grenzen(G: dict) -> list[str]:
    """Was dieses Netz NICHT kann -- an jedem Ergebnis, nicht nur im Modulkopf."""
    ax = G["_axial"]
    return [
        "Ein Netz aus Korrelationen, kein geloestes Temperaturfeld -- wie das "
        "radiale LPTN auch.",
        f"Die Rueckseite der Laeuferscheibe traegt {ax['h_scheibe_Wm2K']:.0f} "
        f"W/m^2K ({ax['scheibe_art']}, Re = {ax['Re_scheibe']:.2e}) nach "
        "Cobb/Saunders bzw. Dorfman. Das ist eine Korrelation fuer die FREIE "
        "Scheibe; ein enges Gehaeuse dahinter senkt sie.",
        "H_VERGUSS (Wickelkopf -> Gehaeuse) ist eine ANNAHME und der "
        "empfindlichste Wert des Netzes -- beim YASA ist das der Hauptweg.",
        "EIN Wicklungsknoten: der Verlauf ueber dem Radius fehlt. Der Innenrand "
        "wird waermer sein als der Aussenrand (schmalerer Zahn, dieselbe "
        "Nutbreite), und das sagt dieses Netz NICHT.",
        "Kein Wickelkopf-Stroemungsmodell: bei Oelkuehlung traegt `ema_cfd` "
        "einen gemessenen HTC bei, sonst steht hier der Preset-Wert.",
    ]
