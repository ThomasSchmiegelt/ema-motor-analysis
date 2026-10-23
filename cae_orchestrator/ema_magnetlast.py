"""Die Fliehkraft der MAGNETE -- die Last, die der Rotor-FEM gefehlt hat.

Was fehlte und warum es nicht auffiel
--------------------------------------

Die Struktur-FEM vernetzt ausdruecklich **nur das Rotoreisen**
(``ema_freecad.build_rotor_fem_script``: „the magnets must NOT be part of the
centrifugal FEM") und laedt es mit ``*DLOAD CENTRIF`` -- einer Volumenkraft, die
ueber die Dichte des BLECHS wirkt. Die Magnettaschen sind in diesem Modell Luft.
Damit rechnete die Kette die Fliehkraft des Eisens und **keine einzige Newton**
der Magnete, obwohl der Magnet das schwerste Einzelteil im Laeufer ist und sein
ganzes Gewicht an genau der duennsten Stelle haengt, die es dort gibt: dem
Blechsteg zwischen Tasche und Luftspalt.

Unauffaellig blieb es, weil beide Vergleichswerte denselben Fehler teilen: die
analytische Ringspannung (``ema_rotorcheck._bore_hoop_mpa``) ist die eines
GLATTEN rotierenden Ringes, und der Kerbfaktor ``KT_POCKET = 1.5`` darueber ist
ein Zuschlag fuer die scharfe Taschenecke -- keiner fuer eine zusaetzliche Last.
Das Tor verglich also eine Spannung ohne Magnete mit einer Spannung ohne
Magnete, und die FEM bestaetigte sie.

Gemessen am frischen Payload (V-Form, 2p = 6, Laeufer Ø 188,6 mm, L = 80 mm,
Magnet 42,2 x 6,0 mm, Schwerpunkt bei r = 72,9 mm, NdFeB 7500 kg/m³):

    Drehzahl     Kraft je Magnet    je Pol      alle Pole
     12.000 1/min      17,5 kN      35,0 kN      210,1 kN
     20.000 1/min      48,6 kN      97,3 kN      583,7 kN

Der Steg, an dem das haengt, ist ``ema_topology.BRIDGE_MM`` = **1,3 mm** breit.
Zwei solche Stege je Pol tragen bei L = 80 mm zusammen 208 mm²; 35 kN darauf
sind **168 MPa** -- neben einer Ringspannung von 93,6 MPa bei derselben
Drehzahl. Die vergessene Last ist also nicht ein Zuschlag, sondern der
**groessere** Posten an der bindenden Stelle.

Wie die Last ins Modell kommt
-----------------------------

Nicht als Koerper: die Magnete mitzuvernetzen hiesse Kontakt zu rechnen (sie
sind geklebt, nicht verschweisst, und Klebstoff traegt keinen Zug), und das ist
ein anderes Problem als das hier. Gerechnet wird, was die Fliehkraft des
Magneten dem Eisen ANTUT: eine Flaechenlast auf die Taschenwand, gegen die er
gedrueckt wird. Das ist die klassische Bauform dieser Rechnung und sie braucht
keinen Kontakt.

Drei Entscheidungen darin, jede mit ihrem Grund:

1. **Welche Wand? BEIDE, und die Aufteilung ist exakt.** Der erste Entwurf
   suchte die Wand, deren Aussennormale am meisten in Richtung der Fliehkraft
   zeigt, und trug den ganzen Vektor dort auf. Gemessen am V-Schenkel des
   frischen Payloads ist das die **Endkappe** (Laengsachse zur Fliehkraft
   ``u·e_r = 0,747``) und nicht die lange Flanke (``v·e_r = -0,664``) -- beide
   Anteile sind erheblich, und einer von ihnen waere verschwunden.

   Ein Magnet in einer Langlochtasche liegt an zwei zueinander senkrechten
   Flaechen an, und ``u``/``v`` sind eine Orthonormalbasis: zerlegt man die
   Fliehkraft in ihre Komponenten entlang beider, ergibt die Summe der zwei
   Wandreaktionen **genau** den Kraftvektor wieder, und jede Wand traegt nur
   ihre Normalkomponente. Das ist keine Naeherung mehr, sondern die
   Gleichgewichtsbedingung eines anliegenden Koerpers -- und sie erledigt
   zugleich die Bauformfrage: beim **Speichenmagneten** (Laengsachse radial)
   faellt fast alles auf die Kappe am Rotorrand, bei einem flachen Balken fast
   alles auf die Flanke. Ohne Fallunterscheidung.

2. **Was bleibt angenommen.** Dass die TASCHE traegt und nicht die Klebung
   (unsicherere und damit richtige Richtung), und dass die Last auf jeder Wand
   gleichmaessig verteilt ist -- in Wirklichkeit konzentriert sie sich dort, wo
   die Tasche am steifsten abgestuetzt ist. Beides steht in ``grenzen()``.

3. **Gleichanteilig auf die Wandknoten.** Keine Flaechenlast ueber
   Elementflaechen, sondern Knotenkraefte auf den Knoten der Wand. Der Grund ist
   die Wiederverwendbarkeit: eine Knotenkraft laesst sich in **jedem** der vier
   Loeser dieser Werkzeugkette in einer Zeile ausdruecken (CalculiX ``*CLOAD``
   auf ein NSET, Z88 ``Art 1``, Code Aster ``FORCE_NODALE`` auf eine
   ``GROUP_NO``), eine Druckrandbedingung dagegen braucht in jedem von ihnen
   Elementflaechen, die aus verschiedenen Netzschreibern kommen. Weil alle
   Knoten einer Wand denselben Anteil bekommen, ist die Last eine Zeile und
   nicht eine Liste -- und die Summe ist in allen vier Loesern dieselbe.

Was NICHT drin ist -- ausgesprochen
-----------------------------------

* **Kaefigstaebe, Ankerwicklung, Erregerspulen.** Dieselbe Luecke, anderer
  Koerper. Der Kaefigsteg hat seine eigene Pruefung (``ema_asm.steg_check``),
  der Schenkelpol seine (``ema_schenkelpol.befestigung``) -- beide rechnen die
  Masse, die auf ihnen haengt, bereits mit. Hier geht es um die Magnettasche.
* **Klebung und Reibung.** Der Magnet wird als loses Teil behandelt, das
  anliegt. Eine tragende Klebung wuerde die Last verteilen; sie zu unterstellen
  waere die unsichere Richtung.
* **Schrumpfsitz und Waermedehnung.** Der Pressverband bringt eine
  Ringvorspannung mit, die ``ema_pipeline.connection_assessment`` analytisch
  rechnet und die FEM nicht sieht. Steht in ``BEFUNDE.md``.

Der Rechenkern steht EINMAL
---------------------------

``KERN`` ist der Quelltext der Knotenauswahl und wird mit ``exec`` in dieses
Modul geladen **und** woertlich in das FreeCAD-Skript geschrieben. FreeCAD laeuft
in einem fremden Prozess und kann nichts importieren (derselbe Fall wie
``ema_purge._STANDALONE`` und ``ema_wicklung.hairpin_radien``) -- aber anders als
dort gibt es hier keine zweite Abschrift, die auseinanderlaufen koennte: es ist
dieselbe Zeichenkette.
"""

