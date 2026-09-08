// ── Was ema_agent.html und ema_studio.html gemeinsam haben ───────────────────
//
// Ereignisstrom, Mitlaufen, Stoppuhr, Archivwiedergabe, Bildschirmaufnahme und
// die Kopfklammer. Das stand bis zum dritten Kopf in ema_agent.html; die zweite
// Seite haette es abschreiben muessen, und die Abschrift waere beim ersten
// Fehlerbericht auseinandergelaufen -- dieselbe Ueberlegung, aus der PI, Hermes
// und Studio EINE SKILL.md lesen statt dreier Kopien.
//
// Die Aufteilung ist nicht „alles Gemeinsame", sondern eine Grenze mit einem
// Kriterium: hier steht, was VERHALTEN ist; in der Seite bleibt, was AUSSEHEN
// ist. Deshalb ruft diese Datei Funktionen auf, die die Seite mitbringen MUSS:
//
//   links(art, text) -> Element   eine Zeile/Blase in den Verlauf
//   kachelText(e), kachelBild(e)  ein Ergebnis, ein Bild
//   zustand(s)                    Zustandsanzeige ('arbeitet'|'bereit'|'beendet')
//   denkenUm()                    Denkzeilen ein-/ausblenden
//   ordnerZeigen(o), gesichertZeigen(a)
//   arbeitZeigen(d)               die Arbeitsanzeige (Form ist Sache der Seite)
//
// und die Seite benutzt von hier: K(), lauschen(), frageSenden(), stoppen(),
// videoUm(), archivAuf(), arbeitStart(), folgeUeberwachen(), uhrTick().

// ── Welcher Agentenkopf, und mit welchem Token? ──────────────────────────────
// EINE Seite je Layout, mehrere Koepfe -- unterschieden allein durch ?kopf=.
// Der Server liest ``kopf`` aus der Abfragezeichenkette, auch bei POST; deshalb
// genuegt es, JEDE Adresse durch K() zu schicken.
//
// Das Token gilt nur fuer den Studio-Kopf: seine Seite steht absichtlich im
// Heimnetz. Es kommt aus ``?t=`` (dem QR) oder aus dem Speicher des Browsers,
// damit ein Startbildschirm-Eintrag es nicht bei jedem Aufruf braucht.
// Ehrlich dazugesagt: die uebrigen Routen dieses Servers sind offen wie eh und
// je -- das Token haelt Gelegenheitszugriffe von der Studio-Seite fern, es ist
// keine Benutzerverwaltung und war nie als eine gemeint.
// ``KOPF_VORGABE`` setzt die Seite, BEVOR sie diese Datei laedt. Ohne das faellt
// die Studio-Seite auf 'pi' zurueck, sobald ``?kopf=`` fehlt -- und genau so kommt
// sie ueber den QR herein (``/studio?t=…``): das Handy triebe dann den falschen
// Kopf, und niemand saehe daran etwas Ungewoehnliches.
const KOPF = (new URLSearchParams(location.search).get('kopf') ||
              window.KOPF_VORGABE || 'pi').toLowerCase();
const TOKEN = (() => {
  const aus = new URLSearchParams(location.search).get('t') || '';
  try{
    if(aus) localStorage.setItem('cae_token', aus);
    return aus || localStorage.getItem('cae_token') || '';
  }catch(_){ return aus; }
})();
const K = u => {
  const s = u + (u.includes('?') ? '&' : '?') + 'kopf=' + encodeURIComponent(KOPF);
  return TOKEN ? s + '&t=' + encodeURIComponent(TOKEN) : s;
};

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

let LETZT = 0, LAEUFT = false, ABBRUCH = null;
let blaseDenken = null, blaseText = null;
let LABEL = 'PI';

// Wohin gerendert wird, steht in SPALTEN und nicht fest im Code: das Archiv
// zeichnet einen alten Lauf mit GENAU denselben Funktionen wie der laufende
// Strom. Ein zweiter Satz Zeichenfunktionen fuers Archiv waere ein Satz, der mit
// dem ersten auseinanderlaeuft -- das durchsichtige Feldbild bekaeme dort dann
// kein Schachbrett, weil jemand die eine Zeile im anderen Zweig vergisst.
// Umgeschaltet wird nur synchron (Wiedergabe ist eine for-Schleife), deshalb
// kann kein Live-Ereignis dazwischenrutschen.
let SPALTEN = {l:'links', r:'rechts'};

