"""Mehrere Leistungselektroniken -- A1..A4, B1..B4, C1..C4 statt A, B, C.

**Das Erste, was dazu zu sagen ist: Aufteilen macht die Maschine nicht staerker.**
Das Moment haengt an den Amperewindungen, und die sind durch Nutquerschnitt,
Stromdichte und Kuehlung festgelegt. Vier Systeme mit je einem Viertel der Leiter
liefern zusammen dieselbe Durchflutung wie eines mit allen; die gesamte
Umrichter-Scheinleistung bleibt gleich und verteilt sich nur auf k Module.

Wer trotzdem so baut, kauft vier andere Dinge:

* **kleinere Halbleiter** -- ein Modul traegt 1/k der Scheinleistung,
* **n-1-Betrieb** statt Totalausfall,
* **verteilte Verlustwaerme**,
* **Auslöschung von Harmonischen**, wenn die Systeme gegeneinander versetzt sind.

Nur das Erste und das Zweite rechnet dieses Modul. Die Harmonischen braeuchten
einen zeitabhaengigen Feldlauf -- der hiesige FDM ist magnetostatisch --, und das
steht als Grenze in jeder Ausgabe.

Die Rechnung, und warum sie so herum geht
-----------------------------------------

Der Nutquerschnitt liegt fest, also bekommt jedes der k Systeme **1/k der
Leiter**: ``N_System = N/k``. Daraus folgt alles Weitere zwingend.

* Flussverkettung je System ``psi/k`` -> **Spannung je Modul E/k**.
* Durchflutung ``sum(N_j * I_j) = k * (N/k) * I = N * I`` -> **Strom je Modul
  unveraendert I**.

Von der Maschine aus gesehen heisst das: k Module zu je ``V_Modul`` verhalten
sich wie **ein** Umrichter mit ``k * V_Modul`` bei demselben Strom. Mehr Module
kaufen also **Spannungsreserve** (und damit Eckdrehzahl), nicht Strom -- oder,
andersherum gelesen, sie erlauben billigere Niedervolt-Halbleiter fuer dieselbe
Maschine.

Das ist genau dieselbe Algebra wie die Windungszahlbruecke in
``ema_analysis.umrichter`` (``Kt ~ N``, ``i ~ 1/N``, ``u ~ N``); ein Umrichter
mit 24 V und 200 A treibt dieselbe Maschine wie einer mit 800 V und 6 A. Deshalb
steht die Modulzahl auch **dort** und nicht in einer zweiten Rechnung daneben --
``umrichter()`` bleibt die eine Quelle der Grenzen, und die neun Module, die
durch sie hindurchlesen, erben die Aufteilung, ohne angefasst zu werden.

Was die Bauart unterscheidet -- und was NICHT
---------------------------------------------

``verschachtelt`` und ``sektoriert`` ergeben in diesem Modell **dieselben
Modulkennwerte**. Das wird hier ausdruecklich gesagt, statt einen Unterschied zu
erfinden, den die Rechnung nicht hergibt. Sie unterscheiden sich im Fehlerfall
und in der Wickelbarkeit:

* **verschachtelt** -- jedes System liegt in JEDER Nut. Faellt eines aus, sinkt
  das Moment gleichmaessig auf (k-1)/k, und es bleibt symmetrisch.
* **sektoriert** -- jedes System bekommt eigene Nuten. Faellt eines aus, fehlt
  das Moment auf EINEM Umfangsabschnitt: es entsteht ein **einseitiger
  Magnetzug** auf die Lager. Der ist hier **nicht gerechnet** und steht als
  Warnung an jeder sektorierten Auslegung.
"""

from __future__ import annotations

import math

