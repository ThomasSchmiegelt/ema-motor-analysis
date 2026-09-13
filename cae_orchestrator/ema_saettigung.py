"""Saettigung -- was das Eisen tragen muss, gegen das, was es tragen kann.

Die Saettigung war die eine der vier Grenzen, die dieses Werkzeug **nicht**
rechnet. Der FDM ist linear (``MU_R_IRON = 500``), ``_analytical_Bgap`` hat
keinen Eisenterm, und ``B_SAT_IRON`` wirkt ausschliesslich im Anzeigepfad
(``_saturate_field``, die Berichtsbilder). Das Moment waechst in diesem Modell
also linear mit dem Strom weiter, als gaebe es kein Eisen -- und ein Optimierer,
der "alle Punkte ausreizt", laeuft genau in diese Luecke.

**Der naheliegende Weg funktioniert nicht, und das ist gemessen.** Man koennte
|B| im Statoreisen aus dem Feldlauf ablesen. Gemessen am Projekt
``20260913_153549_super_auto_52`` (305-mm-Maschine, 30 Nm bei 4440 1/min),
p98 im Eisen ohne die Randschicht, Erosion bei jeder Stufe auf dieselben
**1,5 mm** gesetzt (in Zellen gerechnet vergleicht man sonst verschiedene
Gebiete statt verschiedener Aufloesungen):

    N        300     420     600     800     Streuung der letzten drei
    Zahn   0,209   0,206   0,128   0,465 T        72,5 %
    Joch   0,056   0,052   0,038   0,128 T        70,6 %

Nicht konvergent, nicht einmal monoton -- dieselbe Lage wie beim Rotoreisen, wo
sie in ``BEFUNDE.md`` schon steht. Auf dieser Groesse laesst sich kein Kriterium
bauen; jede Zahl waere Rauschen.

**Also die Flusserhaltung.** Sie braucht kein Gitter, sondern nur ``B_gap`` --
und das ist ausdruecklich die aufloesungsunabhaengige Groesse dieses Werkzeugs
(``B_gap`` und ``Kt`` kommen aus der Formel, nicht aus dem Raster; ueber
N = 120...600 auf vier Stellen identisch). Derselbe Weg wird hier schon einmal
benutzt: die Polzahl-Untersuchung in ``BEFUNDE.md`` rechnet die noetige
Jochhoehe genau so.

Der Fluss je Pol muss durch die Zaehne und durch das Joch:

    Phi_pol  = (2/pi) * B_gap * tau_pol * L  =  B_gap * D_gap * L / p
    B_zahn   = B_gap * tau_nut / (b_zahn * k_fe)
    B_joch   = Phi_pol / (2 * h_joch * L * k_fe)

``B_zahn`` ist die uebliche lokale Form: der Zahn sammelt im Wellenberg den
Fluss **einer Nutteilung**. Der Faktor 2 im Joch ist keine Willkuer -- der
Polfluss teilt sich dort in beide Umfangsrichtungen.

**Was das Ergebnis bedeutet, und was nicht.** Ueberschreitet der geforderte Wert
die Saettigungsflussdichte des Blechs (``LAMINATES[...]["B_sat_T"]``, 1,65 bis
2,0 T je Sorte), dann ist das **keine Wand, an der die Maschine stehenbleibt**.
Es heisst: das lineare Modell verlangt vom Eisen mehr, als es hergibt, also sind
Kt, Moment und Leistung ab diesem Punkt zu optimistisch. Genau so steht es auch
in der Ausgabe -- ein Kriterium, das mehr behauptet, waere schlimmer als keins.

**Ein Hebel, der dabei sichtbar wird und nicht offensichtlich ist.** In diesem
Werkzeug setzt ``ema_wicklung.nutgeometrie`` die Nutbreite als festen ANTEIL der
Nutteilung (``slotWidthRatio``, Vorgabe 0,5). Damit kuerzt sich die Nutteilung
aus ``B_zahn = B_gap * tau_nut / (b_zahn * k_fe)`` vollstaendig heraus:

    B_zahn = B_gap / ((1 - slotWidthRatio) * k_fe)

Die **Nutzahl bewegt die Zahnflussdichte also nicht** -- nachgemessen liefern 24,
36, 48 und 60 Nuten alle 1,2500 T bei B_gap = 0,6 T --, waehrend
``slotWidthRatio`` von 0,35 auf 0,65 sie von 0,962 auf 1,786 T treibt. Wer gegen
die Saettigung auslegt, dreht an diesem Wert und nicht an der Nutzahl. Beim Joch
ist es umgekehrt: dort zaehlt die Hoehe, und die Nutzahl geht gar nicht ein.

Nicht enthalten und benannt: Nutstreuung, Zahnkopfstreuung, die dreidimensionale
Aufweitung an den Stirnseiten, die oertliche Ueberhoehung am Zahnfuss und die
Tatsache, dass der Zahn ueber seiner Hoehe verschieden breit ist -- gerechnet
wird mit der Breite an der Bohrung, also der ENGSTEN Stelle (konservativ).
"""

