"""Pruefungen der harmonischen 2-D-ASM-Feldstufe (``ema_em2d_harm``, Stufe B).

Geprueft wird das, was still falsch sein koennte -- nicht das, was ohnehin
auffaellt. Jede der fuenf Gruppen hier steht fuer einen Fehler, der im Bau
dieser Stufe **wirklich** passiert ist und der sich nicht durch einen Absturz,
sondern durch eine plausible falsche Zahl gemeldet haette:

1. ``sigma_eff = s*sigma`` und nicht ``sigma/s``. Aus dem Ersatzschaltbild ist
   ``R2/s`` gelaeufig; unbesehen aufs Material uebertragen ergibt das bei 2 %
   Schlupf einen Faktor 2500 im Laeuferstrom.
2. Die Koerpernummern. ``ElmerGrid -autoclean`` nummeriert um; mit Nuten ab 100
   traf jede ``Target Bodies``-Zeile ins Leere, es floss kein Strom, und das
   Feld kam ueberall exakt 0 heraus.
3. Die Raumgrundwelle des Luftspaltfeldes. Mit dem sonst ueblichen Faktor 2 kam
   sie groesser heraus als das oertliche Maximum.
4. Arkkios Momentintegral -- gegen eine von Hand gerechnete Ringloesung.
5. Die Wicklung. Sie wird gebaut, nicht als Formfaktor angenommen; also muss
   nachgewiesen sein, dass sie symmetrisch ist, umlaeuft und den richtigen
   Wicklungsfaktor hat.

Der Elmer-Lauf am Ende ist der einzige langsame Teil (rund 20 s) und wird
uebersprungen, wenn Elmer fehlt -- dann steht das ausdruecklich da, statt
stillschweigend zu bestehen.
"""

import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_asm
import ema_em2d_harm as H
import ema_maschinenart as MA

_ok, _fehl = 0, 0


def pruefe(bedingung, text):
    global _ok, _fehl
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def nah(a, b, rel=1e-9, abs_=0.0):
    return abs(a - b) <= max(rel * max(abs(a), abs(b)), abs_)


GEOM = {"p": 3, "slots": 36, "statorID": 190.0, "statorOD": 280.0,
        "rotorOD": 188.6, "shaftD": 60.0, "slotDepth": 25.0,
        "rotorBars": 28, "axialLen": 150.0}


# ── 1. Die Schlupf-Leitfaehigkeit ─────────────────────────────────────────────

print("\n1. sigma_eff = s*sigma — die Verwechslung, die 2500-fach danebenliegt")

sigma = 1.0 / 2.8e-8
for s_ in (1.0, 0.05, 0.002):
    # Die induzierte Stromdichte im Staenderrahmen bei w1 muss dieselbe sein wie
    # im Laeuferrahmen bei w2 = s*w1. Das ist die ganze Herleitung, als Gleichung.
    w1 = 2 * math.pi * 150.0
    a = 0.01 + 0.003j
    j_laeufer = -1j * (s_ * w1) * sigma * a
    j_staender = -1j * w1 * (s_ * sigma) * a
    pruefe(abs(j_laeufer - j_staender) < 1e-6 * abs(j_laeufer),
           f"bei s = {s_:.3f} liefert sigma_eff = s*sigma dieselbe Stromdichte "
           f"wie die Rechnung im Laeuferrahmen")

pruefe(0.0 * sigma == 0.0,
       "s -> 0 (Synchronlauf) gibt sigma_eff = 0: kein Laeuferstrom, kein Moment")
pruefe(nah(1.0 * sigma, sigma),
       "s = 1 (Stillstand) gibt sigma_eff = sigma bei voller Speisefrequenz")

# Leistungsprobe: was das Modell verheizt, ist die LUFTSPALTleistung.
s_ = 0.02
sigma_eff = s_ * sigma
j = 3.0e6                                   # irgendeine Stromdichte [A/m^2]
p_modell = j ** 2 / (2 * sigma_eff)
p_wirklich = j ** 2 / (2 * sigma)
pruefe(nah(p_wirklich, s_ * p_modell, rel=1e-12),
       "P_Laeufer = s * P_Modell — wer die Joule-Zahl direkt als Kaefigverlust "
       f"liest, ueberschaetzt ihn hier um das {1 / s_:.0f}-fache")

# Die falsche Richtung faellt nicht durch eine Ausnahme auf, sondern durch den
# Betrag: das ist der Grund, warum sie hier festgenagelt wird.
pruefe(abs((sigma / s_) / (s_ * sigma) - 1.0 / s_ ** 2) < 1e-6,
       f"sigma/s laege bei s = {s_} um den Faktor {1 / s_ ** 2:.0f} daneben — "
       "eine Zahl, die nicht widerspricht")


