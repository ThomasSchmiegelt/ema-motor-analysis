#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Was den Schenkelpol haelt, was ihn daempft — und der Buerstenapparat.

Geprueft werden **Formeln gegen ihre Invarianten**, nicht festgenagelte Zahlen.
Eine eingefrorene Zahl prueft nur, dass sich nichts geaendert hat; eine
Invariante prueft, dass die Formel stimmt:

  * Die Fliehkraft waechst mit ``n^2`` — exakt, nicht ungefaehr.
  * Die ZULAESSIGE Drehzahl ist deshalb drehzahl-UNABHAENGIG (``sigma ~ n^2``
    und ``n_zul = n * sqrt(SF/SF_ziel)`` heben sich auf). Kaeme dort etwas
    anderes heraus, waere eine der beiden Formeln falsch.
  * Der Daempferquerschnitt trifft seine Regel (``K_QUERSCHNITT`` x
    Staenderkupfer je Pol) — sonst ist die Regel nur aufgeschrieben.
  * Kommutator und Schleifring lesen DIESELBE Stromdichte und denselben
    Kontaktabfall: ein Kohlekontakt ist ein Kohlekontakt.

Ohne Loeser, ohne FreeCAD, ohne Server.
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cae_cli                                               # noqa: E402
import ema_eesm                                              # noqa: E402
import ema_eesm_cad                                          # noqa: E402
import ema_gsm                                               # noqa: E402
import ema_pipeline                                          # noqa: E402
import ema_schenkelpol as SP                                 # noqa: E402
import ema_schleifring                                       # noqa: E402
import ema_text2ema                                          # noqa: E402

_ok = _bad = 0


def pruefe(bed, text):
    global _ok, _bad
    if bed:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def nah(a, b, rel=1e-6):
    return abs(float(a) - float(b)) <= rel * max(abs(float(b)), 1e-12)


def geom(art="eesm", **extra):
    p = cae_cli.frischer_payload()
    g = p["geom"]
    g["machineType"] = art
    g.update(extra)
    return g, float(p["axial_len"])


print("1. Die Fliehkraft am Polfuss — gegen ihre eigene Formel")

g, L = geom("eesm")
b1 = SP.befestigung(g, L, 3000.0)
b2 = SP.befestigung(g, L, 6000.0)
pruefe(nah(b2["F_flieh_kN"], 4.0 * b1["F_flieh_kN"], rel=2e-3),
       f"doppelte Drehzahl = vierfache Kraft ({b1['F_flieh_kN']} -> "
       f"{b2['F_flieh_kN']} kN) — F = m*omega^2*r, nicht geschaetzt")
pruefe(nah(b2["sigma_hals_MPa"], 4.0 * b1["sigma_hals_MPa"], rel=2e-3),
       "und die Halsspannung ebenso — sie ist die Kraft durch einen festen "
       "Querschnitt")
pruefe(nah(b1["n_zulaessig_1pmin"], b2["n_zulaessig_1pmin"], rel=2e-3),
       f"die ZULAESSIGE Drehzahl ist von der gerechneten unabhaengig "
       f"({b1['n_zulaessig_1pmin']:.0f} = {b2['n_zulaessig_1pmin']:.0f} 1/min) "
       f"— sqrt(SF) ~ 1/n hebt das n davor exakt auf")

# Die Masse ist die des ganzen Pols: Schuh, Kern UND Spule. Die Spule sitzt
# auf dem Kern und wird vom Schuh gehalten -- ihre Fliehkraft laeuft durch
# denselben Hals.
pruefe(b1["m_pol_eisen_kg"] > 0 and b1["m_pol_kupfer_kg"] > 0
       and nah(b1["m_pol_kg"], b1["m_pol_eisen_kg"] + b1["m_pol_kupfer_kg"], rel=1e-3),
       f"gewogen wird der GANZE Pol: {b1['m_pol_eisen_kg']} kg Eisen + "
       f"{b1['m_pol_kupfer_kg']} kg Kupfer = {b1['m_pol_kg']} kg")
_k = ema_eesm_cad.koerper(g, L)
pruefe(_k["r_joch_aussen_mm"] < b1["r_schwerpunkt_mm"] < _k["r_rotor_mm"],
       f"der Schwerpunkt liegt zwischen Joch und Rand "
       f"({b1['r_schwerpunkt_mm']} mm) — nicht am Rand und nicht auf der Achse")


