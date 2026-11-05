// Cloudflare Worker: прокси к Telegram Bot API для сервера в РФ,
// откуда api.telegram.org недоступен. На сервере: TELEGRAM_API_BASE=https://<адрес воркера>
// Пропускает только пути /bot<token>/<метод>, больше ничего не делает и не логирует.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (!/^\/bot\d+:[\w-]+\/\w+$/.test(url.pathname)) {
      return new Response('not found', { status: 404 });
    }
    if (request.method !== 'GET' && request.method !== 'POST') {
      return new Response('method not allowed', { status: 405 });
    }
    const target = 'https://api.telegram.org' + url.pathname + url.search;
    return fetch(target, {
      method: request.method,
      headers: { 'content-type': request.headers.get('content-type') || 'application/json' },
      body: request.method === 'POST' ? await request.text() : undefined,
    });
  },
};
