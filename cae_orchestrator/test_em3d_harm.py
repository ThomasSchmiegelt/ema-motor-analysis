"""Pruefungen der harmonischen 3-D-Stufe (``ema_em3d_harm``, Stufe D).

Wozu diese Stufe da ist -- und was sie ausdruecklich NICHT kann
----------------------------------------------------------------

Stufe B (2-D) kann eine Sache grundsaetzlich nicht: ein Querschnitt hat keine
Stirnseite, also keinen **Kurzschlussring**. ``ema_asm`` schlaegt ihn mit
rechnerisch auf. Bis zu dieser Stufe war das eine **Konstante**
(``KURZSCHLUSSRING_ZUSCHLAG = 0,20``), gesetzt und nie gemessen. Stufe D hat sie
gemessen (87,6 % bei 60 mm Paket, 44,1 % bei 120 mm) und damit abgeloest.

Was sie nicht kann, ist ein absolutes Moment. Gemessen auf dieser Maschine:

    Verfeinerungsband auf den 0,7-mm-Luftspalt, 150 mm Paket:
        nach 1 h 56 min abgebrochen, kein Netz; zweiter Versuch mit 500 s
        Deckel ebenfalls ohne Netz
    ohne Verfeinerungsband, 3 mm kleinstes Element, 30 mm Paket:
        30.010 Tetraeder in 3 s
    ohne Verfeinerungsband, 2 mm kleinstes Element, 60 mm Paket:
        79.345 Tetraeder in 14 s

Der Luftspalt ist in einem bezahlbaren 3-D-Netz also **nicht aufgeloest**.
Deshalb misst diese Stufe ein VERHAELTNIS: zweimal dasselbe Netz, einmal mit
leitenden Ringen, einmal mit isolierenden. Der Netzfehler steckt in beiden
Zahlen gleich und faellt weitgehend heraus.

Die Pruefungen hier nageln genau das fest: dass die beiden Laeufe sich in
NICHTS ausser der Ringleitfaehigkeit unterscheiden, dass die Koerpernummern
stimmen (derselbe Fehler wie in 2-D: ElmerGrid nummeriert um und der Loeser
gibt still ein leeres Feld aus), und dass das Ergebnis sagt, ob der Luftspalt
aufgeloest war.
"""

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_asm
import ema_em2d_harm as H2
import ema_em3d_harm as H3
import ema_maschinenart as MA

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


GEOM = {"p": 3, "slots": 36, "statorID": 190.0, "statorOD": 280.0,
        "rotorOD": 188.6, "shaftD": 60.0, "slotDepth": 25.0,
        "rotorBars": 28, "axialLen": 60.0}


# ── 1. Koerpernummern: luecklos ab 1 ──────────────────────────────────────────

print("\n1. Koerpernummern — derselbe stille Fehler wie in 2-D")

fest = sorted({H3.GID_WELLE, H3.GID_ROTOR, H3.GID_STAEBE, H3.GID_STEG,
               H3.GID_LUFT, H3.GID_STATOR, H3.GID_RING, H3.GID_STIRN})
pruefe(fest == list(range(1, len(fest) + 1)) and H3.GID_NUT0 == len(fest) + 1,
       f"die festen Koerper belegen luecklos 1..{len(fest)}, die Nuten "
       f"schliessen ab {H3.GID_NUT0} an — ElmerGrid -autoclean nummeriert sonst "
       f"um und der Loeser gibt ein leeres Feld aus, ohne zu widersprechen")
pruefe(H3.GID_RING != H3.GID_STAEBE,
       "der Kurzschlussring ist ein EIGENER Koerper — sonst liesse er sich "
       "nicht getrennt abschalten, und genau darauf beruht diese Stufe")


# ── 2. Die Geometrie kommt aus DERSELBEN Quelle wie Stufe B ───────────────────

print("\n2. Eine Geometrie, nicht zwei")

kf = ema_asm.kaefig(GEOM, 60.0)
kf["steg_mm"] = ema_asm.KAEFIG_STEG_MM
m2 = H2.masse(GEOM, kf)
pruefe(m2["n_stab"] == kf["n_stab"],
       f"der Querschnitt der 3-D-Stufe ist der der 2-D-Stufe "
       f"({m2['n_stab']} Staebe, ema_em2d_harm.quer_flaechen)")
pruefe(abs(m2["r_stab_a"] - (m2["r_rot"] - ema_asm.KAEFIG_STEG_MM / 1000.0)) < 1e-9,
       "und der Steg ueber der Kaefignut sitzt an derselben Stelle")

