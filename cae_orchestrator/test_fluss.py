"""Pruefungen des Flusswegs (``ema_fluss``, Stufe 0 aus ``AXIALFLUSS.md``).

Die erste Pruefung ist die wichtigste und hat nichts mit Axialfluss zu tun:
**bewegt sich am Radialfluss etwas?** ``flaechen()`` legt zwei Formeln
zusammen, die bisher an zwei Stellen standen (``compute_performance`` und
``rated_torque``) -- eine Umstellung, keine Aenderung. Wenn sie eine Aenderung
waere, verschoebe sie die Kennzahlen jedes bestehenden Projekts, und zwar um
Promille: nicht genug, um aufzufallen, genug, um Vergleiche wertlos zu machen.
Deshalb wird ziffernweise verglichen und nicht mit Toleranz.

Danach das Tor. Alle Faelle, gegen die hier geprueft wird, waeren ohne Absturz
durchgelaufen und haetten eine plausible Zahl geliefert:

* ``rated_torque`` legt ``2*sigma*pi*R^2*L`` auf eine Scheibe -- eine
  Zylinderformel auf eine Geometrie ohne Zylinder;
* ``psi_pm`` nimmt ``R_gap*L`` fuer einen Ringraum (gemessen Faktor 1,49);
* das Raster baut ``R = hypot(X, Y)``-Ringe, das 3-D-Netz Scheiben EINES
  Querschnitts -- den es axial nicht gibt.

Und die Probe, die den Kern festnagelt: Fluss waechst mit r^1, Moment mit r^2.
Radial fallen beide auf einen Radius zusammen, axial nicht. Ein Ersatzradius
kann nur eines von beiden treffen, und ein Test, der das nicht prueft, laesst
genau den Fehler durch, um den es geht.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_analysis
import ema_fluss as F
import ema_text2ema as T
import ema_thermal

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def vorgabe(**auf):
    g = {k: v.get("def") for k, v in T.SCHEMA.items() if v.get("geom")}
    g["axialLen"] = T.SCHEMA["axialLen"]["def"]
    g.update(auf)
    return g


print("\n— 1. Invarianz: am Radialfluss darf sich NICHTS bewegen —")

g = vorgabe()
L_mm = g["axialLen"]
f = F.flaechen(g, L_mm)

# Genau die Ausdruecke, die compute_performance und rated_torque heute bilden.
soll_fluss = ema_analysis.r_gap_m(g) * ema_analysis.stapellaenge_m(g, L_mm)
soll_mom = (g["rotorOD"] / 2 / 1000) ** 2 * (L_mm / 1000)
pruefe(f["a_fluss_m2"] == soll_fluss,
       f"a_fluss ist ziffernweise r_gap_m*L  ({f['a_fluss_m2']!r})")
pruefe(f["a_moment_m3"] == soll_mom,
       f"a_moment ist ziffernweise (rotorOD/2)^2*L  ({f['a_moment_m3']!r})")

# Und durch die beiden Kennzahlen hindurch.
B, p, rpm = 0.63, int(g["p"]), 1000.0
perf = ema_analysis.compute_performance(g, B, rpm, L_mm)
psi_aus_flaechen = p * (2 / math.pi) * B * f["a_fluss_m2"]
pruefe(round(psi_aus_flaechen, 4) == perf["psi_pm_Wb"],
       f"psi_pm aus flaechen() == compute_performance ({perf['psi_pm_Wb']} Wb)")

t_haus = ema_thermal.rated_torque(g, L_mm, "water")
t_flaechen = 2 * math.pi * 40e3 * f["a_moment_m3"]
pruefe(abs(t_flaechen - t_haus) < 1e-9,
       f"T = 2*pi*sigma*a_moment == rated_torque ({t_haus:.4f} Nm, water)")
pruefe(round(t_haus, 1) == 178.8,
       f"und das ist die Zahl aus dem Docstring von mit_umrichtergrenze "
       f"({t_haus:.1f} Nm)")

# Die Bauform darf die Invarianz nicht aufheben.
for pos in ("innen", "aussen"):
    ga = vorgabe(rotorPosition=pos)
    if pos == "aussen":
        ga.update(statorOD=180, statorID=60, rotorID=181.4, rotorOD=200, shaftD=40)
    fa = F.flaechen(ga, L_mm)
    pruefe(fa["a_fluss_m2"] == ema_analysis.r_gap_m(ga)
           * ema_analysis.stapellaenge_m(ga, L_mm),
           f"auch beim {pos.capitalize()}laeufer unveraendert")

print("\n— 2. Das Tor: kein Axialfluss unter fremdem Namen —")

# Stufe 0 hatte hier `== ()`. Seit Stufe 1 (05.10.2026) traegt `analytisch`
# den Axialfluss ueber `ema_axial`; die Tabelle ist der Sinn des Moduls, und ein
# Test, der sie auf leer festnagelt, verhindert genau den Ausbau, fuer den das
# Tor gebaut wurde. Festgenagelt wird statt dessen, WAS NICHT traegt.
pruefe(F.STUFEN_AXIAL == ("analytisch", "feld"),
       "STUFEN_AXIAL traegt 'analytisch' (Stufe 1) und 'feld' (Stufe 2)")
pruefe(F.flussweg(vorgabe()) == "radial" and F.flussweg({}) == "radial"
       and F.flussweg(None) == "radial",
       "ohne Angabe gilt radial (Vorgabe, nicht Rateschritt)")
pruefe(F.flussweg({"geom": {"fluxPath": "axial"}}) == "axial"
       and F.flussweg({"fluxPath": "AFPM"}) == "axial",
       "axial wird in geom UND oben im Payload erkannt, auch als Synonym")

ax = {"geom": vorgabe(fluxPath="axial", axialAktivOD=260.0)}
pruefe(F.pruefe_flussweg(ax, "analytisch") == "axial",
       "'analytisch' laeuft durch (ema_axial rechnet sie)")
# 'feld' traegt seit Stufe 2 -- aber auf einem EIGENEN Loeser. Die Unterscheidung
# ist die von ema_maschinenart: "traegt die Stufe" ist nicht "geht DIESEN Weg".
pruefe(F.pruefe_flussweg(ax, "feld") == "axial",
       "'feld' laeuft durch (Stufe 2, ema_axial_fdm)")
try:
    F.pruefe_feldweg(ax, "fdm")
    pruefe(False, "aber die radiale FDM muesste abweisen")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "aber NICHT ueber die radiale FDM der Pipeline")
for stufe in ("cad", "em3d", "lauf"):
    try:
        F.pruefe_flussweg(ax, stufe)
        pruefe(False, f"Stufe '{stufe}' muesste abweisen — tut es nicht")
    except F.FlusswegNichtUnterstuetzt as e:
        pruefe("AXIALFLUSS.md" in str(e) and "1,49" in str(e),
               f"Stufe '{stufe}' weist ab und nennt Plan und Groessenordnung")
pruefe(F.pruefe_flussweg({"geom": vorgabe()}, "feld") == "radial",
       "radial laeuft durch alle Stufen wie bisher")

print("\n— 3. Das zentrale Pipelinetor fragt den Flussweg wirklich —")

import ema_pipeline
try:
    ema_pipeline._gate_maschinenart(ax, None, "lauf")
    pruefe(False, "_gate_maschinenart laesst Axialfluss durch")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "_gate_maschinenart weist Axialfluss ab (dieselbe Stelle wie "
                 "die Bauform)")
except Exception as e:                                  # pragma: no cover
    pruefe(False, f"_gate_maschinenart wirft das Falsche: {type(e).__name__}: {e}")

print("\n— 4. Der Kern: zwei Integrale, nicht ein Ersatzradius —")

# Die Axialflussmaschine aus AXIALFLUSS.md §1: Ro = 130, lambda = 0,577, 2 Spalte.
gax = vorgabe(fluxPath="axial", axialAktivOD=260.0, axialLambda=0.5774,
              axialSpalte=2, axialBauform="yasa")
fx = F.flaechen(gax, L_mm)
ro, ri, n = fx["r_aussen_m"], fx["r_innen_m"], fx["n_spalte"]
pruefe(abs(fx["a_fluss_m2"] - n * (ro ** 2 - ri ** 2) / 2) < 1e-15,
       f"a_fluss = n*(Ro^2-Ri^2)/2 = {fx['a_fluss_m2'] * 1e4:.2f} cm^2")
pruefe(abs(fx["a_moment_m3"] - n * (ro ** 3 - ri ** 3) / 3) < 1e-18,
       f"a_moment = n*(Ro^3-Ri^3)/3 = {fx['a_moment_m3'] * 1e6:.2f} cm^3")

v_fluss = fx["a_fluss_m2"] / f["a_fluss_m2"]
v_mom = fx["a_moment_m3"] / f["a_moment_m3"]
pruefe(round(v_fluss, 2) == 1.49 and round(v_mom, 2) == 1.66,
       f"und sie sind VERSCHIEDEN: Fluss x{v_fluss:.2f}, Moment x{v_mom:.2f} "
       f"— ein Ersatzradius trifft nur eines von beiden")

t_ax = 2 * math.pi * 40e3 * fx["a_moment_m3"]
pruefe(round(t_ax, 1) == 297.2,
       f"T_axial(water, 2 Spalte) = {t_ax:.1f} Nm gegen {t_haus:.1f} Nm radial")

# Der Kreuzungspunkt: ab welcher Paketlaenge gewinnt der Radialfluss zurueck?
L_kreuz = t_ax / (2 * math.pi * 40e3 * (g["rotorOD"] / 2 / 1000) ** 2) * 1000
pruefe(round(L_kreuz) == 133 and L_kreuz < T.SCHEMA["axialLen"]["hi"],
       f"Kreuzungspunkt bei L = {L_kreuz:.0f} mm — INNERHALB der Schemagrenze "
       f"({T.SCHEMA['axialLen']['hi']:.0f} mm), also eine erreichbare Auslegung")

print("\n— 5. Verlangte Masse und Aussagen —")

try:
    F.flaechen(vorgabe(fluxPath="axial"), L_mm)
    pruefe(False, "axialAktivOD fehlt und wird nicht verlangt")
except ValueError as e:
    pruefe("axialAktivOD" in str(e) and "statorOD" in str(e),
           "ohne axialAktivOD ein klarer Fehler, der sagt, warum es nicht aus "
           "statorOD kommt")
f0 = F.flaechen(vorgabe(fluxPath="axial", axialAktivOD=260.0, axialLambda=0.0),
                L_mm)
pruefe(round(f0["lambda"], 4) == 0.5774,
       "lambda=0 heisst 'nicht gesetzt' und faellt auf 1/sqrt(3) — nicht auf "
       "einen Ringraum ohne Innenradius")
for lam in (0.99, 1.5, -0.2):
    try:
        F.flaechen(vorgabe(fluxPath="axial", axialAktivOD=260.0, axialLambda=lam),
                   L_mm)
        pruefe(False, f"lambda={lam} muesste abgewiesen werden")
    except ValueError:
        pruefe(True, f"lambda={lam} wird abgewiesen (Ringraum verschwindet)")

tr = F.traeger(gax)
pruefe(tr["kraft_hebt_sich_auf"] and not tr["lastart_vorhanden"]
       and "ema_deck" in tr["aussage"],
       "traeger() sagt: Kraft hebt sich am Staender auf, die Lastart gibt es "
       "aber in keiner Strukturstufe")
tr1 = F.traeger(vorgabe(fluxPath="axial", axialAktivOD=260.0,
                        axialBauform="einseitig", axialSpalte=1))
pruefe(not tr1["kraft_hebt_sich_auf"] and tr1["traeger"] == "das Lager",
       "beim einseitigen Aufbau traegt das LAGER, und das sagt es")
pruefe(F.traeger(vorgabe())["lastart_vorhanden"],
       "radial ist die bemessende Last (Fliehkraft) vorhanden und gerechnet")

print("\n— 6. Schema und Werkzeugstand fuehren denselben Stand —")

pruefe(T.SCHEMA["fluxPath"]["opts"] == list(F.FLUSSWEGE)
       and T.SCHEMA["fluxPath"]["def"] == F.VORGABE,
       "das Schema fuehrt die Flusswege aus ema_fluss")
pruefe(T.SCHEMA["fluxPath"].get("adv") is True,
       "und als Feinparameter — Text->Auslegung erfragt ihn nicht, solange "
       "keine Stufe ihn traegt")
pruefe(sorted(T.SCHEMA["axialBauform"]["opts"]) == sorted(F.AXIAL_BAUFORMEN),
       "die Axialfluss-Bauformen ebenfalls aus EINER Quelle")
import ema_werkzeugstand
pruefe("ema_fluss.py" in ema_werkzeugstand.PHYSIK,
       "ema_fluss.py steht im Fingerabdruck (PHYSIK) — es bewegt Kt und das "
       "Dauermoment")

# Die Zurechtrueckung im Schema darf den Flussweg nicht aufheben.
roh = {k: v.get("def") for k, v in T.SCHEMA.items()}
roh.update(fluxPath="axial", axialAktivOD=260.0)
v = T._validate(roh)
pruefe(v.get("fluxPath") == "axial" and float(v.get("axialAktivOD", 0)) == 260.0,
       "_validate haelt fluxPath und axialAktivOD (zieht sie nicht still auf "
       "radial zurueck)")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
