"""Text → EMA: derive an IPM-motor parameter set from a free-text application
description via the local LLM (see ema_report.DEFAULT_MODEL), then validate/clamp it to a safe,
self-consistent geometry. First stage only — no RAG / no web research yet; this is
deliberately a deterministic schema fill so the result always loads into the UI.

The LLM proposes values for the fields in SCHEMA; everything is then clamped to the
allowed range / enum and the radial ordering (statorOD > statorID > rotorOD > shaftD
> shaftBoreD) is enforced, so a sloppy LLM answer can never produce broken geometry.
"""

import json
import re
import urllib.request

import ema_maschinenart
import ema_wicklung
from ema_report import OLLAMA_URL, DEFAULT_MODEL, DEFAULT_NUM_CTX

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Allowed enum codes (must match the pipeline tables + UI dropdowns)
_LAM   = ["m250_35a", "m270_35a", "m400_50a", "m800_65a", "steel_s235", "steel_42crmo4"]
_HAIR  = ["cu_etp", "cu_crZr", "cu_ag01", "al_1350"]
_MAG   = ["ndfeb_n35", "ndfeb_n42", "ndfeb_n50", "ferrite"]
_COOL  = ["natural", "forced", "water", "oil"]
_SHAPE = ["v", "vasym", "vv", "u", "delta", "pmasynrm", "spm", "halbach", "spoke", "bar"]
# Maschinenart. Die Liste kommt aus ``ema_maschinenart``, damit sie nicht als
# zweite, handgepflegte Menge daneben lebt -- welche Art welche Rechenstufe
# heute wirklich traegt, sagt allein dieses Modul.
_ART   = list(ema_maschinenart.ARTEN)
_WICKLUNG = list(ema_wicklung.ARTEN)
_ORIENT = ["transverse", "longitudinal"]
_POCKET = ["position", "diameter"]
_THREAD = ["M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"]

