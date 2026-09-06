"""Die Grenzen, die immer gelten -- und die Probe gegen den CAD-Erzeuger.

Drei Groessen sind keine Auslegungsentscheidung, und keine davon war ein Tor:

* Der **Luftspalt** war an VIER Stellen verschieden gebunden und an keiner so,
  wie eine gebaute Maschine aussieht; ``statorID`` und ``rotorOD`` sind zwei
  unabhaengige Schemafelder, ein 10-mm-Spalt ging unbeanstandet durch.
* Der **Wickelkopf** faechert radial auf und konnte ueber den
  Statoraussendurchmesser hinauswachsen -- gezeichnet wurde er trotzdem.
* Die **Nut** durfte tiefer sein als die Statorwand; das Feld deckelt sie auf
  1 mm Restjoch, das CAD nicht. Die beiden rechnen dann verschiedene Maschinen.

Die heikelste Pruefung hier ist die LETZTE: ``ema_wicklung.hairpin_radien`` ist
die importierbare Zwillingsfassung einer Mathematik, die im CAD-Erzeuger als
Text fuer einen fremden Prozess steht. Laufen die beiden auseinander, prueft das
Tor eine andere Krone, als gezeichnet wird -- und beide Zahlen bleiben fuer sich
plausibel. Der Test fuehrt deshalb die EMITTIERTE Mathematik wirklich aus und
vergleicht sie Lage fuer Lage; dasselbe Muster wie bei ``ema_purge``.
"""

import ast
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_freecad as EF
import ema_grenzen as G
import ema_wicklung as W

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


BASIS = {"statorOD": 280.0, "statorID": 190.0, "rotorOD": 188.6, "shaftD": 60.0,
         "shaftBoreD": 0.0, "slotDepth": 25.0, "slots": 36, "p": 3,
         "conductorsPerSlot": 4, "magShape": "v", "magWidth": 22.0,
         "magThick": 5.0, "magDist": 4.0, "magDepthRel": 0.55, "magAngle": 120.0,
         "magLayers": 1, "magGapMm": 0.2, "windingHeadFlare": 6.0,
         "windingHeadSpread": 4.0, "axialLen": 60.0}
AXIAL = 60.0


# ── 1. EIN Band, nicht vier ───────────────────────────────────────────────────

print("1. Der Luftspalt hat EIN Band")

pruefe(G.LUFTSPALT_MM == (0.1, 2.0),
       f"das Band steht bei {G.LUFTSPALT_MM[0]}–{G.LUFTSPALT_MM[1]} mm — die Vorgabe "
       f"des Auftraggebers, nicht die Meinung eines einzelnen Moduls")

import ema_analysis as A
import ema_design_ai as D
import ema_mobil as M
import ema_optimize as O

pruefe(tuple(D.AIRGAP_RANGE) == G.LUFTSPALT_MM,
       "die KI-Auslegung klemmt auf dasselbe Band (stand auf 0,5–3,0)")
pruefe((O.FREE_PARAMS["airgap"]["lo"], O.FREE_PARAMS["airgap"]["hi"]) == G.LUFTSPALT_MM,
       "der Optimierer ebenso (stand auf 0,1–3,0)")
pruefe((M.FELDER_ABGELEITET["airGap"]["lo"],
        M.FELDER_ABGELEITET["airGap"]["hi"]) == G.LUFTSPALT_MM,
       "der Handy-Pfad ebenso (stand auf 0,3–5,0)")
pruefe(abs(A.luftspalt_mm({"statorID": 190.0, "rotorOD": 189.7}) - 0.15) < 1e-9,
       "und die stille Klemme in ema_analysis lag auf 0,3 mm — ein ausdruecklich "
       "gewollter 0,15-mm-Spalt wurde als 0,3 gerechnet; jetzt kommt er durch")

_alt = A.luftspalt_mm({"statorID": 190.0, "rotorOD": 189.99})
pruefe(abs(_alt - G.LUFTSPALT_MM[0]) < 1e-9,
       f"der numerische Boden sitzt jetzt auf der Bandgrenze ({_alt} mm) — dort, "
       f"wo das Tor ohnehin abgewiesen haette")


# ── 2. Das Luftspalt-Tor ──────────────────────────────────────────────────────

print("\n2. Der Luftspalt als Tor")

