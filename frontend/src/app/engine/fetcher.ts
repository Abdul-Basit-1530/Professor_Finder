/**
 * Polite page fetcher running in the browser. Pages are requested through the tiny `/api/fetch`
 * function (browsers can't read other sites directly), then decoded and parsed here.
 *
 * - per-host delay + global concurrency cap + page budget
 * - robots.txt respected
 * - CAPTCHA / anti-bot pages are reported, never bypassed
 * - VSB/Tsites faculty systems: emails published as encrypted tokens are decoded with the site's own
 *   public endpoint — the same request every visitor's browser makes to show the email
 * - nothing is stored: results live in memory for this tab only
 */
import { decodeHtml, Link, looksBlocked, parseHtml } from './html';
import { hostname, normalizeUrl } from './url';

export interface RawResponse {
  status: number; // upstream HTTP status (0 = network/proxy error)
  finalUrl: string;
  contentType: string;
  bytes: Uint8Array;
  error?: string;
}

export type Transport = (url: string) => Promise<RawResponse>;

export interface Page {
  url: string;
  finalUrl: string;
  status: number;
  title: string;
  text: string;
  html: string;
  links: Link[];
  mailtos: string[];
  blocked: boolean;
  error: string | null;
  fetchedAt: Date;
  ok: boolean;
}

export interface FetcherOptions {
  maxPages: number;
  delayMs: number;
  concurrency: number;
  respectRobots: boolean;
  userAgentToken: string; // robots.txt user-agent we identify as
}

export const DEFAULT_FETCHER_OPTIONS: FetcherOptions = {
  maxPages: 220,
  delayMs: 500,
  concurrency: 4,
  respectRobots: true,
  userAgentToken: 'ProfessorFinder',
};

/** Default transport: the same-origin Vercel function. */
export const proxyTransport: Transport = async (url) => {
  try {
    const res = await fetch(`/api/fetch?url=${encodeURIComponent(url)}`);
    if (!res.ok) {
      let error = `proxy error ${res.status}`;
      try {
        error = ((await res.json()) as { error?: string }).error ?? error;
      } catch {
        /* not json */
      }
      return { status: 0, finalUrl: url, contentType: '', bytes: new Uint8Array(), error };
    }
    return {
      status: Number(res.headers.get('x-upstream-status') ?? '200'),
      finalUrl: res.headers.get('x-final-url') ?? url,
      contentType: res.headers.get('content-type') ?? '',
      bytes: new Uint8Array(await res.arrayBuffer()),
    };
  } catch {
    return { status: 0, finalUrl: url, contentType: '', bytes: new Uint8Array(), error: 'network error' };
  }
};

function emptyPage(url: string, error: string, status = 0, blocked = false): Page {
  return { url, finalUrl: url, status, title: '', text: '', html: '', links: [], mailtos: [], blocked, error,
    fetchedAt: new Date(), ok: false };
}