# field → spec.
#   kind: "num" (lo/hi/def, optional int) | "enum" (opts/def) | "bool" (def)
#   geom: True  → gehoert in ``payload["geom"]``, sonst auf die obere Ebene.
#         Frueher stand diese Zuordnung als zweite, handgepflegte Menge in
#         ``server.py:/param_schema``; sie lebt jetzt hier, damit ein neuer Schluessel
#         nicht an einer Stelle bekannt und an der anderen unbekannt sein kann.
#   adv:  True  → Feinparameter. Wird NICHT vom LLM erfragt (``_prompt``) und NICHT
#         von ``_validate`` gefuellt — Text→Auslegung bleibt damit unveraendert.
#         Fuer ``/param_schema`` (Parametertabelle, ``cae_cli --set``) zaehlt er voll:
#         genau das ist der Zweck, denn ungepruefte Schluessel sind schlimmer als
#         abgewiesene — bisher nahm ``--set`` alles an, was zufaellig schon im
#         Grundpayload stand, ohne Grenzen und ohne Typ.
SCHEMA = {
    "statorOD":   {"kind": "num", "lo": 80,  "hi": 600, "def": 280, "geom": True, "desc": "Stator-Außendurchmesser [mm]"},
    "statorID":   {"kind": "num", "lo": 50,  "hi": 500, "def": 190, "geom": True, "desc": "Stator-Innendurchmesser [mm]"},
    "rotorOD":    {"kind": "num", "lo": 40,  "hi": 498, "def": 188.6, "geom": True, "desc": "Rotor-Außendurchmesser [mm] (< statorID, Luftspalt ~0.7 mm)"},
    "shaftD":     {"kind": "num", "lo": 15,  "hi": 300, "def": 60, "geom": True,  "desc": "Wellendurchmesser [mm]"},
    "shaftBoreD": {"kind": "num", "lo": 0,   "hi": 250, "def": 0, "geom": True,   "desc": "Hohlwellen-Bohrung [mm] (0 = Vollwelle)"},
    "axialLen":   {"kind": "num", "lo": 30,  "hi": 300, "def": 80,  "desc": "Blechpaketlänge [mm]"},
    "slots":      {"kind": "num", "lo": 6,   "hi": 96,  "def": 54, "geom": True,  "desc": "Statornutzahl (Vielfaches von 3, typ. 6·p)", "int": True},
    "slotDepth":  {"kind": "num", "lo": 8,   "hi": 60,  "def": 25, "geom": True,  "desc": "Nuttiefe [mm]"},
    "p":          {"kind": "num", "lo": 1,   "hi": 12,  "def": 3, "geom": True,   "desc": "Polpaarzahl", "int": True},
    "machineType":{"kind": "enum", "opts": _ART, "def": "pmsm", "geom": True, "adv": True,
                   "desc": "Maschinenart: pmsm=permanenterregt, asm=Asynchron (Käfig), synrm=Reluktanz, eesm=fremderregt (analytisch getragen: pmsm, asm)"},
    "rotorBars":  {"kind": "num", "lo": 0, "hi": 120, "def": 0, "geom": True, "adv": True, "int": True,
                   "desc": "Läufernutzahl (ASM-Käfig); 0 = automatisch nach der Auswahlregel"},
    "bZielT":     {"kind": "num", "lo": 0.55, "hi": 0.95, "def": 0.80, "geom": True, "adv": True,
                   "desc": "Ziel-Luftspaltfeld [T] der ASM (wird über den Magnetisierungsstrom eingestellt)"},
    "magShape":   {"kind": "enum", "opts": _SHAPE, "def": "v", "geom": True, "desc": "Magnet-Topologie"},
    "magAngle":   {"kind": "num", "lo": 40,  "hi": 170, "def": 120, "geom": True, "desc": "V-Öffnungswinkel [°] (kleiner → mehr Flusskonzentration)"},
    "magDepthRel":{"kind": "num", "lo": 0.4, "hi": 0.92,"def": 0.7, "geom": True, "desc": "radiale Magnetposition (0=Welle … 1=Rotorrand)"},
    "magWidth":   {"kind": "num", "lo": 10,  "hi": 90,  "def": 45, "geom": True,  "desc": "Magnetlänge [mm]"},
    "magThick":   {"kind": "num", "lo": 2,   "hi": 15,  "def": 6, "geom": True,   "desc": "Magnetdicke [mm]"},
    # 2 mm war die Vorgabe und ist an der Vorgabegeometrie (V, p=3, magAngle 120)
    # nicht baubar: die beiden V-Schenkel kommen nie aneinander vorbei --
    # ``einpassen`` schrumpfte den Magneten dafuer auf 43 % (Dicke 6 -> 2,6 mm).
    # Bei 4 mm bleibt er ungeschmaelert. Gemessen, s. cae_cli.frischer_payload.
    "magDist":    {"kind": "num", "lo": 0,   "hi": 30,  "def": 4, "geom": True,   "desc": "Stegabstand zwischen den Magneten [mm]"},
    "nAx":        {"kind": "num", "lo": 1,   "hi": 12,  "def": 1, "geom": True,   "desc": "Magnet-Segmente axial (Wirbelstromreduktion)", "int": True},
    "nCirc":      {"kind": "num", "lo": 1,   "hi": 6,   "def": 1, "geom": True,   "desc": "Magnet-Segmente in Umfangsrichtung", "int": True},
    "rotor_lam":  {"kind": "enum", "opts": _LAM,  "def": "m270_35a", "desc": "Rotorblech"},
    "stator_lam": {"kind": "enum", "opts": _LAM,  "def": "m270_35a", "desc": "Statorblech"},
    "hairpin_mat":{"kind": "enum", "opts": _HAIR, "def": "cu_etp",   "desc": "Hairpin-Leitermaterial"},
    "magnet":     {"kind": "enum", "opts": _MAG,  "def": "ndfeb_n35","desc": "Magnetwerkstoff"},
    "cooling":    {"kind": "enum", "opts": _COOL, "def": "water",    "desc": "Kühlung"},
    "rpm_from":   {"kind": "num", "lo": 100, "hi": 25000, "def": 5000,  "desc": "Basisdrehzahl / Auslegungsdrehzahl [U/min]"},
    "rpm_to":     {"kind": "num", "lo": 500, "hi": 50000, "def": 20000, "desc": "Maximaldrehzahl [U/min]"},
    "load_nm":    {"kind": "num", "lo": 0,   "hi": 1000,  "def": 120,   "desc": "Auslegungs-Lastmoment [Nm]"},
    "T_ambient":  {"kind": "num", "lo": -40, "hi": 80,    "def": 25,    "desc": "Umgebungstemperatur [°C]"},

    # ── Feinparameter (adv) — vom LLM nicht erfragt, ueber die Parametertabelle und
    #    ``cae_cli --set`` aber voll gepflegt. Aufgenommen ist, was die Rechnung
    #    nachweislich liest (ema_analysis / ema_topology / ema_thermal / ema_em3d);
    #    reine CAD-Schalter (Lager, Splines, Wickelkopfform) bleiben bewusst draussen.
    # Wicklung
    "conductorsPerSlot":   {"kind": "num", "lo": 2,    "hi": 12,   "def": 4,   "int": True, "geom": True, "adv": True, "desc": "Leiter je Nut (Hairpin, geradzahlig)"},
    # Wicklungsart. Vorgabe bleibt der Hairpin -- alles Bestehende gilt damit
    # unveraendert; der Runddraht ist die zweite Bauart und keine Umstellung.
    "windingType":         {"kind": "enum", "opts": _WICKLUNG, "def": ema_wicklung.VORGABE, "geom": True, "adv": True, "desc": "Wicklungsart: hairpin=rechteckige Staebe (Vorgabe), rundraht=gewickelt"},
    "turnsPerSlot":        {"kind": "num", "lo": 0,    "hi": 400,  "def": 0,   "int": True, "geom": True, "adv": True, "desc": "Windungen je Nut (Runddraht; 0 = wie conductorsPerSlot)"},
    "slotWidthRatio":      {"kind": "num", "lo": 0.2,  "hi": 0.8,  "def": 0.5,  "geom": True, "adv": True, "desc": "Nutbreite / Nutteilung (Rest ist Zahn)"},
    # Magnetlagen und Polkontur
    "magLayers":           {"kind": "num", "lo": 2,    "hi": 4,    "def": 3,   "int": True, "geom": True, "adv": True, "desc": "Magnetlagen je Pol (nur pmasynrm)"},
    "magLayerGap":         {"kind": "num", "lo": 1,    "hi": 50,   "def": 8,    "geom": True, "adv": True, "desc": "Abstand zwischen den Magnetlagen [mm] (nur vv, pmasynrm)"},
    "poleArcFrac":         {"kind": "num", "lo": 0.5,  "hi": 0.98, "def": 0.83, "geom": True, "adv": True, "desc": "Polbedeckung, Anteil der Polteilung (nur spm, halbach)"},
    "segPerPole":          {"kind": "num", "lo": 2,    "hi": 24,   "def": 6,   "int": True, "geom": True, "adv": True, "desc": "Magnete je Pol (nur halbach)"},
    "magAngle2":           {"kind": "num", "lo": 40,   "hi": 170,  "def": 90,   "geom": True, "adv": True, "desc": "zweiter V-Winkel [°] (nur vv)"},
    "magAsym":             {"kind": "num", "lo": -60,  "hi": 60,   "def": 0,    "geom": True, "adv": True, "desc": "Asymmetrie der V-Schenkel [°], 0 = symmetrisch (nur vasym)"},
    "magTangLen":          {"kind": "num", "lo": 0,    "hi": 200,  "def": 0,    "geom": True, "adv": True, "desc": "Tangentialmagnet-Länge [mm], 0 = automatisch (nur u, delta)"},
    "magGapMm":            {"kind": "num", "lo": 0.05, "hi": 0.3,  "def": 0.1,  "geom": True, "adv": True, "desc": "Klebespalt Magnet↔Tasche je Seite [mm]"},
    "magOrient":           {"kind": "enum", "opts": _ORIENT, "def": "transverse", "geom": True, "adv": True, "desc": "Magnetisierungsrichtung (quer / längs)"},
    # Magnettasche
    "pocketMode":          {"kind": "enum", "opts": _POCKET, "def": "position", "geom": True, "adv": True, "desc": "Tasche über Position oder Durchmesser (nur v)"},
    "pocketOuterD":        {"kind": "num", "lo": 10,   "hi": 2970, "def": 178,  "geom": True, "adv": True, "desc": "Taschen-Außendurchmesser [mm] (pocketMode=diameter)"},
    "pocketInnerD":        {"kind": "num", "lo": 5,    "hi": 2960, "def": 150,  "geom": True, "adv": True, "desc": "Taschen-Innendurchmesser [mm] (pocketMode=diameter)"},
    # Flusssperren
    "genFluxBarrierD":     {"kind": "bool", "def": False, "geom": True, "adv": True, "desc": "Flusssperre in der d-Achse erzeugen"},
    "genFluxBarrierQ":     {"kind": "bool", "def": False, "geom": True, "adv": True, "desc": "Flusssperre in der q-Achse erzeugen"},
    "fluxBarrierDepth":    {"kind": "num", "lo": 1,    "hi": 120,  "def": 10,   "geom": True, "adv": True, "desc": "Tiefe der Flusssperre [mm]"},
    "fluxBarrierWidth":    {"kind": "num", "lo": 0.5,  "hi": 40,   "def": 3,    "geom": True, "adv": True, "desc": "Breite der Flusssperre [mm]"},
    # Wuchtbohrungen (verdraengen Rotoreisen, daher in der Rechnung sichtbar)
    "genBalanceBolts":     {"kind": "bool", "def": False, "geom": True, "adv": True, "desc": "Wuchtbohrungen erzeugen"},
    "balanceBoltCircleD":  {"kind": "num", "lo": 0,    "hi": 3000, "def": 0,    "geom": True, "adv": True, "desc": "Lochkreis der Wuchtbohrungen [mm] (0 = automatisch)"},
    "balanceBoltOffsetDeg":{"kind": "num", "lo": -180, "hi": 180,  "def": 0,    "geom": True, "adv": True, "desc": "Winkelversatz der Wuchtbohrungen [°]"},
    "balanceBoltThread":   {"kind": "enum", "opts": _THREAD, "def": "M6", "geom": True, "adv": True, "desc": "Gewinde der Wuchtbohrungen"},
}


