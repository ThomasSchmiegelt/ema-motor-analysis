# lego — LEGO-Roboterhand per LLM

Untersucht, ob sich mit einem Sprachmodell **funktionale LEGO-Technic-Mechaniken**
erzeugen lassen. Leitbeispiel: eine Roboterhand mit beweglichen Fingern.

## Der Ansatz in einem Absatz

Nicht BrickGPT, sondern **BrickNet** (CVPR 2026, MIT) ist die Grundlage. BrickGPT
kennt nur acht rechteckige Steintypen auf einem Voxelraster und schliesst Technic
ausdruecklich aus. BrickNet stellt ein Modell stattdessen als *Konnektivitaetsgraph*
dar: Teile, verbunden ueber typisierte Konnektoren (`stud`, `hinge`, `axle`, `ball`,
`fixed`). Entscheidend ist, dass die Gelenkparameter **Attribute der Kante** sind —
eine `AxleEdge` traegt `rot` (Drehung) und `yaw` (Verschiebung). Ein Fingergelenk ist
damit eine Zahl, kein Modellierungsproblem.

Verifiziert: ein Technic-Pin (`3673`) im Loch eines Balkens (`32523`) wird als Kante
mit `family='axle'` geparst; das Setzen von `rot[0]` schwenkt das Folgeglied auf einer
exakten Kreisbahn mit Radius 20 LDU (eine Noppe).

## Was hier neu entsteht

BrickNet erzeugt *statische* Baugruppen. Der Beitrag dieses Projekts ist die
**Funktionspruefung**: ein Entwurf zaehlt nur, wenn seine Gelenke einen nennenswerten
Winkelbereich kollisionsfrei durchlaufen und die Fingerspitzen dabei zusammenlaufen.
Das ist das Gegenstueck zu BrickGPTs Stabilitaetspruefung — dort muss ein Modell
stehen, hier muss es sich bewegen.

Bewertet wird gegen die **ORCA-Hand** (ETH Zurich, 17 DoF, sehnengetrieben) als
Zielkinematik, statt gegen ein erfundenes Kriterium.

## Aufbau

```
install.sh                  Werkzeugkette (uv, venv, bricknet, torch, LDraw, ORCA)
studio/install_studio.sh    Studio 2.0 unter Wine (eigener Prefix)
reference/orca_spec.py      ORCA-URDF -> reference/orca/joint_spec.json (17 DoF)
articulation/
  pose.py                   Gelenke finden, stellen, als LDraw realisieren
  sweep.py                  Bewegungsbereich + Kollisionspruefung je Pose
  score.py                  Funktionsnote gegen die ORCA-Zielkinematik
  reference_hand.py         handgebaute Greifhand zur Kalibrierung der Bewertung
corpus/                     (offen) OMR-Sets + Studio-Exporte -> Pfadtext
train/                      (offen) LoRA-Fine-Tuning auf Qwen3
data/                       LDraw, Kollisionsnetze, Wine-Prefix — nicht versioniert
```

## Loslegen

```bash
./install.sh
source .venv/bin/activate
export BRICKNET_DATA="$PWD/data/bricknet" LDRAW_LIBRARY_PATH="$PWD/data/ldraw"

python reference/orca_spec.py --print          # ORCA-Zielkinematik, 17 DoF
python -m articulation.reference_hand          # Referenzhand bauen
```

Bewertung einer Hand:

```python
from articulation import pose, score
g = pose.load_ldr("data/reference_hand.ldr")
print(score.score(g).report())
```

Studio 2.0 (Betrachter, Bauanleitung, Teileliste):

```bash
./studio/install_studio.sh
WINEPREFIX="$PWD/data/wine-studio" DISPLAY=:1 \
  wine "$PWD/data/wine-studio/drive_c/Program Files/Studio 2.0/Studio.exe"
```

## Stand

| Teil | Stand |
|---|---|
| Werkzeugkette (bricknet, torch+CUDA, LDraw 24.591 Teile, 21.084 Kollisionsnetze) | steht |
| Studio 2.0 unter Wine | installiert |
| Artikulationsmechanik (Pin-Gelenk stellen und schwenken) | verifiziert |
| ORCA-Zielkinematik | 17 DoF extrahiert |
| Bewertung + Referenzhand | kalibriert (Kamm 0.00 vs. Greifhand 0.16) |
| Korpus (OMR + Studio-Exporte) | offen |
| Fine-Tuning | offen |

Die Referenzhand erreicht 4 Ketten, 107 Grad mittlere Beweglichkeit (91 % von ORCAs
medianer Beugespanne) und 22 % Greifschluss. Bewusst niedrig: sie ist ein grober
Pruefstein, kein Entwurfsziel.

## Quellen und Lizenzen

* **BrickNet** — Kulits & Schmid, CVPR 2026, MIT.
  <https://github.com/kulits/BrickNet>. Die Datensaetze (253k/67k Graphen) sind
  ueber ein Formular gated: <https://forms.gle/dm4eYSa5gh4DqzRT6>. Bibliothek,
  Kollisionsnetze und die vortrainierten Qwen3-Adapter sind frei.
* **ORCA Hand** — ETH Zurich Soft Robotics Lab / ORCA Dexterity, Inc.
  `orcahand_description` (URDF/MJCF) MIT, `orcahand_hardware` CC BY 4.0.
  Namensnennung: „ORCA Hand by ORCA Dexterity, Inc. — CC BY 4.0".
* **LDraw** — Teilebibliothek, CCAL 2.0.
* **Studio 2.0** — BrickLink, proprietaer, kostenlos.
