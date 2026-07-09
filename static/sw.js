/* Service worker do Gestão de Frota (PWA).
   - Guarda o "esqueleto" (CSS, fontes, ícones) para carregar rápido / offline.
   - Páginas e dados são sempre buscados na rede primeiro (nunca mostra dado velho);
     só recorre ao cache se estiver sem internet.
   - Nunca intercepta POST (login, cadastros, exclusões passam direto). */

const CACHE = 'frota-v1';
const SHELL = [
  '/static/style.css',
  '/static/vendor/bootstrap/bootstrap.min.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
  '/static/vendor/fonts/fonts.css',
  '/static/icon.svg',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE)
      .then(function (cache) { return cache.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(
        nomes.filter(function (n) { return n !== CACHE; })
             .map(function (n) { return caches.delete(n); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  const req = event.request;
  if (req.method !== 'GET') return;                 // não mexe em POST
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // só o próprio site

  // Arquivos estáticos: cache primeiro (rápido), rede se não tiver.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then(function (hit) {
        return hit || fetch(req).then(function (resp) {
          const copia = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copia); });
          return resp;
        });
      })
    );
    return;
  }

  // Páginas e dados: rede primeiro; cache só como reserva offline.
  event.respondWith(
    fetch(req).catch(function () { return caches.match(req); })
  );
});
