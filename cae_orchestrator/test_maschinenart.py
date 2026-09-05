"""Maschinenart als Tor, und die ASM analytisch — ohne Server, ohne FreeCAD.

Der Anlass steht im Kopf von ``ema_maschinenart``: das Werkzeug ist als PSM mit
Hairpins gewachsen, und die Annahme sitzt verteilt in sechs Modulen, nicht in
einem Schalter. Wer eine Asynchronmaschine hineinreicht, bekaeme ohne diese Tore
keine Fehlermeldung, sondern PSM-Zahlen unter fremdem Namen.

Diese Datei haelt vier Dinge fest:

  1. das Tor -- eine nicht getragene Art wird ABGEWIESEN, nicht ersetzt;
  2. die Normierungsbruecke ``ema_asm.k_norm`` -- ihre Rechtfertigung ist die
     Momenterhaltung, und die wird hier nachgerechnet, nicht geglaubt;
  3. den ASM-Betriebspunkt -- Magnetisierungsstrom, Schlupf, Kaefigverlust;
  4. die 14. Paarvergleichs-Achse -- PSM und ASM am GEMEINSAMEN Betriebspunkt.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cae_cli
import ema_analysis
import ema_asm
import ema_maschinenart as MA
import ema_paarvergleich as PV
import ema_pipeline
import ema_screen
import ema_text2ema
import ema_thermal

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def _basis(art="pmsm"):
    pl = cae_cli.frischer_payload()
    pl["geom"]["machineType"] = art
    return pl


# ── 1. Der Begriff und das Tor ────────────────────────────────────────────────

print("1. Maschinenart als Begriff — und als Tor")

pruefe(MA.art_code({}) == "pmsm",
       "ohne Angabe gilt pmsm — alles Bestehende bleibt unveraendert")
pruefe(MA.art_code({"geom": {"machineType": "asm"}}) == "asm",
       "die Art wird aus geom gelesen (dort, wo die analytischen Funktionen sie sehen)")
pruefe(MA.art_code({"geom": {"machineType": "quatsch"}}) == "pmsm",
       "ein unbekannter Wert im Payload faellt auf die Vorgabe zurueck")

try:
    MA.hole("quatsch")
    pruefe(False, "hole() weist einen unbekannten Code ab")
except MA.ArtNichtUnterstuetzt:
    pruefe(True, "hole() weist einen unbekannten Code ab — ein Tippfehler geht "
                 "NICHT still als PSM durch")

pruefe(MA.traegt("pmsm", "em3d") and MA.traegt("asm", "analytisch"),
       "PSM traegt alle vier Stufen, die ASM die analytische")
pruefe(MA.traegt("asm", "feld") and MA.ARTEN["asm"].feldweg == "elmer2d_harm",
       "die ASM traegt den Feldlauf — aber ueber Elmers harmonischen Loeser "
       "(ema_em2d_harm), nicht ueber die FDM")
try:
    MA.pruefe_feldweg("asm", "fdm")
    pruefe(False, "die ASM darf NICHT in die 2-D-FDM")
except MA.ArtNichtUnterstuetzt as e:
    pruefe("feld2d" in str(e),
           "wer die ASM in die FDM schickt, bekommt die Adresse des richtigen "
           "Werkzeugs (feld2d) statt ein magnetostatisches Feld ohne Laeuferstroeme")
pruefe(MA.pruefe_feldweg("pmsm", "fdm").code == "pmsm",
       "die PSM laeuft weiterhin durch die FDM")
pruefe(MA.traegt("synrm", "analytisch") and MA.traegt("eesm", "analytisch"),
       "SynRM und EESM tragen die analytische Stufe (ema_synrm, ema_eesm)")
pruefe(not any(MA.traegt(c, st) for c in ("synrm", "eesm")
               for st in ("feld", "cad", "em3d")),
       "aber keine der beiden traegt Feld, CAD oder 3D — und die Tabelle sagt es, "
       "statt es einen Lauf herausfinden zu lassen")

try:
    MA.pruefe_stufe("asm", "cad")
    pruefe(False, "pruefe_stufe wirft")
except MA.ArtNichtUnterstuetzt as e:
    txt = str(e)
    pruefe("analytisch" in txt and "NICHT ersatzweise" in txt,
           "der Fehlertext sagt, was statt dessen geht, und dass NICHT ersatzweise "
           "mit PSM-Physik gerechnet wird")

pruefe(not MA.gilt("asm", "Isc_A") and not MA.gilt("asm", "T_rel_pct"),
       "Kurzschlussstrom und Reluktanzanteil gelten fuer die ASM nicht")
pruefe(MA.gilt("asm", "magnet_kg") and MA.gilt("asm", "gesamt_kg"),
       "Magnetmasse gilt sehr wohl — 0 kg ist eine Aussage, keine fehlende Zahl")
pruefe(MA.filtern("asm", {"Isc_A": 123.0, "gesamt_kg": 40.0})["Isc_A"] == "n. v.",
       "filtern() beschriftet die nicht anwendbaren Kennzahlen, statt sie zu nullen")

pruefe(list(MA.ARTEN) == ema_text2ema.SCHEMA["machineType"]["opts"],
       "die Auswahlliste im Schema kommt aus DIESEM Modul — keine zweite, "
       "handgepflegte Menge, die driften koennte")
pruefe(ema_text2ema.SCHEMA["machineType"]["def"] == "pmsm"
       and cae_cli.frischer_payload()["geom"]["machineType"] == "pmsm",
       "der frische Payload traegt die Art ausdruecklich mit (pmsm)")


# ── 2. Die Tore in Pipeline und Vorauswahl ────────────────────────────────────

print("\n2. Die Tore vor der Physik")

ema_pipeline._gate_maschinenart({"geom": {"machineType": "pmsm"}}, None, "feld")
pruefe(True, "die PSM passiert das Pipeline-Tor unveraendert")

for stufe in ("feld", "cad", "em3d"):
    try:
        ema_pipeline._gate_maschinenart({"geom": {"machineType": "asm"}}, None, stufe)
        pruefe(False, f"das Pipeline-Tor weist die ASM auf Stufe {stufe} ab")
    except MA.ArtNichtUnterstuetzt:
        pruefe(True, f"das Pipeline-Tor weist die ASM auf Stufe {stufe} ab — "
                     f"kein stiller PSM-Ersatz")

try:
    ema_screen.screene(_basis("asm"))
    pruefe(False, "die Vorauswahl weist die ASM ab")
except MA.ArtNichtUnterstuetzt as e:
    pruefe("paarvergleich --achse maschinenart" in str(e),
           "die Vorauswahl weist die ASM ab UND nennt den Weg, der heute geht")


# ── 3. Die Normierungsbruecke: nachgerechnet, nicht geglaubt ──────────────────

print("\n3. ema_asm.k_norm — die Bruecke zwischen Haus- und SI-Stromskala")

g = _basis("asm")["geom"]
L = float(g.get("axialLen") or 80.0)
p_ = int(g["p"])
n_ph = int(g["slots"]) / 3.0
kn = ema_asm.k_norm(g)

pruefe(abs(kn - math.pi * ema_asm.K_W * n_ph / p_ ** 2) < 1e-12,
       "k_norm = pi*k_w*N_ph/p^2 — genau der Faktor zwischen der normierten "
       "psi_pm-Formel und der physikalischen Flussverkettung")

b_m = ema_asm.ziel_feld(g)
R_gap = ((g["statorID"] / 2) + (g["rotorOD"] / 2)) / 2 / 1000.0
psi_haus = ema_analysis.compute_performance(g, b_m, axial_mm=L)["psi_pm_Wb"]
psi_phys = ema_asm.K_W * n_ph * 2.0 * b_m * R_gap * (L / 1000.0) / p_
pruefe(abs(psi_phys / psi_haus - kn) / kn < 0.02,
       "psi_phys / psi_haus == k_norm (2 % Rundung durch die Rundung in "
       "compute_performance)")

# Die eigentliche Rechtfertigung: das Moment ist unter der Bruecke INVARIANT.
mg = ema_asm.magnetisierungsstrom(g)
t_haus = 1.5 * p_ * psi_haus * mg["i_mag_A"]
t_phys = 1.5 * p_ * psi_phys * mg["i_mag_phys_A"]
pruefe(abs(t_haus - t_phys) / max(t_phys, 1e-9) < 0.02,
       "dasselbe Moment in beiden Skalen — die Bruecke aendert keine Physik, sie "
       "sorgt nur dafuer, dass i_mag und i_q dieselbe Einheit haben")

# Der Magnetisierungsstrom kommt aus derselben Funktion, an der das FDM-Statorfeld
# geeicht ist -- also muss sie ihn auch wieder herausgeben.
b_zurueck = ema_analysis._analytical_Barm(g, mg["i_mag_phys_A"])
pruefe(abs(b_zurueck - b_m) / b_m < 1e-6,
       "_analytical_Barm(i_mag) gibt das Zielfeld zurueck — der "
       "Magnetisierungsstrom ist die Umkehrung genau dieser Funktion, keine "
       "zweite eigene Formel")


# ── 4. Kaefig und Betriebspunkt ───────────────────────────────────────────────

print("\n4. Kaefiglaeufer: Geometrie, Stroeme, Schlupf")

kf = ema_asm.kaefig(g, L)
pruefe(kf["n_stab"] != int(g["slots"]),
       "die Laeufernutzahl ist nie gleich der Statornutzahl (synchrone "
       "Oberwellenmomente)")
pruefe(abs(kf["n_stab"] - int(g["slots"])) not in (0, p_, 2 * p_, 3 * p_),
       "und liegt nicht um 0, p, 2p oder 3p daneben")
pruefe(kf["n_stab"] % (2 * p_) != 0, "und ist kein Vielfaches der Polzahl")
pruefe(ema_asm.stabzahl({**g, "rotorBars": 34}) == 34,
       "eine ausdrueckliche Vorgabe (rotorBars) sticht die Auswahlregel")

# 0,02 mm Luft: Tiefe und Breite werden einzeln auf zwei Stellen gerundet.
pruefe(kf["nuttiefe_mm"] <= ema_asm.KAEFIG_TIEFE_ZU_BREITE * kf["stabbreite_mm"] + 0.02,
       "die Nut bleibt unter dem Tiefe/Breite-Deckel — darueber bestimmt die "
       "Stromverdraengung den Widerstand, und die ist hier NICHT gerechnet")
pruefe(kf["nuttiefe_mm"] < kf["nutraum_mm"],
       "sie frisst also nicht den ganzen Ringraum zwischen Steg und Joch")

bp = ema_asm.betriebspunkt(g, L, 3000.0, 100.0)
pruefe(abs(bp["I_s_A"] - math.hypot(bp["i_mag_A"], bp["i_q_A"])) < 0.2,
       "I_s = hypot(i_mag, i_q) — die ASM traegt den Magnetisierungsstrom DAUERND mit")
pruefe(0.0 < bp["schlupf"] < 0.1,
       f"der Schlupf liegt im Nennbereich ({bp['schlupf_pct']:.2f} %)")
pruefe(bp["n_laeufer_1pmin"] < bp["n_syn_1pmin"],
       "der Laeufer laeuft langsamer als das Drehfeld — sonst gaebe es keinen Strom")
pruefe(bp["P_kaefig_W"] > 0.0, "der Kaefigverlust ist groesser als null")

# Die Fliehkraft muss quadratisch mit der Drehzahl gehen -- sonst stimmt die
# Balkenformel im Steg nicht.
s1 = ema_asm.steg_check(g, L, {"density": 7650, "yield_mpa": 340}, 6000)
s2 = ema_asm.steg_check(g, L, {"density": 7650, "yield_mpa": 340}, 12000)
pruefe(abs(s2["sigma_steg_MPa"] / max(s1["sigma_steg_MPa"], 1e-9) - 4.0) < 0.05,
       "die Stegspannung waechst mit dem Quadrat der Drehzahl (Faktor 4 bei "
       "doppelter Drehzahl)")

# Verluste: das Statorkupfer muss den Magnetisierungsstrom mittragen.
mat = ema_pipeline.LAMINATES["m270_35a"]
hp = ema_pipeline.HAIRPIN_MATS["cu_etp"]
verl = ema_asm.verluste(g, L, 3000.0, 100.0, bp, mat, mat, hp, "water")
pruefe(verl["P_Mag_eddy"] == 0.0, "kein Magnet, also kein Magnetwirbelstromverlust")
pruefe(verl["P_Cu_mag_anteil"] > 0.0,
       "das Statorkupfer traegt einen Aufschlag fuer den Magnetisierungsstrom "
       "— (I_s/i_q)^2 auf den momentbildenden Anteil")
pruefe(abs(verl["P_total"] - (verl["P_Cu"] + verl["P_Fe_stator"] + verl["P_Fe_rotor"]
                              + verl["P_Kaefig"] + verl["P_Bearing"])) < 0.5,
       "die Verlustsumme geht auf und enthaelt den Kaefig")

t_geo = ema_thermal.rated_torque(g, L, "water")
t_asm = ema_asm.dauermoment(g, L, "water", bp)
pruefe(0.0 < t_asm < t_geo,
       "das ASM-Dauermoment liegt UNTER dem rein geometrischen — der "
       "Magnetisierungsstrom nimmt thermischen Platz weg")

mk = ema_asm.massen_und_kosten(_basis("asm"))
mk_pm = ema_screen.massen_und_kosten(_basis("pmsm"))
pruefe(mk["magnet_kg"] == 0.0 and mk["kosten"]["magnet_EUR"] == 0.0,
       "keine Magnetmasse, keine Magnetkosten")
pruefe(mk["kaefig_kg"] > 0.0, "dafuer ein Kaefig mit eigener Masse")
pruefe(mk["kosten"]["gesamt_EUR"] < mk_pm["kosten"]["gesamt_EUR"],
       "und in Summe billiger als dieselbe Geometrie mit Magneten")


# ── 5. Die 14. Achse im Paarvergleich ─────────────────────────────────────────

print("\n5. Paarvergleich — die Achse „Maschinenart“")

pruefe("maschinenart" in PV.ACHSEN and list(PV.ACHSEN)[0] == "maschinenart",
       "die Achse steht ganz vorn — sie entscheidet ueber die Bedeutung fast "
       "aller uebrigen")

erg = PV.vergleiche(_basis("pmsm"), achsen=["maschinenart"],
                    n_max=12000, rpm=3000, last_nm=100)
a = erg["achsen"]["maschinenart"]
namen = {o["wert"]: o for o in a["optionen"]}
pruefe(set(namen) == set(MA.ARTEN), "alle vier Arten stehen als Option da")
pruefe(namen["pmsm"]["ok"] and namen["asm"]["ok"],
       "PSM und ASM sind analytisch baubar")
pruefe(namen["synrm"]["ok"] and namen["eesm"]["ok"],
       "SynRM und EESM sind jetzt ebenfalls analytisch baubar — die Achse "
       "vergleicht alle vier Bauarten am selben Betriebspunkt")
# Der Ausbaustand zeigt sich weiterhin: eine Art ohne getragene Stufe kommt als
# Zeile MIT Begruendung, nicht als Ausnahme. Geprueft an einer erfundenen Art.
import dataclasses as _dc
MA.ARTEN["_probe"] = _dc.replace(MA.ARTEN["synrm"], code="_probe",
                                 label="Probe", stufen=())
try:
    e2 = PV.vergleiche(_basis("pmsm"), achsen=["maschinenart"],
                       n_max=12000, rpm=3000, last_nm=100)
    n2 = {o["wert"]: o for o in e2["achsen"]["maschinenart"]["optionen"]}
    pruefe(not n2["_probe"]["ok"] and "analytisch" in n2["_probe"]["grund"],
           "eine Art ohne getragene Stufe erscheint als Zeile MIT Begruendung, "
           "statt den Vergleich abzureissen — so zeigt die Achse ihren eigenen "
           "Ausbaustand")
finally:
    MA.ARTEN.pop("_probe", None)

for m, (_l, _e, _r, zaehlt) in PV.METRIKEN.items():
    if zaehlt:
        pruefe(m in namen["asm"], f"die ASM-Zeile liefert die gezaehlte Kennzahl {m}")

pruefe("T_rel_pct" not in namen["asm"],
       "T_rel_pct fehlt bei der ASM ganz — der Anteil ist gegen psi_pm definiert "
       "und ohne Magnetfluss nicht gebildet (eine 0 laese sich als Messwert lesen)")
pruefe(namen["asm"].get("magnet_kg") == 0.0,
       "magnet_kg dagegen steht als 0.0 da — das ist die Aussage, nicht ihr Fehlen")
pruefe(namen["asm"]["xi_LqLd"] == 1.0,
       "der Kaefiglaeufer ist magnetisch glatt: keine Salienz")
pruefe(namen["asm"]["I_s_A"] > namen["asm"]["i_q_A"] if "i_q_A" in namen["asm"]
       else namen["asm"]["mag_anteil"] > 0.0,
       "der Magnetisierungsanteil an I_s ist ausgewiesen")

paar = a["paare"][0]
pruefe("T_rel_pct" not in paar["deltas"] and "magnet_kg" in paar["deltas"],
       "im Paar PSM/ASM wird T_rel_pct uebersprungen, magnet_kg verglichen")
pruefe("EINGESTELLT" in a["hinweis"] and "Umrichter-Limit" in a["hinweis"],
       "die Achse sagt ausdruecklich, dass das ASM-Feld eingestellt und das "
       "PSM-Feld festgelegt ist — und woran man sieht, ob der Strom dafuer reicht")

# Basis ohne Magnete: die magnetabhaengigen Achsen muessen benannt entfallen.
erg2 = PV.vergleiche(_basis("asm"), achsen=["anordnung", "magnetwerkstoff", "hairpins"],
                     n_max=12000, rpm=3000, last_nm=100)
pruefe(erg2["achsen"]["anordnung"]["geprueft"] == 0
       and "keine Permanentmagnete" in erg2["achsen"]["anordnung"]["hinweis"],
       "die Achse „Magnetanordnung“ entfaellt an einer ASM — benannt, nicht "
       "stillschweigend mit lauter gleichen Zahlen")
pruefe(erg2["achsen"]["hairpins"]["brauchbar"] > 0,
       "die Wicklungsachse laeuft dagegen auch an der ASM")

# ── Die Auswahlliste im Browser sagt den WIRKLICHEN Ausbaustand ──────────────

print("\nDie Auswahlliste im Browser (server./param_schema)")

import server as _srv
_opt = {o["value"]: o["label"] for o in _srv._art_optionen()}
pruefe(set(_opt) == set(MA.ARTEN), "alle vier Arten stehen zur Wahl")
pruefe("noch nicht getragen" not in _opt["asm"],
       f"die ASM steht NICHT mehr als 'noch nicht getragen' da")
pruefe("analytisch, feld" in _opt["asm"],
       "sondern mit den Stufen, die sie wirklich traegt")
pruefe("feld2d" in _opt["asm"],
       "und mit dem Werkzeug, ueber das ihr Feldlauf geht — wer sie waehlt und "
       "auf Rechnen drueckt, wird sonst vom Tor abgewiesen, ohne zu wissen wohin")
pruefe(_opt["pmsm"] == MA.ARTEN["pmsm"].label,
       "die PSM traegt alle Stufen und bekommt darum keinen Zusatz")
for _c in ("synrm", "eesm"):
    pruefe("getragen: analytisch" in _opt[_c] and "feld" not in _opt[_c],
           f"'{_c}' steht mit genau seiner einen Stufe da")

# Der Zusatz muss der Tabelle FOLGEN, nicht sie beschreiben: eine Art ohne
# Stufen sagt das, unabhaengig von der Anzahl der Stufen ueberhaupt.
import dataclasses as _dc2
MA.ARTEN["_leer"] = _dc2.replace(MA.ARTEN["synrm"], code="_leer", label="Leer",
                                 stufen=())
try:
    pruefe("noch nicht getragen" in
           {o["value"]: o["label"] for o in _srv._art_optionen()}["_leer"],
           "eine Art ohne jede Stufe sagt 'noch nicht getragen'")
finally:
    MA.ARTEN.pop("_leer", None)


print(f"\n{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
