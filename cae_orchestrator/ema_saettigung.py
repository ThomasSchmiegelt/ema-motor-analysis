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
