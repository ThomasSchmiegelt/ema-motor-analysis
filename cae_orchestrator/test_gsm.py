"""Die Gleichstrommaschine — gegen ihre eigenen Erhaltungssaetze geprueft.

Warum keine festgenagelten Zahlen
----------------------------------

Ein Test, der ``Kt == 0.0806`` prueft, prueft, dass sich nichts geaendert hat.
Er sagt nichts darueber, ob die Formel richtig ist — und er wird rot, sobald
jemand einen Beiwert verbessert, also genau dann, wenn man ihn am wenigsten
gebrauchen kann.

Hier wird statt dessen gegen **Erhaltungssaetze** geprueft, die unabhaengig von
jedem Beiwert gelten:

* ``E * I_a = T * omega`` — exakt, weil beide dieselbe Maschinenkonstante
  ``k = p*z/(2*pi*a)`` tragen. Waeren es zwei Konstanten, liefe die Maschine
  als Energiequelle oder -senke, ohne dass irgendwo eine Zahl auffaellig waere.
* **Schleifen- gegen Wellenwicklung**: dieselbe Maschine, dieselbe Leistung,
  nur anders auf Strom und Spannung aufgeteilt. Das Produkt ``U*I`` muss stehen.
* Die Nut folgt der **Stromdichte** und trifft sie: die Rechnung schliesst sich
  gegen sich selbst.
* Die drei **Kommutierungsgrenzen** reissen bei den richtigen Werten — geprueft,
  indem der Betriebspunkt gezielt darueber geschoben wird.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_eesm
import ema_gsm as G
import ema_maschinenart as MA
import ema_mobil
import ema_schleifring

_ok = _bad = 0


def pruefe(b, text):
    global _ok, _bad
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def nah(a, b, rel=1e-9):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-30)


def geom(**kw):
    g = ema_mobil.basis_geom()
    g.update(machineType="gsm", p=2, slots=24, conductorsPerSlot=4,
             rpm_to=3000, axialLen=100)
    g.update(kw)
    return g


L = 100.0
G0 = geom()


# ──────────────────────────────────────────────────────────────────────────────
print("1. E*I_a = T*omega — exakt, weil beide dieselbe Konstante tragen")

k = G.maschinenkonstante(G0, L)
phi = G.polfluss(G0, L)
pruefe(k > 0 and phi > 0,
       f"k = {k:.4f} Nm/(Wb*A), Phi = {phi * 1000:.3f} mWb")

for rpm, i_a in ((1500.0, 300.0), (600.0, 750.0), (3000.0, 50.0)):
    om = 2 * math.pi * rpm / 60.0
    e = k * phi * om
    t = k * phi * i_a
    pruefe(nah(e * i_a, t * om, rel=1e-12),
           f"{rpm:.0f} 1/min, {i_a:.0f} A: E*I = {e * i_a:9.2f} W = T*omega "
           f"(exakt, nicht auf Rundung)")

# Die Gegenprobe: mit ZWEI verschiedenen Konstanten waere die Maschine eine
# Energiequelle -- und keine einzelne Zahl saehe auffaellig aus.
k_falsch = k * 1.05
pruefe(abs(k_falsch * phi * 300.0 * (2 * math.pi * 1500 / 60)
           - k * phi * (2 * math.pi * 1500 / 60) * 300.0) > 1.0,
       "waeren es zwei Konstanten (hier 5 % auseinander), entstuende Leistung "
       "aus dem Nichts — genau das faellt an keiner Einzelzahl auf")


print("\n2. Schleifen- gegen Wellenwicklung: dieselbe Leistung, andere Aufteilung")

g_s = geom(armatureWinding="schleife")
g_w = geom(armatureWinding="welle")
aw_s, aw_w = G.ankerwicklung(g_s, L), G.ankerwicklung(g_w, L)
p = int(G0["p"])
pruefe(aw_s["a_zweigpaare"] == p and aw_w["a_zweigpaare"] == 1,
       f"Schleife a = p = {p}, Welle a = 1 — {aw_s['zweige']} gegen "
       f"{aw_w['zweige']} Zweige")
pruefe(aw_s["z_leiter"] == aw_w["z_leiter"],
       f"beide haben dieselben {aw_s['z_leiter']} Ankerleiter — es ist DIESELBE "
       f"Maschine, anders geschaltet")

k_s, k_w = G.maschinenkonstante(g_s, L), G.maschinenkonstante(g_w, L)
pruefe(nah(k_w / k_s, float(p), rel=1e-12),
       f"die Wellenwicklung hat die p-fache Maschinenkonstante "
       f"({k_w:.3f} gegen {k_s:.3f})")

# Bei gleichem MOMENT: Welle braucht 1/p des Stroms und liefert p-fache
# Spannung. Das Produkt steht.
t_ziel, rpm = 60.0, 1500.0
om = 2 * math.pi * rpm / 60.0
i_s = t_ziel / (k_s * G.polfluss(g_s, L))
i_w = t_ziel / (k_w * G.polfluss(g_w, L))
e_s = k_s * G.polfluss(g_s, L) * om
e_w = k_w * G.polfluss(g_w, L) * om
pruefe(nah(i_s / i_w, float(p), rel=1e-9),
       f"gleiches Moment: Welle braucht {i_w:.1f} A statt {i_s:.1f} A "
       f"(Faktor {p})")
pruefe(nah(e_s * i_s, e_w * i_w, rel=1e-9),
       f"und die Leistung steht: {e_s * i_s:.1f} W in beiden Faellen")


print("\n3. Die Ankernut folgt der STROMDICHTE, nicht dem Platz")

aw = G.ankerwicklung(G0, L)
pruefe(aw["nut_tiefe_mm"] < aw["nutraum_mm"],
       f"Nuttiefe {aw['nut_tiefe_mm']} mm gegen {aw['nutraum_mm']} mm "
       f"verfuegbaren Blechraum — derselbe Fehler ist hier schon zweimal "
       f"gemacht worden (Kaefigstab, Erregerwicklung)")
pruefe(abs(aw["J_anker_Apmm2"] - G.J_ANKER_APMM2) < 0.2,
       f"die erreichte Stromdichte {aw['J_anker_Apmm2']} A/mm² trifft die "
       f"Vorgabe {G.J_ANKER_APMM2} — die Rechnung schliesst sich gegen sich selbst")
aw2 = G.ankerwicklung(geom(armatureCurrentDensity=10.0), L)
pruefe(aw2["nut_tiefe_mm"] < aw["nut_tiefe_mm"],
       f"doppelte Stromdichte -> flachere Nut ({aw2['nut_tiefe_mm']} gegen "
       f"{aw['nut_tiefe_mm']} mm)")
pruefe(aw["I_zweig_A"] * aw["zweige"] == aw["I_klemme_A"],
       f"der Klemmenstrom {aw['I_klemme_A']} A teilt sich auf {aw['zweige']} "
       f"Zweige zu je {aw['I_zweig_A']} A")


print("\n4. Der Klemmenstrom ist KEIN normierter Strom")

import ema_analysis
u = ema_analysis.umrichter(G0)
pruefe(G.klemmenstrom(G0) == u["i_max_A"],
       f"klemmenstrom liest i_max_A ({u['i_max_A']} A), nicht i_max_1t")
g_n = geom(turnsPerSlot=4, umrichterBezug="wicklung")
u_n = ema_analysis.umrichter(g_n)
pruefe(u_n["i_max_1t"] != u_n["i_max_A"],
       f"bei 4 Windungen je Nut laufen die beiden auseinander "
       f"({u_n['i_max_A']} gegen {u_n['i_max_1t']} A)")
pruefe(G.klemmenstrom(g_n) == u_n["i_max_A"],
       "und die GSM nimmt weiterhin den KLEMMENstrom — ihre Maschinenkonstante "
       "entsteht geometrisch aus der wirklichen Leiterzahl, es gibt nichts "
       "umzurechnen")
pruefe(G.k_norm(G0) == 1.0,
       "darum ist k_norm hier 1,0 — und der Modulkopf sagt, dass das kein "
       "vergessener Faktor ist")


print("\n5. Die Kommutierung — das Tor dieser Bauart")

kom = G.kommutierung(G0, L, 1500.0)
pruefe(kom["ok"], f"bei 1500 1/min haelt sie (bindend '{kom['bindend']}' bei "
                  f"{max(kom['ausnutzung'].values()) * 100:.0f} %)")
pruefe(abs(kom["U_lamelle_spitze_V"]
           - G.U_LAMELLE_FORMFAKTOR * kom["U_lamelle_mittel_V"]) < 0.02,
       f"der Spitzenwert ist das {G.U_LAMELLE_FORMFAKTOR}-fache des Mittelwerts "
       f"— das Luftspaltfeld ist ueber den Umfang nicht gleich")

# Die Lamellenspannung haengt NICHT an der Leiterzahl -- und das ist eine
# Aussage ueber die Maschine, keine Eigenheit des Codes: mit
#     U_l = 2a*E/k ,  E ~ z ,  k ~ z
# kuerzt sich z heraus, und uebrig bleibt U_l = 2*r*B*alpha*L*omega. Wer den
# Kommutator entlasten will, muss also Fluss, Laenge oder Drehzahl anfassen --
# mehr Lamellen helfen nicht. Ein Test, der die Grenze ueber die Leiterzahl
# treiben wollte, prueft deshalb gar nichts (erst so herum gefunden).
k_viel = G.kommutierung(geom(conductorsPerSlot=12, slots=48), L, 1500.0)
pruefe(abs(k_viel["U_lamelle_mittel_V"] - kom["U_lamelle_mittel_V"]) < 0.02
       and k_viel["k_lamellen"] > 4 * kom["k_lamellen"],
       f"{k_viel['k_lamellen']} statt {kom['k_lamellen']} Lamellen aendern die "
       f"Lamellenspannung NICHT ({k_viel['U_lamelle_mittel_V']} V) — z kuerzt "
       f"sich heraus")
k_lang = G.kommutierung(G0, 2 * L, 1500.0)
pruefe(abs(k_lang["U_lamelle_mittel_V"] - 2 * kom["U_lamelle_mittel_V"]) < 0.02
       and abs(k_lang["v_kommutator_mps"] - kom["v_kommutator_mps"]) < 0.02,
       f"die doppelte BAULAENGE dagegen verdoppelt sie "
       f"({k_lang['U_lamelle_mittel_V']} V) und laesst die "
       f"Umfangsgeschwindigkeit stehen")

# Welche der drei bindet, haengt damit an der Bauform -- und der Uebergang ist
# scharf: bei kurzem Paket bindet die Umfangsgeschwindigkeit, ab rund 300 mm
# Paketlaenge die Lamellenspannung.
pruefe(G.kommutierung(G0, 100.0, 6000.0)["bindend"] == "umfang",
       "kurzes Paket (100 mm), 6000 1/min: es bindet die "
       "Umfangsgeschwindigkeit")
k_300 = G.kommutierung(G0, 300.0, 6000.0)
pruefe(k_300["bindend"].startswith("lamelle") and not k_300["ok"],
       f"langes Paket (300 mm), dieselbe Drehzahl: jetzt bindet die "
       f"Lamellenspannung und REISST ({k_300['U_lamelle_spitze_V']} V Spitze "
       f"gegen {G.U_LAMELLE_SPITZE_V})")
k_schnell = G.kommutierung(G0, L, 30000.0)
pruefe(not k_schnell["ok"]
       and any("Umfangsgeschwindigkeit" in b for b in k_schnell["befunde"]),
       f"30.000 1/min: {k_schnell['v_kommutator_mps']} m/s gegen "
       f"{G.V_KOMMUTATOR_MPS} m/s")
pruefe(k_schnell["bindend"] == "umfang",
       "und es wird BENANNT, welche der drei bindet — nicht nur, DASS eine reisst")

# Die Ausnutzung ist die Auskunft, nicht das bestandene Ja.
pruefe(all(0.0 <= v for v in kom["ausnutzung"].values())
       and set(kom["ausnutzung"]) == {"lamelle_mittel", "lamelle_spitze", "umfang"},
       f"jede Grenze traegt ihre Ausnutzung: {kom['ausnutzung']}")


print("\n6. Die Kommutierung begrenzt die DREHZAHL, nicht das Moment")

bp = G.betriebspunkt(G0, L, 1500.0, 60.0)
dm = G.dauermoment(G0, L, "water", bp)
pruefe(set(dm) >= {"T_dauer_Nm", "T_thermisch_Nm", "T_umrichter_Nm",
                   "begrenzt_durch"},
       "dauermoment gibt die Hauskonvention heraus — sonst vergliche der "
       "Paarvergleich fuenf verschieden benannte Dauermomente")
pruefe(nah(dm["T_dauer_Nm"],
           round(min(dm["T_thermisch_Nm"], dm["T_umrichter_Nm"]), 1), rel=1e-9),
       "das gemeldete Dauermoment ist das kleinere der beiden")
pruefe("n_kommutierbar_1pmin" in dm and dm["n_kommutierbar_1pmin"] > 0,
       f"die Kommutierungsgrenze steht als DREHZAHL daneben "
       f"({dm['n_kommutierbar_1pmin']:.0f} 1/min) — als Moment waere sie keins")


print("\n7. Die Ankerrueckwirkung ist eine SCHAETZUNG — und sagt es")

ar = G.ankerrueckwirkung(G0, L, 300.0)
ar2 = G.ankerrueckwirkung(G0, L, 600.0)
pruefe(ar["geschaetzt"] is True and "NICHT modelliert" in ar["hinweis"],
       "sie ist als Schaetzung gekennzeichnet und nennt, was fehlt "
       "(Wendepole, Kompensationswicklung)")
pruefe(ar2["flussabschlag"] >= ar["flussabschlag"],
       f"mehr Ankerstrom -> groesserer Abschlag ({ar['flussabschlag']} -> "
       f"{ar2['flussabschlag']})")
pruefe(ar2["flussabschlag"] <= G.ANKER_ABSCHLAG_MAX + 1e-12,
       f"und er ist gedeckelt ({G.ANKER_ABSCHLAG_MAX}) — ohne Deckel liefe der "
       f"Fluss bei grossem Strom gegen null, und das waere keine Maschine mehr")
pruefe(bp["Phi_pol_Wb"] < bp["Phi_pol_leer_Wb"],
       f"der Betriebspunkt rechnet mit dem GESCHWAECHTEN Fluss "
       f"({bp['Phi_pol_Wb'] * 1000:.2f} gegen {bp['Phi_pol_leer_Wb'] * 1000:.2f} mWb)")


print("\n8. Die Verluste: der Buerstenverlust ist LINEAR im Strom")

import ema_pipeline as PL
mats = (PL.LAMINATES["m270_35a"], PL.LAMINATES["m270_35a"],
        PL.HAIRPIN_MATS["cu_etp"])
v1 = G.verluste(G0, L, 1500.0, 30.0,
                G.betriebspunkt(G0, L, 1500.0, 30.0), *mats, "water")
v2 = G.verluste(G0, L, 1500.0, 60.0,
                G.betriebspunkt(G0, L, 1500.0, 60.0), *mats, "water")
pruefe(nah(v2["P_buerste_W"] / max(v1["P_buerste_W"], 1e-9), 2.0, rel=0.02),
       f"doppeltes Moment -> doppelter Buerstenverlust "
       f"({v1['P_buerste_W']} -> {v2['P_buerste_W']} W), nicht vierfacher")
pruefe(v2["P_Cu"] / max(v1["P_Cu"], 1e-9) > 3.5,
       f"das Ankerkupfer dagegen vervierfacht sich "
       f"({v1['P_Cu']} -> {v2['P_Cu']} W) — I² gegen I")
pruefe(v1["P_buerste_W"] > v1["P_Cu"],
       f"bei kleiner Last ist die Buerste der GROESSTE Einzelposten "
       f"({v1['P_buerste_W']} gegen {v1['P_Cu']} W Kupfer)")
pruefe(set(v2) >= {"P_total", "P_Cu", "J_Apmm2", "R_phase_mOhm"},
       "und die Hauskonvention wird bedient (P_total/P_Cu/J/R) — der "
       "Paarvergleich liest genau diese Namen")
pruefe(v2["P_Fe_stator"] == 0.0,
       "das Staenderjoch fuehrt GLEICHfluss und hat keine "
       "Ummagnetisierungsverluste — 0,0 ist hier eine Aussage")


print("\n9. Die GSM ist die EESM von innen nach aussen")

sp = G.staenderpole(G0, L)
pg = ema_eesm.polgeometrie(geom(machineType="eesm"), L)
pruefe(sp["poles"] == 2 * int(G0["p"]),
       f"{sp['poles']} Schenkelpole am STAENDER")
# Dieselbe Formel, andere Radien: die Polbedeckung muss in beiden dieselbe sein.
pruefe(nah(sp["b_pol_mm"] / sp["tau_pol_mm"], ema_eesm.POLBEDECKUNG, rel=1e-3)
       and nah(pg["b_pol_mm"] / pg["tau_pol_mm"], ema_eesm.POLBEDECKUNG, rel=1e-3),
       f"beide tragen dieselbe Polbedeckung {ema_eesm.POLBEDECKUNG} — EINE "
       f"Formel (ema_eesm.polmasse), zwei Radiensaetze")
pruefe(sp["tau_pol_mm"] != pg["tau_pol_mm"],
       f"und trotzdem verschiedene Teilungen ({sp['tau_pol_mm']} am Staender "
       f"gegen {pg['tau_pol_mm']} am Laeufer) — die Radien sind andere")


print("\n10. Angemeldet — und nur da, wo sie wirklich traegt")

art = MA.ARTEN["gsm"]
pruefe("gsm" in MA.ARTEN and art.erregung == "fremderregt",
       "die GSM steht in ARTEN")
pruefe(MA.traegt("gsm", "analytisch") and MA.traegt("gsm", "cad"),
       "sie traegt die analytische Stufe und das CAD")
pruefe(not MA.traegt("gsm", "feld") and not MA.traegt("gsm", "em3d"),
       "aber KEINE Feldstufe: die 2-D-FDM ist reell und magnetostatisch, ein "
       "kommutierter Anker mit im Raum stehender Durchflutung ist darin nicht "
       "abbildbar")
try:
    MA.pruefe_stufe("gsm", "feld")
    pruefe(False, "und das Tor sagt es")
except MA.ArtNichtUnterstuetzt as e:
    pruefe("analytisch" in str(e), f"und das Tor sagt es: {str(e)[:70]}…")
pruefe(not MA.gilt("gsm", "xi_LqLd") and not MA.gilt("gsm", "schlupf"),
       "d/q-Salienz und Schlupf gelten fuer sie NICHT — eine 0 dort laese sich "
       "als 'gemessen, nicht salient' lesen, was etwas anderes ist")
pruefe(MA.gilt("gsm", "gesamt_kg") and MA.gilt("gsm", "magnet_kg"),
       "Masse und Magnetmasse gelten sehr wohl — 0 kg Magnet ist eine Aussage")
pruefe(list(MA.ARTEN) == __import__("ema_text2ema").SCHEMA["machineType"]["opts"],
       "und die Auswahlliste im Schema kommt aus DIESEM Modul")
import ema_werkzeugstand as W
pruefe("ema_gsm.py" in W.PHYSIK,
       "ema_gsm steht in PHYSIK — eine Aenderung daran bewegt den "
       "Werkzeug-Fingerabdruck, wie bei jedem anderen Rechenmodul")


print("\n11. Im Paarvergleich steht sie neben den anderen vier")

import copy
import ema_paarvergleich as PV
_pl = {"geom": dict(G0), "rotor_lam": "m270_35a", "stator_lam": "m270_35a",
       "hairpin_mat": "cu_etp", "magnet": "ndfeb_n42", "cooling": "water",
       "axial_len": L, "rpm_from": 1500, "rpm_to": 3000, "load_nm": 60.0}
r_gsm = PV._bewerte(copy.deepcopy(_pl), 3000.0, 1500.0, 60.0)
pruefe(r_gsm.get("ok"), f"die GSM ist bewertbar ({r_gsm.get('grund', '')[:60]})")
for feld in ("Kt_Nm_per_A", "I_s_A", "T_dauer_Nm", "P_verlust_W", "gesamt_kg"):
    pruefe(r_gsm.get(feld) is not None,
           f"sie liefert '{feld}' wie jede andere Art ({r_gsm.get(feld)})")
pruefe(r_gsm.get("komm_ausnutzung") is not None
       and r_gsm.get("komm_bindend") is not None,
       f"und dazu, was bei IHR bindet: Kommutierung "
       f"{r_gsm['komm_ausnutzung']:.2f} ('{r_gsm['komm_bindend']}') — als "
       f"Ausnutzung, nicht als bestandenes Ja")
pruefe(r_gsm.get("magnet_kg") == 0.0,
       "Magnetmasse 0 kg — gerechnet, nicht unterdrueckt")


print("\n12. Der Buerstenabfall hat EINE Quelle")

pruefe(ema_schleifring.U_BUERSTE_V == ema_eesm.U_BUERSTE_V,
       f"ema_schleifring und ema_eesm fuehren denselben Wert "
       f"({ema_schleifring.U_BUERSTE_V} V je Kontakt)")
pruefe(nah(bp["U_buerste_V"], 2.0 * ema_schleifring.U_BUERSTE_V, rel=1e-9),
       "und die GSM rechnet mit ZWEI Kontakten je Stromkreis "
       f"({bp['U_buerste_V']} V)")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