from __future__ import annotations

import math

from ema_topology import leg_center, magnet_legs

# NdFeB-Dichte als Rueckfall, wenn die Werkstofftabelle keine fuehrt.
# Literaturwert gesinterter N35-N52 (7,4-7,6 g/cm³); derselbe Wert, der in
# ``ema_screen.MAG_DICHTE_KG_M3`` stand, als er dort noch die einzige Quelle war.
DICHTE_VORGABE_KG_M3 = 7500.0

# Wie weit ein Netzknoten von der gerechneten Wandflaeche abweichen darf [mm].
# Die Knoten liegen geometrisch AUF der Flaeche; die Toleranz faengt nur die
# Rundung der Booleschen Operationen (gemessen < 1e-3 mm) und eine gekruemmte
# Kappe, die das Netz als Polygonzug sieht.
TOLERANZ_MM = 0.12

# Wie viele Stege je Pol die Magnete tragen -- fuer den analytischen RICHTWERT
# (nicht fuer die FEM, die das selbst herausrechnet). Zwei ist die Zahl der
# Stellen, an denen die Polkappe am uebrigen Blech haengt: links und rechts der
# Tasche, zum Rotorrand hin. Der Mittelsteg eines V zaehlt NICHT mit -- ihn
# mitzuzaehlen waere die unsichere Richtung.
STEGE_JE_POL = 2