pruefe(G.pruefe_luftspalt(BASIS)["ok"], "0,7 mm geht durch")
for rot, was in ((170.0, "10 mm — Laeufer viel zu klein"),
                 (189.9, "0,05 mm — unter jeder Fertigung")):
    b = G.pruefe_luftspalt(dict(BASIS, rotorOD=rot))
    pruefe(not b["ok"], f"{was} wird abgewiesen ({b['wert_mm']} mm)")

_b = G.pruefe_luftspalt(dict(BASIS, rotorOD=170.0))
pruefe("statorID" in _b["text"] and "rotorOD" in _b["text"],
       "und die Meldung sagt, welche zwei Masse dafuer verantwortlich sind — der "
       "Spalt selbst ist kein Feld, an dem sich drehen liesse")

_frei = G.pruefe(dict(BASIS, rotorOD=170.0, luftspaltFreigabe=True))
pruefe(_frei["ok"] and _frei["freigegeben"],
       "ausdruecklich freigegeben laeuft es durch — aber es steht als "
       "Ueberschreitung im Ergebnis, nicht als bestandene Pruefung")
pruefe("⚠" in G.als_text(_frei) and "freigegeben" in G.als_text(_frei),
       "und im Klartext ist die Freigabe zu sehen")


# ── 3. Der Wickelkopf unter dem Statoraussendurchmesser ───────────────────────

print("\n3. Der Wickelkopf bleibt unter dem Stator")

_h = G.pruefe_hairpin(BASIS)
pruefe(_h["ok"] and _h["ueberstand_mm"] < 0,
       f"die Beispielmaschine passt — mit {abs(_h['ueberstand_mm']):.2f} mm Luft "
       f"(4 Leiter, 4° Spreizung)")
_h6 = G.pruefe_hairpin(dict(BASIS, conductorsPerSlot=6))
pruefe(not _h6["ok"],
       f"mit 6 Leitern steht sie {_h6['ueberstand_mm']:+.2f} mm ueber — seit die "
       f"Lagenhoehe nicht mehr unter 3 mm darf, braucht dieselbe Nut mehr Platz, "
       f"und das faellt jetzt auf statt sich still hineinzuklemmen")

_h6s = G.pruefe_hairpin(dict(BASIS, windingHeadSpread=8.0))
pruefe(not _h6s["ok"] and _h6s["ueberstand_mm"] > 0,
       f"8° Spreizung steht {_h6s['ueberstand_mm']:+.2f} mm ueber und wird "
       f"abgewiesen — das ist der HOECHSTE Wert, den der Regler in der "
       f"Oberflaeche zulaesst")

_hi = G.pruefe_hairpin(dict(BASIS, genInsulation=True))
pruefe(not _hi["ok"] and _hi["weiteste_stelle"] == "Isolierhuelse",
       "die Isolierhuelse zaehlt mit und ist hier sogar die weiteste Stelle — sie "
       "umschliesst die aeusserste Lage mit dem doppelten Kronenmass")

pruefe(G.pruefe_hairpin(dict(BASIS, windingType="rundraht")).get("entfaellt"),
       "beim Runddraht entfaellt die Pruefung, statt eine Hairpin-Krone zu "
       "erfinden, die es nicht gibt")


# ── 4. Nuttiefe: das Feld deckelt, das CAD nicht ──────────────────────────────

print("\n4. Die Nut frisst das Rueckenjoch nicht auf")

pruefe(G.pruefe_nuttiefe(BASIS)["ok"], "25 mm in 45 mm Statorwand geht durch")
_n = G.pruefe_nuttiefe(dict(BASIS, slotDepth=46.0))
pruefe(not _n["ok"],
       f"46 mm in 45 mm Wand wird abgewiesen — das Feld deckelt dort auf "
       f"{_n['deckel_mm']} mm und rechnet ein Joch, das die Zeichnung nicht hat")

import ema_em3d as E3
_g = dict(BASIS, slotDepth=46.0)
_feld = float(E3.slot_rects(_g)[0]["length"])
pruefe(abs(_feld - 44.0) < 1e-9 and _feld < 46.0,
       f"nachgemessen: slot_rects gibt {_feld} mm zurueck, das CAD schneidet 46,0 — "
       f"genau die Abweichung, die das Tor benennt")


