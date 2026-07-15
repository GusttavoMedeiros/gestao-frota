/* Service worker do Gestão de Frota (PWA).
   - Arquivos estáticos: responde do cache (rápido) e atualiza em segundo
     plano — na próxima visita, a versão nova já está valendo.
   - Páginas e dados: sempre rede primeiro (nunca mostra dado velho).
   - Nunca intercepta POST (login, cadastros, exclusões passam direto). */

const CACHE = 'frota-v6';
const SHELL = [
  '/static/style.css',
  '/static/vendor/bootstrap/bootstrap.min.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
  '/static/vendor/fonts/fonts.css',
  '/static/icon.svg',
  '/static/icon-192.png',
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

  // Estáticos: cache primeiro + atualização em segundo plano
  // (stale-while-revalidate: rápido agora, fresco na próxima visita).
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(CACHE).then(function (cache) {
        return cache.match(req).then(function (guardado) {
          const atualiza = fetch(req).then(function (resp) {
            if (resp && resp.ok) cache.put(req, resp.clone());
            return resp;
          }).catch(function () { return guardado; });
          return guardado || atualiza;
        });
      })
    );
    return;
  }

  // Páginas e dados: rede primeiro; sem rede, tenta o cache como reserva.
  event.respondWith(
    fetch(req).catch(function () { return caches.match(req); })
  );
});