from __future__ import annotations

import math

# Stapelfaktor: Anteil Eisen am Blechpaketvolumen. Fuer 0,35-mm-Elektroblech
# liegt er bei 0,95...0,97; die Tabelle in `ema_pipeline.LAMINATES` fuehrt ihn
# nicht, deshalb EINE benannte Annahme statt einer versteckten Zahl. Die
# Wirkung ist klein (<= 2 % auf B) und die Richtung bekannt: ohne ihn faellt B
# zu niedrig aus, die Rechnung waere also nicht konservativ.
STAPELFAKTOR = 0.96

# Ab wo gewarnt wird. 0,95 statt 1,00, weil die BH-Kurve kein Knick ist: bei
# 95 % der Saettigungsflussdichte steigt die noetige Feldstaerke bereits stark
# an, und die Eisenverluste mit ihr.
WARNSCHWELLE = 0.95


def _blech_bsat(blech) -> tuple:
    """(B_sat [T], Bezeichnung) -- aus dem Werkstoff-DICT oder seinem Schluessel.

    Beide Wege, weil beide Aufrufer da sind: ``ema_leistung`` hat den Schluessel
    aus dem Payload, der gemeinsame Bewerter hat das aufgeloeste Dict aus
    ``ema_optimize._materials`` bereits in der Hand. Es waere die Sorte Fehler,
    die still danebengeht, den Schluessel aus dem Dict zurueckraten zu wollen --
    ``LAMINATES``-Eintraege fuehren keinen, und ein Rueckfall auf M270 haette
    jedem anderen Blech dessen Grenze untergeschoben.
    """
    if isinstance(blech, dict):
        return (float(blech.get("B_sat_T") or 1.7),
                str(blech.get("label") or "unbekanntes Blech"))
    try:
        from ema_pipeline import LAMINATES
    except Exception:                                            # noqa: BLE001
        return 1.7, str(blech)
    m = LAMINATES.get(str(blech)) or LAMINATES.get("m270_35a")
    if m is None:
        return 1.7, str(blech)
    return float(m.get("B_sat_T") or 1.7), str(m.get("label") or blech)


def gap_resultierend(geom: dict, b_gap_magnet: float,
                     i_q: float = 0.0, i_d: float = 0.0) -> dict:
    """Das resultierende Luftspaltfeld aus Magnet UND Ankerrueckwirkung.

    Beide Anteile kommen aus den beiden analytischen Ankern, an denen auch der
    FDM geeicht wird (``_analytical_Bgap`` fuer die Magnete,
    ``_analytical_Barm`` fuer den Stator) -- keine dritte Formel.

    Zusammengesetzt wird **vektoriell** und nicht durch Addition: bei MTPA ist
    ``i_d`` negativ, der d-Anteil der Ankerrueckwirkung schwaecht den Magneten
    also, waehrend der q-Anteil quer dazu steht. Wer beide Betraege addiert,
    ueberschaetzt den Zahn gerade dort, wo die Feldschwaechung arbeitet.
    """
    import ema_analysis

    i_pk = math.hypot(float(i_q), float(i_d))
    b_arm = ema_analysis._analytical_Barm(geom, i_pk) if i_pk > 1e-6 else 0.0
    if i_pk > 1e-6:
        b_d = float(b_gap_magnet) + b_arm * (float(i_d) / i_pk)
        b_q = b_arm * (float(i_q) / i_pk)
    else:
        b_d, b_q = float(b_gap_magnet), 0.0
    return {"B_gap_T": math.hypot(b_d, b_q), "B_d_T": b_d, "B_q_T": b_q,
            "B_arm_T": b_arm, "i_pk_A": i_pk}