print("\n2. Zwei Bauarten, und die engere bindet")

g, L = geom("eesm")
bs = SP.befestigung(dict(g, polBefestigung="schwalbenschwanz"), L, 6000.0)
bb = SP.befestigung(dict(g, polBefestigung="bolzen"), L, 6000.0)
pruefe(nah(bs["F_flieh_kN"], bb["F_flieh_kN"]),
       "beide tragen dieselbe Kraft — die Wahl aendert den Halt, nicht die Last")
pruefe(nah(bs["SF"], bs["SF_schwalbenschwanz"])
       and nah(bb["SF"], bb["SF_bolzen"]),
       "gewertet wird die GEWAEHLTE Bauart, gerechnet werden beide — die "
       "andere steht als Vergleich daneben")
b_mehr = SP.befestigung(dict(g, polBefestigung="bolzen", polBolzen=6), L, 6000.0)
pruefe(nah(b_mehr["SF_bolzen"], 3.0 * bb["SF_bolzen"], rel=2e-3),
       f"dreimal so viele Schrauben = dreifache Sicherheit "
       f"({bb['SF_bolzen']} -> {b_mehr['SF_bolzen']})")
pruefe(SP.BOLZEN_AS_MM2["M10"] == 58.0 and SP.BOLZEN_AS_MM2["M6"] == 20.1,
       "die Spannungsquerschnitte sind die der ISO 898-1 und nicht d^2*pi/4")

# Das Urteil kippt GENAU an der Zielsicherheit -- nicht irgendwo daneben.
n_kipp = bs["n_zulaessig_1pmin"]
pruefe(SP.befestigung(g, L, n_kipp * 0.98)["haelt"]
       and not SP.befestigung(g, L, n_kipp * 1.02)["haelt"],
       f"das Urteil kippt an der ausgerechneten Grenze ({n_kipp:.0f} 1/min) — "
       f"knapp darunter haelt es, knapp darueber nicht")
pruefe(not SP.befestigung(g, L, n_kipp * 1.5)["haelt"]
       and "Noetig waeren" in SP.befestigung(g, L, n_kipp * 1.5)["grund"],
       "und das Nein nennt den Weg (noetige Halsbreite bzw. Schraubenzahl), "
       "statt nur abzusagen")
pruefe("Flankenpressung" in bs["ungeprueft"] and "Dauerfestigkeit" in bs["ungeprueft"],
       "was NICHT darin steckt, steht dabei — Schweigen laese sich als "
       "geprueft lesen")


print("\n3. Der Daempferkaefig — die Regel wird auch eingehalten")

g, L = geom("eesm", daempferkaefig="ja")
d = SP.daempferkaefig(g, L)
pruefe(d["aktiv"] and d["passt"], f"er passt in den Polschuh "
       f"({d['noetige_schuhhoehe_mm']} von {d['h_schuh_mm']} mm)")
pruefe(nah(d["A_je_pol_mm2"], d["A_soll_je_pol_mm2"], rel=0.02),
       f"der Querschnitt trifft seine Regel ({d['A_je_pol_mm2']} gegen "
       f"{d['A_soll_je_pol_mm2']} mm² Soll)")
pruefe(nah(d["A_soll_je_pol_mm2"],
           SP.K_QUERSCHNITT * d["A_staender_je_pol_mm2"], rel=1e-3),
       f"und das Soll ist {SP.K_QUERSCHNITT:.2f} x Staenderkupfer je Pol "
       f"({d['A_staender_je_pol_mm2']} mm²) — die Regel steht im Modulkopf "
       f"mit ihrer Quelle")
pruefe(d["teilung_ok"] and abs(d["teilungsverhaeltnis"] - 1.0) > 0.07,
       f"die Stabteilung ist bewusst VERSCHIEDEN von der Staendernutteilung "
       f"({d['teilungsverhaeltnis']}) — gleiche Teilungen lassen den Laeufer "
       f"in einer Oberwelle haengen")
