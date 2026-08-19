# Integration: Von einem anderen Programm/Verzeichnis auf die PicoGK Web API zugreifen

Diese Notiz beschreibt, was zu beachten ist, wenn **ein anderes Programm** (z. B. später die E-Maschinen-Pipeline, ein Testskript, ein Jupyter-Notebook o. ä.) sich — unabhängig von seinem eigenen Arbeitsverzeichnis — mit `PicoGKWebApi` verbinden will. Es ist eine reine HTTP-Schnittstelle, also ist der Aufrufort irrelevant — wichtig sind nur die Punkte unten.

## 1. Der Server muss vorher separat laufen

`PicoGKWebApi` ist kein Hintergrunddienst/systemd-Service, sondern ein manuell gestarteter Prozess:

```bash
~/ai-workspace/pikogk/start.sh
```

Das rufende Programm startet ihn **nicht automatisch mit** — es muss vorher (in einem eigenen Terminal, `nohup`, tmux, o. ä.) laufen. Sinnvoll ist ein kurzer Erreichbarkeits-Check vor der eigentlichen Nutzung:

```bash
curl -sf http://localhost:5266/ >/dev/null || echo "PicoGK Web API läuft nicht"
```

**Nur eine Instanz gleichzeitig.** PicoGK erlaubt pro Prozess nur eine globale `Library`-Instanz (`Library.Go()` wirft eine Exception, wenn man versucht, eine zweite zu starten). `start.sh` beendet deshalb beim Start automatisch noch laufende alte Instanzen (inkl. SIGKILL-Eskalation, falls der Prozess auf SIGTERM nicht reagiert) — ein erneuter `start.sh`-Aufruf ist damit auch der einfachste Weg, den Server nach einem Update neu zu starten. Für mehrere parallele Anfragen siehe Punkt 5 (Nebenläufigkeit).

## 2. Netzwerk-Bindung: nur localhost

Der Server bindet aktuell explizit an `http://localhost:5266` (siehe `PicoGKWebApi/Program.cs`, `UseUrls`). Das bedeutet:

- Ein Programm auf **demselben Rechner** (egal in welchem Verzeichnis) erreicht ihn problemlos über `http://localhost:5266`.
- Ein Programm auf einem **anderen Rechner** erreicht ihn **nicht** — dafür müsste `UseUrls` auf `http://0.0.0.0:5266` geändert werden. Das ist bewusst nicht der Fall, da es sich um einen lokalen PoC ohne Auth/TLS handelt (siehe Punkt 6).

## 3. Endpunkt: Geometrie erzeugen

Der Server unterstützt vier eingebaute parametrische Grundformen: `box`, `cylinder`, `nozzle` (Laval-Düse), `screw` (Schraube, vereinfacht ohne Gewinde) — plus alle über das Skill-System erzeugten und freigegebenen Formen. Die aktuelle Liste inkl. Parameterschema (Name, Label, Einheit, Default, Min/Max) liefert `GET /skills`.

```
POST /generate-shape
Content-Type: application/json
```

```json
{
  "type": "cylinder",
  "values": { "radius": 15, "height": 80 }
}
```

Erfolgsantwort (`200 OK`):

```json
{
  "fileUrl": "/stl/cylinder_20260716_125835_59f3fcc7.stl",
  "triangleCount": 51264,
  "boundingBoxMM": { "x": 30, "y": 30, "z": 80 }
}
```

Wichtig: `fileUrl` ist **relativ zum Server**, nicht absolut. Das aufrufende Programm muss `http://localhost:5266` selbst voranstellen:

```
http://localhost:5266/stl/cylinder_20260716_125835_59f3fcc7.stl
```

Der Dateiname wird server-seitig generiert (Zeitstempel + zufälliges Suffix) — er lässt sich nicht vorhersagen und sollte nicht geraten, sondern immer aus der Antwort übernommen werden.

`type` muss ein Name aus `GET /skills` sein, `values` muss exakt die Felder des jeweiligen Typs enthalten — der Server validiert serverseitig erneut (nie dem Client blind vertrauen), auch wenn die Werte z. B. schon einmal über `/interpret` geprüft wurden. Fehlercodes siehe Punkt 4.

**`/interpret`** (Freitext → Ollama → Typ+Parameter) liefert bei Erfolg `{"type": "...", "values": {...}}` — dieselbe Form, die `/generate-shape` als Body erwartet. Ein aufrufendes Programm kann also direkt `/interpret`-Ausgabe an `/generate-shape` durchreichen, sollte aber (wie die mitgelieferte UI) die Werte dazwischen anzeigen/prüfen, statt PicoGK blind laufen zu lassen — genau das war die Vorgabe für diese Ausbaustufe. Bei `type: "none"` liefert `/interpret` `400` statt Werten (Text passt zu keiner unterstützten Grundform).