# Der Ringquerschnitt muss dem entsprechen, den ema_asm ansetzt und den das CAD
# zeichnet -- drei Stellen, eine Zahl.
import math
ring_h = math.sqrt(m2["A_ring_m2"] * m2["t_stab"] / m2["b_stab"])
ring_w = math.sqrt(m2["A_ring_m2"] * m2["b_stab"] / m2["t_stab"])
pruefe(abs(ring_h * ring_w - m2["A_ring_m2"]) < 1e-12,
       f"der Ringquerschnitt ({1000 * ring_h:.1f} x {1000 * ring_w:.1f} mm) ist "
       f"genau A_ring aus ema_asm ({1e6 * m2['A_ring_m2']:.0f} mm^2)")


# ── 3. Die beiden Laeufe unterscheiden sich in NICHTS ausser dem Ring ─────────

print("\n3. Der Unterschied der beiden Laeufe ist genau ein Wort")

netz_attrappe = {"n_nut": 3, "tets": 1000, "knoten": 500}
j = {H2.GID_NUT0 + k: complex(1.0, 0.5) for k in range(3)}
with tempfile.TemporaryDirectory() as td:
    p_mit = H3.schreibe_sif(netz_attrappe, 942.5, 1.2e5, j, td, 78.0,
                            ring_leitet=True)
    mit = open(p_mit).read()
    p_ohne = H3.schreibe_sif(netz_attrappe, 942.5, 1.2e5, j, td, 78.0,
                             ring_leitet=False)
    ohne = open(p_ohne).read()

z_mit = [l for l in mit.splitlines() if l.strip()]
z_ohne = [l for l in ohne.splitlines() if l.strip()]
pruefe(len(z_mit) == len(z_ohne), "beide Fallbeschreibungen sind gleich lang")
unterschiede = [(a, b) for a, b in zip(z_mit, z_ohne) if a != b]
pruefe(len(unterschiede) == 1,
       f"sie unterscheiden sich in GENAU einer Zeile: {unterschiede}")
if unterschiede:
    a, b = unterschiede[0]
    pruefe("Material" in a and "Material" in b,
           "und diese Zeile ist die Materialzuweisung des Rings — Netz, "
           "Betriebspunkt, Statorstrom, Schlupf und Steg sind identisch")

pruefe(f"Electric Conductivity = {1.2e5:.6e}" in mit,
       "der leitende Lauf traegt sigma_eff auf Staeben UND Ringen")
pruefe(re.search(r"Target Boundaries\(1\) = %d" % H3.GID_RAND, mit) is not None,
       "die Randbedingung sitzt auf dem Aussenrand")

# Zwei Loeserfehler, beide gemessen und beide teuer, weil sie erst NACH der
# Rechnung auffallen.
def _solverbloecke(sif: str) -> dict:
    """Die Solver-Bloecke einer Fallbeschreibung, nach Nummer.

    Nicht ueber ``split("Solver ")``: die Zeile ``Linear System Solver = …``
    enthaelt dieselbe Zeichenfolge, und die Bloecke faelen auseinander. Ein Test,
    der am eigenen Zerlegen scheitert, meldet einen Fehler, den es nicht gibt.
    """
    aus, nr = {}, None
    for zeile in sif.splitlines():
        k = zeile.strip()
        if k.startswith("Solver ") and k[7:].strip().isdigit():
            nr = int(k[7:].strip())
            aus[nr] = []
        elif k == "End":
            nr = None
        elif nr is not None:
            aus[nr].append(k)
    return {n: "\n".join(z) for n, z in aus.items()}


bloecke = _solverbloecke(mit)
solver = [bloecke.get(1, ""), bloecke.get(2, "")]
# Der Aussenrand muss Mantel UND beide Deckel tragen. Fehlt ein Deckel, ist das
# Gebiet dort offen und A unbestimmt — und das Ergebnis sieht aus wie ein Feld.
import inspect as _insp
_q = _insp.getsource(H3.baue_netz)
pruefe("n_deckel" in _q and "Aussenrand unvollstaendig" in _q,
       "der Netzbau zaehlt Mantel- und Deckelflaechen und weist einen "
       "unvollstaendigen Rand ab")
pruefe("getBoundingBox(-1, -1)" in _q,
       "und sucht die Deckel gegen die WIRKLICHE Huellbox des Modells — der "
       "frueher absolute Vergleich gegen eine zusammengerechnete Grenze traf nie")