def eisenwege(geom: dict, axial_mm: float, b_gap_t: float,
              blech="m270_35a") -> dict:
    """Was Zahn und Joch bei diesem Luftspaltfeld tragen muessen.

    ``b_gap_t`` ist die **resultierende** Luftspalt-Grundwelle (s.
    ``gap_resultierend``), nicht das Leerlauffeld -- sonst kennt die Rechnung
    die Ankerrueckwirkung nicht, und die ist unter Last der groessere Teil.
    """
    import ema_wicklung

    ng = ema_wicklung.nutgeometrie(geom)
    p = max(int(geom.get("p") or 1), 1)
    L = max(float(axial_mm) / 1000.0, 1e-6)
    r_si = ng["r_si_m"]
    r_so = ng["r_so_m"]
    b_zahn = max(ng["zahn_breite_m"], 1e-9)
    h_joch = max(r_so - (r_si + ng["nut_tiefe_m"]), 1e-9)
    tau_nut = 2.0 * math.pi * r_si / max(ng["n_slots"], 1)
    d_gap = 2.0 * r_si
    b = abs(float(b_gap_t))

    phi_pol = b * d_gap * L / p                       # Wb, (2/pi)*B*tau_pol*L
    b_zahn_t = b * tau_nut / (b_zahn * STAPELFAKTOR)
    b_joch_t = phi_pol / (2.0 * h_joch * L * STAPELFAKTOR)

    b_sat, label = _blech_bsat(blech)
    schlimmer = "zahn" if b_zahn_t >= b_joch_t else "joch"
    wert = max(b_zahn_t, b_joch_t)
    return {
        "B_zahn_T": round(b_zahn_t, 3),
        "B_joch_T": round(b_joch_t, 3),
        "B_gap_T": round(b, 4),
        "phi_pol_mWb": round(phi_pol * 1000.0, 4),
        "zahn_breite_mm": round(b_zahn * 1000.0, 2),
        "joch_hoehe_mm": round(h_joch * 1000.0, 2),
        "nutteilung_mm": round(tau_nut * 1000.0, 2),
        "B_sat_T": b_sat, "blech": label,
        "wert_T": round(wert, 3), "engstelle": schlimmer,
        "ausnutzung": round(wert / b_sat, 3),
        "gesaettigt": bool(wert > b_sat),
        "warnt": bool(wert > WARNSCHWELLE * b_sat),
        "stapelfaktor": STAPELFAKTOR,
    }


def bewerten(geom: dict, axial_mm: float, b_gap_magnet: float,
             i_q: float = 0.0, i_d: float = 0.0,
             blech="m270_35a") -> dict:
    """Ein Aufruf vom Betriebspunkt zur Saettigungsaussage."""
    g = gap_resultierend(geom, b_gap_magnet, i_q, i_d)
    e = eisenwege(geom, axial_mm, g["B_gap_T"], blech)
    return {**e, "anker": g}