TOPOLOGIEN = {
    "verschachtelt": {
        "text": "verschachtelt (jedes System in jeder Nut)",
        "ausfall": "symmetrisch — Moment sinkt gleichmaessig auf (k-1)/k",
        "warnung": "",
    },
    "sektoriert": {
        "text": "sektoriert (jedes System auf eigenen Nuten)",
        "ausfall": "unsymmetrisch — ein Umfangsabschnitt faellt aus",
        "warnung": ("einseitiger Magnetzug auf die Lager im Fehlerfall — "
                    "in diesem Werkzeug NICHT gerechnet"),
    },
}
TOPOLOGIE_VORGABE = "verschachtelt"

ANZAHL_SPANNE = (1, 8)


def anzahl(geom: dict) -> int:
    """Wieviele Leistungselektroniken -- geklemmt, Vorgabe 1."""
    try:
        k = int(float((geom or {}).get("inverterAnzahl") or 1))
    except (TypeError, ValueError):
        k = 1
    return max(ANZAHL_SPANNE[0], min(ANZAHL_SPANNE[1], k))


def topologie(geom: dict) -> str:
    t = str((geom or {}).get("inverterTopologie") or TOPOLOGIE_VORGABE).strip().lower()
    return t if t in TOPOLOGIEN else TOPOLOGIE_VORGABE


def wickelbar(geom: dict, k: int | None = None, topo: str | None = None) -> dict:
    """Laesst sich die Wicklung ueberhaupt in k Systeme teilen?

    Ein Tor wie ``rotor_layout_check``: reine Algebra, Millisekunden, und es sagt
    **warum** nicht und **was statt dessen ginge**. Ohne das bekaeme man
    Modulkennwerte fuer eine Wicklung, die niemand legen kann.

    Drei Bedingungen, jede aus der Wicklung und nicht aus einer Faustregel:

    * ``slots % (3*k) == 0`` -- jedes System braucht je Strang eine ganze Zahl
      Nuten. Gilt fuer beide Bauarten.
    * **sektoriert** zusaetzlich ``2p % k == 0`` -- sonst umfasst ein Sektor
      keine ganze Polzahl, und die Maschine ist schon im GESUNDEN Betrieb
      unsymmetrisch.
    * **verschachtelt mit Versatz** braucht ``q = slots/(2p*3) >= k`` -- fuer
      den Winkelversatz, aus dem die Harmonischenausloeschung kommt, muss je
      System mindestens eine eigene Nut je Pol und Strang da sein. Ohne das
      geht verschachtelt trotzdem, nur **ohne** Versatz: dann teilen sich die
      Systeme dieselben Nuten, und der harmonische Vorteil entfaellt.
    """
    g = geom or {}
    k = anzahl(g) if k is None else int(k)
    topo = topologie(g) if topo is None else str(topo)
    slots = int(g.get("slots") or 0)
    p = int(g.get("p") or 0)
    if slots <= 0 or p <= 0:
        return {"ok": False, "grund": "Nutzahl oder Polpaarzahl fehlt",
                "k": k, "topologie": topo}
    pole = 2 * p
    q = slots / float(pole * 3)
    befunde, ok = [], True

    if k > 1 and slots % (3 * k) != 0:
        ok = False
        moeglich = [j for j in range(2, ANZAHL_SPANNE[1] + 1)
                    if slots % (3 * j) == 0]
        befunde.append({"hart": True, "text":
            f"{slots} Nuten lassen sich nicht auf {k} Dreiphasensysteme teilen "
            f"({slots}/(3·{k}) ist nicht ganz)"
            + (f" — moeglich waeren k = {', '.join(map(str, moeglich))}"
               if moeglich else "")})

    if topo == "sektoriert" and k > 1 and pole % k != 0:
        ok = False
        befunde.append({"hart": True, "text":
            f"sektoriert braucht eine ganze Polzahl je Sektor: {pole} Pole / "
            f"{k} Sektoren = {pole / k:.2f} — die Maschine waere schon im "
            f"gesunden Betrieb unsymmetrisch"})

    versetzt = bool(k <= 1 or q >= k)
    if topo == "verschachtelt" and k > 1 and not versetzt:
        # KEIN hartes Nein: ohne Versatz laesst sich die Wicklung sehr wohl
        # teilen, nur entfaellt der harmonische Vorteil. Den Unterschied
        # einzuebnen hiesse, einen Hinweis wie einen Ausschluss zu lesen.
        befunde.append({"hart": False, "text":
            f"verschachtelt geht, aber OHNE Winkelversatz: q = {q:.2f} Nut je "
            f"Pol und Strang, fuer {k} versetzte Systeme braeuchte es q ≥ {k}. "
            f"Ohne Versatz entfaellt die Harmonischenausloeschung — der "
            f"Hauptgrund, aus dem man verschachtelt baut"})

    return {"ok": ok, "k": k, "topologie": topo, "q": round(q, 3),
            "pole": pole, "slots": slots,
            "nuten_je_system": (slots / k if k else slots),
            "pole_je_sektor": (pole / k if k else pole),
            "versatz_moeglich": versetzt,
            "versatz_grad_el": (round(60.0 / k, 2) if versetzt and k > 1 else None),
            "befunde": befunde,
            "grund": "; ".join(b["text"] for b in befunde
                                if b["hart"]) if not ok else ""}