// ── Ereignisstrom ────────────────────────────────────────────────────────────
async function lauschen(){
  ABBRUCH = new AbortController();
  let rest = '';
  try{
    const r = await fetch(K('/agent/strom?ab=' + LETZT), {signal: ABBRUCH.signal});
    const leser = r.body.getReader(), dek = new TextDecoder();
    while(true){
      const {value, done} = await leser.read();
      if(done) break;
      rest += dek.decode(value, {stream:true});
      const zeilen = rest.split('\n'); rest = zeilen.pop();
      for(const z of zeilen){
        if(!z.trim()) continue;
        try{ verarbeiten(JSON.parse(z)); }catch(_){}
      }
    }
  }catch(e){ if(e.name !== 'AbortError') links('sys', 'Verbindung unterbrochen: ' + e.message); }
  // Der Strom endet, wenn der Prozess endet ODER die Leitung abreisst. Nur im
  // zweiten Fall neu verbinden -- sonst hinge die Seite ewig an einem toten Agenten.
  if(LAEUFT) setTimeout(lauschen, 900);
}

function verarbeiten(e){
  if(e.i) LETZT = e.i;
  switch(e.art){
    case 'start':   T0 = e.t || T0; uhrTick(); if(e.ordner) ordnerZeigen(e.ordner);
                    links('sys', '▶ ' + e.befehl); break;
    case 'sitzung': links('sys', 'Sitzung ' + (e.id||'').slice(0,8) + ' · ' + (e.cwd||'')); break;
    case 'frage':   blaseDenken = blaseText = null; ZUG0 = e.t || Date.now()/1000;
                    rekTaetig('auftrag', e.text);
                    links('frage', e.text); zustand('arbeitet'); break;
    case 'denken':  anfuegen('denken', e.text); break;
    case 'text':    anfuegen('text', e.text); break;
    case 'werkzeug':
      blaseDenken = blaseText = null;
      links('wz', '$ ' + e.befehl); break;
    case 'ergebnis': kachelText(e); break;
    case 'bild':     kachelBild(e); break;
    case 'bereit':   zugEnde(e); zustand('bereit'); break;
    case 'gesichert': gesichertZeigen(e); break;
    case 'gemerkt':  links('hinweis', '📣 ' + e.text +
                           '  (wird nach dem laufenden Zug übergeben)'); break;
    // Der Kopf selbst meldet etwas, das der Mensch wissen muss -- heute: das
    // Werkzeug hat sich mitten im Lauf geaendert. Steht im Verlauf, damit es
    // im ``protokoll_*.md`` dieses Laufs landet und nicht nur in einer Lampe,
    // die beim naechsten Abruf wieder aus ist.
    case 'hinweis':  links('hinweis', e.text); break;
    case 'fehler':   zugEnde(e); links('fehl', '⚠ ' + e.text); zustand('bereit'); break;
    case 'roh':      links('sys', e.text); break;
    case 'ende':     LAEUFT = false; zugEnde(e);
                     links('sys', 'Agent beendet (Code ' + e.code + ')');
                     zustand('beendet'); break;
  }
}

// Wie `verarbeiten`, aber ohne alles, was den LAUFENDEN Agenten betrifft
// (Uhr, Zustandspille, Ordneranzeige, Zaehler). Ein Archivlauf darf die Anzeige
// des lebenden nicht anfassen -- sonst stuende nach dem Nachlesen eines alten
// Laufs „beendet" ueber einem, der noch rechnet.
function verarbeitenStumm(e){
  switch(e.art){
    case 'sitzung':  links('sys', 'Sitzung ' + (e.id||'').slice(0,8)); break;
    case 'frage':    blaseDenken = blaseText = null; links('frage', e.text); break;
    case 'denken':   anfuegen('denken', e.text); break;
    case 'text':     anfuegen('text', e.text); break;
    case 'werkzeug': blaseDenken = blaseText = null;
                     links('wz', '$ ' + e.befehl); break;
    case 'ergebnis': kachelText(e); break;
    case 'bild':     kachelBild(e); break;
    case 'gemerkt':  links('hinweis', '📣 ' + e.text); break;
    case 'hinweis':  links('hinweis', e.text); break;
    case 'fehler':   links('fehl', '⚠ ' + e.text); break;
    case 'roh':      links('sys', e.text); break;
  }
}

function zugEnde(e){
  if(ZUG0) ZUG_LETZT = (e.t || Date.now()/1000) - ZUG0;
  ZUG0 = 0; uhrTick();
}

