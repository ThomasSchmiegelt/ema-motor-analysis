#!/usr/bin/env python3
"""Die Magnetfliehkraft und das Schnittbild -- ohne Loeser, ohne FreeCAD.

Geprueft wird gegen **Invarianten**, nicht gegen festgenagelte Zahlen: ein Test,
der 17,512 kN erwartet, prueft nur, dass sich nichts geaendert hat. Hier steht
statt dessen, was gelten MUSS, egal welche Geometrie:

* die Summe der Wandreaktionen ist die Fliehkraft (Gleichgewicht),
* vierfache Drehzahl heisst vierfache Kraft (``F ~ omega²``),
* die Masse des Magneten zaehlt EINMAL, obwohl er zwei Waende traegt,
* der Speichenmagnet laedt die KAPPE, der flache Balken die FLANKE
  (die Bauformfrage, die die Zerlegung ohne Fallunterscheidung loest),
* in jedem der vier Loeserformate steht am Ende dieselbe Summe,
* und das Schnittbild findet die Loecher, wo die Taschen sind.

Lauf: ``python test_magnetlast.py`` oder unter pytest.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_magnetlast as ML                                      # noqa: E402
import ema_struktbild as SB                                      # noqa: E402

_OK, _FEHL = [], []


def pruefe(name, fn):
    try:
        info = fn()
        _OK.append(name)
        print(f"  ✓ {name}" + (f"  — {info}" if info else ""))
    except Exception as e:                                       # noqa: BLE001
        _FEHL.append((name, e))
        print(f"  ✗ {name}  — {type(e).__name__}: {e}")


def _geom(**zusatz):
    """Ein V-Laeufer, der durch das Layouttor geht -- aus dem frischen Payload."""
    import cae_cli
    g = dict(cae_cli.frischer_payload()["geom"])
    g.update(zusatz)
    return g


# ── 1. Dichte: eine Quelle, je Werkstoff ─────────────────────────────────────

print("\n[1] Dichte")


def _dichte_je_sorte():
    n = ML.dichte("ndfeb_n35")
    f = ML.dichte("ferrite")
    assert n > f * 1.3, (n, f)                 # Ferrit ist deutlich leichter
    assert ML.dichte(None) == ML.DICHTE_VORGABE_KG_M3
    assert ML.dichte("gibtsnicht") == ML.DICHTE_VORGABE_KG_M3
    return f"NdFeB {n:.0f} gegen Ferrit {f:.0f} kg/m³"


pruefe("Ferrit ist leichter als NdFeB -- und war es vorher NICHT", _dichte_je_sorte)


def _dichte_aus_tabelle():
    from ema_pipeline import MAGNETS
    for k, m in MAGNETS.items():
        assert "density" in m, f"{k} fuehrt keine Dichte"
        assert ML.dichte(k) == float(m["density"]), k
    return f"{len(MAGNETS)} Werkstoffe, alle mit Dichte"


pruefe("jede Sorte der MAGNETS-Tabelle fuehrt ihre Dichte", _dichte_aus_tabelle)


# ── 2. Die Waende ────────────────────────────────────────────────────────────

print("\n[2] Waende und Kraefte")


def _gleichgewicht():
    """Die Vektorsumme der Wandreaktionen EINES Magneten ist seine Fliehkraft."""
    g = _geom()
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    assert wl, "keine Waende"
    je = {}
    for w in wl:
        je.setdefault((w["pol"], w["leg"]), []).append(w)
    schlimmste = 0.0
    for schl, ws in je.items():
        fx = sum(w["fx"] for w in ws)
        fy = sum(w["fy"] for w in ws)
        soll = ws[0]["F_magnet_N"]
        ist = math.hypot(fx, fy)
        abw = abs(ist - soll) / soll
        schlimmste = max(schlimmste, abw)
        assert abw < 1e-9, (schl, ist, soll)
    return f"{len(je)} Magnete, groesste Abweichung {schlimmste:.2e}"


pruefe("Summe der Wandreaktionen = Fliehkraft des Magneten", _gleichgewicht)


def _quadratisch():
    # Gegen die ROHEN Kraefte, nicht gegen `summe` -- die rundet auf drei
    # Stellen, und ein Test, der an der Rundung haengt, prueft die Rundung.
    g = _geom()
    def _f(n):
        return sum(w["F_magnet_N"] for w in
                   {(w["pol"], w["leg"]): w
                    for w in ML.waende(g, 80.0, n, magnet_code="ndfeb_n35")}.values())
    v = _f(10000.0) / _f(5000.0)
    assert abs(v - 4.0) < 1e-12, v
    return f"doppelte Drehzahl -> {v:.6f}x Kraft"


pruefe("F waechst mit omega² -- die Grundlage der rpm²-Skalierung", _quadratisch)


def _masse_einmal():
    """Ein Magnet traegt zwei Waende, seine Masse zaehlt trotzdem einmal."""
    g = _geom()
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    s = ML.summe(wl)
    assert s["n_waende"] > s["n_magnete"], (s["n_waende"], s["n_magnete"])
    ueber_waende = sum(w["m_kg"] for w in wl)
    assert ueber_waende > s["magnet_kg"] * 1.5, "die Falle existiert gar nicht"
    # Gegenprobe gegen die unabhaengige Rechnung in ema_screen.
    import ema_screen
    import cae_cli
    pl = cae_cli.frischer_payload()
    mk = ema_screen.massen_und_kosten(pl)["magnet_kg"]
    # EINE Dichtequelle: die beiden duerfen sich nur um die Rundung
    # unterscheiden, nicht um 7600 gegen 7500.
    assert abs(mk - s["magnet_kg"]) < 1e-3, (mk, s["magnet_kg"])
    return (f"{s['n_magnete']} Magnete / {s['n_waende']} Waende, "
            f"{s['magnet_kg']:.3f} kg gegen ema_screen {mk:.3f} kg")


pruefe("Magnetmasse zaehlt je MAGNET, nicht je Wand", _masse_einmal)


def _ferrit_leichter():
    g = _geom()
    n = ML.summe(ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35"))
    f = ML.summe(ML.waende(g, 80.0, 12000.0, magnet_code="ferrite"))
    assert f["kraft_gesamt_kN"] < n["kraft_gesamt_kN"] * 0.8, (f, n)
    return (f"NdFeB {n['kraft_gesamt_kN']:.0f} kN gegen Ferrit "
            f"{f['kraft_gesamt_kN']:.0f} kN")


pruefe("der Werkstoff bewegt die Last -- sonst waere die Dichte wirkungslos",
       _ferrit_leichter)


def _bauform_waehlt_die_wand():
    """Speiche -> Kappe, flacher Balken -> Flanke. Ohne Fallunterscheidung."""
    sp = ML.waende(_geom(magShape="spoke"), 80.0, 12000.0,
                   magnet_code="ndfeb_n35")
    ba = ML.waende(_geom(magShape="bar"), 80.0, 12000.0,
                   magnet_code="ndfeb_n35")
    assert sp and ba
    sp_kappe = sum(w["anteil"] for w in sp if w["art"] == "kappe") / len(
        {(w["pol"], w["leg"]) for w in sp})
    ba_flanke = sum(w["anteil"] for w in ba if w["art"] == "flanke") / len(
        {(w["pol"], w["leg"]) for w in ba})
    assert sp_kappe > 0.9, f"Speiche laedt die Kappe nicht ({sp_kappe:.3f})"
    assert ba_flanke > 0.9, f"Balken laedt die Flanke nicht ({ba_flanke:.3f})"
    return f"Speiche {sp_kappe:.3f} auf die Kappe, Balken {ba_flanke:.3f} auf die Flanke"


pruefe("die Zerlegung findet die richtige Wand je Bauform",
       _bauform_waehlt_die_wand)


def _oberflaechenmagnete_zaehlen_nicht():
    wl = ML.waende(_geom(magShape="spm"), 80.0, 12000.0, magnet_code="ndfeb_n35")
    assert wl == [], f"Oberflaechenmagnet hat keine Tasche, aber {len(wl)} Waende"
    return "SPM -> keine Taschenwand (er sitzt aussen auf)"


pruefe("ein Oberflaechenmagnet bekommt keine Taschenwand",
       _oberflaechenmagnete_zaehlen_nicht)


def _wandlage_trifft_die_tasche():
    """Jeder Wandpunkt liegt auf dem Rand der Tasche, die ema_rotorcheck kennt."""
    from ema_rotorcheck import _magnettaschen
    g = _geom()
    pockets, _s = _magnettaschen(g)
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    schlimmste = 0.0
    for w in wl:
        r = math.hypot(w["px"], w["py"])
        # der Wandpunkt muss im Radienband IRGENDEINER Tasche liegen
        passt = False
        for _b, P in pockets:
            rmin, rmax = P.radius_bounds()
            if rmin - 0.6 <= r <= rmax + 0.6:
                passt = True
                break
        assert passt, (w["art"], r)
        schlimmste = max(schlimmste, r)
    return f"{len(wl)} Waende, groesster Wandradius {schlimmste:.1f} mm"


pruefe("die Waende liegen auf den Taschen, die das Layouttor prueft",
       _wandlage_trifft_die_tasche)


# ── 3. Knotenauswahl ─────────────────────────────────────────────────────────

print("\n[3] Knotenauswahl -- der Kern, der auch im FreeCAD-Prozess laeuft")


def _kern_ist_eine_quelle():
    import ema_freecad
    code = ema_freecad.build_rotor_fem_script(
        "/tmp/x.FCStd", 12000.0,
        {"Name": "x", "YoungsModulus": "200000 MPa", "PoissonRatio": "0.3",
         "Density": "7650 kg/m^3"}, "/tmp/sd", mesh_mm=4.0,
        magnet_walls=ML.waende(_geom(), 80.0, 12000.0, magnet_code="ndfeb_n35"))
    assert ML.KERN in code, "der Kern steht NICHT woertlich im FreeCAD-Skript"
    import ast
    ast.parse(code)
    return f"{len(ML.KERN)} Zeichen woertlich im {len(code) // 1024} kB Skript"


pruefe("der Rechenkern steht woertlich im erzeugten FreeCAD-Skript "
       "(keine Abschrift)", _kern_ist_eine_quelle)


def _knoten_auf_der_wand():
    """Gestellte Knoten: auf der Wand werden gefunden, danebenliegende nicht."""
    g = _geom()
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    w = next(x for x in wl if x["art"] == "flanke")
    kn = {}
    nid = 1
    for t in (-w["halb"] * 0.9, 0.0, w["halb"] * 0.9):
        for dz in (0.0, 40.0):
            kn[nid] = (w["px"] + t * w["tx"], w["py"] + t * w["ty"], dz)
            nid += 1
    treffer_soll = set(kn)
    # danebenliegende: 1 mm ausserhalb, und einer jenseits der Wandbreite
    kn[nid] = (w["px"] + 1.0 * w["nx"], w["py"] + 1.0 * w["ny"], 0.0); nid += 1
    kn[nid] = (w["px"] + w["halb"] * 2.0 * w["tx"],
               w["py"] + w["halb"] * 2.0 * w["ty"], 0.0); nid += 1
    ids = set(ML._ml_wandknoten(kn, w, ML.TOLERANZ_MM))
    assert ids == treffer_soll, (sorted(ids), sorted(treffer_soll))
    return f"{len(ids)} von {len(kn)} Knoten -- z spielt keine Rolle (durchgehende Tasche)"


pruefe("die Wandauswahl trifft genau die Wandknoten", _knoten_auf_der_wand)


def _verlorene_last_wird_benannt():
    g = _geom()
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    lasten, bericht = ML.knotenlasten({1: (0.0, 0.0, 0.0)}, wl)
    assert lasten == {}, lasten
    fehlt = ML.fehlende_waende(bericht)
    assert len(fehlt) == len(wl), (len(fehlt), len(wl))
    assert all(b["F_aufgetragen_N"] == 0.0 for b in fehlt)
    return f"{len(fehlt)} Waende ohne Knoten werden gemeldet statt verschwiegen"


pruefe("eine Wand ohne Netzknoten ist eine GEMELDETE verlorene Last",
       _verlorene_last_wird_benannt)


def _summe_bleibt_erhalten():
    """Ueber die Knoten aufsummiert steht dieselbe Kraft wie in der Wandliste."""
    g = _geom()
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    # Fuer jede Wand ein paar Knoten DARAUF stellen.
    kn = {}
    nid = 1
    for w in wl:
        if w["art"] == "flanke":
            for t in (-0.5, 0.0, 0.5):
                kn[nid] = (w["px"] + t * w["halb"] * w["tx"],
                           w["py"] + t * w["halb"] * w["ty"], 0.0)
                nid += 1
        else:
            for a in (-0.6, 0.0, 0.6):
                tx, ty = -w["ny"], w["nx"]
                kn[nid] = (w["px"] + w["radius"] * (math.cos(a) * w["nx"]
                                                    + math.sin(a) * tx),
                           w["py"] + w["radius"] * (math.cos(a) * w["ny"]
                                                    + math.sin(a) * ty), 0.0)
                nid += 1
    lasten, bericht = ML.knotenlasten(kn, wl)
    assert not ML.fehlende_waende(bericht), ML.fehlende_waende(bericht)
    fx = sum(v[0] for v in lasten.values())
    fy = sum(v[1] for v in lasten.values())
    soll_x = sum(w["fx"] for w in wl)
    soll_y = sum(w["fy"] for w in wl)
    assert abs(fx - soll_x) < 1e-6 and abs(fy - soll_y) < 1e-6, (fx, soll_x, fy, soll_y)
    return f"{len(lasten)} Lastknoten, Summe bitgenau"


pruefe("die Knotenlast summiert sich zur Wandlast", _summe_bleibt_erhalten)


# ── 4. Dieselbe Last in allen Loeserformaten ─────────────────────────────────

print("\n[4] dieselbe Last in ccx, Z88 und Code Aster")


def _netz_bauen():
    """Ein winziges Netz von Hand -- genug fuer die Schreiber, ohne gmsh."""
    import ema_deck as deck
    kn = {}
    nid = 1
    for a in range(0, 360, 30):
        kn[nid] = (20.0 * math.cos(math.radians(a)),
                   20.0 * math.sin(math.radians(a)), 0.0)
        nid += 1
    kn[nid] = (60.0, 0.0, 30.0)
    letzter = nid
    return deck.Netz(knoten=kn, elemente={1: (1, 2, 3, letzter)}, ordnung=1,
                     nset_bohrung=list(range(1, 13)),
                     nset_stirn_a=list(range(1, 13)), nset_stirn_b=[letzter],
                     poles=6, sektoren=0, r_rot=94.3, r_shaft=20.0,
                     axial_len=30.0)


def _drei_formate_gleiche_summe():
    import ema_aster as aster
    import ema_deck as deck
    import ema_z88 as z88
    netz = _netz_bauen()
    mat = {"density": 7650, "E": 200000, "nu": 0.3, "yield_mpa": 340}
    zl = {2: (1000.0, 500.0, 0.0), 3: (1000.0, 500.0, 0.0),
          netz.nset_stirn_b[0]: (-250.0, 0.0, 0.0)}
    soll = sum(abs(v[0]) for v in zl.values())
    d = tempfile.mkdtemp()

    # ccx
    pfad = deck.schreibe_inp(netz, mat, 12000.0, os.path.join(d, "r.inp"),
                             zusatzlasten=zl)
    zeilen = open(pfad).read().splitlines()
    i = zeilen.index("*CLOAD")
    ccx = 0.0
    for z in zeilen[i + 1:]:
        if z.startswith("*"):
            break
        t = z.split(",")
        if len(t) == 3 and int(t[1]) == 1:
            ccx += abs(float(t[2]))
    assert abs(ccx - soll) / soll < 1e-8, (ccx, soll)

    # Z88: dieselbe Zeile traegt Flieh- UND Magnetlast, also gegen den
    # Lauf OHNE Zusatzlast differenzieren.
    def _z88_fx(mit):
        p = os.path.join(d, "z_mit" if mit else "z_ohne")
        z88.schreibe_satz(netz, mat, 12000.0, p,
                          zusatzlasten=(zl if mit else None))
        summe = 0.0
        for z in open(os.path.join(p, "z88i2.txt")).read().splitlines()[1:]:
            t = z.split()
            if len(t) == 4 and t[1] == "1" and t[2] == "1":
                summe += float(t[3])
        return summe

    z_delta = _z88_fx(True) - _z88_fx(False)
    soll_sig = sum(v[0] for v in zl.values())
    # %.9g in der Z88-Datei: relativ pruefen, nicht absolut.
    assert abs(z_delta - soll_sig) / abs(soll_sig) < 1e-8, (z_delta, soll_sig)

    # Code Aster: Gruppen gleicher Knotenkraft, je eine FORCE_NODALE-Zeile
    info = aster.schreibe_mail(netz, os.path.join(d, "fort.20"), zusatzlasten=zl)
    a_sum = sum(abs(g["fx"]) * g["n_knoten"] for g in info["lastgruppen"])
    assert abs(a_sum - soll) / soll < 1e-8, (a_sum, soll)
    sk = aster.schreibe_skript(netz, mat, 12000.0, d,
                               os.path.join(d, "fort.20"), info)
    import py_compile
    py_compile.compile(sk, doraise=True)
    assert "FORCE_NODALE" in open(sk).read()
    return (f"ccx {ccx:.0f} N | Z88 {z_delta:.0f} N | Aster "
            f"{a_sum:.0f} N ueber {len(info['lastgruppen'])} Gruppen")


pruefe("alle drei Loeser bekommen DIESELBE Summe -- sonst vergleicht der "
       "Loeservergleich Lastfaelle", _drei_formate_gleiche_summe)


def _ohne_zusatzlast_bitgleich():
    """Kein `zusatzlasten` -> die Datei ist Zeichen fuer Zeichen die alte."""
    import ema_deck as deck
    netz = _netz_bauen()
    mat = {"density": 7650, "E": 200000, "nu": 0.3, "yield_mpa": 340}
    d = tempfile.mkdtemp()
    a = open(deck.schreibe_inp(netz, mat, 9000.0, os.path.join(d, "a.inp"))).read()
    b = open(deck.schreibe_inp(netz, mat, 9000.0, os.path.join(d, "b.inp"),
                               zusatzlasten={})).read()
    assert a == b, "leere Zusatzlast veraendert den Satz"
    assert "*CLOAD" not in a, "CLOAD ohne Last"
    return f"{len(a)} Zeichen, unveraendert"


pruefe("ohne Magnetlast bleibt jeder Altlauf Ziffer fuer Ziffer derselbe",
       _ohne_zusatzlast_bitgleich)


# ── 5. Der Steg-Richtwert ────────────────────────────────────────────────────

print("\n[5] Steg-Richtwert")


def _steg_haengt_am_randsteg():
    from ema_pipeline import LAMINATES
    g = _geom()
    mat = LAMINATES["m270_35a"]
    s = ML.stegspannung(g, mat, 12000.0, 80.0, magnet_code="ndfeb_n35")
    assert s["steg_traegt"] is True
    assert s["sigma_steg_MPa"] > 0
    # Die Formel ist sigma = F/(n*s*L): doppelte Laenge -> halbe Spannung,
    # denn F waechst mit L UND die Flaeche auch ... also GLEICH.
    s2 = ML.stegspannung(g, mat, 12000.0, 160.0, magnet_code="ndfeb_n35")
    assert abs(s2["sigma_steg_MPa"] - s["sigma_steg_MPa"]) < 0.05, \
        (s["sigma_steg_MPa"], s2["sigma_steg_MPa"])
    # Ueberlagert ist strenger als die Magnetlast allein.
    assert s["sigma_ueberlagert_MPa"] > s["sigma_steg_MPa"]
    assert s["sf_ueberlagert"] < s["sf_steg"]
    return (f"{s['sigma_steg_MPa']:.0f} MPa (Magnet) + {s['sigma_ring_MPa']:.0f} "
            f"MPa (Ring) bei {s['s_rand_mm']:.2f} mm Steg, laengenunabhaengig")


pruefe("der Steg-Richtwert haengt am Randsteg und nicht an der Baulaenge",
       _steg_haengt_am_randsteg)


def _aussenlaeufer_hat_keinen_steg():
    from ema_pipeline import LAMINATES
    g = _geom(rotorPosition="aussen", rotorID=200.0, rotorOD=240.0,
              statorOD=190.0, statorID=60.0)
    s = ML.stegspannung(g, LAMINATES["m270_35a"], 12000.0, 80.0,
                        magnet_code="ndfeb_n35")
    assert s["steg_traegt"] is False, s
    assert "sigma_steg_MPa" not in s, "eine Zahl, wo es die Last nicht gibt"
    assert s["grund"], "kein Grund genannt"
    return "Aussenlaeufer: die Fliehkraft drueckt gegen den Ring, kein Steg"


pruefe("beim Aussenlaeufer gibt es die Stegspannung NICHT -- und keine Zahl",
       _aussenlaeufer_hat_keinen_steg)


def _grenzen_stehen_dabei():
    g = ML.grenzen()
    assert len(g) >= 4
    txt = " ".join(g).lower()
    for wort in ("klebung", "kaefig", "schrumpf"):
        assert wort in txt, wort
    return f"{len(g)} benannte Grenzen"


pruefe("was die Last NICHT ist, steht als Liste dabei", _grenzen_stehen_dabei)


# ── 6. Das Schnittbild ───────────────────────────────────────────────────────

print("\n[6] Schnittbild")


def _wuerfelnetz(n=6, h=4.0):
    """Ein Quader aus Tetraedern -- jeder Wuerfel in 5, Werte = x."""
    knoten, elemente = {}, {}
    idx = {}
    nid = 1
    for i in range(n + 1):
        for j in range(n + 1):
            for k in range(3):
                idx[(i, j, k)] = nid
                knoten[nid] = (float(i), float(j), k * h / 2.0)
                nid += 1
    eid = 1
    for i in range(n):
        for j in range(n):
            for k in range(2):
                c = [idx[(i + a, j + b, k + c2)]
                     for a, b, c2 in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                                      (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))]
                for t in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6),
                          (3, 4, 6, 7), (1, 3, 4, 6)):
                    elemente[eid] = tuple(c[x] for x in t)
                    eid += 1
    return knoten, elemente


def _schnitt_findet_die_flaeche():
    kn, el = _wuerfelnetz(n=6, h=4.0)
    werte = {i: kn[i][0] for i in kn}                  # linear in x
    polys, w = SB.schnittpolygone(kn, el, 1.0, wert_knoten=werte)
    assert polys, "kein Schnitt"
    flaeche = 0.0
    for q in polys:
        a = 0.0
        for i in range(len(q)):
            x1, y1 = q[i]
            x2, y2 = q[(i + 1) % len(q)]
            a += x1 * y2 - x2 * y1
        flaeche += abs(a) / 2.0
    assert abs(flaeche - 36.0) / 36.0 < 1e-6, flaeche
    return f"{len(polys)} Polygone, Flaeche {flaeche:.4f} gegen 36 (6x6 Quader)"


pruefe("der Schnitt deckt die Querschnittsflaeche lueckenlos ab",
       _schnitt_findet_die_flaeche)


def _schnitt_interpoliert_linear():
    """Ein lineares Feld muss der Schnitt exakt wiedergeben."""
    kn, el = _wuerfelnetz(n=4, h=4.0)
    werte = {i: 3.0 * kn[i][0] + 7.0 for i in kn}
    polys, w = SB.schnittpolygone(kn, el, 1.0, wert_knoten=werte)
    schlimmste = 0.0
    for q, v in zip(polys, w):
        cx = sum(p[0] for p in q) / len(q)
        schlimmste = max(schlimmste, abs(v - (3.0 * cx + 7.0)))
    assert schlimmste < 1e-9, schlimmste
    return f"groesste Abweichung {schlimmste:.2e}"


pruefe("ein lineares Feld kommt exakt heraus (Kanteninterpolation)",
       _schnitt_interpoliert_linear)


def _skalierung_ist_linear():
    kn, el = _wuerfelnetz(n=4)
    werte = {i: kn[i][0] + 1.0 for i in kn}
    vorab = SB.schnittpolygone(kn, el, 1.0, wert_knoten=werte)
    b1, k1 = SB.feldbild(kn, el, {"rotorOD": 10, "shaftD": 0},
                         groesse="spannung", vorab=vorab, skal=1.0, px=400)
    b4, k4 = SB.feldbild(kn, el, {"rotorOD": 10, "shaftD": 0},
                         groesse="spannung", vorab=vorab, skal=4.0, px=400)
    assert b1 and b4
    # `feldbild` rundet seine Kennzahlen auf vier Stellen -- relativ pruefen.
    assert abs(k4["wert_max"] - 4.0 * k1["wert_max"]) / k4["wert_max"] < 1e-4, (k1, k4)
    return f"max {k1['wert_max']} -> {k4['wert_max']} bei skal=4"


pruefe("rpm²-Skalierung wirkt exakt auf den vorberechneten Schnitt",
       _skalierung_ist_linear)


def _groessen_heissen_wie_die_bilder():
    """Die Schluessel der Tabelle sind die, mit denen die Pipeline benennt.

    Gemessen am ersten echten Lauf: die Pipeline schreibt ``verformung``, die
    Tabelle kannte nur ``verschiebung``, und der stille Rueckfall auf die
    Spannung schrieb „Vergleichsspannung [MPa]" ueber eine Mikrometer-Skala.
    Eine falsche Einheit an einer richtigen Zahl ist schlimmer als gar keine.
    """
    import re
    quelle = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "ema_pipeline.py"), encoding="utf-8").read()
    i = quelle.index("_groessen = [")
    verwendet = set(re.findall(r'\("(\w+)",\s*"[^"]+",\s*(?:_vorab|None)',
                               quelle[i:i + 600]))
    assert verwendet, "die Groessenliste der Pipeline ist nicht lesbar"
    fehlt = verwendet - set(SB.GROESSEN)
    assert not fehlt, f"ema_struktbild kennt {sorted(fehlt)} nicht"
    # und ein Tippfehler leiht sich KEINE fremde Beschriftung
    assert SB.GROESSEN.get("verfomung", SB.UNBEKANNT) == SB.UNBEKANNT
    assert "MPa" not in SB.UNBEKANNT[0] and "µm" not in SB.UNBEKANNT[0]
    return f"{sorted(verwendet)} -- alle benannt, Rueckfall ohne Einheit"


pruefe("die Pipeline-Groessen stehen alle in GROESSEN -- und ein Tippfehler "
       "erbt keine falsche Einheit", _groessen_heissen_wie_die_bilder)


def _ohne_elemente_kein_bild():
    kn, _el = _wuerfelnetz(n=3)
    b, k = SB.feldbild(kn, {}, {"rotorOD": 10, "shaftD": 0},
                       groesse="spannung", wert_knoten={i: 1.0 for i in kn},
                       px=300)
    assert b == "", "ein Bild ohne Elemente"
    assert "fehler" in k and k["n_polygone"] == 0
    return "leere Elementtabelle -> benannter Fehler statt leeres Bild"


pruefe("ohne Elementtabelle wird GESAGT, dass es keinen Schnitt gibt",
       _ohne_elemente_kein_bild)


def _sicherheitskarte_braucht_die_fliessgrenze():
    kn, el = _wuerfelnetz(n=3)
    werte = {i: 100.0 for i in kn}
    b, k = SB.feldbild(kn, el, {"rotorOD": 10, "shaftD": 0},
                       groesse="sicherheit", wert_knoten=werte,
                       yield_mpa=0.0, px=300)
    assert b == "" and "fehler" in k
    b2, k2 = SB.feldbild(kn, el, {"rotorOD": 10, "shaftD": 0},
                         groesse="sicherheit", wert_knoten=werte,
                         yield_mpa=300.0, px=300)
    assert b2 and abs(k2["wert_median"] - 3.0) < 1e-6, k2
    return "ohne Fliessgrenze keine Karte; mit 300 MPa auf 100 MPa -> SF 3,0"


pruefe("die Sicherheitskarte entsteht aus der Fliessgrenze -- oder gar nicht",
       _sicherheitskarte_braucht_die_fliessgrenze)


def _lastbild_zeichnet_die_echte_liste():
    g = _geom()
    wl = ML.waende(g, 80.0, 12000.0, magnet_code="ndfeb_n35")
    b, s = SB.lastbild(g, wl, 80.0, 12000.0, px=500)
    assert b and len(b) > 5000, len(b or "")
    assert s["n_waende"] == len(wl)
    return f"{s['n_waende']} Waende gezeichnet, PNG {len(b) // 1024} kB base64"


pruefe("das Lastbild zeichnet genau die Waende, die in den Loeser gehen",
       _lastbild_zeichnet_die_echte_liste)


# ── 7. Die Marke des FreeCAD-Laufs ───────────────────────────────────────────

print("\n[7] Rueckmeldung aus dem FreeCAD-Lauf")


def _marke_nimmt_die_letzte():
    import ema_pipeline as P
    aus = ("blabla\n"
           'MAGNETLAST:{"n_waende": 24, "n_ohne_knoten": 7, "n_lastknoten": 10}\n'
           "MESH_TRY[1] ...\n"
           'MAGNETLAST:{"n_waende": 24, "n_ohne_knoten": 0, "n_lastknoten": 9999}\n'
           "SOLVE_OK\n")
    m = P._magnetlast_aus_stdout(aus)
    assert m["n_lastknoten"] == 9999, m
    assert P._magnetlast_aus_stdout("nichts") == {}
    assert P._magnetlast_aus_stdout("MAGNETLAST:{kaputt") == {}
    return "die LETZTE Marke gilt -- sie gehoert zum Netz, das geloest hat"


pruefe("von mehreren Netzversuchen zaehlt der letzte", _marke_nimmt_die_letzte)



# ── Das EBENE Netz ist der Schnitt ───────────────────────────────────────────

print("\n[eben] Ein ebenes Netz wird nicht geschnitten")


def _ebenes_netz_ist_der_schnitt():
    """Beim ebenen Lauf liegen alle Knoten auf z = 0.

    Eine Schnittebene bei z = 0 streift dort JEDES Element, und
    `schnittpolygone` gaebe nichts zurueck -- das Mehrkoerperbild des ebenen
    Laufs waere leer, und die Pipeline faengt das in einem `except` und sagt
    nur „uebersprungen". Erkannt wird es an der Elementlaenge.
    """
    # Rechtwinkliges Dreieck, Flaeche 6,0 mm²
    kn = {1: (0., 0., 0.), 2: (3., 0., 0.), 3: (0., 4., 0.)}
    pf, wf = SB.schnittpolygone(kn, {1: (1, 2, 3)}, 0.0,
                                wert_element={1: 100.0})
    assert len(pf) == 1, f"{len(pf)} Polygone statt 1"
    assert len(pf[0]) == 3, pf[0]
    flaeche = abs((pf[0][1][0] - pf[0][0][0]) * (pf[0][2][1] - pf[0][0][1])
                  - (pf[0][2][0] - pf[0][0][0]) * (pf[0][1][1] - pf[0][0][1])) / 2
    assert abs(flaeche - 6.0) < 1e-9, flaeche
    assert wf == [100.0], wf
    # Die rpm²-Skalierung gilt hier wie im raeumlichen Fall.
    _, w4 = SB.schnittpolygone(kn, {1: (1, 2, 3)}, 0.0,
                               wert_element={1: 100.0}, skal=4.0)
    assert w4 == [400.0], w4
    # Gegenprobe: ein TETRAEDER wird weiterhin geschnitten.
    kn4 = {1: (0., 0., -1.), 2: (3., 0., -1.), 3: (0., 4., -1.), 4: (0., 0., 1.)}
    pt, _ = SB.schnittpolygone(kn4, {1: (1, 2, 3, 4)}, 0.0,
                               wert_element={1: 7.0})
    assert len(pt) == 1 and len(pt[0]) >= 3, pt
    return ("Dreieck -> 1 Polygon mit 6,0 mm², skal wirkt, "
            "Tetraeder wird weiter geschnitten")


pruefe("ein ebenes Netz IST der Schnitt (Tetraeder weiter geschnitten)",
       _ebenes_netz_ist_der_schnitt)


def _zweite_ordnung_nur_ecken():
    """Ein Dreieck 2. Ordnung traegt Mittenknoten -- nicht im Umriss."""
    kn = {1: (0., 0., 0.), 2: (4., 0., 0.), 3: (0., 4., 0.),
          4: (2., 0., 0.), 5: (2., 2., 0.), 6: (0., 2., 0.)}
    pf, _ = SB.schnittpolygone(kn, {1: (1, 2, 3, 4, 5, 6)}, 0.0,
                               wert_element={1: 1.0})
    assert len(pf) == 1 and len(pf[0]) == 3, pf
    assert (2.0, 0.0) not in pf[0], "ein Mittenknoten steht im Umriss"
    return "6-Knoten-Dreieck -> Umriss aus den 3 Ecken"


pruefe("beim Dreieck 2. Ordnung zaehlen nur die Ecken",
       _zweite_ordnung_nur_ecken)


print("\n" + "=" * 62)
print(f"{len(_OK)} bestanden, {len(_FEHL)} fehlgeschlagen")
if _FEHL:
    for n, e in _FEHL:
        print(f"  ✗ {n}: {e}")
    sys.exit(1)
