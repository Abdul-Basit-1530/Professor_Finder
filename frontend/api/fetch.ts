/**
 * Vercel serverless function: GET /api/fetch?url=<university page>
 *
 * Browsers are not allowed to read other websites directly (CORS), so the app asks this
 * function to fetch a page and hand the raw bytes back. It is deliberately tiny:
 *   - stores nothing (no database, no cache, no logs of results)
 *   - only fetches Chinese academic hosts (*.edu.cn, *.ac.cn, …), so it is not an open proxy
 *   - re-checks every redirect hop, refuses IP addresses / non-standard ports
 *   - caps time (15 s) and size (4 MB)
 *
 * Plain Web-standard Request/Response, so the same file also runs in `node dev-server.mjs`.
 */

const DEFAULT_SUFFIXES = ['edu.cn', 'ac.cn', 'edu.hk', 'edu.mo', 'edu.tw'];
const MAX_BYTES = 4 * 1024 * 1024;
const TIMEOUT_MS = 15000;
const MAX_REDIRECTS = 5;
const USER_AGENT = 'Mozilla/5.0 (compatible; ProfessorFinder/2.0; academic-research)';
const ALLOWED_TYPES = /text\/html|application\/xhtml|text\/plain|application\/json|text\/xml|application\/xml|text\/javascript/i;

function allowedSuffixes(): string[] {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  const extra = env?.['ALLOWED_HOST_SUFFIXES'];
  return extra ? extra.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean) : DEFAULT_SUFFIXES;
}

/** Returns an error message if the URL may not be fetched, otherwise null. */
export function checkUrl(raw: string, suffixes: string[] = allowedSuffixes()): string | null {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return 'invalid URL';
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return 'only http(s) URLs are allowed';
  if (u.username || u.password) return 'credentials in URL are not allowed';
  if (u.port && u.port !== '80' && u.port !== '443') return 'non-standard ports are not allowed';
  const host = u.hostname.toLowerCase();
  if (/^[\d.]+$/.test(host) || host.includes(':') || host.startsWith('[')) return 'IP addresses are not allowed';
  if (!suffixes.some((s) => host === s || host.endsWith('.' + s))) {
    return `only university domains are allowed (${suffixes.join(', ')})`;
  }
  return null;
}

function json(status: number, error: string): Response {
  return new Response(JSON.stringify({ error }), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}

export async function GET(request: Request): Promise<Response> {
  const target = new URL(request.url).searchParams.get('url') ?? '';
  let current = target;
  const problem = checkUrl(current);
  if (problem) return json(400, problem);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    let upstream: Response | null = null;
    for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
      upstream = await fetch(current, {
        redirect: 'manual',
        signal: controller.signal,
        headers: {
          'user-agent': USER_AGENT,
          accept: 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
          'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
        },
      });
      const location = upstream.headers.get('location');
      if (upstream.status >= 300 && upstream.status < 400 && location) {
        const next = new URL(location, current).toString();
        const hopProblem = checkUrl(next);
        if (hopProblem) return json(400, `redirect blocked: ${hopProblem}`);
        current = next;
        continue;
      }
      break;
    }
    if (!upstream) return json(502, 'no response');
    if (upstream.status >= 300 && upstream.status < 400) return json(502, 'too many redirects');

    const type = upstream.headers.get('content-type') ?? '';
    if (type && !ALLOWED_TYPES.test(type)) return json(415, `unsupported content type ${type.split(';')[0]}`);
    const declared = Number(upstream.headers.get('content-length') ?? '0');
    if (declared > MAX_BYTES) return json(413, 'page too large');
    const body = new Uint8Array(await upstream.arrayBuffer());
    if (body.byteLength > MAX_BYTES) return json(413, 'page too large');

    return new Response(body, {
      status: 200,
      headers: {
        'content-type': type || 'text/html',
        'x-final-url': current,
        'x-upstream-status': String(upstream.status),
        'cache-control': 'no-store',
      },
    });
  } catch (err) {
    const aborted = (err as Error)?.name === 'AbortError';
    return json(aborted ? 504 : 502, aborted ? 'timeout' : 'could not reach the website');
  } finally {
    clearTimeout(timer);
  }
}