# ── Rechengüte: Entwurf gegen Detail ────────────────────────────────────────
#
# Gemessen am Projekt 20260827_170019_Alpenpass (vasym, p=3, 36 Nuten, Saettigung
# an), ``run_em_analysis`` ueber die Aufloesung:
#
#   N             120     150     200     240     300     400     600
#   Sekunden      0.54    1.13    3.53    4.79    9.18    20.9    68.75
#   B_gap [T]     0.477   0.477   0.477   0.477   0.477   0.477   0.477
#   Kt            0.031   0.031   0.031   0.031   0.031   0.031   0.031
#   Br-Grundwelle -92.0%  -83.7%  -72.1%  -52.5%  -2.8%   +8.2%   0
#
# Zwei Befunde tragen die Voreinstellungen:
#   1. ``B_gap`` und ``Kt`` haengen NICHT an N -- sie kommen aus
#      ``_analytical_Bgap``. Ein Entwurfslauf verliert also keinen Kennwert, nur
#      Bildschaerfe. Das ist der Grund, warum sich mit ``entwurf`` ueberhaupt
#      entscheiden laesst.
#   2. Die FORM der Luftspaltwelle knickt bei N=300 ein; darunter liegt sie um
#      die Haelfte daneben. Deshalb geht KEINE Stufe unter 300.
#
# **Warum das hier steht und nicht nur in ``ema.html``:** die Oberflaeche hatte
# diese Tabelle als ``CALC_PRESETS`` schon, die Kommandozeile nicht -- und die
# Schluessel stehen in KEINEM Schema. Ein Agent konnte die Guete also gar nicht
# waehlen (``--set fdm_resolution=300`` wurde als unbekannt abgewiesen) und
# rechnete jeden Entwurfsversuch in Detailgenauigkeit. ``test_steckbrief.py``
# nagelt die JS-Kopie gegen diese Tabelle fest, wie es ``test_topology.py`` fuer
# die Topologien tut.
GUETE = {
    "entwurf": {
        "label": "Entwurf",
        "zweck": "durchspielen, entscheiden, verwerfen — Minuten statt Stunden",
        "felder": {"n_frames": 12, "frame_resolution": 180, "fdm_resolution": 300,
                   "rpm_step": 1000, "struct_solver": "ccx", "struct_mesh_mm": 4,
                   "struct_img_px": 1500, "struct_video": False,
                   "struct_frames": 20},
    },
    "detail": {
        "label": "Detail",
        "zweck": "die Zahl, die in den Bericht geht",
        "felder": {"n_frames": 36, "frame_resolution": 300, "fdm_resolution": 800,
                   "rpm_step": 500, "struct_solver": "freecad",
                   "struct_mesh_mm": 2.5, "struct_img_px": 3000,
                   "struct_video": True, "struct_frames": 48},
    },
}