def als_text(e: dict) -> str:
    """Und immer dazu, was die Zahl bedeutet -- und was sie nicht bedeutet."""
    z = []
    a = z.append
    a(f"Eisenwege (Flusserhaltung, aufloesungsunabhaengig aus B_gap):")
    a(f"  Luftspalt resultierend  {e['B_gap_T']:.3f} T   "
      f"(Polfluss {e['phi_pol_mWb']:.3f} mWb)")
    a(f"  Zahn  {e['B_zahn_T']:6.3f} T  bei {e['zahn_breite_mm']:.2f} mm Breite "
      f"(Nutteilung {e['nutteilung_mm']:.2f} mm)")
    a(f"  Joch  {e['B_joch_T']:6.3f} T  bei {e['joch_hoehe_mm']:.2f} mm Hoehe")
    a(f"  Grenze {e['B_sat_T']:.2f} T ({e['blech']}), Stapelfaktor "
      f"{e['stapelfaktor']:.2f}")
    a(f"  -> Engstelle {e['engstelle'].upper()}, Ausnutzung "
      f"{e['ausnutzung'] * 100:.0f} %")
    if e["gesaettigt"]:
        a("")
        a("  ⚠ Das lineare Modell verlangt vom Eisen mehr, als es hergibt.")
        a("    Das ist KEINE Wand, an der die Maschine stehenbleibt -- sie laeuft")
        a("    weiter, nur liefert sie weniger Moment als hier gerechnet. Kt,")
        a("    Moment und Leistung sind ab diesem Punkt zu optimistisch.")
    elif e["warnt"]:
        a(f"  ⚠ ueber {WARNSCHWELLE * 100:.0f} % der Saettigung -- die noetige "
          f"Feldstaerke und die Eisenverluste steigen dort schon stark.")
    return "\n".join(z)


# ── Bilder: analog zum Magnetfeld, aber ehrlich anders ───────────────────────
#
# Das Magnetfeldbild kommt aus einem geloesten Feld. Diese beiden hier NICHT --
# sie kommen aus der Flusserhaltung, weil |B| im Statoreisen bei den benutzten
# Aufloesungen nicht konvergiert (56...73 % Streuung ueber N = 300...800, s.
# BEFUNDE.md). Ein Bild, das wie ein Feldbild aussieht und keines ist, waere die
# schlimmste Variante; deshalb steht die Herkunft IM Bild und nicht in einer
# Bildunterschrift, die beim Kopieren verlorengeht.

_FARBEN = ((0.00, "#2e7d32"), (0.70, "#f9a825"), (1.00, "#e64a19"),
           (1.40, "#7b1fa2"))


def _farbe(q: float) -> str:
    """Ausnutzung -> Farbe. Ueber 1,0 wird es violett: das ist kein Betriebs-
    zustand mehr, sondern die Aussage, dass das Modell hier zu optimistisch ist."""
    q = max(0.0, float(q))
    for i in range(len(_FARBEN) - 1):
        q0, c0 = _FARBEN[i]
        q1, c1 = _FARBEN[i + 1]
        if q <= q1:
            t = (q - q0) / max(q1 - q0, 1e-9)
            a = tuple(int(c0[1 + 2 * j:3 + 2 * j], 16) for j in range(3))
            b = tuple(int(c1[1 + 2 * j:3 + 2 * j], 16) for j in range(3))
            return "#%02x%02x%02x" % tuple(
                int(round(a[j] + t * (b[j] - a[j]))) for j in range(3))
    return _FARBEN[-1][1]


