// Das Chatfenster ueber die Ergebnisse (Ollama).
//
// Erdet auf dem Steckbrief des Projekts, nicht auf dem Gespraechsverlauf;
// der Verlauf selbst liegt serverseitig im Projekt.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Ergebnis-Chat (Ollama) ───────────────────────────────────────────────────
let _chatHistory = [];
function toggleChat() {
  const p = document.getElementById('chat-panel');
  const open = p.style.display === 'none' || !p.style.display;
  p.style.display = open ? 'flex' : 'none';
  if (open) { _updateChatScope(); document.getElementById('chat-input').focus();
              _chatVerlaufHolen();
              if (!_chatHistory.length) _renderChat(); }
}
function clearChat() { _chatHistory = []; _renderChat(); }

// ── Vom gerissenen Tor in den Chat ─────────────────────────────────────────
// Gemeldet als: „Ich brauche hier mehr Kontext oder einen konkreten Vorschlag,
// was zu tun ist. Vielleicht auch ueber den Chat." Der Chat erdet ohnehin auf
// dem Steckbrief des Projekts und kann nachschlagen — was ihm fehlte, ist der
// FEHLSCHLAG. Ohne ihn fragt der Mensch „warum geht das nicht" und der Chat
// raet.
//
// Die Frage wird nur EINGESETZT, nicht abgeschickt: was gefragt wird, bleibt
// beim Menschen — dieselbe Haltung wie bei „übernehmen setzt nur das Formular".
function _gateZumChat() {
  const frage = window._gateChat || '';
  if (!frage) return;
  const p = document.getElementById('chat-panel');
  if (p && (p.style.display === 'none' || !p.style.display)) toggleChat();
  const feld = document.getElementById('chat-input');
  if (feld) {
    feld.value = frage;
    feld.focus();
    feld.style.height = 'auto';
    feld.style.height = Math.min(feld.scrollHeight, 160) + 'px';
  }
}

// Der Verlauf liegt SERVERseitig im Projekt (<projekt>/gespraeche/<kennung>.jsonl)
// und ueberlebt das Neuladen — vorher war ein Gespraech mit dem Fenster weg.
// Beim Oeffnen wird er nachgezogen, damit man dort weitermacht, wo man war.
async function _chatVerlaufHolen() {
  const pid = _activeProject && _activeProject.id;
  if (!pid || _chatHistory.length) return;
  try {
    const j = await (await fetch('/project/' + encodeURIComponent(pid)
                                 + '/gespraeche?kennung=chat')).json();
    _chatHistory = (j.zuege || []).map(z => ({
      role: z.role, content: z.content,
      werkzeuge: z.werkzeuge || [], ungedeckt: z.ungedeckt || [] }));
    if (_chatHistory.length) _renderChat();
  } catch (e) { /* ohne Verlauf faengt man eben neu an */ }
}

// „Nachprüfen lassen": alles RECHNENDE gehört nicht in ein Chatfenster — ein
// Pipelinelauf dauert Stunden. Der Agentenkopf hat die Rechenverben bereits;
// hier wird nichts neu gebaut, nur verbunden. Läuft schon einer, geht die Bitte
// als Zwischenruf (merken) an ihn, statt einen zweiten zu starten.
async function chatNachpruefen() {
  const pid = _activeProject && _activeProject.id;
  const letzte = [..._chatHistory].reverse().find(m => m.role === 'user');
  if (!pid || !letzte) { alert('Erst ein Projekt wählen und etwas fragen.'); return; }
  const auftrag = 'Prüfe das nach und nenne die Belege — erfinde nichts. '
                + 'Frage aus dem Chat: ' + letzte.content;
  try {
    const st = await (await fetch('/agent/status?kopf=pi')).json();
    const laeuft = !!(st && st.laeuft);
    const r = await fetch(laeuft ? '/agent/hinweis' : '/agent/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(laeuft ? { kopf: 'pi', text: auftrag }
                                  : { kopf: 'pi', projekt: pid, prompt: auftrag })
    });
    const j = await r.json();
    // Die /agent/…-Routen melden ihren Zustand im RUMPF ({ok, grund}) und nicht
    // immer über den HTTP-Code — `r.ok` allein hätte ein „Projekt gibt es nicht"
    // als Erfolg gelesen.
    const gut = r.ok && j && j.ok !== false;
    _chatHistory.push({ role: 'assistant', content: gut
      ? ('🔬 An den Agentenkopf PI übergeben' + (laeuft ? ' (als Zwischenruf — er arbeitet gerade)' : '')
         + '. Was dabei herauskommt, steht im Reiter 🤖 PI.')
      : ('⚠ Nicht übergeben: ' + ((j && (j.grund || j.error)) || r.status)) });
  } catch (e) {
    _chatHistory.push({ role: 'assistant', content: '⚠ Nicht übergeben: ' + e.message });
  }
  _renderChat();
}