def guete_anwenden(payload: dict, stufe: str) -> dict:
    """Die Guetefelder in einen Payload schreiben. Gibt die gesetzten zurueck.

    Sie gehen NICHT durch die Schemapruefung: es sind Regler der Pipeline
    (Aufloesung, Netzweite, Bildzahl), keine Groessen der Maschine. Im Schema
    haetten sie nichts zu suchen -- dort steht, was die MASCHINE beschreibt.
    """
    stufe = str(stufe or "").lower()
    if stufe not in GUETE:
        raise ValueError(f"Unbekannte Guete '{stufe}'. Waehlbar: "
                         + ", ".join(GUETE))
    felder = GUETE[stufe]["felder"]
    payload.update(felder)
    return dict(felder)


def _extract_obj(txt: str):
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _validate(raw: dict) -> dict:
    out = {}
    for key, spec in SCHEMA.items():
        if spec.get("adv"):
            continue          # Feinparameter: nicht erfragt, also auch nicht gefuellt —
        v = raw.get(key)      # sonst schriebe Text->Auslegung 22 Vorgaben in den Entwurf
        if spec["kind"] == "enum":
            out[key] = v if v in spec["opts"] else spec["def"]
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = spec["def"]
            v = max(spec["lo"], min(spec["hi"], v))
            out[key] = int(round(v)) if spec.get("int") else round(v, 3)
    # slots → nearest multiple of 3 (>=6)
    out["slots"] = max(6, int(round(out["slots"] / 3)) * 3)
    # enforce radial ordering statorOD > statorID > rotorOD > shaftD > shaftBoreD
    if out["statorID"] >= out["statorOD"] - 10:
        out["statorID"] = round(out["statorOD"] - 40, 1)
    if out["rotorOD"] >= out["statorID"] - 0.4:
        out["rotorOD"] = round(out["statorID"] - 1.4, 1)        # ~0.7 mm air gap each side
    if out["shaftD"] >= out["rotorOD"] - 5:
        out["shaftD"] = round(out["rotorOD"] * 0.35, 1)
    if out["shaftBoreD"] >= out["shaftD"] - 2:
        out["shaftBoreD"] = 0
    if out["rpm_to"] <= out["rpm_from"]:
        out["rpm_to"] = out["rpm_from"] * 2
    return out