// Deltas an dieselbe Blase haengen, statt je Token ein Element zu erzeugen --
// sonst stehen fuer zwei Woerter Antwort 75 Knoten im DOM.
// Zeichentempo: die Seite kann Zeichen exakt zaehlen, Token nicht -- wer sie
// aus Zeichen hochrechnet, schreibt eine Zahl hin, die wie eine Messung
// aussieht. Also wird gezaehlt, was zaehlbar ist, und es heisst auch „Z/s".
// Hermes liefert daneben ECHTE Token/s aus seiner eigenen Buchfuehrung.
let ZTEMPO = {zeichen: 0, t0: 0, rate: 0};
function zeichenZaehlen(n){
  const jetzt = Date.now() / 1000;
  if(!ZTEMPO.t0 || jetzt - ZTEMPO.t0 > 3){
    if(ZTEMPO.t0 && jetzt > ZTEMPO.t0)
      ZTEMPO.rate = ZTEMPO.zeichen / (jetzt - ZTEMPO.t0);
    ZTEMPO.t0 = jetzt; ZTEMPO.zeichen = 0;
  }
  ZTEMPO.zeichen += n;
}

function anfuegen(art, text){
  let b = art === 'denken' ? blaseDenken : blaseText;
  if(!b){ b = links(art, ''); if(art === 'denken') blaseDenken = b; else blaseText = b; }
  // Der ROHE Text bleibt an der Blase haengen. Er ist die Quelle: eine Seite,
  // die ihn beim Anzeigen umformt (Markdown), kann sonst beim naechsten Delta
  // nicht mehr sagen, was vorher dastand -- aus dem gerenderten HTML laesst
  // sich der Ursprungstext nicht zurueckgewinnen.
  b.dataset.roh = (b.dataset.roh || '') + text;
  if(typeof blaseFuellen === 'function') blaseFuellen(b, art);
  else b.textContent = b.dataset.roh;
  if(SPALTEN.l !== 'a_links') zeichenZaehlen((text || '').length);
  runter($(SPALTEN.l));
}

// ── Mitlaufen ────────────────────────────────────────────────────────────────
// „Laeuft nach oben weg": die Spalte folgt dem Neuesten, solange der Betrachter
// unten steht. Wer hochscrollt, um etwas zu lesen, wird NICHT weggerissen --
// stattdessen erscheint „⤓ Neues", und ein Klick haengt ihn wieder an.
//
// Der Zustand wird gemerkt und nicht bei jedem Anhaengen neu geschaetzt: eine
// einzelne Kachel kann hoeher sein als jede Schwelle (ein langes Ergebnis, ein
// Bild, das erst nach dem Anhaengen seine Hoehe bekommt), und dann bliebe die
// Anzeige mitten im Lauf stehen -- genau das, was hier nicht passieren soll.
const FOLGT = {};

// GLEITEN statt SPRINGEN. Vorher setzte `runter` einfach `scrollTop =
// scrollHeight`: die Spalte stand mit dem naechsten Bild schon wieder unten,
// und WAS dazugekommen war, sah man nur, wenn man es ohnehin schon wusste. In
// der Bildschirmaufnahme ist das der Unterschied zwischen einem lesbaren Lauf
// und einer Folge von Spruengen.
//
// Das Tempo ist nicht fest, sondern eine Zeitkonstante: `rest/GLEIT_TAU_S`,
// nach unten begrenzt auf eine ruhige Lesegeschwindigkeit. Fest waere eins von
// beidem falsch -- bei einem Zeichen-Anhang stuende die Spalte sekundenlang
// nach, bei fuenf Kacheln auf einmal liefe sie eine halbe Minute hinterher.
const GLEIT_MIN_PX_S = 260;    // ruhiges Nachziehen, wenn wenig dazukam
const GLEIT_TAU_S    = 2.5;    // grosser Rueckstand wird in dieser Zeit abgebaut
const GLEIT = {};              // id -> {raf, t, erwartet}

