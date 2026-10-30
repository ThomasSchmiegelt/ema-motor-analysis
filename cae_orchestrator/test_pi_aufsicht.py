"""Wächter über PI, Entscheidung und Magnetschluss -- ohne Server, ohne Ollama.

Der Magnetschluss rechnet FDM-Läufe (N=300, je ~6 s); alles andere
laeuft auf synthetischen Sitzungs- und Projektdateien in einem temporaeren Ordner.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ema_pi_waechter as W
import ema_entscheidung as E

ok = fehl = 0


def pruefe(bedingung, text):
    global ok, fehl
    if bedingung:
        ok += 1
        print(f"  ✓ {text}")
    else:
        fehl += 1
        print(f"  ✗ {text}")


def sitzung(pfad, zuege):
    """zuege: Liste von (denken_zeichen, [(name, args)], [(isError, text)])"""
    with open(pfad, "w") as f:
        f.write(json.dumps({"type": "session"}) + "\n")
        for d, aufrufe, res in zuege:
            inhalt = [{"type": "thinking", "thinking": "x" * d}]
            for n, a in aufrufe:
                inhalt.append({"type": "toolCall", "name": n, "arguments": a})
            f.write(json.dumps({"type": "message", "timestamp": "2026-10-30T08:00:00Z",
                                "message": {"role": "assistant", "content": inhalt}}) + "\n")
            for err, t in res:
                f.write(json.dumps({"type": "message", "message": {
                    "role": "toolResult", "toolName": "bash", "isError": err,
                    "content": [{"type": "text", "text": t}]}}) + "\n")


print("— Wächter —")
with tempfile.TemporaryDirectory() as t:
    p = os.path.join(t, "a.jsonl")
    sitzung(p, [(300, [("bash", {"c": i})], [(False, "ok")]) for i in range(6)])
    u = W.pruefen(p)
    pruefe(u["stufe"] == "ok", "ruhige Sitzung: ok")

    sitzung(p, [(200, [("bash", {"c": 1})], [(False, "x")])] * 4)
    u = W.pruefen(p)
    pruefe(u["stufe"] == "eingreifen" and "hintereinander" in " ".join(u["befunde"]),
           "derselbe Aufruf viermal hintereinander: eingreifen, benannt")

    sitzung(p, [(20000, [], [])])
    u = W.pruefen(p)
    pruefe(u["stufe"] == "eingreifen" and u["sage_ihm"], "20 k Denkzeichen ohne Aufruf: eingreifen mit Satz an PI")

    sitzung(p, [(100, [("bash", {"c": i})], [(True, "Fehler")]) for i in range(3)])
    u = W.pruefen(p)
    pruefe(u["kennzahlen"]["fehler_in_folge"] == 3 and u["stufe"] == "eingreifen", "drei Fehler in Folge: eingreifen")

    # erfundene Zahl: im Text 4321, im Werkzeugergebnis nur 1234
    with open(p, "w") as f:
        f.write(json.dumps({"type": "message", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "name": "bash", "arguments": {"c": 1}}]}}) + "\n")
        f.write(json.dumps({"type": "message", "message": {"role": "toolResult", "toolName": "bash",
            "isError": False, "content": [{"type": "text", "text": "Moment 1.234 Nm"}]}}) + "\n")
        f.write(json.dumps({"type": "message", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Moment 1234 Nm, Drehzahl 4321, 5678, 8765, 9999 U/min"}]}}) + "\n")
    k = W.kennzahlen(p)
    pruefe("1234" not in k["ungedeckte_zahlen"], "1.234 im Ergebnis deckt 1234 im Text (Schreibweise egal)")
    pruefe(k["ungedeckt_n"] == 4, f"vier erfundene Zahlen gefunden ({k['ungedeckt_n']})")
    pruefe(W.urteil(k)["stufe"] == "warnen", "ungedeckte Zahlen warnen, greifen nicht ein")

with tempfile.TemporaryDirectory() as t:
    p2 = os.path.join(t, "b.jsonl")
    sitzung(p2, [(100, [("bash", {"command": f"cae_cli.py run analyse --frisch --set x={i}"})], [(False, "ok")]) for i in range(5)]
            + [(100, [("bash", {"command": "cae_cli.py run analyse --dry-run"})], [(False, "ok")])])
    pruefe(W.pruefen(p2)["kennzahlen"]["rechenlaeufe"] == 5, "--dry-run zaehlt nicht als Rechenlauf (5 von 6 Aufrufen)")
    pruefe(W.pruefen(p2, max_laeufe=3)["stufe"] == "eingreifen", "5 Laeufe bei Obergrenze 3: eingreifen")
    pruefe(W.pruefen(p2, max_laeufe=5)["stufe"] == "ok", "5 Laeufe bei Obergrenze 5: ok")

pruefe(W.pruefen("/gibt/es/nicht")["stufe"] == "unbekannt", "fehlende Datei: unbekannt, kein Absturz")

print("— Entscheidung —")


def projekt(t, name, sf=2.0, kw=100.0, g=1000.0, tmax=60.0, wick=100.0):
    d = os.path.join(t, name)
    os.makedirs(d)
    s = {"safety_factor_fem": sf, "structural_basis": "fem", "fem_rpm": 5000, "P_max_kW": kw,
         "mass_g": g, "T_peak_max_Nm": 300, "T_magnet_C": tmax, "T_winding_C": wick,
         "magnet": "NdFeB N50", "max_safe_rpm": 9000}
    json.dump({"summary": s}, open(os.path.join(d, "results.json"), "w"))
    json.dump({"payload": {"cycle": "off"}}, open(os.path.join(d, "meta.json"), "w"))
    return d


with tempfile.TemporaryDirectory() as t:
    a = projekt(t, "a", kw=100)
    b = projekt(t, "b", kw=140)
    c = projekt(t, "c", sf=0.5, kw=999)             # reisst, hoechste Leistung
    e = E.entscheide([a, b, c], "leistungsdichte", mit_magnetschluss=False)
    gewinner_ok = e["gewinner"] == "b"
    pruefe(gewinner_ok, f"c reisst und gewinnt trotz groesster Leistung NICHT; Sieger b ({e['gewinner']})")
    pruefe(any(z["projekt"] == "c" and z["status"] == "abgewiesen" for z in e["zeilen"]), "c abgewiesen")
    pruefe(e["klar"], "40 % Vorsprung ist klar")
    e = E.entscheide([a, projekt(t, "a2", kw=102)], mit_magnetschluss=False)
    pruefe(not e["klar"] and "Kein klarer Sieger" in e["urteil"], "2 % Vorsprung: kein klarer Sieger")
    e = E.entscheide([c], mit_magnetschluss=False)
    pruefe(e["gewinner"] is None and e["bindend"], f"kein Entwurf besteht: kein Sieger, bindendes Tor genannt ({e['bindend']})")
    leer = os.path.join(t, "leer"); os.makedirs(leer)
    e = E.entscheide([leer], mit_magnetschluss=False)
    pruefe(e["zeilen"][0]["status"] == "nicht_entscheidbar", "ungerechnet: nicht entscheidbar, nicht abgewiesen")
    try:
        E.entscheide([a], "schoen")
        pruefe(False, "unbekanntes Ziel wird abgewiesen")
    except ValueError:
        pruefe(True, "unbekanntes Ziel wird abgewiesen")

    # Saettigung: darunter Hinweis, darueber Tor (Moment/Leistung zu optimistisch)
    orig = E.ema_sicherheit.pruefen
    def _mit(wert):
        return lambda r, m: {"kriterien": [{"name": "saettigung", "ok": False, "schwere": "hinweis",
                                            "text": "JOCH", "wert": wert, "grenze": 2.0}]}
    try:
        E.ema_sicherheit.pruefen = _mit(2.2)          # 110 %
        z = E.bewerten(a, "leistungsdichte", False)
        pruefe(z["status"] == "bestanden" and z["hinweise"], "Saettigung 110 %: Hinweis, kein Tor")
        E.ema_sicherheit.pruefen = _mit(5.9)          # 295 %
        z = E.bewerten(a, "leistungsdichte", False)
        pruefe(z["status"] == "abgewiesen" and z["abweisungen"][0]["tor"] == "saettigung",
               "Saettigung 295 %: abgewiesen")
    finally:
        E.ema_sicherheit.pruefen = orig

print("— Magnetschluss —")
import cae_cli
import ema_magnetschluss as M
g = cae_cli.frischer_payload().get("geom")
werte = {}
for a in (40, 90):
    werte[a] = M.messen({**g, "magAngle": a}, N=300)["streuanteil"]
pruefe(werte[40] > werte[90], f"steiler V (40 deg) streut mehr als flacher (90 deg): {werte[40]} > {werte[90]}")
pruefe(0.0 <= werte[90] <= 1.0, "Streuanteil liegt in [0, 1]")
m = M.messen({**g, "magAngle": 90}, N=300)
pruefe(M.messen(g, N=240)["N"] >= M.N_MIN, "N unter der Mindestaufloesung wird angehoben, nicht gerechnet")
pruefe(m["stufe"] in ("ok", "auffaellig", "kurzschluss") and m["grund"], "Stufe und Grund immer gesetzt")
pruefe(M.STREU_AUFFAELLIG < M.STREU_KURZ, "Schwellen geordnet")

kaputt = {**g, "statorID": 155, "rotorOD": 153, "statorOD": 200, "p": 5, "slots": 36, "magShape": "v"}
r = M.messen(kaputt, N=300)
pruefe(r["ok"] is False and "Layout" in r["grund"], "Taschenkollision: keine Streuzahl, sondern Ablehnung mit Grund")
st = M.messen_stabil(g, N=300)
pruefe("abweichung_n" in st and st["abweichung_n"] <= M.STABIL_TOL and st["stufe"] != "unsicher",
       f"V-Anordnung ist auflösungsstabil (Abweichung {st.get('abweichung_n')})")

print(f"\n{ok} bestanden, {fehl} fehlgeschlagen")
sys.exit(1 if fehl else 0)
