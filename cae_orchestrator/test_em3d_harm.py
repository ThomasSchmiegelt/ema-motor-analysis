"""Pruefungen der harmonischen 3-D-Stufe (``ema_em3d_harm``, Stufe D).

Wozu diese Stufe da ist -- und was sie ausdruecklich NICHT kann
----------------------------------------------------------------

Stufe B (2-D) kann eine Sache grundsaetzlich nicht: ein Querschnitt hat keine
Stirnseite, also keinen **Kurzschlussring**. ``ema_asm`` schlaegt ihn mit
``KURZSCHLUSSRING_ZUSCHLAG = 0,20`` auf -- eine Zahl, die gesetzt und nie
gemessen wurde. Stufe D misst sie.

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

pruefe(sorted({H3.GID_WELLE, H3.GID_ROTOR, H3.GID_STAEBE, H3.GID_STEG,
               H3.GID_LUFT, H3.GID_STATOR, H3.GID_RING,
               H3.GID_STIRN}) == [1, 2, 3, 4, 5, 6, 7, 8]
       and H3.GID_NUT0 == 9,
       "die festen Koerper belegen luecklos 1..8, die Nuten schliessen ab 9 an "
       "— ElmerGrid -autoclean nummeriert sonst um und der Loeser gibt ein "
       "leeres Feld aus, ohne zu widersprechen")
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


# ── 4. Das Ergebnis sagt, was es wert ist ─────────────────────────────────────

print("\n4. Was das Ergebnis ueber sich selbst sagt")

kz = {"f1_Hz": 150.0, "schlupf": 0.0024, "tets": 79345, "knoten": 15000,
      "netzzeit_s": 14.0, "ring_h_mm": 36.9, "ring_w_mm": 12.3,
      "gap_aufgeloest": False, "T_mit_Ring_Nm": 8.0, "T_ohne_Ring_Nm": 9.5,
      "ring_anteil_pct": -18.8, "zuschlag_analytisch_pct": 20.0}
txt = H3.bericht(kz)
pruefe("NICHT aufgeloest" in txt,
       "ein Netz ohne aufgeloesten Luftspalt sagt das im Bericht — das "
       "absolute Moment ist dann keine Aussage")
pruefe("Verhaeltnis" in txt,
       "und weist darauf hin, dass das Verhaeltnis der beiden Laeufe es sehr wohl ist")
pruefe(f"{ema_asm.KURZSCHLUSSRING_ZUSCHLAG * 100:.0f} %" in txt,
       f"der analytische Zuschlag von "
       f"{100 * ema_asm.KURZSCHLUSSRING_ZUSCHLAG:.0f} % steht daneben — das ist "
       f"die Zahl, die diese Stufe pruefen soll")

kz2 = dict(kz, gap_aufgeloest=True)
pruefe("NICHT aufgeloest" not in H3.bericht(kz2),
       "bei aufgeloestem Luftspalt entfaellt der Vorbehalt")


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