def bild(geom: dict, axial_mm: float, b_gap_magnet: float, pfad: str,
         i_q: float = 0.0, i_d: float = 0.0, blech="m270_35a",
         dpi: int = 130) -> str:
    """Der Querschnitt, Zahn und Joch nach ihrer AUSNUTZUNG eingefaerbt.

    Gezeichnet wird die Maschine ueber ``ema_pipeline.render_cross_section`` --
    dieselbe Funktion, aus der das CAD-Schnittbild und der Bilddatensatz kommen,
    also keine zweite Zeichnung, die auseinanderlaufen koennte. Darueber liegen
    zwei halbdurchsichtige Ringe: das Zahnband (Bohrung bis Nutgrund) und das
    Joch (Nutgrund bis Aussenrand).

    Die Farbe ist die Ausnutzung, nicht |B| -- gruen bis gelb bis rot bis
    violett, und violett heisst ausdruecklich *ueber* der Blechgrenze, also
    "hier ist die Rechnung zu optimistisch" und nicht "hier ist es heiss".
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge
    import ema_pipeline
    import ema_wicklung

    e = bewerten(geom, axial_mm, b_gap_magnet, i_q, i_d, blech)
    ng = ema_wicklung.nutgeometrie(geom)
    r_si = ng["r_si_m"] * 1000.0
    r_so = ng["r_so_m"] * 1000.0
    r_nut = r_si + ng["nut_tiefe_m"] * 1000.0

    fig, ax = plt.subplots(figsize=(7.4, 7.4))
    ema_pipeline.render_cross_section(geom, ax, beschriftung=False)
    # Zahn und Joch bekommen ihre Beschriftung an VERSCHIEDENEN Winkeln (oben
    # und unten). Beide auf die Senkrechte gesetzt lagen sie uebereinander und
    # verdeckten einander -- gemessen am ersten erzeugten Bild.
    for r0, r1, q, name, wert, winkel in (
            (r_si, r_nut, e["B_zahn_T"] / e["B_sat_T"], "Zahn", e["B_zahn_T"], 90.0),
            (r_nut, r_so, e["B_joch_T"] / e["B_sat_T"], "Joch", e["B_joch_T"], -90.0)):
        ax.add_patch(Wedge((0, 0), r1, 0, 360, width=r1 - r0,
                           facecolor=_farbe(q), alpha=0.40, edgecolor="none",
                           zorder=6))
        rm = (r0 + r1) / 2.0
        ax.text(rm * math.cos(math.radians(winkel)),
                rm * math.sin(math.radians(winkel)),
                f"{name}  {wert:.2f} T\n{q * 100:.0f} % von {e['B_sat_T']:.2f} T",
                ha="center", va="center", zorder=7, fontsize=10,
                fontweight="bold", color="#111",
                bbox=dict(boxstyle="round,pad=0.35", fc="white", alpha=0.88,
                          ec="none"))
    ax.set_title(f"Eisenausnutzung — Engstelle {e['engstelle'].upper()}, "
                 f"{e['ausnutzung'] * 100:.0f} %\n{e['blech']}", fontsize=10.5)
    # Die Herkunft gehoert INS Bild: es sieht aus wie ein Feldbild und ist keines.
    fig.text(0.5, 0.02,
             "aus der FLUSSERHALTUNG (B_gap -> Zahn/Joch), nicht aus einem "
             "geloesten Feld:\n|B| im Statoreisen konvergiert bei diesen "
             "Aufloesungen nicht (s. BEFUNDE.md)",
             ha="center", va="bottom", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.075, 1, 1))
    fig.savefig(pfad, dpi=dpi)
    plt.close(fig)
    return pfad


def diagramm(geom: dict, axial_mm: float, b_gap_magnet: float, pfad: str,
             rpm: float, t_bis: float = 0.0, blech="m270_35a",
             punkte: int = 60, dpi: int = 130) -> str:
    """B_Zahn und B_Joch ueber dem Moment -- mit der Blechgrenze als Linie.

    Die Frage, die dieses Bild beantwortet, ist die eigentliche: **ab welchem
    Moment laeuft die Auslegung ins Eisen?** Eine einzelne Zahl sagt das nicht,
    und die Kurve zeigt zugleich, wie steil es dort wird.

    Das Joch laeuft mit, obwohl es meist weit darunter bleibt -- gerade DAS ist
    die Auskunft: ein Joch bei 25 %, waehrend der Zahn reisst, ist verschenktes
    Material, und man sieht es hier auf einen Blick.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import ema_analysis

    if t_bis <= 0:
        t_bis = max(10.0, _knie_suchen(geom, axial_mm, b_gap_magnet, rpm,
                                       blech) * 1.6)
    ts = np.linspace(0.0, float(t_bis), int(punkte))
    zahn, joch = [], []
    for t in ts:
        iq = id_ = 0.0
        if t > 1e-9 and rpm > 0:
            iq, id_ = ema_analysis.estimate_dq_currents(
                geom, float(rpm), float(t), b_gap_t=b_gap_magnet, rpm_base=rpm)
        e = bewerten(geom, axial_mm, b_gap_magnet, iq, id_, blech)
        zahn.append(e["B_zahn_T"])
        joch.append(e["B_joch_T"])
    b_sat, label = _blech_bsat(blech)

    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.plot(ts, zahn, lw=2.2, color="#c62828", label="Zahn")
    ax.plot(ts, joch, lw=2.2, color="#1565c0", label="Joch")
    ax.axhline(b_sat, ls="--", lw=1.6, color="#37474f",
               label=f"Blechgrenze {b_sat:.2f} T ({label})")
    # Der Schnittpunkt ist die Antwort -- also wird er markiert und beziffert.
    z = np.asarray(zahn)
    ueber = np.where(z >= b_sat)[0]
    if len(ueber):
        t_knie = float(ts[ueber[0]])
        ax.axvline(t_knie, ls=":", lw=1.4, color="#c62828")
        # Nach RECHTS UNTEN: oben links sitzt die Legende, und der erste
        # Entwurf schrieb die Beschriftung mitten hinein.
        ax.annotate(f"ab {t_knie:.0f} Nm laeuft\nder Zahn ins Eisen",
                    xy=(t_knie, b_sat), xytext=(t_knie * 1.12, b_sat * 0.45),
                    fontsize=9, color="#c62828",
                    arrowprops=dict(arrowstyle="->", color="#c62828", lw=1.2))
    ax.set_xlabel(f"Moment [Nm]  (bei {rpm:.0f} 1/min)")
    ax.set_ylabel("Flussdichte im Eisen [T]")
    ax.set_title("Wo die Auslegung ins Eisen laeuft")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylim(0, max(b_sat * 1.6, float(z.max()) * 1.05))
    fig.text(0.5, 0.015,
             "Flusserhaltung aus B_gap (Magnet + Ankerrueckwirkung, vektoriell), "
             "kein geloestes Feld.\nNut- und Zahnkopfstreuung nicht enthalten — "
             "die Rechnung ist damit konservativ.",
             ha="center", va="bottom", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.085, 1, 1))
    fig.savefig(pfad, dpi=dpi)
    plt.close(fig)
    return pfad


