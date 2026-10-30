"""Preisvariante des Paarvergleichs: Werkstoffpreise und die grosse Tabelle -- ohne Server."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ema_screen as S
import ema_paarvergleich as PV
import ema_preistabelle as PT

ok = fehl = 0


def pruefe(bedingung, text):
    global ok, fehl
    if bedingung:
        ok += 1
        print(f"  ✓ {text}")
    else:
        fehl += 1
        print(f"  ✗ {text}")


import cae_cli
BASIS = cae_cli.frischer_payload()

print("— Werkstoffpreise —")
k = {m: S.massen_und_kosten(dict(BASIS, magnet=m))["kosten"] for m in S.PREIS_FAKTOR["magnet"]}
pruefe(k["ferrite"]["magnet_EUR"] < k["ndfeb_n35"]["magnet_EUR"] < k["ndfeb_n42"]["magnet_EUR"]
       < k["ndfeb_n50"]["magnet_EUR"], "Magnetkosten: Ferrit < N35 < N42 < N50")
pruefe(k["ndfeb_n42"]["kupfer_EUR"] == k["ferrite"]["kupfer_EUR"], "der Magnet bewegt das Kupfer nicht")
ohne = {x: v for x, v in BASIS.items() if x not in ("magnet", "rotor_lam", "stator_lam", "hairpin_mat")}
pruefe(S.preis(ohne, "magnet") == S.PREISE_EUR_KG["magnet"]
       and S.preis(ohne, "kupfer") == S.PREISE_EUR_KG["kupfer"]
       and S.preis(ohne, "stahl_rotor") == S.PREISE_EUR_KG["stahl"],
       "ohne Werkstoffangabe gilt der Grundpreis (alte Rechnungen bleiben dieselben)")
pruefe(S.preis(dict(BASIS, magnet="gibtsnicht"), "magnet") == S.PREISE_EUR_KG["magnet"],
       "unbekannter Werkstoff: Grundpreis, kein Fehler")
a = S.massen_und_kosten(dict(BASIS, rotor_lam="m250_35a"))["kosten"]["stahl_EUR"]
b = S.massen_und_kosten(dict(BASIS, rotor_lam="m800_65a"))["kosten"]["stahl_EUR"]
pruefe(a > b, f"Premiumblech teurer als Grobblech ({a:.0f} > {b:.0f} EUR)")

print("— Tabelle —")
erg = PV.vergleiche(BASIS, achsen=list(PT.PREIS_ACHSEN))
t = PT.tabelle(erg, BASIS)
pruefe(t["ok"] and len(t["zeilen"]) > 10, f"Tabelle hat Zeilen ({len(t['zeilen'])})")
kosten = [z["kosten_EUR"] for z in t["zeilen"]]
pruefe(kosten == sorted(kosten), "nach Kosten aufsteigend sortiert")
arten = {z["option"].split(" ")[0] for z in t["zeilen"] if z["achse"] == "maschinenart"}
pruefe({"PSM", "ASM", "EESM"} <= arten, f"mehrere Maschinenarten stehen in EINER Tabelle ({sorted(arten)})")
mw = {z["option"]: z["kosten_EUR"] for z in t["zeilen"] if z["achse"] == "magnetwerkstoff"}
fer = next(v for n, v in mw.items() if n.startswith("Ferrit"))
n50 = next(v for n, v in mw.items() if "N50" in n)
pruefe(fer < n50, f"Ferrit billiger als N50 ({fer:.0f} < {n50:.0f} EUR)")
pruefe(all(z["urteil"] in ("teurer", "billiger", "gleich") for z in t["zeilen"]), "jede Zeile teurer/billiger/gleich")
pruefe(all(abs(z["magnet_EUR"] + z["leiter_EUR"] + z["eisen_EUR"] - z["kosten_EUR"]) <= 2
           for z in t["zeilen"]), "Magnet + Leiter + Eisen = Summe (Rundung)")
pruefe("Kaefig" in " ".join(t["ohne_preiswirkung"]) or t["ohne_preiswirkung"],
       "Achsen ohne Preiswirkung werden genannt statt als Nullzeilen aufgefuehrt")
text = PT.als_text(t)
pruefe("Platzhalter" in text and "teurer" in text, "Text nennt die Platzhalterpreise")
gsm = [z for z in t["zeilen"] if z["option"].startswith("GSM")]
pruefe(not gsm or gsm[0]["gilt"] is None, "GSM ohne Eisenpruefung: 'gilt' ist unbekannt, nicht ja")

print(f"\n{ok} bestanden, {fehl} fehlgeschlagen")
sys.exit(1 if fehl else 0)