# ── Der Rechenkern: Knoten auf einer Taschenwand ─────────────────────────────
#
# Steht als Quelltext, weil er an zwei Stellen laufen muss (hier und im
# FreeCAD-Prozess) und eine Abschrift die Stelle waere, an der die beiden
# Rechensaetze auseinanderlaufen, ohne dass es jemand merkt.

KERN = '''
def _ml_wandknoten(knoten, wand, tol):
    """IDs der Netzknoten, die auf EINER Taschenwand liegen.

    knoten: Abbildung id -> (x, y, z) in Millimetern, globales Koordinatensystem.
    wand:   ein Eintrag aus ema_magnetlast.waende().
    Die z-Richtung wird nicht geprueft: die Tasche geht durch das ganze Paket.
    """
    px = wand["px"]; py = wand["py"]
    nx = wand["nx"]; ny = wand["ny"]
    treffer = []
    if wand["art"] == "flanke":
        tx = wand["tx"]; ty = wand["ty"]
        halb = wand["halb"] + tol
        for i in knoten:
            x, y = knoten[i][0], knoten[i][1]
            dx = x - px; dy = y - py
            if abs(dx * nx + dy * ny) > tol:
                continue
            if abs(dx * tx + dy * ty) > halb:
                continue
            treffer.append(i)
    else:
        r = wand["radius"]
        for i in knoten:
            x, y = knoten[i][0], knoten[i][1]
            dx = x - px; dy = y - py
            if dx * nx + dy * ny < -tol:
                continue
            if abs((dx * dx + dy * dy) ** 0.5 - r) > tol:
                continue
            treffer.append(i)
    return treffer


def _ml_knotenkraft(wand, anzahl):
    """Gleichanteilige Knotenkraft (fx, fy) [N] fuer eine Wand mit `anzahl` Knoten."""
    if anzahl <= 0:
        return (0.0, 0.0)
    return (wand["fx"] / float(anzahl), wand["fy"] / float(anzahl))
'''

exec(KERN, globals())      # noqa: S102 — EINE Quelle, siehe Modulkopf


# ── Dichte: eine Quelle, je Werkstoff ────────────────────────────────────────

def dichte(magnet_code: str | None = None) -> float:
    """Magnetdichte [kg/m³] zum Werkstoffschluessel der ``MAGNETS``-Tabelle.

    Sie stand bis zum 22.10.2026 an ZWEI Stellen als Konstante -- 7600 in
    ``ema_screen`` und 7500 in ``ema_thermal`` -- und in der Werkstofftabelle
    gar nicht. Damit war **Ferrit genauso schwer wie NdFeB** (gemessen: dieselbe
    Magnetmasse und derselbe Preis fuer Br 1,40 wie fuer Br 0,40 T), obwohl
    Ferrit rund 35 % leichter ist; und genau diese Masse haengt hier am Steg.

    ``ema_pipeline`` wird erst beim Aufruf geholt: dieses Modul wird von
    ``ema_rotorcheck``-Nachbarn benutzt, die ``ema_pipeline`` nicht kennen
    duerfen, ohne einen Importzirkel zu bauen.
    """
    if not magnet_code:
        return DICHTE_VORGABE_KG_M3
    try:
        from ema_pipeline import MAGNETS
    except Exception:                                    # noqa: BLE001
        return DICHTE_VORGABE_KG_M3
    m = MAGNETS.get(str(magnet_code))
    if not m:
        return DICHTE_VORGABE_KG_M3
    return float(m.get("density") or DICHTE_VORGABE_KG_M3)


