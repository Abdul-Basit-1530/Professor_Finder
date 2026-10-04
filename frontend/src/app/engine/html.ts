/** HTML parsing (browser DOMParser) and charset handling for Chinese sites. */
import { normalizeSpace } from './text';
import { resolveLink } from './url';

export interface Link {
  url: string;
  text: string;
  context: string; // text of the surrounding element (helps classify person links)
}

export interface ParsedPage {
  title: string;
  text: string;
  links: Link[];
  mailtos: string[];
  doc: Document;
}

const META_CHARSET_RE = /<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_-]+)/i;

/** Decode HTML bytes. Chinese sites often use GBK/GB2312, frequently without telling the server header. */
export function decodeHtml(bytes: Uint8Array, contentType: string | null): string {
  // Valid UTF-8 is almost never GBK text, while GB18030 "successfully" decodes UTF-8 into mojibake —
  // so strict UTF-8 wins whenever it works.
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    /* not UTF-8 */
  }
  const candidates: string[] = [];
  const header = /charset=([\w-]+)/i.exec(contentType ?? '');
  if (header) candidates.push(header[1]);
  const head = new TextDecoder('latin1').decode(bytes.slice(0, 4096));
  const meta = META_CHARSET_RE.exec(head);
  if (meta) candidates.push(meta[1]);
  candidates.push('gb18030');
  for (let enc of candidates) {
    enc = enc.toLowerCase();
    if (['gb2312', 'gbk', 'x-gbk', 'gb_2312-80'].includes(enc)) enc = 'gb18030'; // superset, decodes both
    try {
      return new TextDecoder(enc, { fatal: true }).decode(bytes);
    } catch {
      /* try next */
    }
  }
  return new TextDecoder('utf-8').decode(bytes);
}

const CONTEXT_TAGS = new Set(['LI', 'TR', 'DIV', 'TD', 'P', 'DD']);

export function parseHtml(html: string, baseUrl: string): ParsedPage {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  let title = doc.querySelector('title')?.textContent?.trim() ?? '';
  if (!title) title = doc.querySelector('meta[property="og:site_name"]')?.getAttribute('content')?.trim() ?? '';

  const mailtos: string[] = [];
  const links: Link[] = [];
  const seen = new Set<string>();
  doc.querySelectorAll('a').forEach((a) => {
    const href = a.getAttribute('href') ?? '';
    if (/^mailto:/i.test(href)) {
      mailtos.push(href.slice(7));
      return;
    }
    const url = resolveLink(baseUrl, href);
    if (!url) return;
    let text = (a.textContent ?? '').replace(/\s+/g, ' ').trim() || a.getAttribute('title') || '';
    if (!text) text = a.querySelector('img')?.getAttribute('alt') ?? '';
    text = text.replace(/\s+/g, ' ').trim().slice(0, 200);
    let parent: Element | null = a.parentElement;
    while (parent && !CONTEXT_TAGS.has(parent.tagName)) parent = parent.parentElement;
    const context = parent ? (parent.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 300) : '';
    const key = url + '|' + text;
    if (seen.has(key)) return;
    seen.add(key);
    links.push({ url, text, context });
  });

  const body = doc.body ? (doc.body.cloneNode(true) as HTMLElement) : null;
  let text = '';
  if (body) {
    body.querySelectorAll('script,style,noscript,svg,iframe,template').forEach((n) => n.remove());
    // Block-level elements -> line breaks, so headings/labels stay on their own lines.
    body.querySelectorAll('br,p,div,li,tr,h1,h2,h3,h4,h5,h6,dt,dd,section,article,header,footer,ul,ol,table')
      .forEach((n) => n.appendChild(doc.createTextNode('\n')));
    text = normalizeSpace(body.textContent ?? '');
  }
  return { title, text, links, mailtos, doc };
}

const BLOCK_MARKERS = ['captcha', '验证码', '人机验证', '安全验证', 'access denied', 'are you a robot', '滑动验证',
  'cf-challenge', 'challenge-platform'];

export function looksBlocked(status: number, text: string): boolean {
  if ([401, 403, 429, 503].includes(status)) return true;
  const low = text.slice(0, 3000).toLowerCase();
  return text.length < 1500 && BLOCK_MARKERS.some((m) => low.includes(m));
}
