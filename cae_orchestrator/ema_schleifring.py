"""Schleifringe und Buersten — Strom auf einen drehenden Laeufer bringen.

Warum ein eigenes Modul
-----------------------

Ein Schleifring gehoert weder der Asynchron- noch der Synchronmaschine. Beide
brauchen ihn, aus verschiedenen Gruenden und in verschiedener Zahl:

    ASM, Schleifringlaeufer   DREI Ringe -- eine Drehstromwicklung wird nach
                              aussen auf den Anlasswiderstand gefuehrt.
    EESM                      ZWEI Ringe -- ein Gleichstromkreis, die Erregung.
    GSM (Erregerkreis)        ebenfalls zwei, aber am STAENDER; der Anker
                              bekommt statt dessen einen Kommutator.

Die Geometrie ist in allen Faellen dieselbe: der Ring sitzt auf der Welle,
seine Breite folgt der Stromdichte am Buerstenkontakt, und die Umfangs-
geschwindigkeit ist die Grenze, die diese Bauart wirklich begrenzt. Zwei
Fassungen davon waeren zwei verschieden breite Ringe fuer denselben Strom.

Was hier eine GRENZE ist und was ein Vorgabewert
------------------------------------------------

``J_BUERSTE_APCM2`` ist ein Auslegungswert (Kohlebuersten liegen bei
6-12 A/cm^2, 10 ist der uebliche Ansatz) — er BESTIMMT die Ringbreite.

``V_RING_MAX_MPS`` ist eine Grenze. Oberhalb traegt der Kohlekontakt nicht mehr
zuverlaessig (Buerstenfeuer, Abbrand), und dann ist ein Schleifringlaeufer die
falsche Wahl, egal wie gut er sonst passt. Ueberschritten wird sie **gemeldet**
und nicht stillschweigend unterschritten; ist keine Hoechstdrehzahl bekannt,
steht dort ``None`` und ausdruecklich nicht „ok".
"""

from __future__ import annotations

import math

# Stromdichte am Buerstenkontakt [A/cm^2]. Auslegungswert, kein Deckel.
J_BUERSTE_APCM2 = 10.0

# Umfangsgeschwindigkeit am Schleifring [m/s] -- die Grenze der Bauart.
V_RING_MAX_MPS = 45.0

# Spannungsabfall je Buerstenkontakt [V]. Zwei Kontakte je Stromkreis.
# ``ema_eesm.U_BUERSTE_V`` fuehrt denselben Wert fuer den Erregerkreis; er steht
# dort seit jeher und wird hier NICHT ueberschrieben, sondern nur wiederholt --
# wer ihn aendert, aendert ihn an beiden Stellen, und der Test haelt sie gleich.
U_BUERSTE_V = 1.0

# Seitenverhaeltnis der Buerstenauflage (Umfangslaenge : Ringbreite).
BUERSTE_LAENGE_ZU_BREITE = 2.0

# Kleinste sinnvoll gebaute Ringbreite [mm].
RING_BREITE_MIN_MM = 6.0


def geometrie(geom: dict, i_eff_A: float, n_ringe: int = 3,
              rpm_max: float | None = None) -> dict:
    """Ringe auf der Welle: Durchmesser, Breite, Buerstenflaeche, Grenze.

    ``i_eff_A`` ist der Strom, den EIN Ring fuehrt (Effektivwert).
    ``rpm_max`` fehlt = die Umfangsgeschwindigkeit wird NICHT geprueft, und das
    Ergebnis sagt das mit ``v_ok: None`` statt mit einem beruhigenden True.
    """
    r_wel = float(geom["shaftD"]) / 2.0
    # Der Ring sitzt mit einer Isolierhuelse auf der Welle.
    d_ring = 2.0 * (r_wel + max(2.0, 0.04 * r_wel))
    i_eff = max(float(i_eff_A), 1e-6)
    a_buerste_cm2 = i_eff / J_BUERSTE_APCM2
    # Auflageflaeche = Ringbreite x Umfangslaenge der Buerste.
    b_ring = max(RING_BREITE_MIN_MM,
                 math.sqrt(a_buerste_cm2 * 100.0 / BUERSTE_LAENGE_ZU_BREITE))
    n_max = float(rpm_max or geom.get("rpm_to") or 0.0)
    v_ring = math.pi * (d_ring * 1e-3) * n_max / 60.0 if n_max > 0 else None
    return {
        "n_ringe": int(n_ringe),
        "d_ring_mm": round(d_ring, 2),
        "b_ring_mm": round(b_ring, 2),
        "spalt_mm": round(0.4 * b_ring, 2),        # Luft zwischen zwei Ringen
        "A_buerste_cm2": round(a_buerste_cm2, 2),
        "I_ring_eff_A": round(i_eff, 1),
        "v_ring_mps": None if v_ring is None else round(v_ring, 1),
        "v_grenze_mps": V_RING_MAX_MPS,
        "v_ok": None if v_ring is None else bool(v_ring <= V_RING_MAX_MPS),
        "U_buerste_V": U_BUERSTE_V,
        "P_buerste_W": round(2.0 * U_BUERSTE_V * i_eff, 1),
    }


def zeichenmasse(rg: dict) -> dict:
    """Nur die Masse, die ein Zeichenskript braucht — als reine Zahlen.

    Das Urteil ueber die Umfangsgeschwindigkeit (``v_ok``) gehoert ins
    Protokoll und **nicht** in ein erzeugtes Skript: dort waere es als
    JSON-``true``/``null`` ein NameError, weil das Skript Python ist und kein
    JSON. Gemessen genau daran gescheitert.
    """
    return {"n_ringe": int(rg["n_ringe"]),
            "d_ring_mm": float(rg["d_ring_mm"]),
            "b_ring_mm": float(rg["b_ring_mm"]),
            "spalt_mm": float(rg["spalt_mm"])}