def _knie_suchen(geom, axial_mm, b_gap_magnet, rpm, blech, hoechstens=2000.0):
    """Das Moment, bei dem der Zahn die Blechgrenze erreicht -- durch Halbieren.

    Nur fuer die Achsenskalierung des Diagramms: ohne das zeigt die Kurve
    entweder nur den flachen Anfang oder laeuft weit ins Sinnlose.
    """
    import ema_analysis
    b_sat, _ = _blech_bsat(blech)

    def zahn(t):
        iq = id_ = 0.0
        if t > 1e-9 and rpm > 0:
            iq, id_ = ema_analysis.estimate_dq_currents(
                geom, float(rpm), float(t), b_gap_t=b_gap_magnet, rpm_base=rpm)
        return bewerten(geom, axial_mm, b_gap_magnet, iq, id_, blech)["B_zahn_T"]

    lo, hi = 0.0, 1.0
    while hi < hoechstens and zahn(hi) < b_sat:
        lo, hi = hi, hi * 2.0
    if hi >= hoechstens:
        return hoechstens * 0.5
    for _ in range(24):
        m = 0.5 * (lo + hi)
        if zahn(m) < b_sat:
            lo = m
        else:
            hi = m
    return hi


def bilder(geom: dict, axial_mm: float, b_gap_magnet: float, ziel_dir: str,
           rpm: float = 0.0, i_q: float = 0.0, i_d: float = 0.0,
           blech="m270_35a") -> list:
    """Beide Bilder nach ``<projekt>/charts`` -- wie ``ema_feldbild``.

    Der Ablageort ist nicht beliebig: die rechte Spalte beider Agentenkoepfe
    findet neue Bilder dort ueber die Aenderungszeit. Wer sie woanders hinlegt,
    baut einen zweiten Meldeweg.
    """
    import os
    os.makedirs(ziel_dir, exist_ok=True)
    aus = []
    p1 = os.path.join(ziel_dir, "saettigung_eisen.png")
    aus.append(bild(geom, axial_mm, b_gap_magnet, p1, i_q, i_d, blech))
    if rpm > 0:
        p2 = os.path.join(ziel_dir, "saettigung_kennlinie.png")
        aus.append(diagramm(geom, axial_mm, b_gap_magnet, p2, rpm, blech=blech))
    return aus