def klebespalt_mm(geom: dict) -> float:
    """Klebespalt je Seite [mm] -- dieselbe Klemme wie ``ema_freecad`` sie zeichnet."""
    return max(0.05, min(0.3, float(geom.get("magGapMm", 0.1))))


# ── Die Waende ───────────────────────────────────────────────────────────────

def waende(geom: dict, axial_mm: float, rpm: float,
           magnet_code: str | None = None,
           rho_mag: float | None = None,
           anteil_min: float = 0.02) -> list[dict]:
    """Je eingelassener Magnet die ZWEI Taschenwaende, an denen er anliegt.

    Rueckgabe je Eintrag (alles in mm / N, globales Koordinatensystem):

    ``pol``/``leg``      welcher Magnet
    ``art``              ``flanke`` (ebene Wand) oder ``kappe`` (Halbzylinder)
    ``px``/``py``        Punkt ON der Wand: Wandmitte bzw. Kappenachse
    ``nx``/``ny``        Aussennormale der Wand (Einheitsvektor)
    ``tx``/``ty``        Tangente in der Wandebene (nur ``flanke``)
    ``halb``             halbe Wandbreite entlang der Tangente (nur ``flanke``)
    ``radius``           Kappenradius (nur ``kappe``)
    ``m_kg``             Masse DES MAGNETEN (nicht der Wand)
    ``r_cg_mm``          Radius des Magnetschwerpunkts
    ``F_magnet_N``       Betrag seiner Fliehkraft
    ``anteil``           welcher Bruchteil davon auf DIESE Wand faellt
    ``F_N``              ``anteil * F_magnet_N`` -- die Last dieser Wand
    ``fx``/``fy``        ihr Vektor (entlang der Aussennormale)
    ``flaeche_mm2``      tragende Wandflaeche
    ``druck_MPa``        F_N / Flaeche -- die gleichwertige Flaechenlast

    Die beiden ``anteil`` eines Magneten sind ``|u·e_r|`` und ``|v·e_r|`` und
    ihre Vektorsumme ist **genau** die Fliehkraft (``u``/``v`` sind
    orthonormal) -- es geht also keine Last verloren und es kommt keine hinzu.
    Wird ein Anteil kleiner als ``anteil_min``, entfaellt die Wand: eine Wand
    mit einem Promille der Last kostet Knotenauswahl und sagt nichts.

    Die Taschenmasse folgt ``ema_freecad.build_full_motor_script`` Ziffer fuer
    Ziffer: Rechteck ``(L + 2g) x (T + 2g)``, Kappenradius ``T/2 + g``,
    Kappenmitte bei ``+-L/2`` (NICHT bei ``+-(L/2 + g)`` -- der Unterschied ist
    der Klebespalt, und wer ihn vertauscht, legt die Wand um 0,1 mm daneben).
    Belastet wird nur die Wand; der Magnet selbst wird nicht vernetzt.
    """
    rho = float(rho_mag) if rho_mag else dichte(magnet_code)
    gap = klebespalt_mm(geom)
    L_ax = float(axial_mm)
    poles = max(2, int(geom.get("p", 3)) * 2)
    omega = 2.0 * math.pi * float(rpm) / 60.0
    legs, _meta = magnet_legs(geom)

    aus: list[dict] = []
    for li, lg in enumerate(legs):
        if lg.placement != "interior" or lg.length <= 0 or lg.thickness <= 0:
            continue
        hl = lg.length / 2.0 + gap            # halbe Taschenlaenge (Rechteckteil)
        ht = lg.thickness / 2.0 + gap         # halbe Taschendicke = Kappenradius
        m_kg = lg.length * lg.thickness * L_ax * 1e-9 * rho
        cx0, cy0 = leg_center(lg)
        for pol in range(poles):
            pa = pol * 2.0 * math.pi / poles
            ca, sa = math.cos(pa), math.sin(pa)
            cx = cx0 * ca - cy0 * sa
            cy = cx0 * sa + cy0 * ca
            r_cg = math.hypot(cx, cy)
            if r_cg < 1e-6:
                continue
            erx, ery = cx / r_cg, cy / r_cg
            F = m_kg * omega * omega * (r_cg / 1000.0)         # N
            th = lg.tilt + pa                                   # Achse der Tasche
            ux, uy = math.cos(th), math.sin(th)                 # Laengsrichtung
            vx, vy = -uy, ux                                    # Dickenrichtung

            # Zerlegung in die Taschenbasis. Vorzeichen entscheidet, WELCHE der
            # beiden gegenueberliegenden Flaechen gedrueckt wird.
            du = ux * erx + uy * ery          # Anteil auf die Endkappe
            dv = vx * erx + vy * ery          # Anteil auf die Flanke
            su = 1.0 if du >= 0 else -1.0
            sv = 1.0 if dv >= 0 else -1.0
            gemein = {"pol": pol, "leg": li, "m_kg": m_kg, "r_cg_mm": r_cg,
                      "F_magnet_N": F}
            if abs(dv) >= anteil_min:
                w = {"art": "flanke",
                     "nx": sv * vx, "ny": sv * vy,
                     "px": cx + sv * ht * vx, "py": cy + sv * ht * vy,
                     "tx": ux, "ty": uy, "halb": hl, "radius": 0.0,
                     "flaeche_mm2": 2.0 * hl * L_ax, "anteil": abs(dv)}
                aus.append(_wand_fertig(w, gemein, F))
            if abs(du) >= anteil_min:
                w = {"art": "kappe",
                     "nx": su * ux, "ny": su * uy,
                     "px": cx + su * (lg.length / 2.0) * ux,
                     "py": cy + su * (lg.length / 2.0) * uy,
                     "tx": 0.0, "ty": 0.0, "halb": 0.0, "radius": ht,
                     "flaeche_mm2": 2.0 * ht * L_ax, "anteil": abs(du)}
                aus.append(_wand_fertig(w, gemein, F))
    return aus