def zerlegung(geom: dict, rpm_max: float = 0.0) -> dict:
    """Was jedes einzelne Modul liefern muss -- und was die Maschine davon sieht.

    ``inverterVdc``/``inverterImax`` sind die Werte **EINES Moduls**. Das ist die
    Lesart, in der jemand einkauft ("ich habe vier 400-V-Stufen"), und sie ist
    rueckwaertskompatibel: bei k = 1 ist das Modul der ganze Umrichter, und jede
    Altrechnung bleibt Ziffer fuer Ziffer dieselbe.
    """
    import ema_analysis

    g = geom or {}
    k = anzahl(g)
    u = ema_analysis.umrichter(g, rpm_max)
    v_mod = float(g.get("inverterVdc") or 0.0) or ema_analysis.INVERTER_V_DC
    i_mod = float(g.get("inverterImax") or 0.0) or ema_analysis.INVERTER_I_MAX
    s_mod = math.sqrt(3.0) * v_mod * i_mod / 2.0 / 1000.0   # kVA, Amplitude->eff
    tor = wickelbar(g, k, topologie(g))
    return {
        "k": k, "topologie": topologie(g),
        "topologie_text": TOPOLOGIEN[topologie(g)]["text"],
        "v_modul_V": v_mod, "i_modul_A": i_mod,
        "S_modul_kVA": round(s_mod, 1), "S_gesamt_kVA": round(s_mod * k, 1),
        # Was die MASCHINE sieht: k Module zu je V_Modul wirken wie EIN
        # Umrichter mit k*V_Modul bei demselben Strom (s. Modulkopf).
        "v_maschine_V": u["v_dc_V"], "i_maschine_A": u["i_max_A"],
        "v_dc_1t": u["v_dc_1t"], "i_max_1t": u["i_max_1t"],
        "n_wdg": u["n_wdg"], "n_quelle": u["n_quelle"],
        "wickelbar": tor,
        "warnung": TOPOLOGIEN[topologie(g)]["warnung"],
    }


