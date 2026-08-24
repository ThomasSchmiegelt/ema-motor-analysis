/* Service Worker der Handy-App.
 *
 * Aufgabenteilung, damit nichts still veraltet:
 *   Huelle (HTML/Symbole/Manifest) .. cache first  -> App startet ohne WLAN
 *   /m/schema ..................... network first -> geaenderte Grenzen kommen an,
 *                                                     alte Fassung als Rueckfall
 *   /m/punkte ..................... NIE gecacht   -> ein zwischengespeichertes
 *                                                     Rechenergebnis waere eine Luege
 *                                                     ueber eine geaenderte Geometrie
 *
 * Die Version steckt im Cache-Namen. Beim Aendern der App hochzaehlen, sonst haelt
 * das Handy die alte Huelle fest.
 */
const VERSION = 'ema-mobil-v1';
const HUELLE = ['/m', '/m/manifest.webmanifest', '/m/icon-192.png', '/m/icon-512.png'];

self.addEventListener('install', ev => {
  ev.waitUntil((async () => {
    const c = await caches.open(VERSION);
    // Einzeln, damit ein fehlendes Symbol nicht die ganze Installation kippt.
    await Promise.all(HUELLE.map(u => c.add(u).catch(() => {})));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', ev => {
  ev.waitUntil((async () => {
    const namen = await caches.keys();
    await Promise.all(namen.filter(n => n !== VERSION).map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', ev => {
  const req = ev.request;
  if (req.method !== 'GET') return;                 // /m/punkte ist POST -> durchreichen
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith('/m')) return;

  if (url.pathname === '/m/schema') {
    ev.respondWith((async () => {
      try {
        const netz = await fetch(req);
        const c = await caches.open(VERSION);
        c.put(req, netz.clone());
        return netz;
      } catch (e) {
        const alt = await caches.match(req);
        if (alt) return alt;
        throw e;
      }
    })());
    return;
  }

  // Huelle: cache first. Der Token-Parameter darf den Treffer nicht verhindern,
  // deshalb wird ohne Abfragezeichenfolge nachgeschlagen.
  ev.respondWith((async () => {
    const ohneParam = new Request(url.origin + url.pathname, { method: 'GET' });
    const treffer = (await caches.match(req)) || (await caches.match(ohneParam));
    if (treffer) {
      fetch(req).then(async n => {
        if (n && n.ok) (await caches.open(VERSION)).put(ohneParam, n.clone());
      }).catch(() => {});
      return treffer;
    }
    const netz = await fetch(req);
    if (netz && netz.ok) (await caches.open(VERSION)).put(ohneParam, netz.clone());
    return netz;
  })());
});