def _wand_fertig(w: dict, gemein: dict, F: float) -> dict:
    """Kraftvektor, Druck und die gemeinsamen Magnetangaben an eine Wand haengen."""
    f = F * w["anteil"]
    w.update(gemein)
    w.update({"F_N": f, "fx": f * w["nx"], "fy": f * w["ny"],
              "druck_MPa": (f / w["flaeche_mm2"]) if w["flaeche_mm2"] > 0 else 0.0})
    return w


def summe(wl: list[dict], poles: int | None = None) -> dict:
    """Kennzahlen ueber alle Waende -- was die Magnete dem Blech zumuten.

    Masse und Gesamtkraft zaehlen je MAGNET, nicht je Wand: ein Magnet traegt
    zwei Waende, und beide fuehren seine Masse mit. Ueber die Waende summiert
    kaeme die doppelte Magnetmasse heraus -- eine Zahl, die man einem
    Ergebnisblock nicht ansieht.
    """
    if not wl:
        return {"n_waende": 0, "n_magnete": 0, "magnet_kg": 0.0,
                "kraft_gesamt_kN": 0.0, "kraft_je_pol_kN": 0.0,
                "kraft_je_magnet_kN": 0.0, "druck_max_MPa": 0.0, "arten": []}
    pole = poles or (max(w["pol"] for w in wl) + 1)
    je_magnet = {(w["pol"], w["leg"]): w for w in wl}      # einer je Magnet genuegt
    f_ges = sum(w["F_magnet_N"] for w in je_magnet.values())
    return {
        "n_waende": len(wl),
        "n_magnete": len(je_magnet),
        "magnet_kg": round(sum(w["m_kg"] for w in je_magnet.values()), 4),
        "kraft_gesamt_kN": round(f_ges / 1e3, 3),
        "kraft_je_pol_kN": round(f_ges / 1e3 / max(1, pole), 3),
        "kraft_je_magnet_kN": round(max(w["F_magnet_N"]
                                        for w in je_magnet.values()) / 1e3, 3),
        "druck_max_MPa": round(max(w["druck_MPa"] for w in wl), 2),
        "arten": sorted({w["art"] for w in wl}),
    }


