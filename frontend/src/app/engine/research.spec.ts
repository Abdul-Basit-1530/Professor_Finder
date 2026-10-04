import { beforeAll, describe, expect, it } from 'vitest';

import { ROOT, allSiteText, mockTransport } from '../../testing/mock-site';
import { Fetcher } from './fetcher';
import { deduplicate, runResearch, verifyProfessor } from './research';
import { extractEmails } from './text';
import type { ProfessorInfo, ResearchResult, Step } from './types';

const FIELDS = ['Artificial Intelligence', 'Machine Learning', 'Computer Vision', 'Software Engineering'];

describe('research workflow against the mock university', () => {
  let result: ResearchResult;
  let fetched: string[];
  let lastSteps: Step[] = [];
  const streamed: ProfessorInfo[] = [];

  beforeAll(async () => {
    fetched = [];
    const fetcher = new Fetcher(mockTransport(fetched), { delayMs: 0 });
    result = await runResearch(ROOT + '/', FIELDS, fetcher, {}, {
      onStep: (s) => (lastSteps = s),
      onProfessor: (p) => streamed.push(p),
    });
  });

  const byCn = () => new Map(result.professors.map((p) => [p.nameChinese ?? p.name, p]));

  it('completes every step', () => {
    expect(result.error).toBeNull();
    expect(lastSteps.map((s) => s.status)).toEqual(['done', 'done', 'done', 'done']);
    expect(streamed.length).toBeGreaterThan(0);
  });

  it('identifies the university', () => {
    expect(result.university?.name).toBe('Mock University');
    expect(result.university?.nameChinese).toBe('模拟大学');
    expect(result.university?.location).toContain('Beijing');
    expect(result.university?.verified).toBe(true);
  });

  it('picks only relevant departments, with Chinese names', () => {
    const names = result.departments.map((d) => `${d.name} ${d.nameChinese ?? ''}`).join(' | ');
    expect(names).toContain('计算机科学与技术学院');
    expect(names).toContain('软件学院');
    expect(names).not.toMatch(/外国语|化学|Foreign|论坛/);
  });

  it('extracts verified emails and profile links, de-duplicating the English profile', () => {
    const profs = byCn();
    const zhang = result.professors.filter((p) => p.email === 'zhangwei@mocku.edu.cn');
    expect(zhang).toHaveLength(1);
    expect(zhang[0].name).toBe('Wei Zhang'); // English name written on the English page wins
    expect(zhang[0].nameChinese).toBe('张伟');
    expect(zhang[0].position).toBe('Professor');
    expect(zhang[0].verification).toBe('VERIFIED');
    expect(zhang[0].profileUrl).toMatch(/^https:\/\/cs\.mocku\.edu\.cn\//);

    expect(profs.get('李娜')!.name).toBe('Li Na');
    expect(profs.get('李娜')!.profileUrl).toBe('https://cs.mocku.edu.cn/szdw/lina.htm');
    expect(profs.get('陈静')!.email).toBe('chenjing@sse.mocku.edu.cn');
    expect(result.professors.find((p) => p.name === 'John Smith')!.email).toBe('jsmith@sse.mocku.edu.cn');
  });

  it('decodes VSB/Tsites encrypted emails via the site endpoint', () => {
    const zhao = byCn().get('赵磊')!;
    expect(zhao.email).toBe('zhaolei@mocku.edu.cn');
    expect(zhao.verification).toBe('VERIFIED');
    expect(fetched.some((u) => u.includes('tsitesencrypt.jsp'))).toBe(true);
  });

  it('never guesses: ambiguous names, missing and personal emails, broken links', () => {
    const profs = byCn();
    const le = profs.get('王乐')!; // 乐 is le/yue in given names -> Chinese name kept
    expect(le.name).toBe('王乐');
    expect(le.email).toBeNull();
    expect(le.verification).toBe('PARTIALLY VERIFIED');

    const liu = profs.get('刘洋')!; // only a gmail address on the page
    expect(liu.email).toBeNull();
    expect(liu.notes.join(' ')).toContain('personal (non-university) email');

    const wang = profs.get('王强')!; // profile link 404s
    expect(wang.verification).toBe('NOT VERIFIED');
    expect(wang.notes.join(' ')).toContain('could not be loaded');
  });

  it('never invents emails or uses office/footer emails', () => {
    const siteEmails = new Set(extractEmails(allSiteText()));
    for (const p of result.professors) {
      if (!p.email) continue;
      expect(siteEmails.has(p.email)).toBe(true);
      expect(['cs@mocku.edu.cn', 'office@mocku.edu.cn']).not.toContain(p.email);
    }
  });

  it('lists verified contacts first', () => {
    const rank = { 'VERIFIED': 0, 'PARTIALLY VERIFIED': 1, 'NOT VERIFIED': 2 } as const;
    const order = result.professors.map((p) => rank[p.verification]);
    expect(order).toEqual([...order].sort());
  });

  it('respects robots.txt and does not crawl unrelated pages', () => {
    expect(fetched.some((u) => u.includes('/private/'))).toBe(false);
    expect(fetched.some((u) => u.includes('fl.mocku') || u.includes('chem.mocku'))).toBe(false);
  });
});

describe('workflow limits and failures', () => {
  it('honours maxProfessors', async () => {
    const r = await runResearch(ROOT + '/', FIELDS, new Fetcher(mockTransport(), { delayMs: 0 }), { maxProfessors: 2 });
    expect(r.professors.length).toBeLessThanOrEqual(2);
  });

  it('fails gracefully when the site cannot be loaded', async () => {
    const r = await runResearch('https://nothing.mocku.edu.cn/', FIELDS, new Fetcher(mockTransport(), { delayMs: 0 }));
    expect(r.error).toContain('Could not load');
    expect(r.professors).toEqual([]);
  });

  it('can be cancelled', async () => {
    const r = await runResearch(ROOT + '/', FIELDS, new Fetcher(mockTransport(), { delayMs: 0 }), {},
      { isCancelled: () => true });
    expect(r.error).toBe('Search cancelled.');
  });

  it('stops at the page budget', async () => {
    const f = new Fetcher(mockTransport(), { delayMs: 0, maxPages: 3 });
    await runResearch(ROOT + '/', FIELDS, f);
    expect(f.networkFetches).toBeLessThanOrEqual(4);
  });
});

describe('dedup and verification', () => {
  const base = (p: Partial<ProfessorInfo>): ProfessorInfo => ({
    id: 0, name: 'X', nameChinese: null, nameIsRomanized: false, position: null, positionOriginal: null,
    department: 'CS', email: null, emailVerified: false, profileUrl: null, listingUrl: null, profileOk: false,
    verification: 'NOT VERIFIED', checks: {}, notes: [], sources: [], profileText: '', profileMailtos: [], ...p,
  });

  it('merges transitively by email, URL and Chinese name', () => {
    const out = deduplicate([
      base({ name: 'Zhang Wei', nameChinese: '张伟', nameIsRomanized: true, profileUrl: 'https://cs.x.edu.cn/zw.htm', profileOk: true }),
      base({ name: 'Wei Zhang', email: 'zw@x.edu.cn', profileUrl: 'https://cs.x.edu.cn/en/zw.html', profileOk: true }),
      base({ name: 'Zhang Wei', nameChinese: '张伟', email: 'zw@x.edu.cn' }),
      base({ name: 'Li Na', nameChinese: '李娜' }),
    ]);
    expect(out).toHaveLength(2);
    expect(out[0].name).toBe('Wei Zhang');
    expect(out[0].email).toBe('zw@x.edu.cn');
  });

  it('removes an email that is not on the page and grades the record', () => {
    const ghost = base({ name: 'Zhang Wei', nameChinese: '张伟', email: 'ghost@mocku.edu.cn', profileOk: true,
      profileUrl: 'https://cs.mocku.edu.cn/zw.htm', profileText: '张伟 教授' });
    verifyProfessor(ghost, 'mocku.edu.cn');
    expect(ghost.email).toBeNull();
    expect(ghost.verification).toBe('PARTIALLY VERIFIED');

    const external = base({ name: 'Zhang Wei', nameChinese: '张伟', email: 'zw@mocku.edu.cn', profileOk: true,
      profileUrl: 'https://blog.example.com/zw', profileText: '张伟 zw@mocku.edu.cn' });
    verifyProfessor(external, 'mocku.edu.cn');
    expect(external.verification).toBe('NOT VERIFIED');
  });
});
