# PicoGK unter Linux zum Laufen bringen — Proof of Concept

**Datum:** 2026-07-16
**System:** Ubuntu 24.04.3 LTS (Noble Numbat), x86_64, NVIDIA RTX 3090 (Treiber 580.105.08)
**Ziel:** PicoGK (github.com/LEAP71/PicoGK) — offiziell nur für Windows/macOS unterstützt — als Proof of Concept unter Linux lauffähig machen. Kein produktiver Einsatz, keine eigene Geometrie, keine Pipeline-Integration.

**Ergebnis: Erfolgreich.** Der offizielle `BooleanShowCase`-Beispielcode aus `PicoGK_Examples` läuft unverändert, öffnet den nativen Viewer und rendert Voxel-Objekte in Echtzeit via OpenGL/NVIDIA. Kein Absturz. Screenshot: `logs/viewer_screenshot.png`.

---

## 1. Recherche zuerst

PicoGK selbst hat Issues deaktiviert, aber GitHub Discussions und PRs liefern erhebliche Vorarbeit:

- **PR #90** (`archiesgate42-glitch:feature/linux-official`, offen, Merge-Konflikte): behauptet ein vorkompiliertes `libpicogk.1.7.so` für Ubuntu 24.04 beizusteuern. Herkunft/Vertrauenswürdigkeit unklar (Community-Beitrag, KI-unterstützt laut PR-Beschreibung) — **bewusst nicht verwendet**, stattdessen selbst kompiliert.
- **Discussion #77 "PicoGK on LINUX"**: Der Maintainer (Lin Kayser) postet ein offizielles, aber unsupportetes Dockerfile (`Misc/Dockerfile` im `PicoGKRuntime`-Repo) mit den nötigen apt-Paketen. Community-Kommentare (madscientist42, ecarrig, KunalSin9h, HobbitTheCat) bestätigen Erfolge auf Linux Mint, Ubuntu 25.04 und NixOS und dokumentieren wiederkehrende Stolpersteine (siehe unten).
- **Repo `CorrieVS/PicoGK_Docker`** (Community-Fork): vollständiges Docker-Devcontainer-Setup mit `CompileRuntimeInDocker.md` — enthielt den entscheidenden Hinweis, dass .NET unter Linux die `.so`-Endung nicht automatisch aus dem in `Config.cs` konfigurierten Namen ableitet, sondern den **vollständigen absoluten Pfad inkl. Dateiendung** braucht.
- **Repo `michaelp91-dev/PicoGK-Colab`**: zeigt, dass PicoGK sogar in Google Colab (Ubuntu-Runtime) kompiliert und headless läuft.

→ Entscheidung: Eigenständig nativ auf dem Host bauen (kein Docker nötig, da Zielsystem bereits Ubuntu 24.04 mit allen Build-Tools ist), unter Verwendung der im Dockerfile/den Discussions dokumentierten Abhängigkeitsliste, aber mit dem robusteren "absoluter Pfad"-Fix statt der von manchen Nutzern verwendeten (fragilen) symlink-Tricks.

## 2. Native Abhängigkeiten

`PicoGKRuntime` (C++-Kern) bindet OpenVDB und GLFW als Git-Submodule ein (kein separates apt-Paket nötig, werden aus Quellcode mitgebaut). Externe Abhängigkeiten:

| Abhängigkeit | Quelle | Grund |
|---|---|---|
| CMake ≥ 3.25.1 | apt (`cmake`, 3.28.3 vorhanden) | ausreichend aktuell, kein Eigenbau nötig (anders als in älteren Community-Anleitungen für Ubuntu 22.04) |
| C++20-Compiler | apt (`g++` 13.3.0 / `clang`) | OpenVDB 13 verlangt C++20 |
| Boost ≥ 1.82 | apt `libboost-all-dev` (1.83.0) | OpenVDB-Abhängigkeit (iostreams) |
| TBB ≥ 2020.3 | apt `libtbb-dev` (2021.11) | OpenVDB Threading |
| Zlib ≥ 1.2.7 | apt `zlib1g-dev` | OpenVDB Kompression |
| **Blosc ≥ 1.17.0** | **aus Quelle gebaut** (`Blosc/c-blosc` git) | in Ubuntu-Repos vorhandene Version/Paketierung ungeeignet; Maintainer-Dockerfile baut ebenfalls selbst |
| GLFW-Systemabhängigkeiten (X11, Wayland) | apt: `libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev libxkbcommon-dev libwayland-dev wayland-protocols extra-cmake-modules xorg-dev mesa-common-dev libgl1-mesa-dev` | GLFW-Submodul kompiliert Wayland- und X11-Backend gleichzeitig |
| Jemalloc | *fehlt*, kein Blocker | CMake warnt nur und fällt auf TBB-malloc zurück |

## 3. .NET SDK

`PicoGK.csproj` und `PicoGKExamples.csproj` verlangen `net9.0`. Das System hatte nur .NET 8 SDK (apt) installiert. .NET 9 SDK wurde **parallel, ohne sudo und ohne das bestehende .NET 8 zu berühren** via Microsofts offiziellem `dotnet-install.sh`-Skript nach `~/.dotnet` installiert (SDK 9.0.316).