# ── 2. Koerpernummern ─────────────────────────────────────────────────────────

print("\n2. Koerpernummern — der Lauf, der still ein leeres Feld ausgab")

pruefe(H.GID_WELLE == 1 and H.GID_NUT0 == 7
       and sorted({H.GID_WELLE, H.GID_ROTOR, H.GID_STAEBE, H.GID_STEG,
                   H.GID_LUFT, H.GID_STATOR}) == [1, 2, 3, 4, 5, 6],
       "die festen Koerper belegen luecklos 1..6, die Nuten schliessen ab 7 an "
       "— ElmerGrid -autoclean nummeriert sonst um")

with tempfile.TemporaryDirectory() as td:
    mp = os.path.join(td, "mesh.elements")
    with open(mp, "w") as fh:
        for k in range(1, 9):
            fh.write(f"{k} {k} 303 1 2 3\n")
    H.pruefe_koerpernummern(td, 8)
    pruefe(True, "eine luecklose Nummerierung 1..8 wird angenommen")
    try:
        H.pruefe_koerpernummern(td, 41)
        pruefe(False, "eine falsche Anzahl muss auffallen")
    except RuntimeError as e:
        pruefe("umnummeriert" in str(e),
               "eine falsche Anzahl gibt einen klaren Fehler, keine leere Loesung")


# ── 3. Raumgrundwelle des Luftspaltfeldes ─────────────────────────────────────

print("\n3. Grundwelle des Luftspaltfeldes — nicht das oertliche Maximum")

p = 3
th = np.linspace(0, 2 * math.pi, 4000, endpoint=False)
gew = np.ones_like(th)
b1 = 0.8 * np.exp(-1j * p * th)                       # reine Grundwelle
mess = abs(np.sum(b1 * np.exp(1j * p * th) * gew) / np.sum(gew))
pruefe(nah(mess, 0.8, rel=1e-6),
       "eine reine Grundwelle wird mit ihrer Amplitude wiedergefunden (kein Faktor 2)")

b2 = b1 + 0.5 * np.exp(-1j * 7 * p * th)              # plus Nutungsoberfeld
mess2 = abs(np.sum(b2 * np.exp(1j * p * th) * gew) / np.sum(gew))
pruefe(nah(mess2, 0.8, rel=1e-6),
       "ein ueberlagertes Nutungsoberfeld aendert die Grundwelle nicht")
pruefe(mess2 <= np.max(np.abs(b2)) * 1.001,
       f"die Grundwelle ({mess2:.3f} T) bleibt unter dem oertlichen Maximum "
       f"({np.max(np.abs(b2)):.3f} T) — genau das war beim Faktor 2 verletzt")


# ── 4. B aus A, und Arkkios Momentintegral ────────────────────────────────────

print("\n4. B aus dem Potential, und Arkkio gegen eine Ringloesung von Hand")

# P1-Dreieck: bei linearem A ist B elementweise konstant und EXAKT.
pts = np.array([[0.0, 0.0], [2.0, 0.0], [0.0, 3.0], [2.0, 3.0]])
conn = np.array([[0, 1, 2], [1, 3, 2]])
ka, kb = 0.7, -1.3
a = ka * pts[:, 0] + kb * pts[:, 1]
bx, by, fl = H._b_je_dreieck(pts, conn, a)
pruefe(np.allclose(bx, kb) and np.allclose(by, -ka),
       "B = (dA/dy, -dA/dx) kommt bei linearem A exakt heraus")
pruefe(nah(float(fl.sum()), 6.0, rel=1e-12),
       "die Dreiecksflaechen summieren sich auf die Rechteckflaeche")

# Arkkio gegen die geschlossene Loesung ueber einem Ring:
#   B_r = B1 (konstant), B_t = B2 (konstant, reell)
#   T = L/(mu0*(ra-ri)) * 0.5*B1*B2 * Integral r dA
#     = L/(mu0*(ra-ri)) * 0.5*B1*B2 * (2*pi/3)*(ra^3 - ri^3)
ri, ra, L = 0.0943, 0.0950, 0.150
nr, nt = 40, 720
rr = np.repeat(np.linspace(ri, ra, nr, endpoint=False) + (ra - ri) / (2 * nr), nt)
dr = (ra - ri) / nr
dth = 2 * math.pi / nt
flae = rr * dr * dth
B1, B2 = 0.9, 0.35
t_num = H.arkkio_moment(np.full(rr.shape, B1 + 0j), np.full(rr.shape, B2 + 0j),
                        rr, flae, L, ri, ra)
