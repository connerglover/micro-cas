// Self-hosted worker enables WebTILP on static hosts without custom headers.
// It never caches packages or USB data and only controls this site's directory.
globalThis.isolationReady = (async () => {
  if (globalThis.crossOriginIsolated) return true;
  if (!isSecureContext || !('serviceWorker' in navigator)) return false;
  const wait = promise => {
    let timer;
    return Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Browser isolation timed out')), 8000);
    })]).finally(() => clearTimeout(timer));
  };
  try {
    await wait(navigator.serviceWorker.register('./sw.js', { scope: './' }));
    await wait(navigator.serviceWorker.ready);
    if (sessionStorage.getItem('casevo-isolation-reload') !== '1') {
      if (!navigator.serviceWorker.controller) {
        await wait(new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true })));
      }
      sessionStorage.setItem('casevo-isolation-reload', '1');
      location.reload();
    }
  } catch (error) { console.warn('Browser isolation could not be enabled:', error); }
  return false;
})();