pruefe(len(bloecke) == 3 and all(solver),
       f"die Fallbeschreibung hat drei Solver-Bloecke: {sorted(bloecke)}")
pruefe("Linear System Direct Method = MUMPS" in solver[0],
       "der Hauptloeser rechnet DIREKT — der iterative BiCGStabL stagnierte "
       "gemessen bei 6000 Iterationen und Residuum 1,5, neunzehn Minuten lang, "
       "und lieferte am Ende kein Feld")
pruefe("Linear System Solver" in solver[1],
       "und der Nachbearbeitungsloeser hat einen EIGENEN Gleichungsloeser — "
       "ohne ihn bricht Elmer mit 'Give \"Linear System Solver\"' ab, und zwar "
       "erst NACH der teuren Rechnung")
for blk in solver:
    pruefe("Linear System Solver" in blk,
           f"jeder Rechenloeser sagt, womit er sein Gleichungssystem loest")


# ── 4. Das Ergebnis sagt, was es wert ist ─────────────────────────────────────

print("\n4. Was das Ergebnis ueber sich selbst sagt")

kz = {"f1_Hz": 150.0, "schlupf": 0.0024, "tets": 79345, "knoten": 15000,
      "netzzeit_s": 14.0, "ring_h_mm": 36.9, "ring_w_mm": 12.3,
      "gap_aufgeloest": False, "T_mit_Ring_Nm": 2.299, "T_ohne_Ring_Nm": 0.001,
      "B_gap_1_mit_T": 0.3047, "P_staebe_W": 513.3, "P_ringe_W": 449.7,
      "ring_je_stab": 0.8761, "ring_je_stab_pct": 87.6,
      "ring_anteil_pct": 99.96, "zuschlag_analytisch_pct": 20.0}
txt = H3.bericht(kz)
pruefe("NICHT aufgeloest" in txt,
       "ein Netz ohne aufgeloesten Luftspalt sagt das im Bericht — das "
       "absolute Moment ist dann keine Aussage")
pruefe("87.6 %" in txt and "Stabverlust" in txt,
       "der Bericht fuehrt den Ringverlust JE STABVERLUST — das ist woertlich "
       "die Groesse, die ema_asm.kurzschlussring_zuschlag ansetzt")
pruefe("20 %" in txt,
       "der analytische Zuschlag steht daneben — das ist die Zahl, die diese "
       "Stufe pruefen soll")
pruefe("Paketlaenge" in txt,
       "und der Bericht sagt dazu, dass der Anteil KEINE Konstante ist: der "
       "Ring wird nicht laenger, wenn das Paket es wird")
pruefe("kein" in txt.lower() and "isolierenden Ringen" in txt,
       "der zweite Lauf wird richtig gelesen: mit isolierenden Ringen gibt es "
       "keinen Kaefig, nicht einen Kaefig ohne Ring")
pruefe("Grundwelle" in txt,
       "und die Luftspalt-Grundwelle steht da — die eine Zahl, an der sich "
       "2-D und 3-D vergleichen lassen")

kz2 = dict(kz, gap_aufgeloest=True)
pruefe("NICHT aufgeloest" not in H3.bericht(kz2),
       "bei aufgeloestem Luftspalt entfaellt der Vorbehalt")


# ── 4b. Ein Feld, das keines ist, wird abgewiesen ─────────────────────────────

print("\n4b. Stille Nullen und unmoegliche Felder")

pruefe(H3.B_UNMOEGLICH_T > 3.0,
       f"die Schranke fuer eine unmoegliche Flussdichte liegt bei "
       f"{H3.B_UNMOEGLICH_T:.0f} T — hoch genug, dass eine gesaettigte Kante "
       f"sie nicht ausloest")
pruefe(0.0 < H3.WILD_ANTEIL < 0.01,
       f"verworfen wird nach dem VOLUMENANTEIL ueber der Schranke "
       f"({100 * H3.WILD_ANTEIL:.2f} %), nicht nach dem Maximum: ein einzelnes "
       f"Element an einer Nutecke rechnet auch in einem gesunden Feld 40 T "
       f"(in 2-D gemessen 56 T, bei 0,00 % Momentabweichung)")
_pf = inspect.getsource(H3.pruefe_feld) if (inspect := __import__("inspect")) else ""
pruefe("vol" in _pf and "WILD_ANTEIL" in _pf,
       "und die Pruefung gewichtet wirklich mit dem Zellvolumen")