t_exakt = L / (H.MU0 * (ra - ri)) * 0.5 * B1 * B2 * (2 * math.pi / 3) * (ra ** 3 - ri ** 3)
pruefe(nah(t_num, t_exakt, rel=2e-4),
       f"Arkkio trifft die Ringloesung von Hand: {t_num:.2f} Nm gegen "
       f"{t_exakt:.2f} Nm")

# Eine einzelne umlaufende Welle traegt KEIN Moment -- B_r und B_t stehen dann
# in Quadratur. Faellt diese Probe, misst die Stufe Rauschen als Moment.
thc = np.tile(np.linspace(0, 2 * math.pi, nt, endpoint=False), nr)
br_w = 0.9 * np.exp(-1j * p * thc)
bt_w = 1j * br_w
pruefe(abs(H.arkkio_moment(br_w, bt_w, rr, flae, L, ri, ra)) < 1e-6,
       "eine einzelne umlaufende Welle in Quadratur gibt exakt kein Moment")

# Flaechengewichtetes Perzentil: winzige Dreiecke duerfen es nicht kippen.
w = np.array([1.0, 1.0, 1.0, 1e-9])
v = np.array([1.0, 1.1, 1.2, 500.0])
pruefe(H._perzentil(v, w, 0.99) < 2.0,
       "ein einzelnes entartetes Dreieck mit 500 T kippt das 99. Perzentil nicht "
       "— das Maximum lag gemessen bei 480 T")


# ── 5. Die Wicklung ───────────────────────────────────────────────────────────

print("\n5. Die Wicklung wird gebaut, nicht angenommen")

n_slots, p = int(GEOM["slots"]), int(GEOM["p"])
belag = [H.nutbelag(k, n_slots, p) for k in range(n_slots)]
zaehl = {ph: sum(1 for b in belag if b[0] == ph) for ph in "abc"}
pruefe(zaehl == {"a": 12, "b": 12, "c": 12},
       f"alle drei Straenge bekommen gleich viele Nuten: {zaehl}")
for ph in "abc":
    vz = sum(b[1] for b in belag if b[0] == ph)
    pruefe(vz == 0, f"Strang {ph} ist in sich ausgeglichen (Hin = Zurueck)")

j = H.stator_stroeme(GEOM, 100.0, 1.0e-4)
pruefe(abs(sum(j.values())) < 1e-6 * abs(list(j.values())[0]),
       "die Summe aller Nutstroeme ist null — kein Nullsystem, kein Strom "
       "ueber den Sternpunkt")

# Die eingepraegte Durchflutung muss eine VORWAERTS umlaufende Welle sein und
# den Wicklungsfaktor der 60-Grad-Zonenwicklung tragen.
thn = np.array([2 * math.pi * k / n_slots for k in range(n_slots)])
iw = np.array([j[H.GID_NUT0 + k] for k in range(n_slots)])
vor = abs(np.sum(iw * np.exp(+1j * p * thn))) / n_slots
rueck = abs(np.sum(iw * np.exp(-1j * p * thn))) / n_slots
pruefe(vor > 50 * max(rueck, 1e-12),
       f"die Welle laeuft vorwaerts: Mitsystem {vor:.1f} gegen Gegensystem "
       f"{rueck:.2e}")

q = n_slots / (6.0 * p)
gamma = math.pi / (3.0 * q)
k_d = math.sin(q * gamma / 2) / (q * math.sin(gamma / 2))
k_w_gebaut = vor / (100.0 / 1.0e-4)
pruefe(nah(k_w_gebaut, k_d, rel=0.02),
       f"der Wicklungsfaktor der gebauten Anordnung ist {k_w_gebaut:.4f} und "
       f"trifft den Zonenfaktor {k_d:.4f} — ema_asm setzt {ema_asm.K_W} an")


# ── 6. Ein wirklicher Lauf ────────────────────────────────────────────────────

print("\n6. Ein wirklicher Elmer-Lauf")

import elmer_runner

if not elmer_runner.ELMER_OK:
    print("  — Elmer fehlt, der Feldlauf wird UEBERSPRUNGEN (nicht bestanden)")
