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
scripts/generate.py         Proben erzeugen (Qwen3 + BrickNet-LoRA, frei oder nach Vorgabe)
eval/score_samples.py       Proben -> Graph -> Funktionsnote, mit Parsequote
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

Erzeugen und bewerten (die vortrainierten BrickNet-Adapter, ohne eigenes Training):

```bash
python scripts/generate.py --model Qwen/Qwen3-0.6B \
  --lora kulits/BrickNet-0.6B-PT --lora kulits/BrickNet-0.6B-SFT \
  --output data/gen_sft.jsonl --prompts_file data/prompts.jsonl \
  --n_per_prompt 4 --stop_after_newlines 60

python -m eval.score_samples --input data/gen_sft.jsonl \
  --report data/eval_gen_sft.jsonl --best-ldr data/best_sft.ldr
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
| Kette Erzeugen -> Parsen -> Bewerten | steht (`eval/score_samples.py`) |
| Korpus (OMR + Studio-Exporte) | offen |
| Fine-Tuning | offen |

Die Referenzhand erreicht 4 Ketten, 107 Grad mittlere Beweglichkeit (91 % von ORCAs
medianer Beugespanne) und 22 % Greifschluss. Bewusst niedrig: sie ist ein grober
Pruefstein, kein Entwurfsziel.

## Erster Messwert: die vortrainierten Adapter, ungetunt

Je 16 Proben mit `BrickNet-0.6B` (13.08.2026, `--stop_after_newlines 60`, Saat 1):

| | frei (PT) | nach Vorgabe (PT+SFT) |
|---|---|---|
| parsebar | 15/16 | 8/16 |
| Gelenke je Probe | 7.7 | 16.8 |
| durchdringende Teilepaare in Ruhe | 13.1 | 28.4 |
| kollisionsfrei in Ruhe | 0/15 | 2/8 |
| Funktionsnote > 0 | 0 | 2 |

Die verbleibenden Parsefehler sind **inhaltlich**, nicht formal: das Modell steckt
Konnektoren zusammen, die das Teil nicht hat (`part 6526 has no open/None
connectors`). Und der beste Wert (0.24 auf „a five-fingered hand") ist **kein
besseres Ergebnis als die Referenzhand**, sondern eine Luecke im Massstab: die Probe
besteht aus zwei langen Ketten duenner Stangen, die die gedeckelten Teilnoten
„Gelenktiefe" und „Beweglichkeit" auf Anschlag ziehen. Eine Peitsche, keine Hand —
s. `CLAUDE.md`, „Bekannte Schwaeche des Massstabs".

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