def grenzen() -> list[str]:
    """Was diese Last NICHT ist -- haengt an jedes Ergebnis, das sie benutzt."""
    return [
        "Die Magnete werden NICHT vernetzt: aufgetragen wird die Reaktion ihrer "
        "Fliehkraft auf die Taschenwaende. Kein Kontakt, keine Klebung, keine "
        "Reibung -- der Magnet gilt als lose anliegendes Teil (die unsicherere "
        "und damit richtige Richtung).",
        "Auf jeder Wand ist die Last GLEICHMAESSIG verteilt. In Wirklichkeit "
        "konzentriert sie sich dort, wo die Tasche am steifsten abgestuetzt ist; "
        "die Spitzenspannung am Steg ist damit eher unterschaetzt.",
        "Die Kraft wird exakt in die Taschenbasis zerlegt (Summe = Fliehkraft), "
        "aber beide Reaktionen wirken gleichzeitig und voll -- ein Spiel in der "
        "Tasche, das eine Flaeche entlasten wuerde, ist nicht modelliert.",
        "Kaefigstaebe, Ankerwicklung und Erregerspulen sind hier NICHT enthalten "
        "(eigene Pruefungen: ema_asm.steg_check, ema_schenkelpol.befestigung).",
        "Der Schrumpfsitz der Welle bringt eine Ringvorspannung mit, die die FEM "
        "nicht sieht (ema_pipeline.connection_assessment rechnet sie analytisch).",
    ]


# ── Der analytische Richtwert: was der Steg davon sieht ──────────────────────