pruefe(d["masse_kg"] > 0 and d["R_stab_mOhm"] > 0,
       f"Masse und Widerstand fallen heraus ({d['masse_kg']} kg, "
       f"{d['R_stab_mOhm']} mOhm je Stab)")
pruefe("Auslegungsregel" in d["regel"] and "keine Messung" in d["regel"],
       "und die Bemessung weist sich als REGEL aus, nicht als Messung")
pruefe("keine Kennzahl" in d["wirkung"],
       "ebenso, dass ihr NUTZEN in keine Kennzahl eingeht — dafuer fehlt der "
       "zeitabhaengige Lauf")

# Der Widerstand haengt an der Temperatur wie jede andere Wicklung hier.
d20 = SP.daempferkaefig(dict(g, tLeiterC=20), L)
d115 = SP.daempferkaefig(dict(g, tLeiterC=115), L)
_rho20 = ema_pipeline.rho_bei(ema_pipeline.HAIRPIN_MATS["cu_etp"], 20.0)
_rho115 = ema_pipeline.rho_bei(ema_pipeline.HAIRPIN_MATS["cu_etp"], 115.0)
pruefe(nah(d115["R_stab_mOhm"] / d20["R_stab_mOhm"], _rho115 / _rho20, rel=1e-3),
       f"und er steigt GENAU wie rho ({d20['R_stab_mOhm']} -> "
       f"{d115['R_stab_mOhm']} mOhm von 20 auf 115 °C) — nicht bei 20 °C "
       f"stehengeblieben")

# Ein zu duenner Polschuh ist ein BEFUND und keine gezeichnete Naeherung.
g2, L2 = geom("eesm", p=2, daempferkaefig="ja")
d2 = SP.daempferkaefig(g2, L2)
pruefe((not d2["passt"] and "Polschuh" in d2["grund"]) or d2["passt"],
       f"bei 4 Polen entscheidet der Platz im Schuh "
       f"({d2['noetige_schuhhoehe_mm']} von {d2['h_schuh_mm']} mm, "
       f"passt={d2['passt']})")
pruefe(d2["teilung_ok"] or "Goerges" in d2["hinweis"],
       "und laeuft die Teilung in die Naehe der Nutteilung, wird der "
       "Goerges-Sattel benannt statt verschwiegen")

# Aus, und es ist wirklich aus.
d_aus = SP.daempferkaefig(dict(g, daempferkaefig="nein"), L)
pruefe(d_aus["aktiv"] is False and d_aus["grund"] == "",
       "ohne Daempfer kommt nichts heraus und auch kein Vorwurf")


print("\n4. Der Daempfer kostet, und das steht in der Masse")

p = cae_cli.frischer_payload(); p["geom"]["machineType"] = "eesm"
mk_ohne = ema_eesm.massen_und_kosten(p)
p2 = dict(p); p2["geom"] = dict(p["geom"], daempferkaefig="ja")
mk_mit = ema_eesm.massen_und_kosten(p2)
pruefe(mk_mit["gesamt_kg"] > mk_ohne["gesamt_kg"]
       and nah(mk_mit["gesamt_kg"] - mk_ohne["gesamt_kg"],
               mk_mit["daempfer_kg"], rel=0.02),
       f"die Masse waechst genau um den Kaefig ({mk_mit['daempfer_kg']} kg) — "
       f"sonst waere die Paarvergleichsachse eine ohne Wirkung")
pruefe(mk_mit["kosten"]["gesamt_EUR"] > mk_ohne["kosten"]["gesamt_EUR"],
       f"und die Kosten mit ({mk_ohne['kosten']['gesamt_EUR']} -> "
       f"{mk_mit['kosten']['gesamt_EUR']} EUR)")


print("\n5. Schleifring und Kommutator — EIN Kohlekontakt, eine Tabelle")

g, L = geom("eesm")
rg = ema_eesm.schleifringe(g, L, 6000.0)
pruefe(rg["n_ringe"] == 2,
       "die EESM fuehrt ZWEI Ringe (Erregerkreis), die ASM drei (Drehstrom)")
pruefe(nah(rg["I_ring_eff_A"], rg["I_f_A"]),
       f"durch den Ring geht der Erregerstrom ({rg['I_f_A']} A) — er wird "
       f"aus `erregung` gelesen und nicht noch einmal geschaetzt")
