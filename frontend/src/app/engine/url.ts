/** URL validation, normalisation and domain helpers. */

const TWO_LEVEL_SUFFIXES = new Set([
  'edu.cn', 'ac.cn', 'com.cn', 'org.cn', 'net.cn', 'gov.cn', 'edu.hk', 'edu.tw', 'edu.mo', 'org.hk', 'com.hk',
]);
const BINARY_EXT = /\.(jpe?g|png|gif|bmp|svg|webp|ico|mp4|mp3|avi|mov|zip|rar|7z|exe|dmg|css|js|woff2?|pdf|docx?|xlsx?|pptx?)$/i;
const SKIP_SCHEMES = /^(mailto:|javascript:|tel:|data:|#)/i;
export const ALLOWED_SUFFIXES = ['edu.cn', 'ac.cn', 'edu.hk', 'edu.mo', 'edu.tw'];

export class InvalidUrlError extends Error {}

/** Validate a user-supplied URL and return its normalised form (throws InvalidUrlError). */
export function validateUniversityUrl(raw: string): string {
  let url = (raw ?? '').trim();
  if (!url) throw new InvalidUrlError('Enter the university website URL.');
  if (!/^[a-z]+:\/\//i.test(url)) url = 'https://' + url;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    throw new InvalidUrlError('That does not look like a valid URL.');
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new InvalidUrlError('Only http(s) URLs are supported.');
  const host = u.hostname.toLowerCase();
  if (!host.includes('.')) throw new InvalidUrlError('That does not look like a website address.');
  if (/^[\d.]+$/.test(host) || host.startsWith('[')) throw new InvalidUrlError('Use the university domain name, not an IP address.');
  if (!ALLOWED_SUFFIXES.some((s) => host === s || host.endsWith('.' + s))) {
    throw new InvalidUrlError('Enter an official Chinese university website (ending in .edu.cn, .ac.cn, .edu.hk, .edu.mo or .edu.tw).');
  }
  return normalizeUrl(u.toString());
}

export function normalizeUrl(raw: string): string {
  const u = new URL(raw.trim());
  u.hash = '';
  u.hostname = u.hostname.toLowerCase();
  if ((u.protocol === 'http:' && u.port === '80') || (u.protocol === 'https:' && u.port === '443')) u.port = '';
  if (!u.pathname) u.pathname = '/';
  return u.toString();
}

/** Key for de-duplicating URLs (ignores scheme, www., trailing slash). */
export function canonicalKey(raw: string): string {
  try {
    const u = new URL(raw);
    const host = u.hostname.toLowerCase().replace(/^www\./, '');
    const path = u.pathname.replace(/\/+$/, '') || '/';
    return u.search ? `${host}${path}${u.search}` : `${host}${path}`;
  } catch {
    return raw;
  }
}

export function hostname(raw: string): string {
  try {
    return new URL(raw).hostname.toLowerCase();
  } catch {
    return '';
  }
}

export function registrableDomain(urlOrHost: string): string {
  const host = urlOrHost.includes('://') ? hostname(urlOrHost) : urlOrHost.toLowerCase();
  const labels = host.split('.').filter(Boolean);
  if (labels.length >= 3 && TWO_LEVEL_SUFFIXES.has(labels.slice(-2).join('.'))) return labels.slice(-3).join('.');
  return labels.slice(-2).join('.');
}

export function isOfficial(url: string, domain: string): boolean {
  const host = hostname(url);
  return host === domain || host.endsWith('.' + domain);
}

export function resolveLink(base: string, href: string | null | undefined): string | null {
  if (!href) return null;
  const h = href.trim();
  if (!h || SKIP_SCHEMES.test(h)) return null;
  let u: URL;
  try {
    u = new URL(h, base);
  } catch {
    return null;
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
  if (BINARY_EXT.test(u.pathname)) return null;
  return normalizeUrl(u.toString());
}