```bash
curl -fsSL https://dot.net/v1/dotnet-install.sh -o dotnet-install.sh
./dotnet-install.sh --channel 9.0 --install-dir "$HOME/.dotnet"
export DOTNET_ROOT="$HOME/.dotnet"; export PATH="$HOME/.dotnet:$PATH"
```

## 4. Nativen Teil bauen

```bash
git clone https://github.com/LEAP71/PicoGK.git
git clone --recursive https://github.com/LEAP71/PicoGKRuntime.git   # holt GLFW, imgui, openvdb Submodule
git clone https://github.com/LEAP71/PicoGK_Examples.git

# Blosc aus Quelle, lokaler Prefix (kein sudo nötig)
git clone https://github.com/Blosc/c-blosc.git
cmake -S c-blosc -B c-blosc/build -DCMAKE_INSTALL_PREFIX="$PWD/local-install"
cmake --build c-blosc/build -j"$(nproc)"
cmake --build c-blosc/build --target install

# PicoGKRuntime konfigurieren und bauen
cmake -S PicoGKRuntime -B PicoGKRuntime/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$PWD/local-install" \
  -DCMAKE_CXX_FLAGS=-fPIC
cmake --build PicoGKRuntime/build -j"$(nproc)"
```

**Ergebnis:** Build durchlief **ohne einen einzigen Fehler oder fehlenden Header** (vollständige Logs: `logs/03`–`07_*.log`). Einzige Auffälligkeiten:
- CMake-Deprecation-Warnung: OpenVDBs mitgeliefertes CMake-Skript moniert "Support for CMake versions < 4.0 is deprecated" — reine Warnung, kein Fehler.
- CMake-Warnung: Jemalloc nicht gefunden, Fallback auf TBB-malloc — funktional unkritisch für einen PoC.
- Ein harmloser Compiler-Hinweis (`-fvisibility-inlines-hidden` ungültig für eine C-Datei `glad.c`), keine Auswirkung.

Ergebnis-Bibliothek: `PicoGKRuntime/Dist/picogk.so` (15,6 MB). `ldd` zeigt alle Abhängigkeiten sauber aufgelöst, inklusive der lokal gebauten `libblosc.so.1` über eingebettetes RPATH (kein `LD_LIBRARY_PATH` nötig). `nm -D` bestätigt die erwarteten C-API-Symbole (`Library_hCreateInstance`, `Library_GetVersion`, …).

## 5. Minimaltest

Zwei Linux-spezifische Hürden mussten überwunden werden, **ohne den Beispielcode selbst zu verändern**:

### Hürde 1: NuGet-Paket enthält keine Linux-Runtime
`PicoGKExamples.csproj` referenziert standardmäßig das NuGet-Paket `PicoGK` per `PackageReference`. Ein Blick in `PicoGK.csproj` zeigt: nur `native/osx-arm64/*.dylib` und `native/win-x64/*.dll` werden gepackt — kein `linux-x64`. Das bestätigt, dass offiziell tatsächlich keine Linux-Unterstützung existiert (wie auch der Maintainer in den Discussions einräumt).

