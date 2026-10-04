import { beforeEach, describe, expect, it } from 'vitest';

import { LocalExtractor } from './local-extractor';

describe('LocalExtractor', () => {
  let extractor: LocalExtractor;

  beforeEach(() => {
    extractor = new LocalExtractor();
  });

  it('extracts published and obfuscated addresses without guessing', async () => {
    const scan = await extractor.parse(
      '<title>Faculty</title><p>Contact Li Wei: li.wei@example.edu.cn</p><p>chen#example.edu.cn</p><a href="mailto:wang [at] example.edu.cn">Email</a>',
      'https://example.edu.cn/faculty',
    );

    expect(scan.contacts.map((contact) => contact.email)).toEqual([
      'li.wei@example.edu.cn',
      'chen@example.edu.cn',
      'wang@example.edu.cn',
    ]);
    expect(scan.title).toBe('Faculty');
  });

  it('resolves page links and profile links relative to the source', async () => {
    const scan = await extractor.parse(
      '<ul><li><a href="people/li.html">Li Wei</a> li@example.edu.cn</li></ul><a href="/faculty">Faculty</a>',
      'https://example.edu.cn/cs/index.html',
    );

    expect(scan.contacts[0].profileUrl).toBe('https://example.edu.cn/cs/people/li.html');
    expect(scan.links).toContainEqual({ label: 'Faculty', url: 'https://example.edu.cn/faculty' });
  });

  it('normalizes host-only inputs to HTTPS', () => {
    expect(extractor.normalizeUrl('example.edu.cn')).toBe('https://example.edu.cn/');
  });
});