// Scope follows the active tab: on the Vergleich tab with ≥2 projects ticked we
// chat about the comparison, otherwise about the currently loaded project.
function _chatScope() {
  if (window._activeTab === 'compare') {
    const ids = [...document.querySelectorAll('.cmp-checkbox:checked')].map(c => c.value);
    if (ids.length >= 2) return { scope: 'compare', ids };
  }
  return { scope: 'project', ids: [] };
}
function _updateChatScope() {
  const s = _chatScope();
  const el = document.getElementById('chat-scope');
  el.textContent = s.scope === 'compare' ? `· Vergleich (${s.ids.length} Varianten)` : '· aktuelles Projekt';
}
function _mdLite(t) {
  return escHtml(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');
}
function _renderChat() {
  const box = document.getElementById('chat-msgs');
  if (!_chatHistory.length) {
    box.innerHTML = '<div style="color:#777;font-size:.78rem">Frag mich etwas zu den Ergebnissen — z.B. „Warum ist T_Magnet so hoch?" oder im Vergleich „Welche Variante ist am effizientesten und warum?".</div>';
    return;
  }
  box.innerHTML = _chatHistory.map(m => {
    const mine = m.role === 'user';
    // Was nachgeschlagen wurde, und welche Zahl im Material NICHT gedeckt ist.
    // Beides gehört an die Antwort und nicht daneben: wer eine Zahl liest, soll
    // sehen, ob sie belegt ist — eine Bitte an ein Sprachmodell ist keine
    // Zusicherung (dieselbe Prüfung wie bei den Beitragsentwürfen).
    const wz = (m.werkzeuge || []).map(w =>
      `<span style="color:#8ab">🔧 ${escHtml(w.werkzeug)}${w.argument ? ' ' + escHtml(w.argument.slice(0, 40)) : ''}`
      + `${w.ok ? '' : ' <span style="color:#d88">(fehlgeschlagen)</span>'}</span>`).join(' · ');
    const ug = (m.ungedeckt || []).length
      ? `<div style="color:#d9a441;font-size:.72rem;margin-top:5px">⚠ nicht im Material gedeckt: `
        + escHtml(m.ungedeckt.join(', ')) + `</div>` : '';
    return `<div style="align-self:${mine ? 'flex-end' : 'flex-start'};max-width:88%;
      background:${mine ? '#2c5d8a' : '#2d2d33'};color:#eee;padding:7px 10px;border-radius:8px;line-height:1.45">
      ${wz ? '<div style="font-size:.72rem;margin-bottom:5px">' + wz + '</div>' : ''}
      ${m.role === 'assistant' ? _mdLite(m.content) : escHtml(m.content)}${ug}</div>`;
  }).join('');
  box.scrollTop = box.scrollHeight;
}
async function sendChat() {
  const inp = document.getElementById('chat-input');
  const msg = inp.value.trim();
  if (!msg) return;
  const { scope, ids } = _chatScope();
  _chatHistory.push({ role: 'user', content: msg });
  inp.value = '';
  _renderChat();
  const btn = document.getElementById('chat-send'); btn.disabled = true;
  _chatHistory.push({ role: 'assistant', content: '…' });
  _renderChat();
  try {
    const r = await fetch('/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      // project_id ausdrücklich: der Chat hing am global aktiven Serverzustand,
      // und wer in einem zweiten Reiter umschaltete, verschob den Gegenstand des
      // Gesprächs unter der Hand.
      body: JSON.stringify({ message: msg, history: _chatHistory.slice(0, -2), scope, ids,
                             project_id: (_activeProject && _activeProject.id) || undefined })
    }).then(x => x.json());
    _chatHistory.pop();
    _chatHistory.push({ role: 'assistant',
                        content: r.error ? ('⚠ ' + r.error) : (r.reply || '(leere Antwort)'),
                        werkzeuge: r.werkzeuge || [], ungedeckt: r.ungedeckt || [] });
  } catch (e) {
    _chatHistory.pop();
    _chatHistory.push({ role: 'assistant', content: '⚠ Fehler: ' + e.message });
  }
  btn.disabled = false;
  _renderChat();
}
