// The nonce nginx puts in the page for this request (see docker/nginx/nginx.conf). The
// Content-Security-Policy only lets a <style> element through if it carries the same nonce,
// and Vuetify writes one for its theme. In development the placeholder is still in the page,
// and there is no policy to satisfy, so there is no nonce.
export function cspNonce(doc: Document = document): string | undefined {
  const nonce = doc.querySelector<HTMLMetaElement>('meta[name="csp-nonce"]')?.content;
  return nonce && !nonce.startsWith("__") ? nonce : undefined;
}