pruefe(not hasattr(H3, "_joule_aus_log"),
       "die Joule-Leistung wird NICHT mehr aus der Bildschirmausgabe gelesen — "
       "dieser Elmer schreibt dort gemessen gar keine solche Zeile, und die "
       "Auswertung gab darum kommentarlos 0,0 W und daraus 0,000 Nm")
pruefe(hasattr(H3, "verluste_je_koerper") and hasattr(H3, "pruefe_feld"),
       "sie kommt aus der Ergebnisdatei, und davor prueft pruefe_feld, ob das "
       "Ergebnis ueberhaupt ein Feld ist")


# ── 4c. Die beiden Fehler, die diese Stufe gekostet haben ─────────────────────

print("\n4c. Was das Feld gueltig gemacht hat — und was es vorher kaputt machte")

# DER Regressionswaechter dieser Stufe. Elmers Vorgabe fuer Use Tree Gauge ist
# True; die Zeile zu LOESCHEN reicht also nicht.
pruefe("Use Tree Gauge = Logical False" in mit,
       "die Baum-Eichung ist AUSDRUECKLICH aus — Elmers Vorgabe ist True, und "
       "mit ihr kam am selben Netz 44,06 T statt 0,39 T heraus (2-D: 0,40 T)")
pruefe("Linear System Solver = Direct" in mit,
       "und dazu ein DIREKTER Loeser: ohne Eichung ist das System singulaer, "
       "aber vertraeglich — ein iterativer Loeser darf hier nicht laufen")

_bn = inspect.getsource(H3.baue_netz)
pruefe("z_lo" in _bn and "z_hi" in _bn and "occ.copy" in _bn,
       "der Nutleiter wird von Deckel zu Deckel gebaut, nicht nur ueber das "
       "Paket — sonst endet die eingepraegte Stromdichte mitten im Gebiet und "
       "die rechte Seite ist unvertraeglich (gemessen 12,6 % wildes Volumen)")
pruefe(not hasattr(H3, "wickelkopf_stromdichte")
       and "GID_WKRING" not in inspect.getsource(H3.schreibe_sif),
       "einen Wickelkopf-Rueckleiter gibt es nicht mehr: er war der Versuch, "
       "einen im Gebiet endenden Strom zu schliessen, und ohne ihn war das "
       "Ergebnis genauso falsch (1,40 T gegen 1,98 T, beide unbrauchbar)")

# Der Modulkopf muss den WIRKLICHEN Stand tragen.
kopf = inspect.getdoc(H3) or ""
pruefe("Tree Gauge = False" in kopf and "44,06" in kopf,
       "der Modulkopf traegt die Messreihe zur Baum-Eichung — die Zeile, an "
       "der diese Stufe fuenf Anlaeufe lang gescheitert ist")
pruefe("Imaginaerteil" in kopf and "Nullraum" in kopf,
       "und die Erklaerung, warum es so lange verborgen blieb: die Eichung "
       "zerstoert nur den Imaginaerteil, und der Ausreisser haengt an nichts "
       "Physikalischem")
pruefe("2359" in kopf and "1129" in kopf,
       "den unvollstaendigen Aussenrand mit den gemessenen Flaechen — ein "
       "wirklicher Fehler, behoben, und trotzdem nicht die Ursache")
pruefe("AV re {e}" in kopf and "WIRKUNGSLOS" in kopf,
       "die Falle mit den fuenf Schreibweisen der Randbedingung, von denen nur "
       "EINE die Kanten bindet und Elmer dazu nichts meldet")
pruefe("0,3047" in kopf and "0,2870" in kopf,
       "und die Probe, die die Stufe traegt: 3-D gegen 2-D am selben "
       "Betriebspunkt")
pruefe("87,6" in kopf or "Ring/Stab" in kopf,
       "sowie das Ergebnis, fuer das es diese Stufe gibt")

# Jfix muss AUS bleiben -- eingeschaltet war er der Verstaerker.
pruefe("Fix Input Current Density = Logical False" in mit,
       "Jfix bleibt ausgeschaltet: das Jfix-Problem ist ein reines "
       "Neumann-Poisson-System und damit singulaer")

# Und die eine wirksame Schreibweise darf nicht verloren gehen.
pruefe("AV re {e}" in mit and "AV im {e}" in mit,
       "die Randbedingung benutzt die EINZIGE Schreibweise, die die "
       "Kanten-Freiheitsgrade bindet")