class Semaphore {
  private queue: (() => void)[] = [];
  constructor(private slots: number) {}
  async acquire(): Promise<void> {
    if (this.slots > 0) {
      this.slots--;
      return;
    }
    await new Promise<void>((r) => this.queue.push(r));
  }
  release(): void {
    const next = this.queue.shift();
    if (next) next();
    else this.slots++;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class Fetcher {
  networkFetches = 0;
  errors = 0;
  private memo = new Map<string, Promise<Page>>();
  private hostNext = new Map<string, number>();
  private robots = new Map<string, Promise<string[] | null>>();
  private sem: Semaphore;
  private opts: FetcherOptions;

  constructor(private transport: Transport = proxyTransport, opts: Partial<FetcherOptions> = {}) {
    this.opts = { ...DEFAULT_FETCHER_OPTIONS, ...opts };
    this.sem = new Semaphore(this.opts.concurrency);
  }

  fetch(rawUrl: string): Promise<Page> {
    let url: string;
    try {
      url = normalizeUrl(rawUrl);
    } catch {
      return Promise.resolve(emptyPage(rawUrl, 'invalid URL'));
    }
    let p = this.memo.get(url);
    if (!p) {
      p = this.load(url).then((page) => {
        if (page.error) this.errors++;
        return page;
      });
      this.memo.set(url, p);
    }
    return p;
  }

  private async throttle(host: string): Promise<void> {
    const now = Date.now();
    const at = Math.max(now, this.hostNext.get(host) ?? 0);
    this.hostNext.set(host, at + this.opts.delayMs);
    if (at > now) await sleep(at - now);
  }

  private async raw(url: string): Promise<RawResponse> {
    await this.sem.acquire();
    try {
      await this.throttle(hostname(url));
      this.networkFetches++;
      return await this.transport(url);
    } finally {
      this.sem.release();
    }
  }

  private async load(url: string): Promise<Page> {
    if (this.networkFetches >= this.opts.maxPages) return emptyPage(url, 'page budget exhausted');
    if (this.opts.respectRobots && !(await this.robotsAllowed(url))) return emptyPage(url, 'disallowed by robots.txt');
    const res = await this.raw(url);
    if (res.error) return emptyPage(url, res.error);
    if (res.status >= 400) {
      const msg = res.status === 412 ? 'HTTP 412 (JavaScript challenge)' : `HTTP ${res.status}`;
      return emptyPage(url, msg, res.status, [403, 412, 429, 503].includes(res.status));
    }
    const html = decodeHtml(res.bytes, res.contentType);
    const parsed = parseHtml(html, res.finalUrl);
    const page: Page = {
      url, finalUrl: res.finalUrl, status: res.status, title: parsed.title, text: parsed.text, html,
      links: parsed.links, mailtos: parsed.mailtos, blocked: false, error: null, fetchedAt: new Date(), ok: true,
    };
    if (looksBlocked(res.status, page.text)) {
      page.blocked = true;
      page.error = 'protected by a CAPTCHA / anti-bot check — open this page manually';
    } else if (!page.text.trim()) {
      page.blocked = res.status === 202;
      page.error = 'page is empty without JavaScript (dynamic page or anti-bot check) — open it manually';
    }
    page.ok = !page.error;
    return page;
  }

  /** Decode VSB/Tsites encrypted fields (e.g. 电子邮箱) using the site's own public decode endpoint. */
  async decodeTsitesFields(page: Page): Promise<string[]> {
    if (!page.html.includes('_tsites_encrypt_field')) return [];
    const mode = /_tsites_com_view_mode_type_\s*=\s*(\d+)/.exec(page.html)?.[1] ?? '8';
    const doc = new DOMParser().parseFromString(page.html, 'text/html');
    const spans = [...doc.querySelectorAll('span[_tsites_encrypt_field]')].slice(0, 8);
    const origin = new URL(page.finalUrl).origin;
    const out: string[] = [];
    for (const span of spans) {
      const id = span.getAttribute('id') ?? '';
      const content = (span.textContent ?? '').trim();
      if (!id || !/^[0-9a-f]{16,}$/i.test(content)) continue;
      const endpoint = `${origin}/system/resource/tsites/tsitesencrypt.jsp?id=${encodeURIComponent(id)}` +
        `&content=${encodeURIComponent(content)}&mode=${encodeURIComponent(mode)}`;
      const res = await this.raw(endpoint);
      if (res.error || res.status >= 400) continue;
      try {
        const data = JSON.parse(decodeHtml(res.bytes, res.contentType)) as { content?: unknown };
        if (typeof data.content === 'string' && data.content.length < 300) out.push(data.content);
      } catch {
        /* not json */
      }
    }
    return out;
  }

  // ------------------------------------------------------------------ robots.txt
  private robotsAllowed(url: string): Promise<boolean> {
    const u = new URL(url);
    let rules = this.robots.get(u.origin);
    if (!rules) {
      rules = this.raw(u.origin + '/robots.txt').then((res) =>
        !res.error && res.status === 200 && /text|^$/.test(res.contentType)
          ? parseRobots(new TextDecoder().decode(res.bytes), this.opts.userAgentToken)
          : null);
      this.robots.set(u.origin, rules);
    }
    return rules.then((disallow) => !disallow || !disallow.some((p) => p && (u.pathname + u.search).startsWith(p)));
  }
}

/** Minimal robots.txt parser: Disallow rules for `*` or our own user-agent token. */
export function parseRobots(txt: string, agent: string): string[] {
  const out: string[] = [];
  let applies = false;
  let lastWasAgent = false;
  for (const raw of txt.split(/\r?\n/)) {
    const line = raw.replace(/#.*/, '').trim();
    const m = /^([A-Za-z-]+)\s*:\s*(.*)$/.exec(line);
    if (!m) continue;
    const key = m[1].toLowerCase();
    const val = m[2].trim();
    if (key === 'user-agent') {
      const match = val === '*' || val.toLowerCase().includes(agent.toLowerCase());
      applies = lastWasAgent ? applies || match : match;
      lastWasAgent = true;
    } else {
      lastWasAgent = false;
      if (applies && key === 'disallow' && val) out.push(val);
    }
  }
  return out;
}