function folgeUeberwachen(id){
  const el = $(id);
  if(!el) return;
  FOLGT[id] = true;
  el.addEventListener('scroll', () => {
    const g = GLEIT[id];
    // Die EIGENE Bewegung nicht als Bedienung deuten. Waehrend des Gleitens
    // steht die Spalte per Definition nicht unten -- ohne diese Unterscheidung
    // schaltete das Mitlaufen sich bei der ersten neuen Kachel selbst ab und
    // „⤓ Neues" erschiene, obwohl niemand gescrollt hat.
    if(g && Math.abs(el.scrollTop - g.erwartet) < 2) return;
    const unten = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if(!unten) gleitStopp(id);   // von Hand hochgescrollt: das Gleiten endet sofort
    if(FOLGT[id] !== unten){
      FOLGT[id] = unten;
      const chip = $('chip_' + id);
      if(chip) chip.style.display = unten ? 'none' : 'block';
    }
  }, {passive:true});
}
function gleitStopp(id){
  const g = GLEIT[id];
  if(!g) return;
  if(g.raf) cancelAnimationFrame(g.raf);
  delete GLEIT[id];
}
function gleitStart(id){
  const el = $(id);
  if(!el || GLEIT[id]) return;   // laeuft schon -- das Ziel wird je Bild neu gelesen
  const schritt = t => {
    const g = GLEIT[id];
    if(!g) return;
    const dt = g.t ? Math.min(0.1, (t - g.t) / 1000) : 0;   // Deckel: Tab war weg
    g.t = t;
    const rest = el.scrollHeight - el.clientHeight - el.scrollTop;
    if(rest <= 1){ gleitStopp(id); el.scrollTop = el.scrollHeight; return; }
    el.scrollTop += Math.max(GLEIT_MIN_PX_S, rest / GLEIT_TAU_S) * dt;
    g.erwartet = el.scrollTop;
    g.raf = requestAnimationFrame(schritt);
  };
  GLEIT[id] = {raf: 0, t: 0, erwartet: el.scrollTop};
  GLEIT[id].raf = requestAnimationFrame(schritt);
}
// „⤓ Neues" ist eine ausdrueckliche Bitte, ans Ende zu kommen -- die wird nicht
// zwei Sekunden lang verhandelt.
function nachUnten(id){
  const el = $(id);
  gleitStopp(id);
  FOLGT[id] = true;
  const chip = $('chip_' + id);
  if(chip) chip.style.display = 'none';
  el.scrollTop = el.scrollHeight;
}
function runter(el){
  if(!el || FOLGT[el.id] === false) return;
  gleitStart(el.id);
}

// ── Stoppuhr ─────────────────────────────────────────────────────────────────
// Zwei Zeiten, weil zwei Fragen dahinterstehen: wie lange laeuft der Agent
// schon, und wie lange haengt er am AKTUELLEN Zug. Beide aus den Zeitstempeln
// der Ereignisse (Server und Browser sind dieselbe Maschine), damit ein neu
// geladenes Fenster nicht bei null anfaengt.
let T0 = 0, ZUG0 = 0, ZUG_LETZT = 0;

const uhrText = s => {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s/3600), m = Math.floor(s/60)%60, k = s%60;
  const zz = n => String(n).padStart(2,'0');
  return h ? `${h}:${zz(m)}:${zz(k)}` : `${zz(m)}:${zz(k)}`;
};
const uhrStempel = t => (T0 && t) ? uhrText(t - T0) : '';

function uhrTick(){
  if(!T0) return;
  const jetzt = Date.now()/1000;
  let t = '⏱ ' + uhrText(jetzt - T0);
  if(ZUG0)           t += ' · Zug ' + uhrText(jetzt - ZUG0);
  else if(ZUG_LETZT) t += ' · Zug ' + uhrText(ZUG_LETZT);
  const p = $('p_uhr');
  if(p) p.textContent = t;
}
setInterval(uhrTick, 1000);

// ── Senden, Zwischenrufen, Beenden ───────────────────────────────────────────
async function frageSenden(text){
  if(!text) return;
  const a = await (await fetch(K('/agent/frage'), {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})})).json();
  if(!a.ok) links('fehl', '⚠ ' + a.grund);
  return a;
}
// Der Zwischenruf bleibt bedienbar, waehrend der Agent arbeitet -- das ist sein
// ganzer Zweck. Er wird nur quittiert, nicht sofort beantwortet.
async function hinweisSenden(text){
  if(!text) return;
  try{
    const a = await (await fetch(K('/agent/hinweis'), {method:'POST',
        headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})})).json();
    if(!a.ok) links('fehl', '⚠ ' + (a.grund || 'Zwischenruf nicht angenommen'));
    return a;
  }catch(e){ links('fehl', '⚠ ' + e.message); }
}
async function stoppen(){
  await fetch(K('/agent/stopp'), {method:'POST'});
  if(ABBRUCH) ABBRUCH.abort();
  LAEUFT = false; zustand('beendet');
}

// ── Sichern ──────────────────────────────────────────────────────────────────
// Der Server schreibt nach jedem Zug von selbst; dieser Knopf ist der Griff
// fuer zwischendurch. Geschrieben wird aus dem Ringpuffer im Server, nicht aus
// dem DOM -- ein geschlossenes Fenster verliert damit nichts.
async function sichernJetzt(){
  const b = $('b_sichern'); if(b) b.disabled = true;
  try{
    const a = await (await fetch(K('/agent/sichern'), {method:'POST'})).json();
    // ``hand`` unterscheidet die Sicherung von Hand von der stillen nach jedem
    // Zug -- die Seite darf darauf verschieden antworten (die Studioseite
    // schreibt nur bei der von Hand eine Zeile in den Verlauf). Und der
    // FEHLERfall geht denselben Weg: hier stand einmal ein direkter Zugriff auf
    // ein Element, das nur die Schreibtischseite hat.
    gesichertZeigen(a.ok ? Object.assign({hand: true}, a)
                         : {fehler: a.grund || 'Sichern fehlgeschlagen'});
  }catch(e){ gesichertZeigen({fehler: e.message}); }
  if(b) b.disabled = false;
}