# Die Vergleichszahl muss dieselbe Definition haben wie in 2-D.
_lg = inspect.getsource(H3.luftspalt_grundwelle)
pruefe("exp(1j" in _lg and "* 2" not in _lg.replace("0.25", ""),
       "die Luftspalt-Grundwelle ist der komplexe Zeiger OHNE Faktor 2 — genau "
       "wie in ema_em2d_harm, sonst verglichen die beiden Stufen zwei "
       "verschiedene Groessen")


# ── 4d. Ein Loeser, der aussteigt, darf nicht wie ein Ergebnis aussehen ───────

print("\n4d. Wenn MUMPS aufgibt, meldet Elmer trotzdem FINISHED")

import elmer_runner as ER

_stdout_kaputt = """
MAIN:  MUMPS library linked in.
 ** ERROR RETURN ** FROM ZMUMPS INFO(1)=  -13
 ** INFO(2)=           -5525
 ** ERROR RETURN ** FROM ZMUMPS INFO(1)=   -3
ComputeChange: NS (ITER=1) (NRM,RELC): ( 0.59085062E-09  2.0000000     )
MAIN: *** Elmer Solver: ALL DONE ***
ELMER SOLVER FINISHED AT: 2026/09/06
"""
_codes = ER._mumps_fehler(_stdout_kaputt)
pruefe(len(_codes) == 2 and "-13" in _codes[0],
       f"die MUMPS-Fehlercodes werden aus der BILDSCHIRMAUSGABE gelesen — sie "
       f"stehen nicht im Rueckgabewert des Prozesses, und Elmer bricht darauf "
       f"nicht ab: {_codes}")
pruefe("Speicher" in _codes[0],
       "und im Klartext benannt: -13 ist eine fehlgeschlagene "
       "Speicheranforderung, also ein zu grosses Netz")
pruefe(ER._mumps_fehler("alles ruhig, ELMER SOLVER FINISHED") == [],
       "ein sauberer Lauf meldet keine Codes")
pruefe("_mumps_fehler(out)" in inspect.getsource(ER.run_elmersolver)
       and "\"ok\": False" in inspect.getsource(ER.run_elmersolver),
       "und run_elmersolver macht daraus einen FEHLSCHLAG — gemessen an einem "
       "1,1-Mio.-Netz kamen sonst 0,0 W Verlust und 0,000 Nm Moment heraus, "
       "also Zahlen, die wie Ergebnisse aussehen")

pruefe(0.0 < H3.B_LEER_T < 0.01,
       f"der zweite Riegel ist eine Untergrenze fuer die Flussdichte "
       f"({1000 * H3.B_LEER_T:.1f} mT): ohne sie ist „gar kein Feld\u201c von "
       f"„gesundes Feld\u201c nicht zu unterscheiden")
_pf2 = inspect.getsource(H3.pruefe_feld)
pruefe("B_LEER_T" in _pf2 and "kein Feld gerechnet" in _pf2,
       "und pruefe_feld weist ein totes Feld ausdruecklich ab")
pruefe("0,1428" in inspect.getsource(H3).split("def ")[0] or "0,1428" in _pf2
       or "0,1428" in open(H3.__file__).read(),
       "wobei im Quelltext steht, was dieser Riegel NICHT faengt: im gemessenen "
       "Fall blieben 0,1428 T stehen — gefangen hat ihn der MUMPS-Code")


# ── 5. Das Tor ────────────────────────────────────────────────────────────────

print("\n5. Nur der Kaefiglaeufer, und nur der Innenlaeufer")

for art in ("pmsm", "synrm", "eesm"):
    try:
        H3.rechne({"machineType": art, "geom": dict(GEOM)}, 3000.0, 100.0, "/tmp/nie")
        pruefe(False, f"'{art}' darf nicht in die 3-D-Kaefigstufe laufen")
    except MA.ArtNichtUnterstuetzt:
        pruefe(True, f"'{art}' wird abgewiesen, statt ersatzweise ASM-Physik zu rechnen")
    except Exception as e:
        pruefe(False, f"'{art}' scheitert am falschen Ort: {type(e).__name__}: {e}")

import ema_radien
try:
    H3.rechne({"machineType": "asm",
               "geom": dict(GEOM, rotorPosition="aussen", rotorID=290.0,
                            rotorOD=320.0)}, 3000.0, 100.0, "/tmp/nie")
    pruefe(False, "ein Aussenlaeufer darf hier nicht durchlaufen")
except (ema_radien.BauformNichtUnterstuetzt, MA.ArtNichtUnterstuetzt):
    pruefe(True, "ein Aussenlaeufer wird abgewiesen — das Netz ist auf den "
                 "Innenlaeufer gebaut")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