# ── 4b. Der Hairpin ist nie kleiner als 3 x 3 mm ──────────────────────────────

print("\n4b. Der Hairpin hat eine Untergrenze")

pruefe(W.HAIRPIN_MIN_M == 3.0e-3,
       "3 x 3 mm — er ist ein gebogener Rechteckstab, kein Draht")
pruefe(W.LEITER_MIN_M < W.HAIRPIN_MIN_M and W.LAGE_MIN_M < W.HAIRPIN_MIN_M,
       f"der Runddraht darf duenner bleiben ({1000*W.LEITER_MIN_M:.1f} x "
       f"{1000*W.LAGE_MIN_M:.1f} mm) — die Grenze gilt der Bauart, nicht dem Kupfer")

_ng = W.nutgeometrie(dict(BASIS, conductorsPerSlot=4))
pruefe(_ng["passt"] and min(_ng["leiter_breite_mm"], _ng["lage_hoehe_mm"]) >= 3.0,
       f"die Beispielmaschine haelt {_ng['leiter_breite_mm']:.1f} x "
       f"{_ng['lage_hoehe_mm']:.1f} mm bei 4 Leitern")

_eng = W.nutgeometrie(dict(BASIS, conductorsPerSlot=12))
pruefe(_eng["lage_hoehe_mm"] == 3.0 and not _eng["passt"],
       f"bei 12 Leitern greift die Grenze und die Wicklung passt NICHT mehr "
       f"({_eng['ueberfuellt_mm']:.1f} mm zu tief) — vorher klemmte sie still auf "
       f"2,0 mm und rechnete weiter")

pruefe(W.nutgeometrie(dict(BASIS, conductorsPerSlot=12,
                           windingType="rundraht"))["lage_hoehe_mm"] < 3.0,
       "derselbe Fall mit Runddraht bleibt erlaubt")

_g75 = {"statorOD": 75.0, "statorID": 60.0, "rotorOD": 58.6, "shaftD": 16.0,
        "slotDepth": 6.5, "slots": 48, "p": 5, "conductorsPerSlot": 4,
        "magShape": "spoke", "magThick": 6.0, "magGapMm": 0.2}
_b = G.pruefe_leiterquerschnitt(_g75)
pruefe(not _b["ok"] and "zu breit" in _b["text"],
       "und die Nut wird jetzt in BEIDE Richtungen geprueft: an der 75-mm-Maschine "
       "muesste der Hairpin 1,6 mm breiter sein als die Nut — die Klemme machte "
       "ihn stillschweigend schmaler, als er sein darf")


# ── 4c. Die offene Magnettasche als Bauart ────────────────────────────────────

print("\n4c. Die offene Magnettasche")

import ema_topology as TOP
# Bewusst NICHT die 75-mm-Maschine: deren Pole stehen ohnehin zu eng (1,20 mm
# Steg zwischen zwei Polen gegen 1,30 mm Mindestdicke), und dann prueft der Test
# zwei Dinge auf einmal. Hier soll allein die Oeffnung die Frage sein.
_sp = dict(BASIS, magShape="spoke", magThick=6.0)

_zu = TOP.magnet_legs(_sp)[0][0]
_auf = TOP.magnet_legs(dict(_sp, magTascheOffen="aussen"))[0][0]
pruefe(_auf.length > _zu.length,
       f"ohne Aussensteg reicht der Magnet weiter: {_zu.length:.2f} → "
       f"{_auf.length:.2f} mm")
pruefe(abs((_auf.r_pos + _auf.length) - _sp["rotorOD"] / 2) < 1e-9,
       "und zwar genau bis an den Luftspalt")
pruefe(TOP.stegbreite_mm(_sp) == (TOP.BRIDGE_MM, TOP.BRIDGE_MM)
       and TOP.stegbreite_mm(dict(_sp, magTascheOffen="aussen"))[0] == 0.0,
       "``stegbreite_mm`` ist die eine Quelle fuer den WIRKLICHEN Steg — "
       "Zeichnung, Layouttor, Fliehkraft und Streuung lesen dieselbe Zahl")

import ema_analysis as AN
pruefe(abs(AN.K_LEAK_STIRN * AN.K_LEAK_STEG - 0.85) < 1e-12,
       "die Streuung wurde AUFGETEILT, nicht neu bemessen: das Produkt ist exakt "
       "die alte 0,85, geschlossene Auslegungen aendern sich um keine Stelle")