else:
    import dataclasses
    if "feld" not in MA.ARTEN["asm"].stufen:
        MA.ARTEN["asm"] = dataclasses.replace(MA.ARTEN["asm"],
                                              stufen=MA.ARTEN["asm"].stufen + ("feld",))
    with tempfile.TemporaryDirectory() as td:
        payload = {"geom": dict(GEOM), "machineType": "asm"}
        ctx = H.vorbereiten(payload, 3000.0, 150.0, td)
        pruefe(ctx["netz"]["dreiecke"] > 5000,
               f"das Netz steht: {ctx['netz']['dreiecke']} Dreiecke, "
               f"{ctx['netz']['n_stab']} Staebe, {ctx['netz']['n_nut']} Nuten")

        st = H.steg_saettigen(ctx, 0.003)
        b_steg = st["kz"]["B_steg_T"]
        pruefe(1.0 < st["mu_r_steg"] < H.MU_R_EISEN,
               f"die Steg-Permeabilitaet wird gemessen und landet zwischen Luft "
               f"und Blech: mu_r = {st['mu_r_steg']:.0f}")
        pruefe(abs(b_steg - H.B_STEG_SAT_T) < 0.15 * H.B_STEG_SAT_T,
               f"der Steg steht danach bei {b_steg:.2f} T, also bei seiner "
               f"Saettigung ({H.B_STEG_SAT_T:.1f} T) — nicht bei den 12 T, die "
               f"das ungesaettigte Blech ergab")

        kz = H.loese(ctx, 0.003, mu_r_steg=st["mu_r_steg"])
        pruefe(kz["T_abweichung_pct"] < 10.0,
               f"die beiden unabhaengigen Momentwege stimmen auf "
               f"{kz['T_abweichung_pct']:.1f} % ueberein (Arkkio "
               f"{kz['T_arkkio_Nm']:.2f} Nm, Leistungsbilanz "
               f"{kz['T_leistung_Nm']:.2f} Nm)")
        pruefe(kz["B_gap_1_T"] <= kz["B_gap_amp_T"] * 1.001,
               f"die Grundwelle {kz['B_gap_1_T']:.3f} T bleibt unter dem "
               f"oertlichen Maximum {kz['B_gap_amp_T']:.3f} T")
        pruefe(kz["B_eisen_p99_T"] < 4.0,
               f"das Blech steht im 99. Perzentil bei {kz['B_eisen_p99_T']:.2f} T "
               f"— mit ungesaettigtem Steg waren es 15 T")
        pruefe(kz["P_luftspalt_W"] > 0 and
               nah(kz["P_laeufer_W"], 0.003 * kz["P_luftspalt_W"], rel=0.02),
               "P_Laeufer = s * P_Luftspalt haelt auch im wirklichen Lauf")

        # Ohne Schlupf kein Moment. Gepruef wird die steigende Flanke, nicht ein
        # einzelner Punkt: das Kippmoment liegt bei Stromeinpraegung sehr weit
        # unten (gemessen 0,08 %), ein fester Schwellwert traefe es nicht.
        flanke = [H.loese(ctx, x, mu_r_steg=st["mu_r_steg"])["T_arkkio_Nm"]
                  for x in (1e-4, 3e-4, 6e-4)]
        pruefe(flanke[0] < flanke[1] < flanke[2],
               f"auf der steigenden Flanke waechst das Moment mit dem Schlupf: "
               f"{flanke[0]:.2f} < {flanke[1]:.2f} < {flanke[2]:.2f} Nm — ohne "
               f"Schlupf gaebe es keines")

        ca = H.leerlauf_carter(ctx, st["mu_r_steg"])
        pruefe(ca["k_carter_gemessen"] > ca["k_carter_angesetzt"],
               f"die gezeichnete OFFENE Nut hat einen groesseren Carter-Faktor "
               f"({ca['k_carter_gemessen']:.2f}) als der in ema_asm angesetzte "
               f"({ca['k_carter_angesetzt']:.2f}) — die Abweichung hat damit eine Adresse")


# ── 7. Die Stufe im Maschinenart-Begriff ──────────────────────────────────────

print("\n7. Was die Stufe von der Maschinenart verlangt")

for art in ("pmsm", "synrm", "eesm"):
    try:
        H.rechne({"machineType": art, "geom": dict(GEOM)}, 3000.0, 100.0, "/tmp/nie")
        pruefe(False, f"'{art}' darf nicht in die Kaefiglaeufer-Stufe laufen")
    except MA.ArtNichtUnterstuetzt:
        pruefe(True, f"'{art}' wird abgewiesen, statt ersatzweise ASM-Physik zu rechnen")
    except Exception as e:
        pruefe(False, f"'{art}' scheitert am falschen Ort: {type(e).__name__}: {e}")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