def ausfall(geom: dict, adv: dict, rpm_max: float, t_rated_Nm: float = 0.0,
            n_aus: int = 1) -> dict:
    """n-1-Betrieb: was bleibt, wenn ein Modul ausfaellt.

    **Der eigentliche Grund, aus dem solche Antriebe gebaut werden** -- und mit
    ``power_envelope`` eine Zeile Arbeit, weil dort die Grenzen von aussen
    hineingereicht werden koennen.

    Faellt eines von k Systemen aus, sind noch ``(k-1)/k`` der Wicklung aktiv.
    Beides skaliert damit: die Spannungsreserve (weniger Flussverkettung in
    Reihe) und die erreichbare Durchflutung bei unveraendertem Modulstrom. Also
    laeuft dieselbe Huellkurve mit beiden Grenzen auf ``(k-n_aus)/k``.

    Was hier NICHT drinsteht und bei ``sektoriert`` wichtig waere: der
    einseitige Magnetzug. Er steht als Warnung dabei, nicht als Zahl.
    """
    import ema_analysis

    g = geom or {}
    k = anzahl(g)
    z = zerlegung(g, rpm_max)
    voll = ema_analysis.power_envelope(g, adv, rpm_max=rpm_max,
                                       T_rated_Nm=t_rated_Nm)
    if k <= 1:
        return {"k": k, "moeglich": False,
                "grund": "nur ein Modul — ein Ausfall ist der Totalausfall",
                "voll": voll, "rest": None, "anteil": 0.0}
    rest_k = max(0, k - int(n_aus))
    if rest_k <= 0:
        return {"k": k, "moeglich": False, "grund": "alle Module ausgefallen",
                "voll": voll, "rest": None, "anteil": 0.0}
    f = rest_k / float(k)
    rest = ema_analysis.power_envelope(
        g, adv, rpm_max=rpm_max, T_rated_Nm=t_rated_Nm * f,
        v_dc=z["v_dc_1t"] * f, i_max=z["i_max_1t"] * f)
    p_v = float((voll or {}).get("P_max_kW") or 0.0)
    p_r = float((rest or {}).get("P_max_kW") or 0.0)
    return {"k": k, "n_aus": int(n_aus), "rest_module": rest_k, "moeglich": True,
            "anteil": round(f, 4), "voll": voll, "rest": rest,
            "P_voll_kW": round(p_v, 2), "P_rest_kW": round(p_r, 2),
            "P_anteil": (round(p_r / p_v, 3) if p_v > 1e-9 else None),
            "warnung": TOPOLOGIEN[topologie(g)]["warnung"]}


def als_text(z: dict, aus: dict | None = None) -> str:
    """Menschenlesbar -- und der erste Satz ist der wichtigste."""
    t = []
    a = t.append
    k = z["k"]
    a(f"{k} Leistungselektronik{'en' if k != 1 else ''} — {z['topologie_text']}")
    if k > 1:
        a("")
        a("  Aufteilen macht die Maschine NICHT staerker: die Amperewindungen")
        a("  liegen durch Nut, Stromdichte und Kuehlung fest. Die gesamte")
        a("  Scheinleistung bleibt gleich und verteilt sich auf die Module.")
    a("")
    a(f"  je Modul     {z['v_modul_V']:.0f} V · {z['i_modul_A']:.0f} A "
      f"= {z['S_modul_kVA']:.1f} kVA")
    a(f"  zusammen     {z['S_gesamt_kVA']:.1f} kVA")
    a(f"  die Maschine sieht  {z['v_maschine_V']:.0f} V · "
      f"{z['i_maschine_A']:.0f} A   (k Module wirken wie EIN Umrichter mit "
      f"k·V_Modul bei gleichem Strom)")
    a(f"  Bezug: {z['n_quelle']}, {z['n_wdg']} Wdg/Nut")

    w = z["wickelbar"]
    a("")
    a(f"  Wicklung: {w['slots']} Nuten, {w['pole']} Pole, q = {w['q']:.2f}")
    if k > 1:
        a(f"            {w['nuten_je_system']:.1f} Nuten je System"
          + (f", {w['pole_je_sektor']:.1f} Pole je Sektor"
             if z["topologie"] == "sektoriert" else ""))
        if w["versatz_moeglich"] and w["versatz_grad_el"]:
            a(f"            Versatz {w['versatz_grad_el']:.1f}° el. moeglich "
              f"(loescht die 5. und 7. Harmonische aus — HIER NICHT GERECHNET, "
              f"der FDM ist magnetostatisch)")
    for b in w["befunde"]:
        a(f"  {'✗' if b.get('hart') else '⚠'} {b.get('text', b)}")
    if w["ok"] and not w["befunde"] and k > 1:
        a("  ✓ teilbar")
    if z.get("warnung"):
        a(f"  ⚠ {z['warnung']}")

    if aus and aus.get("moeglich"):
        a("")
        a(f"  Ausfall eines Moduls ({aus['rest_module']} von {aus['k']} bleiben):")
        a(f"    {aus['P_voll_kW']:.1f} kW  ->  {aus['P_rest_kW']:.1f} kW"
          + (f"   ({aus['P_anteil'] * 100:.0f} %)"
             if aus.get("P_anteil") else ""))
        a(f"    erwartet waeren {aus['anteil'] * 100:.0f} % — beides skaliert "
          f"mit der noch aktiven Wicklung")
    elif aus and not aus.get("moeglich"):
        a("")
        a(f"  Ausfall: {aus.get('grund', '')}")
    return "\n".join(t)