def _prompt(description: str, context: str = "") -> str:
    fields = "\n".join(
        f"  {k}: " + (f"einer von {s['opts']}" if s["kind"] == "enum"
                      else f"Zahl {s['lo']}–{s['hi']}") + f" — {s['desc']}"
        for k, s in SCHEMA.items() if not s.get("adv"))
    ref = ""
    if context:
        ref = ("REFERENZMASCHINEN (aus der Wissensbasis — als gut befundene Auslegungen; "
               "orientiere dich an plausiblen Werten, übernimm aber nicht blind):\n"
               f"{context}\n\n")
    return (
        "Du bist ein erfahrener Auslegungsingenieur für Innenpol-PM-Synchronmaschinen "
        "(IPM). Leite aus der folgenden Anwendungsbeschreibung einen sinnvollen, in sich "
        "stimmigen Parametersatz für eine erste Auslegung ab.\n\n"
        f"ANWENDUNG:\n{description}\n\n"
        + ref +
        "FELDER (Schlüssel: erlaubter Bereich/Auswahl — Bedeutung):\n" + fields + "\n\n"
        "Regeln: statorOD > statorID > rotorOD > shaftD; Luftspalt ~0,7 mm "
        "(rotorOD ≈ statorID − 1,4); slots ≈ 6·p; höhere Maximaldrehzahl → kleinerer "
        "Rotordurchmesser (Fliehkraft); hohes Drehmoment → größerer Durchmesser/Länge, "
        "stärkerer Magnet (n42/n50), kleinerer Öffnungswinkel; sparsam/günstig → Ferrit "
        "oder n35. Wähle die Kühlung passend zur Leistungsdichte.\n\n"
        "Antworte NUR mit einem JSON-Objekt: {\"params\": {<alle Felder>}, "
        "\"begruendung\": \"<2–4 Sätze, warum diese Wahl>\"}. Kein weiterer Text."
    )


def derive(description: str, timeout: int = 180) -> dict:
    """Return {params, begruendung, model}. params is always complete + valid."""
    if not (description or "").strip():
        raise ValueError("Leere Beschreibung")
    # RAG: ground the derivation on deposited reference machines (category "maschinen").
    # Best effort — if the knowledge base / Ollama embeddings are unavailable, derive
    # still works without context.
    context = ""
    try:
        import ema_rag
        context = ema_rag.context_for(description, category=None, k=4)
    except Exception:
        context = ""
    body = json.dumps({
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": _prompt(description, context)}],
        "stream": False,
        "think": False,           # s. ema_report.call_ollama
        "options": {"temperature": 0.4, "num_ctx": DEFAULT_NUM_CTX,
                    "num_predict": 1200},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    txt = _THINK_RE.sub("", (resp.get("message", {}) or {}).get("content", "")).strip()
    obj = _extract_obj(txt)
    raw = obj.get("params", obj) if isinstance(obj, dict) else {}
    why = obj.get("begruendung") if isinstance(obj, dict) else ""
    if isinstance(why, (dict, list)):
        why = json.dumps(why, ensure_ascii=False)
    return {
        "params":      _validate(raw if isinstance(raw, dict) else {}),
        "begruendung": str(why or ""),
        "model":       DEFAULT_MODEL,
        "rag_used":    bool(context),
    }