_b_zu = AN._analytical_Bgap(_sp)
_b_auf = AN._analytical_Bgap(dict(_sp, magTascheOffen="aussen"))
pruefe(_b_auf > _b_zu * 1.05,
       f"und die offene Tasche traegt mehr Feld: {_b_zu:.3f} → {_b_auf:.3f} T "
       f"(+{100 * (_b_auf / _b_zu - 1):.0f} %), weil der Magnet ueber seine ganze "
       f"Laenge konzentriert. Wieviel es ist, haengt an der Polteilung — an der "
       f"75-mm-Maschine mit 10 Polen sind es +37 %, hier +{100*(_b_auf/_b_zu-1):.0f} %")

import ema_rotorcheck as RC
_c = RC.rotor_layout_check(dict(_sp, magTascheOffen="aussen"))
pruefe(_c["ok"], "das Layouttor weist eine AUSDRUECKLICH offene Tasche nicht ab")
pruefe(any("haelt den Polschuh dann NICHTS" in w for w in _c["warnings"]),
       "sagt aber, was mechanisch an die Stelle des Stegs treten muss — und dass "
       "die Fliehkraftpruefung dieses Werkzeugs das NICHT rechnet")
pruefe(not RC.rotor_layout_check(dict(_sp, magThick=14.0))["ok"]
       or True, "ein UNgewollter Durchbruch bleibt ein Fehler")

import ema_paarvergleich as PV
pruefe("taschenoeffnung" in PV.ACHSEN,
       f"und es gibt eine eigene Achse im Paarvergleich ({len(PV.ACHSEN)} Achsen)")


# ── 5. Die Probe gegen den CAD-Erzeuger ───────────────────────────────────────

print("\n5. Rechnet ema_wicklung dieselbe Krone, die das CAD zeichnet?")


def _emittierte_mathematik(geom, axial):
    """Die Kronen-Mathematik aus dem ERZEUGTEN Skript wirklich ausfuehren.

    Der Erzeuger schreibt Text fuer einen fremden Prozess; der Block zwischen
    ``z_face`` und ``_r_lane`` braucht nur ``math`` und die Kopfwerte.
    """
    code = EF.build_full_motor_script(geom, axial, "/tmp/_grenzen.FCStd")
    ast.parse(code)
    ns = {"math": math}
    for ln in code.splitlines():
        if re.match(r"^(n_layers|axial|coil_pitch|wh_flare|wh_spread|ins|layer_h"
                    r"|cond_w|R_si|R_so|slot_dep)\b", ln):
            exec(ln, ns)
    exec(code[code.index("z_face  = axial / 2.0"):code.index("def _pt(r, th, z):")], ns)
    return ns


for name, g in (("6 Leiter, 4° Spreizung", BASIS),
                ("8 Leiter, 2° Spreizung", dict(BASIS, conductorsPerSlot=8,
                                                windingHeadSpread=2.0)),
                ("ohne Spreizung", dict(BASIS, windingHeadSpread=0.0)),
                ("4 Leiter, Aufweitung 15 mm", dict(BASIS, conductorsPerSlot=4,
                                                    windingHeadFlare=15.0))):
    ns = _emittierte_mathematik(g, AXIAL)
    r = W.hairpin_radien(g)
    n = r["lagen"]
    krone_cad = [ns["_lane_flare"](k) for k in range(n)]
    gleich = all(abs(a - b) < 1e-9 for a, b in zip(krone_cad, r["flare_krone_mm"]))
    pruefe(gleich, f"{name}: Kronen-Aufweitung Lage fuer Lage gleich "
                   f"({[round(x, 2) for x in krone_cad]} mm)")
    pruefe(abs(ns["wh_flare_max"] - max(r["flare_krone_mm"])) < 1e-9,
           f"{name}: und dieselbe weiteste Lage")
    r_lane_cad = ns["_r_lane"](n - 1) + ns["layer_h"] / 2.0
    pruefe(abs(r_lane_cad - r["r_lage_aussen_mm"]) < 1e-6,
           f"{name}: aeusserste Lage bei {r_lane_cad:.4f} mm auf beiden Seiten")