// ── Arbeitsanzeige ───────────────────────────────────────────────────────────
// Abgefragt wird hier, GEZEIGT in der Seite: die Form unterscheidet sich (fuenf
// Leuchten am Schreibtisch, eine Zeile am Handy), die Regeln nicht.
let AR_TIMER = null, AR_FEHLER = 0, HAENGT = false;
// Schwellen in Sekunden. Sie muessen UEBER der Dauer eines langen Werkzeugaufrufs
// liegen: waehrend `sleep 180 && status` kommt zu Recht nichts, und Hermes laesst
// ein Werkzeug bis 420 s laufen. Darunter waere die Warnung ein Fehlalarm.
const STILL_WARNUNG = 120, STILL_FREIGABE = 450;

function uhrKurz(s){
  if(s == null) return '—';
  return (s >= 60 ? Math.floor(s/60) + ':' + String(s%60).padStart(2,'0') : s + ' s');
}

async function freigeben(){
  if(!confirm('Zugsperre lösen?\n\nDer Agent wird NICHT beendet — er läuft weiter. ' +
              'Kommt doch noch eine Antwort, erscheint sie im Verlauf.')) return;
  try{
    const a = await (await fetch(K('/agent/freigeben'), {method:'POST'})).json();
    if(!a.ok) links('fehl', '⚠ ' + (a.grund || 'nicht freigegeben'));
  }catch(e){ links('fehl', '⚠ ' + e.message); }
  arbeitTick();
}

function arbeitStart(){
  if(AR_TIMER) return;
  if(typeof arbeitHoehe === 'function') arbeitHoehe();
  arbeitTick();
  AR_TIMER = setInterval(arbeitTick, 2000);
}
function arbeitStopp(){ if(AR_TIMER){ clearInterval(AR_TIMER); AR_TIMER = null; } }

async function arbeitTick(){
  // Nicht abfragen, waehrend das Fenster im Hintergrund liegt: die Leiste ist
  // eine Anzeige, kein Messgeraet -- im verdeckten Reiter misst sie niemanden.
  if(document.hidden) return;
  let d;
  try{
    d = await (await fetch(K('/agent/arbeit'))).json();
    AR_FEHLER = 0;
  }catch(e){
    if(++AR_FEHLER > 2) arbeitZeigen(null);
    return;
  }
  arbeitZeigen(d);
}

// ── Archiv: frueher gelaufene Zuege ──────────────────────────────────────────
//
// Der Gegenweg zu `sichern`. Geschrieben wurde nach jedem Zug -- gelesen bisher
// nie, weil es keinen Weg zurueck gab. Fuer den, der davorsitzt, ist
// „geschrieben, aber unerreichbar" dasselbe wie „nicht gespeichert".
let A_LAEUFE = [], A_OFFEN = '';

async function archivAuf(){
  $('archiv').classList.add('an');
  $('a_liste').innerHTML = '<div class="leer" style="margin-top:6vh">lädt …</div>';
  try{
    const a = await (await fetch(K('/agent/laeufe?max=200'))).json();
    A_LAEUFE = a.laeufe || [];
  }catch(e){ A_LAEUFE = []; }
  archivListe();
}
function archivZu(){ $('archiv').classList.remove('an'); }