pruefe(ema_eesm.schleifringe(dict(g, rpm_to=0), L)["v_ok"] is None,
       "ohne Hoechstdrehzahl steht None da — nicht geprueft ist nicht bestanden")
pruefe(ema_eesm.U_BUERSTE_V == ema_schleifring.U_BUERSTE_V,
       f"Kontaktabfall aus EINER Quelle ({ema_schleifring.U_BUERSTE_V} V)")

g, L = geom("gsm")
ko = ema_gsm.kommutator(g, L, 3000.0, 200.0)
pruefe(nah(ko["A_buerste_ges_cm2"], 200.0 / ema_schleifring.J_BUERSTE_APCM2,
           rel=1e-3),
       f"die Buerstenflaeche kommt aus derselben Stromdichte wie der "
       f"Schleifring ({ema_schleifring.J_BUERSTE_APCM2} A/cm²)")
pruefe(nah(ko["U_buerste_V"], ema_schleifring.U_BUERSTE_V),
       "und derselbe Kontaktabfall — ein Kohlekontakt ist ein Kohlekontakt, "
       "ob er auf einem Ring oder auf Lamellen laeuft")
ko_gross = ema_gsm.kommutator(g, L, 3000.0, 800.0)
pruefe(ko_gross["l_kommutator_mm"] > ko["l_kommutator_mm"],
       f"mehr Ankerstrom = laengerer Kommutator ({ko['l_kommutator_mm']} -> "
       f"{ko_gross['l_kommutator_mm']} mm): die BUERSTENFLAECHE bemisst ihn, "
       f"nicht ein Anteil der Paketlaenge")
pruefe(ko_gross["lang"] and "laenger als das Blechpaket" in ko_gross["hinweis"],
       "und wird er laenger als das Blechpaket, ist das ein BEFUND — bei "
       "Gleichstrommaschinen ueblich, aber es verlaengert die Maschine")
pruefe(nah(ko["lamellen_je_buerste"], ema_gsm.BUERSTE_LAMELLEN, rel=1e-6),
       f"die Buerste ueberdeckt {ema_gsm.BUERSTE_LAMELLEN} Lamellen — weniger "
       f"waere zu kurz kommutiert, mehr legte zu viele Spulen kurz")
pruefe(nah(ko["b_lamelle_mm"] + ko["lamellenspalt_mm"],
           ko["lamellenteilung_mm"], rel=1e-6),
       "Lamelle plus Spalt ergeben die Teilung — der Kommutator ist "
       "geschlossen")
# Die Zeichnung nimmt DIESELBE Laenge wie die Rechnung.
pruefe(nah(ema_gsm.zeichenmasse(g, L)["l_kommutator_mm"],
           ema_gsm.kommutator(g, L, 0.0)["l_kommutator_mm"], rel=1e-3),
       "und der Zeichner liest sie aus derselben Funktion — sonst saesse die "
       "gerechnete Buerste auf einem anderen Kommutator als der gezeichnete")


print("\n6. Erreichbar — sonst ist es fuer den Agenten nicht vorhanden")

for k in ("polBefestigung", "polBolzen", "polBolzenGewinde", "daempferkaefig",
          "daempferStaebeJePol", "daempferMat"):
    pruefe(k in ema_text2ema.SCHEMA and ema_text2ema.SCHEMA[k].get("geom"),
           f"'{k}' steht im Schema und gehoert nach geom — CLI, "
           f"Parametertabelle und Browser erreichen es")
pruefe(list(ema_text2ema.SCHEMA["polBefestigung"]["opts"])
       == list(SP.BEFESTIGUNGEN),
       "die Auswahl kommt aus ema_schenkelpol und ist nicht abgeschrieben")
pruefe(set(ema_text2ema.SCHEMA["polBolzenGewinde"]["opts"])
       == set(SP.BOLZEN_AS_MM2),
       "die Gewindeliste ebenso — ein waehlbares Gewinde, das die Rechnung "
       "nicht kennt, waere die naechste stille Luecke")

import ema_paarvergleich as PV                               # noqa: E402
for achse in ("polbefestigung", "daempferkaefig"):
    pruefe(achse in PV.ACHSEN, f"der Paarvergleich fuehrt die Achse '{achse}'")

print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
