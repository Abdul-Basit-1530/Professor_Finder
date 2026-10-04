// Run with: node --test api/   (Node 22.18+/24 strips TypeScript types natively)
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import handler, { checkUrl } from './fetch.ts';

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

test('allows Chinese university domains only', () => {
  assert.equal(checkUrl('https://www.tsinghua.edu.cn/'), null);
  assert.equal(checkUrl('https://faculty.uestc.edu.cn/x/zh_CN/index.htm'), null);
  assert.equal(checkUrl('http://www.cas.ac.cn/'), null);
  assert.match(checkUrl('https://www.google.com/') ?? '', /only university domains/);
  assert.match(checkUrl('https://evil.com/?x=.edu.cn') ?? '', /only university domains/);
  assert.match(checkUrl('https://edu.cn.evil.com/') ?? '', /only university domains/);
});

test('rejects IPs, ports, credentials and other schemes', () => {
  assert.match(checkUrl('http://127.0.0.1/') ?? '', /IP addresses/);
  assert.match(checkUrl('http://[::1]/') ?? '', /IP addresses/);
  assert.match(checkUrl('http://www.pku.edu.cn:8080/') ?? '', /ports/);
  assert.match(checkUrl('http://user:pw@www.pku.edu.cn/') ?? '', /credentials/);
  assert.match(checkUrl('file:///etc/passwd') ?? '', /http/);
  assert.match(checkUrl('not a url') ?? '', /invalid/);
});

test('returns the page bytes with final URL and upstream status', async () => {
  globalThis.fetch = (async () =>
    new Response('<html>计算机学院</html>', { status: 200, headers: { 'content-type': 'text/html' } })) as typeof fetch;
  const res = await handler.fetch(new Request('https://app.test/api/fetch?url=https://www.pku.edu.cn/'));
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('x-final-url'), 'https://www.pku.edu.cn/');
  assert.equal(res.headers.get('x-upstream-status'), '200');
  assert.equal(res.headers.get('cache-control'), 'no-store');
  assert.match(await res.text(), /计算机学院/);
});

test('serves the documented Vercel Web Standard handler', async () => {
  globalThis.fetch = (async () =>
    new Response('<title>CSU</title>', { status: 200, headers: { 'content-type': 'text/html' } })) as typeof fetch;
  const response = await handler.fetch(new Request('https://app.test/api/fetch?url=https%3A%2F%2Fen.csu.edu.cn%2F'));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('x-final-url'), 'https://en.csu.edu.cn/');
  assert.match(await response.text(), /CSU/);
});

test('follows allowed redirects and blocks redirects to other hosts', async () => {
  const hops: Record<string, Response> = {
    'https://www.pku.edu.cn/': new Response(null, { status: 302, headers: { location: '/en/' } }),
    'https://www.pku.edu.cn/en/': new Response('ok', { status: 200, headers: { 'content-type': 'text/html' } }),
    'https://www.zju.edu.cn/': new Response(null, { status: 301, headers: { location: 'http://169.254.169.254/' } }),
  };
  globalThis.fetch = (async (input: string | URL | Request) => hops[String(input)]) as typeof fetch;
  const ok = await handler.fetch(new Request('https://app.test/api/fetch?url=https://www.pku.edu.cn/'));
  assert.equal(ok.headers.get('x-final-url'), 'https://www.pku.edu.cn/en/');
  const blocked = await handler.fetch(new Request('https://app.test/api/fetch?url=https://www.zju.edu.cn/'));
  assert.equal(blocked.status, 400);
  assert.match(await blocked.text(), /redirect blocked/);
});

test('refuses binary content and passes through upstream errors as status', async () => {
  globalThis.fetch = (async () =>
    new Response('PK..', { status: 200, headers: { 'content-type': 'application/zip' } })) as typeof fetch;
  const res = await handler.fetch(new Request('https://app.test/api/fetch?url=https://www.pku.edu.cn/a.zip'));
  assert.equal(res.status, 415);

  globalThis.fetch = (async () =>
    new Response('nope', { status: 404, headers: { 'content-type': 'text/html' } })) as typeof fetch;
  const missing = await handler.fetch(new Request('https://app.test/api/fetch?url=https://www.pku.edu.cn/x'));
  assert.equal(missing.status, 200);
  assert.equal(missing.headers.get('x-upstream-status'), '404');
});

test('network failure becomes a 502 instead of crashing', async () => {
  globalThis.fetch = (async () => {
    throw new TypeError('fetch failed');
  }) as typeof fetch;
  const res = await handler.fetch(new Request('https://app.test/api/fetch?url=https://www.pku.edu.cn/'));
  assert.equal(res.status, 502);
});