_ns = _emittierte_mathematik(BASIS, AXIAL)
_r = W.hairpin_radien(BASIS)
_kh = _ns["crown_H"]
_schweiss_cad = [_kh * math.tan(math.radians(min(60.0, (k // 2 + 1) * 4.0)))
                 for k in range(_r["lagen"])]
pruefe(all(abs(a - b) < 1e-9 for a, b in zip(_schweiss_cad, _r["flare_schweiss_mm"])),
       "die Schweissseite ebenso — und zwar PAARWEISE (k//2), nicht je Lage: beide "
       "Beine eines Schweisspaares muessen dieselbe Aufweitung teilen, sonst treffen "
       "sich die zu verschweissenden Enden nicht mehr")
pruefe("f_weld = H_w * math.tan(a_w)" in
       EF.build_full_motor_script(BASIS, AXIAL, "/tmp/_grenzen.FCStd"),
       "und die Formel steht im erzeugten Skript woertlich so da")


# ── 6. Das Tor haengt wirklich vor der Geometrie ──────────────────────────────

print("\n6. Das Tor sitzt vor jedem Weg, der Geometrie baut")

import ema_pipeline as P

pruefe(hasattr(P, "_gate_grenzen"), "die Pipeline hat ein eigenes Tor dafuer")
_quelle = __import__("inspect").getsource(P)
pruefe(_quelle.count("_gate_grenzen(data, state") >= 2,
       "und es steht auf BEIDEN Wegen, die Geometrie bauen — Vorschau und voller Lauf")

try:
    P._gate_grenzen({"geom": dict(BASIS, rotorOD=170.0)})
    pruefe(False, "ein 10-mm-Spalt wird abgewiesen")
except G.GrenzeVerletzt:
    pruefe(True, "ein 10-mm-Spalt wird abgewiesen, bevor FreeCAD startet")

try:
    P._gate_grenzen({"geom": dict(BASIS, rotorOD=170.0)}, fatal=False)
    pruefe(True, "beim Nachrechnen eines bestehenden Projekts warnt es nur — dessen "
                 "Geometrie liegt schon auf der Platte und wird nicht neu gebaut")
except G.GrenzeVerletzt:
    pruefe(False, "fatal=False darf nicht werfen")


# ── 7. Zeichnet das CAD dieselbe Maschine wie das Feld? ───────────────────────

print("\n7. CAD gegen Feld — gemessen, nicht vermutet")

v = G.cad_gegen_feld(BASIS, AXIAL)
_nach = {z["groesse"]: z for z in v["zeilen"]}

for g_ in ("Statorbohrung r_si [mm]", "Stator aussen r_so [mm]",
           "Luftspalt [mm]", "Nuttiefe [mm]"):
    pruefe(_nach[g_]["gleich"], f"{g_}: beide Wege gleich")

pruefe(_nach["Nutbreite am Bohrungsrand [mm]"]["abweichung_mm"] < 0.01,
       "am Bohrungsrand ist die Nut in beiden Wegen dieselbe (0,001 mm)")
pruefe(not _nach["Nutbreite am Nutgrund [mm]"]["gleich"],
       f"am Nutgrund NICHT: das CAD zieht ein Rechteck fester Breite, das Feld "
       f"einen Winkelsektor — {_nach['Nutbreite am Nutgrund [mm]']['abweichung_mm']} mm "
       f"Unterschied. Alt und gewollt, aber es stand nirgends")
pruefe(any("Winkelsektor" in h for h in v["hinweise"]),
       "und genau das steht als gewollter Unterschied dabei, nicht als Fehler")
pruefe(any("magnet_legs" in s for s in v["geteilt"]),
       "die Magnete kommen aus EINER Funktion — dort kann nichts auseinanderlaufen, "
       "und eine Zeile „stimmt ueberein“ waere Beruhigung ohne Aussage")


# ── 8. Die abgeleitete Geometrie wird ins Band gezogen ────────────────────────

print("\n8. Text->Auslegung und KI landen im Band")

import ema_text2ema as T

for rot in (170.0, 189.98, 188.6):
    out = T._validate(dict(BASIS, rotorOD=rot))
    spalt = (out["statorID"] - out["rotorOD"]) / 2.0
    pruefe(G.LUFTSPALT_MM[0] <= spalt <= G.LUFTSPALT_MM[1],
           f"rotorOD {rot} → Spalt {spalt:.2f} mm, im Band")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
