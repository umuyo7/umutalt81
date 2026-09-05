window.POS = (() => {
  const prefix = window.APP_PREFIX || '';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const url = path => (!prefix || path.startsWith(prefix + '/')) ? path : prefix + path;

  function toast(message, error = false) {
    let stack = document.querySelector('.toast-stack');
    if (!stack) { stack = document.createElement('div'); stack.className = 'toast-stack'; document.body.appendChild(stack); }
    const item = document.createElement('div'); item.className = error ? 'toast error-toast' : 'toast'; item.textContent = message; stack.appendChild(item);
    setTimeout(() => item.remove(), 3500);
  }

  async function parse(response) {
    let payload;
    try { payload = await response.json(); } catch (_) { payload = null; }
    if (!response.ok || !payload?.success) {
      const message = payload?.error?.message || 'İşlem tamamlanamadı. Lütfen tekrar deneyin.';
      toast(message, true); throw new Error(message);
    }
    if (payload.data?.notice) toast(payload.data.notice);
    return payload;
  }

  async function get(path) {
    try {
      return parse(await fetch(url(path), { credentials: 'same-origin', headers: { Accept: 'application/json' } }));
    } catch (error) {
      if (!navigator.onLine) toast('Bağlantı yok. Sunucu yanıtı alınmadan işlem tamamlanmış sayılmaz.', true);
      throw error;
    }
  }

  async function call(path, body = {}, methodOrOptions = 'POST') {
    const options = typeof methodOrOptions === 'string' ? { method: methodOrOptions } : methodOrOptions;
    const headers = { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-Token': csrf };
    if (options.idempotency) headers['Idempotency-Key'] = crypto.randomUUID();
    let response;
    try {
      response = await fetch(url(path), { method: options.method || 'POST', credentials: 'same-origin', headers, body: JSON.stringify(body) });
    } catch (error) {
      toast('Bağlantı yok. İşlem sunucu tarafından onaylanmadı.', true);
      throw error;
    }
    const payload = await parse(response);
    if (payload.data?.message) toast(payload.data.message);
    return payload;
  }

  function tryMoney(value) {
    return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(Number(value || 0));
  }

  function updateDurations() {
    document.querySelectorAll('[data-opened-at]').forEach(node => {
      const minutes = Math.max(0, Math.floor((Date.now() - new Date(node.dataset.openedAt).getTime()) / 60000));
      node.textContent = minutes < 60 ? `${minutes} dk` : `${Math.floor(minutes / 60)} sa ${minutes % 60} dk`;
    });
  }

  function liveReload(paths) {
    if (!window.EventSource) return;
    const stream = new EventSource(url('/api/v1/events'));
    let timer;
    stream.onmessage = () => { clearTimeout(timer); timer = setTimeout(() => { if (paths.includes(location.pathname.replace(prefix, '') || '/')) location.reload(); }, 700); };
  }

  if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register(url('/service-worker.js'), { scope: url('/') }).catch(() => {}));
  window.addEventListener('offline', () => toast('Bağlantı yok. Ödeme ve adisyon işlemleri durduruldu.', true));
  window.addEventListener('online', () => toast('Bağlantı yeniden kuruldu.'));
  return { get, call, toast, tryMoney, updateDurations, liveReload, url };
})();