def stegspannung(geom: dict, mat: dict, rpm: float, axial_mm: float,
                 magnet_code: str | None = None,
                 rho_mag: float | None = None,
                 sf_ziel: float = 1.3) -> dict:
    """Mittlere Zugspannung im Blechsteg aus der Magnetfliehkraft -- ein RICHTWERT.

    Gerechnet wird ``sigma = F_pol / (n_stege * s_rand * L_ax)`` mit dem
    **gemessenen** Randsteg (Abstand der Tasche zum Rotorrand aus
    ``ema_rotorcheck``), nicht mit dem nominellen ``BRIDGE_MM``: gezeichnet ist
    nicht immer, was vorgegeben war.

    Drei Dinge, die diese Zahl NICHT ist, und sie stehen auch im Ergebnis:

    * **Keine Spitzenspannung.** Mittelwert ueber den Stegquerschnitt; an der
      Taschenecke liegt sie hoeher. Dafuer gibt es die FEM, und die ist bindend.
    * **Keine Ueberlagerung.** Die Ringspannung des rotierenden Blechs
      (``rotor_stress_check``) kommt hinzu; beide am selben Ort zu addieren
      waere nur dann richtig, wenn sie dieselbe Richtung haben -- am Steg zum
      Luftspalt tun sie das weitgehend, deshalb steht die Summe als
      ``sigma_ueberlagert_MPa`` daneben, ausdruecklich als obere Schaetzung.
    * **Kein Mittelsteg.** Ein V traegt zusaetzlich ueber das Eisen zwischen
      seinen Schenkeln; das zu beruecksichtigen waere die unsichere Richtung.

    Beim **Aussenlaeufer** gibt es die Last nicht: dort drueckt die Fliehkraft
    die Magnete gegen den Ring (``ema_radien.magnethaltung``), und der Steg
    traegt sie nicht. Dann kommt ``steg_traegt = False`` heraus und keine Zahl.
    """
    import ema_radien
    from ema_rotorcheck import _magnettaschen

    haltung = ema_radien.magnethaltung(geom)
    wl = waende(geom, axial_mm, rpm, magnet_code=magnet_code, rho_mag=rho_mag)
    s = summe(wl, poles=max(2, int(geom.get("p", 3)) * 2))
    if not wl:
        return {"steg_traegt": bool(haltung["steg_traegt_magnete"]),
                "grund": "keine eingelassenen Magnete in dieser Auslegung",
                **s}
    if not haltung["steg_traegt_magnete"]:
        return {"steg_traegt": False, "grund": haltung["aussage"], **s}

    r = ema_radien.radien(geom)
    R_rot = float(r["r_rotor_gap_mm"])
    pockets, _surf = _magnettaschen(geom)
    s_rand = None
    for _base, P in pockets:
        _rmin, rmax = P.radius_bounds()
        d = R_rot - rmax
        s_rand = d if s_rand is None else min(s_rand, d)
    if s_rand is None or s_rand <= 0.0:
        return {"steg_traegt": True, "grund":
                f"gemessener Randsteg {s_rand if s_rand is None else round(s_rand, 3)} mm "
                f"-- die Tasche ist zum Luftspalt offen oder durchbrochen; eine "
                f"Stegspannung gibt es dann nicht, das Layouttor sagt warum",
                "s_rand_mm": s_rand, **s}

    pole = max(2, int(geom.get("p", 3)) * 2)
    # Je MAGNET einmal -- ueber die Waende summiert kaeme seine Kraft doppelt.
    f_pol = sum(w["F_magnet_N"]
                for w in {(w["pol"], w["leg"]): w for w in wl}.values()) / pole
    a_steg = STEGE_JE_POL * s_rand * float(axial_mm)
    sig = f_pol / a_steg
    sigy = float(mat.get("yield_mpa", 340.0))

    # Ringspannung derselben Drehzahl -- aus DER Quelle, die auch das Tor nimmt.
    sig_ring = None
    try:
        from ema_rotorcheck import rotor_stress_check
        sig_ring = float(rotor_stress_check(geom, mat, {"n_max": rpm})
                         ["sigma_bore_conservative_MPa"])
    except Exception:                                    # noqa: BLE001
        pass
    sig_sum = sig + sig_ring if sig_ring is not None else None

    return {
        "steg_traegt": True,
        "s_rand_mm": round(s_rand, 3),
        "n_stege_je_pol": STEGE_JE_POL,
        "flaeche_steg_mm2": round(a_steg, 1),
        "kraft_je_pol_N": round(f_pol, 1),
        "sigma_steg_MPa": round(sig, 1),
        "sigma_ring_MPa": round(sig_ring, 1) if sig_ring is not None else None,
        "sigma_ueberlagert_MPa": round(sig_sum, 1) if sig_sum is not None else None,
        "yield_mpa": sigy,
        "sf_steg": round(sigy / sig, 3) if sig > 0 else None,
        "sf_ueberlagert": (round(sigy / sig_sum, 3)
                           if sig_sum and sig_sum > 0 else None),
        "sf_ziel": sf_ziel,
        "ok": (sigy / sig_sum >= sf_ziel) if sig_sum and sig_sum > 0 else None,
        "annahme": (f"Mittelwert ueber {STEGE_JE_POL} Stege je Pol von je "
                    f"{round(s_rand, 3)} x {axial_mm:.0f} mm. RICHTWERT, keine "
                    f"Spitzenspannung -- bindend ist die FEM. Ueberlagerung mit "
                    f"der Ringspannung ist eine obere Schaetzung (gleiche "
                    f"Richtung am Steg angenommen). Der Mittelsteg eines V "
                    f"zaehlt nicht mit."),
        **s,
    }