function archivListe(){
  const ziel = $('a_liste');
  if(!A_LAEUFE.length){
    ziel.innerHTML = '<div class="leer" style="margin-top:6vh">Noch keine ' +
                     'gespeicherten Läufe.</div>';
    $('a_titel').textContent = 'Frühere Läufe'; $('a_wo').textContent = '';
    return;
  }
  $('a_titel').textContent = A_LAEUFE.length + ' frühere Läufe';
  $('a_wo').textContent = '· alle Köpfe gemeinsam, neueste zuerst';
  ziel.innerHTML = '';
  for(const l of A_LAEUFE){
    const d = document.createElement('div');
    d.className = 'lauf' + (l.marke === A_OFFEN ? ' an' : '');
    const s = Math.round(l.sekunden || 0);
    const dauer = (s >= 3600 ? Math.floor(s/3600) + ':' : '') +
                  String(Math.floor(s/60)%60).padStart(2,'0') + ':' +
                  String(s%60).padStart(2,'0');
    const auf = (l.auftraege || []).join(' · ');
    d.innerHTML =
      `<div class="z1"><b>${esc(datumHuebsch(l.marke))}</b>` +
      `<span>${esc(l.kopf || '?')}</span>` +
      `<span>${l.ereignisse||0} Ereignisse</span>` +
      `<span>${l.kacheln||0} Ergebnisse</span><span>${dauer}</span></div>` +
      `<div class="z1">${esc(l.projekt || '— ohne Projektbindung —')}</div>` +
      (auf ? `<div class="auf">${esc(auf)}</div>`
           : `<div class="leerlauf">(kein Auftrag gestellt)</div>`);
    d.onclick = () => archivZeigen(l);
    ziel.appendChild(d);
  }
}
// `20260904_124810` → `04.09.2026 12:48`. Die Marke ist der Dateiname; ein
// zweites Datumsfeld daneben koennte von ihm abweichen.
function datumHuebsch(m){
  const t = String(m || '');
  if(!/^\d{8}_\d{6}/.test(t)) return t;
  return `${t.slice(6,8)}.${t.slice(4,6)}.${t.slice(0,4)} ` +
         `${t.slice(9,11)}:${t.slice(11,13)}`;
}

async function archivZeigen(l){
  A_OFFEN = l.marke; archivListe();
  $('a_links').innerHTML = ''; if($('a_rechts')) $('a_rechts').innerHTML = '';
  $('a_hinweis').textContent = 'lädt …';
  let a;
  try{
    a = await (await fetch(K('/agent/lauf?projekt=' +
        encodeURIComponent(l.projekt || '') + '&marke=' +
        encodeURIComponent(l.marke)))).json();
  }catch(e){ $('a_hinweis').textContent = 'nicht lesbar: ' + e.message; return; }
  if(!a.ok){ $('a_hinweis').textContent = a.grund || 'nicht lesbar'; return; }

  // Denselben Weg wie der laufende Strom -- nur in die Archivspalten.
  const vorher = SPALTEN, dText = blaseText, dDenk = blaseDenken;
  SPALTEN = {l:'a_links', r: $('a_rechts') ? 'a_rechts' : 'a_links'};
  blaseText = blaseDenken = null;
  try{
    for(const e of (a.ereignisse_liste || [])){
      if(e.art === 'start' || e.art === 'bereit' || e.art === 'ende' ||
         e.art === 'gesichert' || e.art === 'kontext') continue;
      verarbeitenStumm(e);
    }
  } finally {
    SPALTEN = vorher; blaseText = dText; blaseDenken = dDenk;
  }
  denkenUm();
  $('a_hinweis').textContent =
    (a.gekuerzt ? `nur die letzten ${(a.ereignisse_liste||[]).length} von ${a.ereignisse} Ereignissen · ` : '') +
    (a.protokoll ? '📄 ' + a.protokoll : '');
}

// ── Bildschirmaufnahme ───────────────────────────────────────────────────────
// Aufgenommen wird im Browser, GESPEICHERT wird im Server: jedes Stueck geht
// sofort per POST an /agent/video/stueck und wird dort angehaengt. Der Browser
// behaelt nichts -- sonst laege nach einem stundenlangen Lauf ein Blob von
// hunderten Megabyte im Arbeitsspeicher der Seite, und ein geschlossenes
// Fenster haette alles verloren. 5 Bilder/s und 0,7 Mbit/s reichen fuer Text
// und Diagramme und ergeben rund 5 MB je Minute; bei 800 MB endet die
// Aufnahme von selbst.
const VIDEO_FPS = 5, VIDEO_BITS = 700000, VIDEO_STUECK_MS = 5000;
let REK = null, REK_STROM = null, REK_KETTE = Promise.resolve(),
    REK_BYTES = 0, REK_START = 0, REK_TICK = null,
    REK_PAUSE = false, REK_PAUSE_S = 0, REK_PAUSE_SEIT = 0, REK_WACHE = null;
// Nachlauf: so lange nach der letzten Taetigkeit wird weiter aufgenommen.
// Grosszuegig, damit eine Folge von Kacheln EINE zusammenhaengende Aufnahme bleibt
// statt in Stuecke zu zerfallen -- eine Pipeline schreibt ihre Diagramme in
// Schueben von wenigen Sekunden bis zu einer halben Minute Abstand.
const REK_NACHLAUF = 45;
let REK_AKTIV_TS = 0;

// Wo die Aufnahme gerade steht. NICHT die Uhrzeit: pausiert der Recorder,
// laeuft die Uhr weiter, die Datei aber nicht -- eine Schnittliste nach Wanduhr
// laege mit jeder Pause weiter daneben.
function rekVideoS(){
  if(!REK_START) return 0;
  const pause = REK_PAUSE_S + (REK_PAUSE_SEIT ? Date.now()/1000 - REK_PAUSE_SEIT : 0);
  return Math.max(0, Date.now()/1000 - REK_START - pause);
}