# ── Bilder ───────────────────────────────────────────────────────────────────

SYSTEMFARBEN = ("#1565c0", "#c62828", "#2e7d32", "#f9a825",
                "#6a1b9a", "#00838f", "#ef6c00", "#4e342e")


def system_je_nut(slots: int, k: int, topo: str) -> list:
    """Welche Nut gehoert zu welchem System -- die EINE Zuordnung.

    ``sektoriert`` schneidet den Umfang in k zusammenhaengende Stuecke,
    ``verschachtelt`` verteilt reihum. Beide Male eine Zeile, und beide Male
    steht sie HIER, damit Bild und Rechnung dieselbe Maschine meinen.
    """
    k = max(1, int(k))
    slots = max(1, int(slots))
    if topo == "sektoriert":
        je = slots / float(k)
        return [min(k - 1, int(s // je)) for s in range(slots)]
    return [s % k for s in range(slots)]


def bild(geom: dict, pfad: str, dpi: int = 130) -> str:
    """Der Querschnitt mit den k Systemen -- welche Nut gehoert wem.

    Gezeichnet ueber ``ema_pipeline.render_cross_section`` (dieselbe Zeichnung
    wie CAD-Schnitt, Bilddatensatz und Saettigungsbild), darueber je Nut ein
    farbiger Keil. Das ist der Unterschied, den man sehen WILL: bei
    ``sektoriert`` liegen die Farben in Bloecken, bei ``verschachtelt``
    abwechselnd -- und daran haengt, ob ein Ausfall symmetrisch ist.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge
    from matplotlib.lines import Line2D
    import ema_pipeline
    import ema_wicklung

    g = geom or {}
    k = anzahl(g)
    topo = topologie(g)
    slots = int(g.get("slots") or 0)
    ng = ema_wicklung.nutgeometrie(g)
    r_si = ng["r_si_m"] * 1000.0
    r_nut = r_si + ng["nut_tiefe_m"] * 1000.0
    zuord = system_je_nut(slots, k, topo)
    halb = 360.0 / slots / 2.0 * 0.82

    fig, ax = plt.subplots(figsize=(7.6, 7.6))
    ema_pipeline.render_cross_section(g, ax, beschriftung=False)
    for s in range(slots):
        mitte = s * 360.0 / slots
        ax.add_patch(Wedge((0, 0), r_nut, mitte - halb, mitte + halb,
                           width=r_nut - r_si,
                           facecolor=SYSTEMFARBEN[zuord[s] % len(SYSTEMFARBEN)],
                           alpha=0.62, edgecolor="none", zorder=6))
    w = wickelbar(g, k, topo)
    ax.legend(handles=[Line2D([0], [0], marker="s", lw=0,
                              markerfacecolor=SYSTEMFARBEN[j % len(SYSTEMFARBEN)],
                              markeredgecolor="none", markersize=11,
                              label=f"System {j + 1}  (A{j + 1} B{j + 1} C{j + 1})")
                       for j in range(k)],
              loc="upper right", fontsize=8.5, framealpha=0.9)
    ax.set_title(f"{k} Leistungselektronik{'en' if k != 1 else ''} — "
                 f"{TOPOLOGIEN[topo]['text']}\n"
                 f"{w['nuten_je_system']:.0f} Nuten je System, "
                 f"{TOPOLOGIEN[topo]['ausfall']}", fontsize=10.5)
    fuss = ("Aufteilen macht die Maschine nicht staerker — die Amperewindungen "
            "liegen fest.\nGeteilt wird die Scheinleistung: k Module zu je 1/k.")
    if TOPOLOGIEN[topo]["warnung"]:
        fuss += "\n⚠ " + TOPOLOGIEN[topo]["warnung"]
    fig.text(0.5, 0.02, fuss, ha="center", va="bottom", fontsize=7.5,
             color="#555")
    fig.tight_layout(rect=(0, 0.085, 1, 1))
    fig.savefig(pfad, dpi=dpi)
    plt.close(fig)
    return pfad


def diagramm(aus: dict, pfad: str, dpi: int = 130) -> str:
    """Die n-1-Kennlinie -- der eigentliche Grund fuer mehrere Module.

    Zwei Huellkurven uebereinander: alle Module, und eines weniger. Das ist die
    Antwort auf "was passiert, wenn eines ausfaellt", und sie ist eine Kurve und
    keine Zahl -- der Verlust ist ueber der Drehzahl nicht konstant, weil
    Strom- und Spannungsgrenze an verschiedenen Stellen binden.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    voll, rest = aus.get("voll") or {}, aus.get("rest") or {}
    if not voll.get("rpm") or not rest.get("rpm"):
        raise ValueError("keine Huellkurven zum Zeichnen")
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.plot(voll["rpm"], voll["P_peak_kW"], lw=2.4, color="#1565c0",
            label=f"alle {aus['k']} Module")
    ax.plot(rest["rpm"], rest["P_peak_kW"], lw=2.4, color="#c62828", ls="--",
            label=f"{aus['rest_module']} von {aus['k']} (ein Ausfall)")
    ax.fill_between(voll["rpm"], rest["P_peak_kW"], voll["P_peak_kW"],
                    color="#c62828", alpha=0.10)
    ax.set_xlabel("Drehzahl [1/min]")
    ax.set_ylabel("Leistung [kW]")
    ax.set_title(f"n-1-Betrieb: {aus['P_voll_kW']:.0f} kW → "
                 f"{aus['P_rest_kW']:.0f} kW"
                 + (f"  ({aus['P_anteil'] * 100:.0f} %)"
                    if aus.get("P_anteil") else ""))
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    fuss = ("Beides skaliert mit der noch aktiven Wicklung: Spannungsreserve "
            "UND erreichbare Durchflutung.")
    if aus.get("warnung"):
        fuss += "\n⚠ " + aus["warnung"]
    fig.text(0.5, 0.015, fuss, ha="center", va="bottom", fontsize=7.5,
             color="#555")
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    fig.savefig(pfad, dpi=dpi)
    plt.close(fig)
    return pfad


def bilder(geom: dict, ziel_dir: str, aus: dict | None = None) -> list:
    """Beide Bilder nach ``<projekt>/charts`` -- wie Feldbild und Saettigung.

    Derselbe Ablageort aus demselben Grund: die rechte Spalte beider
    Agentenkoepfe findet neue Bilder dort ueber die Aenderungszeit.
    """
    import os
    os.makedirs(ziel_dir, exist_ok=True)
    raus = [bild(geom, os.path.join(ziel_dir, "umrichter_systeme.png"))]
    if aus and aus.get("moeglich"):
        try:
            raus.append(diagramm(aus, os.path.join(ziel_dir,
                                                   "umrichter_ausfall.png")))
        except ValueError:
            pass
    return raus
