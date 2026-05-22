

export const getToken = () => localStorage.getItem('access_token') || '';

export const getFreshHeaders = () => ({
  Authorization: `Bearer ${getToken()}`,
});

export const isValidHeaders = (headers) => {
  if (!headers) return false;
  const auth = headers.Authorization || '';
  return (
    auth.startsWith('Bearer ') &&
    auth !== 'Bearer null' &&
    auth !== 'Bearer undefined' &&
    auth !== 'Bearer '
  );
};

// ── Script / stylesheet loaders (used by PdfViewer) ──────────────────────────

export function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

export function loadLink(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  document.head.appendChild(link);
}