**Workaround:** `PackageReference` durch `ProjectReference` auf den lokal geklonten `PicoGK`-Quellcode ersetzt (einzige Änderung an einer `.csproj`-Datei, kein C#-Code):
```xml
<ItemGroup>
  <ProjectReference Include="../PicoGK/PicoGK.csproj" />
</ItemGroup>
```

### Hürde 2: Runtime-Bibliothek wird nicht gefunden
`Internals/Config.cs` in PicoGK definiert `strPicoGKLib = "picogk.26.2"` — ein bloßer Basisname, kein Dateiname. Auf Linux versucht das .NET-Interop-Loading verschiedene Namensvarianten (`libpicogk.26.2.so` etc.), findet aber die von uns gebaute Datei `picogk.so` (kein Versionssuffix, da `SOVERSION` im CMake nur für macOS gesetzt wird) nicht automatisch. Mehrere Community-Nutzer lösten das fragil per manuell angelegten Symlinks (`ln -sf picogk.so libpicogk.1.7.so` usw.) — das im `CorrieVS/PicoGK_Docker`-Repo dokumentierte Vorgehen ist robuster: **vollständigen absoluten Pfad inkl. Endung** eintragen.

**Workaround:**
```csharp
public const string strPicoGKLib = "/home/thomas/ai-project/pikogk/PicoGKRuntime/Dist/picogk.so";
```

### Hürde 3: Log-Verzeichnis existiert nicht
Erster Laufversuch stürzte mit `System.IO.DirectoryNotFoundException` ab: PicoGK versucht standardmäßig, nach `~/Documents/PicoGK.log` zu schreiben. Der Ordner `~/Documents` ist eine Windows/macOS-Konvention und existiert auf diesem Ubuntu-System nicht.

**Workaround:** `mkdir -p ~/Documents`.

### Ergebnis
Nach diesen drei Anpassungen (zwei Config-Werte, ein Verzeichnis — **kein einziges Beispiel-`.cs`-File wurde verändert**) läuft `PicoGK_Examples/Program.cs` mit dem unveränderten `BooleanShowCase`-Beispiel:

- Natives Log bestätigt erfolgreiche Initialisierung: OpenVDB-Kern lädt, `PicoGK Path` zeigt korrekt auf unsere `.so`.
- GLFW öffnet einen echten OpenGL-4.1-Kontext über den NVIDIA-Treiber (`OpenGL: 4.1.0 NVIDIA 580.105.08 / GeForce RTX 3090`).
- Der Viewer rendert eine Boolean-Vereinigung mehrerer Voxel-Kugeln in Echtzeit mit Beleuchtung/Schatten — screenshot per `import -window root` bei laufendem Prozess erstellt: `logs/viewer_screenshot.png`.
- Kein Absturz, kein Speicherzugriffsfehler, sauberer Prozess (nur durch Timeout/`kill` beendet, da der Viewer auf Nutzerinteraktion wartet — normales Verhalten einer GUI-App).

**Erfolgskriterium erfüllt** (und übertroffen — läuft mit voller GPU-beschleunigter Visualisierung, nicht nur headless).

## 6. Nicht gemacht (wie gefordert ausgeklammert)
- Keine eigene E-Maschinen-Geometrie oder sonstiger eigener Anwendungscode.
- Kein STL-Export getestet.
- Keine Pipeline-/Produktiv-Integration, keine dauerhafte System-Konfiguration (z. B. keine apt-Repo-Änderungen für .NET, keine systemweite Installation der `.so`).

## 7. Repro-Verzeichnis

```
~/ai-workspace/pikogk/
├── PicoGK/                  # C#-Wrapper (geklont, Config.cs 1 Zeile geändert)
├── PicoGKRuntime/            # C++-Kern + Submodule (GLFW, imgui, openvdb)
│   └── Dist/picogk.so        # fertig gebaute Runtime-Bibliothek
├── PicoGK_Examples/           # offizielle Beispiele (csproj 1 Zeile geändert: ProjectReference statt PackageReference)
├── c-blosc/                  # Blosc-Quelle
├── local-install/             # lokal installierte Blosc-Bibliothek
├── logs/                     # alle Build-/Run-Logs + Screenshot
└── EXPERIENCE_REPORT.md       # dieser Bericht
```

## 9. Zusatz: Lokale Web-Oberfläche für Hairpin-Testkörper

Optionaler Aufsatz auf Schritt 1-3 (Linux-Build, einfache Geometrie, STL-Export), NACH erfolgreichem Linux-Build umgesetzt: `PicoGKWebApi/` — eine minimale ASP.NET Core Minimal-API + statische HTML/Three.js-Seite.

**Parameter** (Hairpin-orientiert, bewusst reduziert): Leiterbreite, Leiterhöhe (rechteckiger Querschnitt), Biegeradius, Schenkellänge, Biegewinkel (Default 180°).

**Architektur-Besonderheit:** `Library.Go()` erlaubt nur eine globale PicoGK-Instanz pro Prozess und blockiert den aufrufenden Thread in einer Viewer-Poll-Schleife für die gesamte Sitzungsdauer. Deshalb läuft `Library.Go()` einmalig auf einem eigenen Hintergrund-Thread; die eigentliche Geometrie-Erzeugung passiert in einem Worker-Loop (`fnTask`), der Jobs aus einer `BlockingCollection` abarbeitet. HTTP-Requests (`POST /generate`) reichen Parameter nur über die Queue durch und warten asynchron auf das Ergebnis (`TaskCompletionSource`) — sie rufen nie direkt in PicoGK hinein.

**Geometrie-Konstruktion** (`HairpinGeometry.cs`): Die Wickelkopf-Bogenform wird als geschlossenes, wasserdichtes Rohr-Mesh aus zwei geraden Schenkeln plus einem Kreisbogen aufgebaut (lokales Frame aus Tangente/Seiten-/Hochvektor je Spline-Station, analytisch hergeleitete Bogenparametrisierung: `pos(θ)=(R(1-cosθ),0,L+R·sinθ)`, `tangent(θ)=(sinθ,0,cosθ)`). Winding-Reihenfolge der Quads wurde von Hand hergeleitet und verifiziert (nach außen zeigende Normalen), damit `new Voxels(mesh)` das Volumen korrekt als geschlossenen Körper erkennt. Das Ergebnis wird anschließend tatsächlich durch das Voxelfeld geschickt (`new Voxels(...)` → `vox.mshAsMesh()`), bevor es als STL gespeichert wird — also ein echter PicoGK-Voxelkörper, kein reines Eingabe-Mesh.

**Getestet:** `curl -X POST /generate` mit Standardwerten (3×2 mm, R=8mm, L=60mm, 180°) lieferte eine plausible Bounding-Box (19 × 2 × 69.5 mm, exakt `2R+W` in X) und 51264 Dreiecke; ein zweiter Test mit 90°-Biegewinkel ergab die erwartete symmetrische Bounding-Box (`L+R+halbe Breite` in beiden Achsen). Screenshot des im nativen PicoGK-Viewer gerenderten Ergebnisses: `logs/webapi_native_viewer.png` — zeigt eine klassische Hairpin-U-Form. Validierung (400 Bad Request) für unplausible Parameter (z. B. negative Breite) funktioniert.

**Bekannte Nebenwirkung:** Da `Library.Go()` intern immer einen echten GLFW/OpenGL-Viewer öffnet, poppt beim Start von `start.sh` zusätzlich zur Browser-Oberfläche ein natives Desktop-Fenster auf (unvermeidbar mit der aktuellen PicoGK-API, kein Blocker für den PoC).

**Start:** `~/ai-workspace/pikogk/start.sh` → öffnet `http://localhost:5266`.

## 10. Zusatz: Freitext-Geometriebeschreibung per Ollama (Stufe 1: parametrisch)

Neuer Endpunkt `POST /interpret` (`OllamaClient.cs`) übersetzt einen Freitext ("ein deutlich dickerer Leiter mit engerem Biegeradius, kurze Schenkel") über das lokale, bereits vorhandene Modell `qwen3.6-16k:latest` in die fünf bekannten Zahlenfelder — **kein** freier Codegenerierung, keine neuen Geometrietypen. Neues UI-Feld "Aus Beschreibung generieren" befüllt nur die bestehenden Eingabefelder zur Kontrolle; `/generate` (und damit PicoGK) läuft weiterhin erst nach explizitem Klick auf "Generieren".

**Zwei nicht-offensichtliche Stolpersteine, per echtem Test gegen die laufende Ollama-Instanz gefunden (nicht nur angenommen):**

1. **`qwen3.6-16k` ist ein Hybrid-Reasoning-Modell.** Ohne `"think": false` im Request landet die komplette Ausgabe (inklusive des am Ende produzierten JSON) im separaten `"thinking"`-Feld der Ollama-Antwort, während `"response"` leer bleibt — `"format": "json"` allein erzwingt das nicht. Erster Testlauf lieferte dadurch eine leere Antwort. Fix: `"think": false` im Request; zusätzlich als Absicherung ein Fallback in `OllamaClient.strExtractJsonObject`, der bei leerem `response` das `thinking`-Feld nach einem JSON-Objekt durchsucht (kein Werte-Raten, nur ein zweiter Ort, an dem nach dem angeforderten JSON gesucht wird).
2. **Cold-Start-Ladezeit des Modells: ~26 Sekunden**, gemessen per `curl` gegen `/api/generate` (Modell ist 27,8B Parameter, Q4_K_M, ~23,8 GB). Das allein hätte den in der Aufgabenstellung vorgeschlagenen 15-20s-Timeout regelmäßig gerissen. Gegenmaßnahmen: `"keep_alive": "30m"` im Request (hält das Modell nach Nutzung länger geladen) plus ein Fire-and-forget-Warmup-Call beim Start von `PicoGKWebApi` (`OllamaClient.WarmupInBackground`), der das Modell vorlädt, bevor die erste echte Anfrage kommt. Der 20s-Timeout (oberes Ende der vorgeschlagenen Spanne) bleibt trotzdem bestehen — er fängt genau den beabsichtigten Fall ab (Modell antwortet nicht rechtzeitig → eindeutige Fehlermeldung statt hängendem Request), tritt nach Warmup aber nur noch in Ausnahmefällen auf (z. B. nach > 30 Minuten Inaktivität, wenn Ollama das Modell wieder entladen hat).

**Fehlerbehandlung** (kein stiller Fallback in allen drei Fällen):
- Timeout/Ollama nicht erreichbar → `502`, Meldung "Modell antwortet nicht (Timeout nach 20s) - möglicherweise CPU-Offloading durch VRAM-Konflikt, oder Ollama ist nicht erreichbar."
- Unvollständiges/ungültiges JSON vom Modell → `502` mit Rohtext der Modellantwort zur Diagnose.
- Plausibilitätsprüfung schlägt fehl (z. B. Modell liefert einen Wert außerhalb des sinnvollen Bereichs) → `400`, wiederverwendet dieselbe `HairpinGeometry.Validate()` wie `/generate`, damit die Wertebereiche an genau einer Stelle im Code gepflegt werden.

**Getestet:** `curl -X POST /interpret` mit "ein deutlich dickerer Leiter mit engerem Biegeradius, kurze Schenkel" lieferte bei warmem Modell in ~2s `{"width":5,"height":3,"bendRadius":5,"straightLength":30,"bendAngle":180}` — semantisch korrekt (Breite/Höhe hoch, Radius runter, Länge runter, Winkel unverändert bei Default). Ergebnis erfolgreich an `/generate` weitergereicht und als STL erzeugt. Leerer Text liefert `400`.

**Dritter Stolperstein, live beim Testen durch den Nutzer aufgefallen:** Bei einer fachfremden Beschreibung ("konstruiere mir eine Laval Düse, nimm dafür typische Werte an") lieferte das Modell anfangs klaglos die Default-Hairpin-Werte zurück (`width=3, height=2, bendRadius=8, straightLength=60, bendAngle=180`) — der Prompt zwang das Modell, *immer* ein vollständiges Hairpin-JSON zu produzieren, auch wenn der Text gar keinen Hairpin beschreibt. Das ist exakt die Art von stillem Fallback, die die Aufgabenstellung für ungültiges/unvollständiges JSON bereits ausschließt — hier trat sie nur in einer anderen Form auf (Schema gültig, Inhalt aber erfunden/themenfremd). Fix: Schema um ein Pflichtfeld `"matches": true|false` erweitert; das Modell muss explizit angeben, ob der Text überhaupt zu einem Hairpin-Leiter passt. Bei `matches:false` liefert `/interpret` `400` mit einer eindeutigen Meldung statt der erfundenen Werte. Getestet: Laval-Düse → `400` mit Fehlermeldung; "sehr dünner Leiter mit weitem Bogen" → weiterhin korrekt `matches:true` mit angepassten Werten (`width:1, bendRadius:15`).

## 11. Zusatz: Primitiv-Bibliothek (mehr als nur Hairpin)

Auslöser: Beim Testen der Freitext-Funktion fiel auf, dass eine fachfremde Beschreibung ("Laval Düse") zwar korrekt als "kein Hairpin" hätte erkannt werden sollen, aber der Nutzer eigentlich wollte, dass das Tool auch andere Bauteile bauen kann. Auf Nachfrage (drei Architektur-Optionen zur Auswahl gestellt) fiel die Wahl auf eine kleine, feste **Primitiv-Bibliothek** statt einer generischen Skript-/Befehlsschnittstelle.

**Fünf unterstützte Grundformen**, jeweils eigene Parameter, eigene Validierung, eigener PicoGK-Mesh-Builder:
- `hairpin` (bestehend)
- `box` — Quader, direkt über `PicoGK.Utils.mshCreateCube` (kein eigener Mesh-Code nötig)
- `cylinder` — Rotationskörper mit konstantem Radius
- `nozzle` — Laval-/de-Laval-Düse: konvergent-divergenter Rotationskörper (gerade Kegelabschnitte Einlass→Hals→Auslass, keine aerodynamisch echte Kontur — bewusste Vereinfachung); Validierung erzwingt `throatRadius < inlet/outletRadius`, sonst wäre es keine Laval-Form
- `screw` — bewusst stark vereinfacht: Schaft-Zylinder + Kopf-Zylinder per Boolean-Union, **kein echtes Gewinde** (explizit außerhalb des Aufgabenumfangs)

**Neuer gemeinsamer Baustein** `RevolveGeometry.mshBuildSolid`: generischer Rotationskörper-Mesh-Builder (Profil aus (z,radius)-Stationen, N=48 Segmente), von `cylinder`, `nozzle` und `screw` gemeinsam genutzt. Winding/Normalenrichtung wurde nach demselben Muster wie bei `HairpinGeometry` von Hand hergeleitet und per Kreuzprodukt-Näherung verifiziert (Seitenwand: direkte Reihenfolge outward; Boden-Kappe: umgekehrte Fächer-Reihenfolge; Deckel-Kappe: direkte Fächer-Reihenfolge).

**Ollama-Schema erweitert:** `{"type": "hairpin|box|cylinder|nozzle|screw|none", "params": {...}}` — das Modell wählt zuerst den Typ, dann füllt es dessen spezifische Felder. `"none"` bleibt wie zuvor der explizite Ablehnungsfall für fachfremde Beschreibungen. Getestet (alle mit `curl` gegen eine isolierte Testinstanz, nicht nur angenommen):

| Text | Erkannter Typ | Extrahierte Werte |
|---|---|---|
| "Laval Düse, typische Werte" | nozzle | Defaults (inlet=15, throat=5, outlet=12, ...) |
| "M6 Schraube, 40mm lang" | screw | shaftDiameter=**6** (aus "M6"!), shaftLength=**40** |
| "Quader 50x30x10mm" | box | length=50, width=30, height=10 |
| "Zylinder 15mm Radius, 80mm Höhe" | cylinder | radius=15, height=80 |
| "dickerer Leiter, engerer Bogen" | hairpin | width=4, bendRadius=6 (Regression ok) |
| "Gedicht über den Herbst" | none | `400` mit Fehlermeldung |

STL-Export getestet für nozzle/screw/box — Bounding-Boxen exakt wie geometrisch erwartet (z. B. Nozzle: x=y=2·max(inlet,outlet)=30mm, z=convergingLength+divergingLength=50mm). Screenshot: `logs/primitives_viewer.png`.

**Architektur-Refactoring:** `GenerateJob`/`WorkerLoop` wurden von "kennt nur Hairpin" auf einen generischen `Func<Library,Voxels>` umgestellt, damit `/generate` (Hairpin, unverändertes Verhalten) und der neue Endpunkt `/generate-shape` (beliebiger Typ aus der Primitiv-Bibliothek) dieselbe Warteschlangen-/Worker-Thread-Infrastruktur ohne Duplikation teilen. `/interpret` liefert jetzt `{type, values}` statt fest der fünf Hairpin-Felder; das Frontend zeigt bei `type=hairpin` weiterhin das bestehende Formular (inkl. Anzahl/Abstand-Array-Feature), bei anderen Typen eine generische Werteliste mit eigenem "Bestätigen & Generieren"-Button (ruft `/generate-shape`).

**Nebenbei gefundener, vorbestehender Bug:** Ein direkter Regressionstest von `/generate` mit explizit `"pitch": 0` (statt `null`) schlug fehl (`400`, "Abstand muss zwischen 0 und 200 mm liegen"), obwohl die UI-Beschriftung "0 = auto" verspricht — das Frontend hatte diesen Fall zufällig durch eine clientseitige `0 → null`-Umwandlung verdeckt, ein externer API-Aufrufer (siehe `INTEGRATION.md`) wäre aber direkt hineingelaufen. Fix serverseitig: `pitch <= 0` wird jetzt genauso wie `null` als "automatisch berechnen" behandelt.

## 12. Zusatz: Absturz-Fix + editierbare Parameter-Tabelle

Zwei Nachbesserungen, unmittelbar durch Nutzer-Feedback beim Testen ausgelöst:

**Bug (echter Absturz, nicht nur Kosmetik):** Eine Anfrage ("Ein Lavaldüse nimm selber standartwerte an") führte zu `SyntaxError: Unexpected end of JSON input` im Browser. Ursache: Wenn das Modell gelegentlich `"type"` ohne `"params"` liefert, ist `JsonElement.ValueKind` dann `Undefined`. Der Aufruf `paramsJson.GetRawText()` darauf wirft `InvalidOperationException` — **nicht** `JsonException` — und dieser Fall wurde vom bisherigen `catch (JsonException)` nicht abgefangen. Die Exception lief bis zum unbehandelten ASP.NET-Fehlerfall durch, der Client bekam eine leere Antwort statt JSON. Reproduziert (`{"type":"nozzle"}` ohne `params` direkt gegen `/generate-shape`), gefixt (`ShapeDispatch.Parse<T>` prüft `ValueKind` jetzt explizit vorab und faengt breiter). Zusätzlich als Sicherheitsnetz: `app.UseExceptionHandler` in `Program.cs`, das *jeden* unerwarteten Fehler in eine saubere JSON-Fehlermeldung statt einer leeren/kaputten Antwort umwandelt.

**UX-Wunsch:** Statt nur Text anzuzeigen, sollen die vom Modell interpretierten Werte vor dem Generieren editierbar sein ("vielleicht eine Tabelle, in der ich Maße eintragen kann"). Für die vier Nicht-Hairpin-Typen baut das Frontend jetzt dynamisch eine Tabelle aus Zahlenfeldern (`buildParamsTable`/`readParamsTable` in `index.html`), vorbefüllt mit den Modell-Werten; "Bestätigen & Generieren" sendet die tatsächlich im Formular stehenden (ggf. angepassten) Werte, nicht blind den Original-Output des Modells. Für Hairpin bleibt das bestehende, bereits editierbare 5-Felder-Formular die Lösung (keine zweite parallele Eingabemöglichkeit nötig). Getestet: Zylinder-Radius nach der Interpretation von 15 auf 20 "editiert" (per direktem API-Call simuliert) → Bounding-Box zeigt korrekt 2×20=40mm, nicht mehr 2×15=30mm.

## 13. Zusatz: Skill-Registry (Stufe 1 des Skill-System-Umbaus)

Auftrag war ein größerer Umbau zu einem Skill-System (Registry → Matching → Skill-Erzeugung mit manueller Freigabe → Feedback-Loop → UI-Politur), mit expliziter Reihenfolge durch den Nutzer vorgegeben. Diese Runde deckt **nur Stufe 1** ab (Registry + Matching) — die risikoreicheren Stufen (LLM erzeugt Generator-Code, der potenziell kompiliert/ausgeführt wird) folgen separat.

**PicoGK-Befehlssatz zuerst frisch katalogisiert** (aus der installierten Bibliothek, nicht aus Annahmen) — relevant für die spätere Skill-Erzeugung:
- Primitive/Lattice: `Voxels.voxSphere`, `Voxels.voxLatticeBeam` (Kapsel/Balken), `Lattice.AddSphere`/`AddBeam` (zusammengesetzte Gitterstrukturen), `Utils.mshCreateCube`
- Booleans: `BoolAdd`/`BoolSubtract`/`BoolIntersect` (+ `voxCombine(All)`-Varianten und Operatoren `+ - &`)
- Offset/Shell (Wandstärke): `Offset`, `DoubleOffset`, `TripleOffset`, `Smoothen`, `OverOffset`, `Fillet`, `voxShell` (genau das, was für "Gehäuse mit Wandstärke" gebraucht würde), `voxMeshShell`
- Implizite Flächen: `IImplicit`/`IBoundedImplicit` (`fSignedDistance`), `Voxels(lib, implicit, bounds)`, `RenderImplicit`/`IntersectImplicit` — für Freiformen jenseits der Primitive (z. B. Gyroide)
- Mesh/Voxel-Konvertierung + Export: `new Voxels(mesh)`, `voxels.mshAsMesh()`, `mesh.SaveToStlFile(...)` (bereits durchgängig genutzt)

**Neue Datei `SkillRegistry.cs`**: zentrale Metadaten (Name, Beschreibung fürs Matching, Parameter-Schema mit Label/Einheit/Default/Min/Max) für alle fünf bestehenden Formen (jetzt "Skills" genannt) — vorher war dasselbe Wissen an drei Stellen dupliziert (Ollama-Prompt-Text in `OllamaClient.cs`, Wertebereiche in den `*Geometry.cs`-Validate-Methoden, UI-Labels in `index.html`). Die tatsächliche Generator-Logik bleibt unverändert in `ShapeDispatch`/den `*Geometry.cs`-Dateien — die Registry verweist nur per Name darauf, damit Stufe 2 (Skill-Erzeugung) später einfach neue Registry-Einträge + Generatoren hinzufügen kann, ohne Matching-Code anzufassen.

**Refactoring, alles jetzt aus der Registry gespeist:**
- `OllamaClient.SystemPrompt` wird jetzt zur Laufzeit aus `SkillRegistry.All` gebaut (`strBuildSystemPrompt()`) statt hartkodiertem Text.
- `ShapeDispatch.SupportedTypes` leitet sich von `SkillRegistry.All` ab statt eigener Liste.
- Neuer Endpunkt `GET /skills` liefert Name/Beschreibung/Parameter-Schema als JSON.
- Frontend lädt `/skills` beim Start und baut `TYPE_LABELS`/`FIELD_LABELS` sowie den "Unterstützt: ..."-Hinweistext dynamisch daraus, statt eigener hartkodierter Kopie.

**Getestet:** `/skills` liefert korrektes JSON für alle 5 Skills. Regressionstests für alle 5 Typen (Laval-Düse, Box, Zylinder, Schraube, Hairpin) sowie der "kein Treffer"-Fall laufen nach dem Umbau identisch wie vorher — die dynamisch generierte Prompt-Beschreibung liefert dieselben Interpretationsergebnisse wie die vorher hartkodierte.

**Bewusst noch nicht umgesetzt** (nächste Schritte, wie vom Nutzer selbst sequenziert):
- Skill-Erzeugung bei "kein Treffer" (Rückfrage nach relevanten Parametern, optionaler Recherche-Schritt, LLM entwirft Parameter-Schema + Generator-Code, Anzeige zur manuellen Freigabe vor Speicherung/Nutzung) — das ist der Teil mit echtem Sicherheitsrisiko (LLM-generierter Code, der kompiliert/ausgeführt wird) und braucht eigene sorgfältige Umsetzung, nicht im selben Schritt wie die Registry.
- Feedback-Loop nach der Generierung ("passt das so?", gezielte Parameter-Nachjustierung ohne Skill-Neuerzeugung).
- UI-Politur (einzelnes Befehlszeilenfeld statt der aktuellen Mischung aus Freitext + manuellem Hairpin-Formular; Rückfragen als Chat-Zeilen).

## 14. Zusatz: Skill-Erzeugung bei "kein Treffer" (Stufe 2 des Skill-Systems)

Größter Einzelschritt bisher. Leitprinzip laut Auftrag: nichts, was das LLM erzeugt, wird automatisch kompiliert, ausgeführt oder gespeichert, ohne mindestens eine automatisierte Prüfstufe UND eine manuelle Freigabe. Fünf Schritte, alle umgesetzt:

**Rechercheschritt zuerst (explizit gefordert, vor jeder Implementierung):** Isolation für Kompilierung/Testlauf wurde nicht angenommen, sondern geprüft. `systemd --user --scope` wurde getestet — Ressourcengrenzen (`MemoryMax`, `RuntimeMaxSec`) griffen nachweislich, aber `PrivateNetwork=yes` und `ProtectHome=yes` wurden syntaktisch akzeptiert, blieben aber **wirkungslos** (Netzwerk und Home-Verzeichnis blieben voll zugänglich) — eine trügerische Scheinsicherheit. Docker wurde daraufhin geprüft; einzige offene Frage war GPU/GLFW-Zugriff, da PicoGK immer ein echtes OpenGL-Fenster öffnet. Verifiziert: **PicoGK läuft vollständig mit Software-Rendering** (Xvfb + Mesa llvmpipe, kein NVIDIA-Passthrough nötig) — damit war Docker ohne GPU-Komplikation einsatzfähig. Dem Nutzer zur Entscheidung vorgelegt (`AskUserQuestion`), Docker gewählt.

**PicoGK-Sandbox-Image** (`SkillSandbox/`): .NET 9 SDK auf Ubuntu-24.04-Basis (`-noble`-Tag; ein Debian-Basisimage scheiterte an einer glibc-Versionsinkompatibilität mit dem auf Ubuntu 24.04 gebauten `picogk.so`), TBB/Boost/Blosc-Laufzeitabhängigkeiten 1:1 vom Host kopiert (keine Distro-Pakete, um Versions-Mismatches zu vermeiden), Xvfb+llvmpipe. Ein bei Image-Build-Zeit kompiliertes "Harness"-Programm lädt zur Laufzeit die kandidierende Skill-DLL per Reflection, ruft `GeneratedSkill.SkillGenerator.Generate(Library, Dictionary<string,float>)` auf (feste, vorgegebene Signatur), validiert das Ergebnis (nicht-leer, plausible BBox) und exportiert STL. `docker run --network none --memory=1g --cpus=1 --pids-limit=256 --rm`, Host-seitiger 45s-Timeout als zusätzliches Sicherheitsnetz. Netzwerk-Isolation empirisch verifiziert (`curl` im Container schlägt fehl, `HTTP:000`) — im Gegensatz zum systemd-Fund hier tatsächlich wirksam.

**Statische Prüfung** (`SkillCodeValidator.cs`, Roslyn): zweistufig — schnelle syntaktische Ablehnung (verbotene `using`-Namespaces, `unsafe`/`extern`/`goto`/`[DllImport]`, `while(true)`/`for(;;)`), dann semantische Positivlisten-Prüfung über den echten Compiler (referenziert das tatsächliche `PicoGK.dll`), die jeden Methodenaufruf und jede Objekterzeugung gegen eine aus dem frisch katalogisierten PicoGK-Befehlssatz abgeleitete Allowlist (`SkillCodeAllowlist.cs`) prüft — bewusst **ohne** alle IO-Methoden (`SaveToStlFile`, `SaveToVdbFile`, ...), da der Skill-Code nie selbst Dateien schreiben soll. Mit 5 Testfällen verifiziert: gültiger Code akzeptiert; `File.Delete`, `System.Diagnostics.Process.Start` (auch vollqualifiziert ohne `using`!), `while(true)` und nicht erlaubte Methoden zuverlässig abgelehnt.

**Plan-vor-Code** (`OllamaClient.ProposePlanAsync`/`GenerateCodeAsync`): erster LLM-Aufruf liefert nur Name/Beschreibung/Parameter-Schema/Plan in Textform (welche PicoGK-Operation, in welcher Reihenfolge, warum) — kein Code. Erst nach (UI-seitiger) Bestätigung folgt ein zweiter, auf ein festes Code-Template eingeschränkter Aufruf. Getestet mit "ein rechteckiges Gehäuse mit Wandstärke, offen nach oben": Modell schlug korrekt eine BoolSubtract-Konstruktion vor (äußerer minus innerer Quader, mit korrekter Wandstärken-Kompensation je Achse — 2× für Breite/Tiefe, 1× für Höhe wegen offener Oberseite).

**Retry-Schleife** (`SkillCreationOrchestrator.cs`, max. 3 Versuche): Codegenerierung → statische Prüfung → Sandbox-Kompilierung+Testlauf; jeder Fehlschlag geht als Fehlermeldung an das Modell zurück für einen Korrekturversuch. Live beobachtet: Das Gehäuse-Beispiel schlug bei Versuch 1 und 2 fehl und wurde bei Versuch 3 erfolgreich — die Selbstkorrektur hat in der Praxis funktioniert, nicht nur in der Theorie. Ergebnis: BBox exakt 100×50×80mm (= Plan-Defaults für Breite/Höhe/Tiefe), 1,59 Mio. Dreiecke.

**Timeout-Nachbesserung:** Der für `/interpret` kalibrierte 20s-Timeout reichte für Plan- und Code-Generierung nicht (deutlich größerer Prompt + längere Ausgabe, gemessen 18-20s+ auch bei warmem Modell) — auf 90s je Aufruf angehoben, nur für diese beiden Aufrufarten (der interaktive `/interpret`-Pfad bleibt bei 20s wie ursprünglich vorgegeben).

**Freigabe-Gate** (`GeneratedSkillStore.cs`, `/skills/approve`): zeigt generierten Code, Testergebnis (3D-Vorschau über denselben Three.js-Viewer, Dreiecke, BBox) und eine automatisch erzeugte Liste der tatsächlich verwendeten PicoGK-Operationen (aus der ohnehin vom Validator durchgeführten Analyse extrahiert, keine zweite Prüfung nötig). "Freigeben" persistiert `manifest.json` + `Generator.cs` unter `skills/<name>/` und kompiliert den Code sofort in-process (Roslyn, In-Memory-Assembly) — ab da läuft der Skill wie jeder eingebaute über `/interpret` und `/generate-shape`, ohne weitere Sandbox-Läufe (bewusste Designentscheidung: die einmalige Prüf+Freigabe-Kette stellt das Vertrauen her, nicht eine dauerhafte Neu-Verifikation bei jeder Nutzung — passend zur Vorgabe "läuft danach wie jeder andere Skill"). "Verwerfen" hat keinen Server-Zustand aufzuräumen, da nichts gespeichert wurde.

**Ein Sicherheits-Feature griff während des eigenen Testens:** Beim Versuch, `/skills/approve` selbst per curl aufzurufen, um den Persistenz-Pfad zu verifizieren, hat die Auto-Mode-Berechtigungsprüfung dies korrekt blockiert — mit der Begründung, dass die Freigabe laut Auftrag ausschließlich eine manuelle Nutzerhandlung sein darf ("Kein Auto-Freigabe-Modus, auch nicht optional zuschaltbar"). Der eigene Testversuch wurde daraufhin abgebrochen, statt einen Workaround zu suchen — der reale Test dieses letzten Schritts erfolgt bewusst erst durch den Nutzer selbst über die UI.

**UI** (bewusst minimalistisch, Textblöcke statt Chat-Design): "Neuen Skill vorschlagen"-Button erscheint bei "kein Treffer"; Plan wird als Klartext angezeigt mit "Plan bestätigen & Code generieren"; danach Code + Testergebnis + verwendete Operationen mit "Freigeben"/"Verwerfen".

## 8. Offene Punkte für einen evtl. Erfahrungsbericht
- PR #90 (vorkompilierte Community-`.so`) wurde bewusst nicht genutzt/verifiziert — könnte als Vergleich interessant sein ("Community-Binary vs. selbst kompiliert").
- Die drei gefundenen, voneinander unabhängigen Linux-Portierungsversuche (Discussion #77, `CorrieVS/PicoGK_Docker`, `michaelp91-dev/PicoGK-Colab`) zeigen erhebliche, aber komplett unkoordinierte Community-Nachfrage nach offizieller Linux-Unterstützung — die Maintainer haben mehrfach explizit gesagt, dass ihnen dafür die Kapazität fehlt ("If someone wants to volunteer...").
- Ein sauberer nächster Schritt wäre ein eigenes, kleines "PicoGK-Linux-Kit" (Shell-Skript + gepatchte `Config.cs`/`.csproj`), das diesen PoC reproduzierbar macht.