# ── Knotenlasten fuer die Loeser ─────────────────────────────────────────────

def knotenlasten(knoten: dict, wl: list[dict],
                 tol: float = TOLERANZ_MM) -> tuple[dict, list[dict]]:
    """Wandliste + Netzknoten -> ``({knoten: (fx, fy, fz)}, bericht)``.

    ``bericht`` fuehrt je Wand, wie viele Knoten sie getroffen hat und welche
    Kraft davon wirklich aufgetragen wurde. Eine Wand mit **null** Knoten ist
    kein Rundungsfehler, sondern eine verlorene Last -- sie wird benannt, statt
    stillschweigend zu fehlen (sonst sieht ein Lauf mit halber Magnetlast aus
    wie einer mit voller).
    """
    lasten: dict[int, list[float]] = {}
    bericht: list[dict] = []
    for w in wl:
        ids = _ml_wandknoten(knoten, w, tol)              # noqa: F821 (aus KERN)
        fx, fy = _ml_knotenkraft(w, len(ids))             # noqa: F821
        for i in ids:
            v = lasten.setdefault(i, [0.0, 0.0, 0.0])
            v[0] += fx
            v[1] += fy
        bericht.append({"pol": w["pol"], "leg": w["leg"], "art": w["art"],
                        "n_knoten": len(ids),
                        "F_N": round(w["F_N"], 1),
                        "F_aufgetragen_N": round(w["F_N"] if ids else 0.0, 1)})
    return ({i: tuple(v) for i, v in lasten.items()}, bericht)


def fehlende_waende(bericht: list[dict]) -> list[dict]:
    """Die Waende ohne einen einzigen Knoten -- die verlorene Last."""
    return [b for b in bericht if b["n_knoten"] == 0]


def cload_zeilen(lasten: dict, start_nset: int = 1) -> list[str]:
    """CalculiX ``*CLOAD``-Zeilen aus Knotenlasten [N].

    Je Knoten bis zu zwei Zeilen (Richtung 1 und 2). Das ist ausdruecklich keine
    NSET-Form: nach dem Zusammenlegen mehrerer Waende kann ein Knoten eine
    beliebige Kraft tragen, und eine Gruppe mit gleichem Wert gibt es dann nicht
    mehr. Gemessen bleibt die Datei klein -- die Wandknoten sind ein Promille
    des Netzes.
    """
    z = ["*CLOAD"]
    for i in sorted(lasten):
        fx, fy, _fz = lasten[i]
        if abs(fx) > 1e-12:
            z.append(f"{i}, 1, {fx:.9g}")
        if abs(fy) > 1e-12:
            z.append(f"{i}, 2, {fy:.9g}")
    return z if len(z) > 1 else []


if __name__ == "__main__":                               # kleine Handprobe
    import json
    import sys

    sys.path.insert(0, ".")
    import cae_cli

    p = cae_cli.frischer_payload()
    g = p["geom"]
    L = float(g.get("axialLen") or p.get("axial_len") or 80.0)
    from ema_pipeline import LAMINATES

    for n in (12000.0, 20000.0):
        wl = waende(g, L, n, magnet_code=p.get("magnet"))
        print(f"--- {n:.0f} 1/min ---")
        print(json.dumps(summe(wl), indent=2, ensure_ascii=False))
        print(json.dumps(stegspannung(g, LAMINATES[p.get("rotor_lam", "m270_35a")],
                                      n, L, magnet_code=p.get("magnet")),
                         indent=2, ensure_ascii=False))