// „Es ist etwas passiert." Setzt die Uhr, nimmt die Aufnahme SOFORT wieder
// auf (statt bis zum naechsten Waechterlauf zu warten) und schreibt eine Marke --
// aus der entsteht beim Beenden die Schnittliste fuers ffmpeg, und aus derselben
// Liste die Vorschlaege fuer ein Reel (`ema_beitrag.clips`).
function rekTaetig(art, text){
  REK_AKTIV_TS = Date.now() / 1000;
  if(!REK) return;
  if(REK_PAUSE) rekPause(false);
  if(!art) return;
  fetch(K('/agent/video/marke'), {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({art: art, text: text || '', video_s: rekVideoS()})
      }).catch(() => {});
}

// WAS aufgenommen wird, haengt an der TAETIGKEIT IM BILD -- nicht daran, ob der
// Server rechnet.
//
// Vorher war es umgekehrt: „Server rechnet → Pause", mit der Begruendung, am
// Bild aendere sich dann nichts ausser einem Fortschrittsbalken. Die Begruendung
// ist gemessen falsch. Im Lauf vom 04.09. kamen MITTEN im Rechenlauf fuenf
// Bilder herein (Querschnitt, Seitenansicht, Luftspalt, Feldbild, Feld unter
// Last) -- angehalten wurde also genau waehrend der einzigen Momente, die
// aufzuheben sich lohnt.
//
// Beim Fortsetzen geht der Bruchteil einer Sekunde VOR dem Ereignis verloren.
// Das ist der Preis der Pause und er ist hier vertretbar: die Kachel bleibt
// stehen, sobald sie da ist.
function rekPause(an){
  if(!REK || REK_PAUSE === an) return;
  try{ an ? REK.pause() : REK.resume(); }catch(_){ return; }
  REK_PAUSE = an;
  if(an){ REK_PAUSE_SEIT = Date.now()/1000; }
  else if(REK_PAUSE_SEIT){ REK_PAUSE_S += Date.now()/1000 - REK_PAUSE_SEIT;
                           REK_PAUSE_SEIT = 0; }
  fetch(K('/agent/video/pause'), {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({an: an})}).catch(() => {});
  videoAnzeige();
}

async function videoUm(){ REK ? videoStopp('beendet') : videoStart(); }

async function videoStart(){
  if(!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia){
    links('sys', 'Aufnahme: dieser Browser bietet keine Bildschirmaufnahme an.'); return;
  }
  let strom;
  try{
    strom = await navigator.mediaDevices.getDisplayMedia({
      video: {frameRate: {ideal: VIDEO_FPS, max: 8}}, audio: false});
  }catch(e){
    if(e.name !== 'NotAllowedError') links('sys', 'Aufnahme: ' + e.message);
    return;
  }
  const a = await (await fetch(K('/agent/video/start'), {method:'POST'})).json();
  if(!a.ok){ strom.getTracks().forEach(t => t.stop());
             links('sys', 'Aufnahme: ' + (a.grund||'')); return; }

  const typ = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm']
                .find(t => MediaRecorder.isTypeSupported(t)) || '';
  REK_STROM = strom; REK_BYTES = 0; REK_START = Date.now()/1000;
  REK_PAUSE = false; REK_PAUSE_S = 0; REK_PAUSE_SEIT = 0;
  REK = new MediaRecorder(strom, {mimeType: typ, videoBitsPerSecond: VIDEO_BITS});
  REK.ondataavailable = ev => {
    if(!ev.data || !ev.data.size) return;
    // Der Reihe nach senden: die Stuecke ergeben nur in ihrer Folge ein Video.
    REK_KETTE = REK_KETTE.then(() => fetch(K('/agent/video/stueck'),
        {method:'POST', headers:{'Content-Type':'application/octet-stream'}, body: ev.data})
      .then(r => r.json())
      .then(r => { if(r.bytes != null) REK_BYTES = r.bytes;
                   if(r.grenze){ links('sys','Aufnahme bei ' + a.max_mb +
                                 ' MB beendet — die Datei liegt bei ' + a.pfad);
                                 videoStopp('grenze'); } })
      .catch(() => {}));
  };
  // Der Betrachter kann die Freigabe auch im Browser beenden.
  strom.getVideoTracks()[0].addEventListener('ended', () => videoStopp('freigabe'));
  REK.start(VIDEO_STUECK_MS);
  $('b_video').textContent = '⏹ Aufnahme beenden';
  $('p_rek').style.display = '';
  if($('l_luecken')) $('l_luecken').style.display = '';
  REK_TICK = setInterval(videoAnzeige, 1000); videoAnzeige();
  REK_AKTIV_TS = Date.now() / 1000;      // der Start selbst ist Taetigkeit
  // Wer den Verlauf durchsieht, TUT etwas -- auch das gehoert aufs Band.
  const beobachtet = $(SPALTEN.r) || $(SPALTEN.l);
  if(beobachtet) beobachtet.addEventListener('scroll', () => rekTaetig(), {passive: true});
  rekTaetig('start', 'Aufnahme begonnen');
  // Die Seite darf festhalten, WOHIN sie aufgenommen wird. Die Studio-Seite
  // schreibt hier ihr Buehnenrechteck in die Markenliste — daraus wird spaeter
  // die Zuschnittzeile aufs Hochformat. Wer den Ausschnitt hinterher im Bild
  // suchen muss, findet ihn naemlich nicht mehr genau.
  if(typeof nachAufnahmeStart === 'function'){
    try{ nachAufnahmeStart(strom); }catch(_){}
  }
  REK_WACHE = setInterval(rekWache, 2000); rekWache();
  links('sys', '🎥 Aufnahme läuft → ' + a.pfad);
}