## 4. Fehlerfälle

| Status | Bedeutung | Response-Form |
|---|---|---|
| `400` | Parameter außerhalb des sinnvollen Bereichs (Validate-Methode des jeweiligen Geometriemoduls) | `{"error": "..."}` |
| `503` | Worker-Thread nicht mehr aktiv (natives PicoGK-Viewer-Fenster wurde von Hand geschlossen) → Server muss neu gestartet werden | ProblemDetails-JSON, Feld `detail` |
| `504` | Geometrieerzeugung hat > 60 s gedauert | ProblemDetails-JSON, Feld `detail` |
| `500` | Unerwarteter Fehler bei der Geometrie-/Voxel-Erzeugung | ProblemDetails-JSON, Feld `detail` |

Ein aufrufendes Programm sollte also sowohl das Feld `error` (bei 400) als auch `detail` (bei 503/504/500) auswerten — das mitgelieferte `wwwroot/index.html` macht das bereits so vor.

## 5. Nebenläufigkeit / Performance

Alle `/generate-shape`-Aufrufe landen in einer **einzigen** Warteschlange, die von **einem** Worker-Thread seriell abgearbeitet wird (Architekturzwang von PicoGK, siehe `EXPERIENCE_REPORT.md` Abschnitt 9). Das heißt für ein aufrufendes Programm:

- Mehrere gleichzeitige Requests werden **nicht parallel** verarbeitet, sondern nacheinander — bei Batch-Verarbeitung (z. B. viele Varianten aus der Pipeline) entsprechend Zeit einplanen.
- Jeder einzelne Request hat serverseitig ein 60-Sekunden-Timeout (siehe Punkt 4). Bei sehr feiner Voxelauflösung oder sehr großen Geometrien könnte das knapp werden — aktuell mit `VoxelSizeMM = 0.25f` fest im Code hinterlegt, nicht über die API einstellbar.

## 6. Kein Auth, kein TLS

Es gibt keinerlei Zugriffsschutz. Das ist für einen lokalen PoC in Ordnung, aber **nicht** geeignet, um den Server auf einer gemeinsam genutzten Maschine oder gar im Netzwerk erreichbar zu machen, ohne das nachzurüsten.

## 7. Erzeugte Dateien: kein automatisches Aufräumen

Jede Generierung legt eine neue `.stl`-Datei in `PicoGKWebApi/output/` ab (aktuell ca. 2,5 MB pro Datei bei den Default-Parametern) — es gibt **keine** automatische Löschung. Ein Programm, das die API oft/automatisiert aufruft (z. B. aus einer Pipeline heraus), sollte selbst dafür sorgen, alte Dateien zu entfernen, sonst wächst der Ordner unbegrenzt.

## 8. Voraussetzung auf dem Server-Rechner: X-Display

`start.sh` setzt `DISPLAY` (Default `:1`), weil PicoGK intern immer ein natives GLFW/OpenGL-Fenster öffnet — auch wenn nur die Web-API genutzt wird. Ohne erreichbaren X-Server scheitert der Start. Für eine spätere headless-taugliche CI-Pipeline-Integration wäre das ein offener Punkt (z. B. Xvfb), aktuell nicht gelöst.

## 9. Minimalbeispiele für ein aufrufendes Programm

**curl** (aus beliebigem Verzeichnis):

```bash
curl -s -X POST http://localhost:5266/generate-shape \
  -H "Content-Type: application/json" \
  -d '{"type":"cylinder","values":{"radius":15,"height":80}}'
```

**Python:**

```python
import requests

BASE_URL = "http://localhost:5266"

resp = requests.post(f"{BASE_URL}/generate-shape", json={
    "type": "cylinder",
    "values": {"radius": 15.0, "height": 80.0},
})
resp.raise_for_status()
data = resp.json()

stl_bytes = requests.get(f"{BASE_URL}{data['fileUrl']}").content
with open("cylinder.stl", "wb") as f:
    f.write(stl_bytes)
```

Kurz zusammengefasst: Basis-URL fest verdrahten (`http://localhost:5266`), `fileUrl` aus der Antwort nehmen statt zu raten, Server vorher separat starten und erreichbar prüfen, mit serieller Verarbeitung und fehlendem Auto-Cleanup rechnen.