function videoAnzeige(){
  if(!REK) return;
  const mb = REK_BYTES / 1048576;
  const pause = REK_PAUSE_S + (REK_PAUSE_SEIT ? Date.now()/1000 - REK_PAUSE_SEIT : 0);
  // Angezeigt wird die AUFGEZEICHNETE Zeit, nicht die verstrichene -- sonst
  // stimmt die Uhr nicht mit der Datei ueberein.
  $('p_rek').textContent = (REK_PAUSE ? '⏸ Pause (nichts Neues) ' : '● REC ') +
                           uhrText(Date.now()/1000 - REK_START - pause) +
                           ' · ' + mb.toFixed(1) + ' MB';
}

function rekWache(){
  if(!REK) return;
  // Kein Serverabruf: was zaehlt, steht im Browser. Ob der Server rechnet,
  // sagt nichts darueber, ob etwas zu sehen ist -- im Gegenteil, gerade dann
  // kommen die Bilder.
  const still = Date.now() / 1000 - (REK_AKTIV_TS || 0);
  // Mit der Markenliste ist die Pause nur noch eine Platzersparnis, kein
  // Zwang: wer lieber alles aufnimmt und hinterher schneidet, schaltet sie ab.
  const luecken = $('c_luecken');
  const soll = (!luecken || luecken.checked) && still > REK_NACHLAUF;
  if(soll !== REK_PAUSE){
    links('sys', soll
      ? `⏸ Aufnahme angehalten — seit ${Math.round(still)} s nichts Neues.`
      : '▶ Aufnahme läuft weiter.');
  }
  rekPause(soll);
}

async function videoStopp(grund){
  if(!REK) return;
  const r = REK; REK = null;
  clearInterval(REK_TICK); clearInterval(REK_WACHE); REK_WACHE = null;
  try{ if(REK_PAUSE) r.resume(); }catch(_){}   // pausiert laesst sich nicht stoppen
  try{ r.stop(); }catch(_){}
  if(REK_STROM) REK_STROM.getTracks().forEach(t => t.stop());
  REK_STROM = null;
  await REK_KETTE;                       // die letzten Stuecke noch loswerden
  const a = await (await fetch(K('/agent/video/ende'), {method:'POST'})).json();
  $('b_video').textContent = '🎥 Aufnahme';
  $('p_rek').style.display = 'none';
  if($('l_luecken')) $('l_luecken').style.display = 'none';
  if(a.ok){
    links('sys', '🎬 Aufnahme ' + (grund === 'grenze' ? '(Grenze) ' : '') +
                 uhrText(a.sekunden) + ' · ' +
                 (a.bytes/1048576).toFixed(1) + ' MB → ' + a.pfad);
    // Die Schnittliste ist der eigentliche Ertrag der Marken -- sie muss
    // dastehen, sonst sucht sie niemand.
    if(a.marken)
      links('sys', '✂ ' + (a.n_marken || 0) + ' Marken, ' + (a.stuecke || 0) +
                   ' Stück(e) mit Inhalt → ' + a.schnitt +
                   '   (ausführen schneidet die Aufnahme; Liste: ' + a.marken + ')');
  }
}
// Ein weggeklicktes Fenster soll keine halbe Datei hinterlassen.
addEventListener('pagehide', () => { if(REK) navigator.sendBeacon(K('/agent/video/ende')); });
