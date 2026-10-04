/**
 * The research workflow, run entirely in the browser:
 *   University → relevant Departments → Faculty directories → Profiles → Verification
 *
 * For each professor only contact data is collected: name (EN/ZH), position, department,
 * publicly listed institutional email and profile URL. Every email must literally appear on
 * the professor's own page — nothing is guessed, and nothing is stored anywhere.
 */
import { Fetcher, Page } from './fetcher';
import { COMPUTING_HINTS_EN, COMPUTING_HINTS_ZH, FieldSpec, matchFields, resolveFields } from './fields';
import type { Link } from './html';
import { paginationLinks, topLinks } from './links';
import {
  cleanPersonText, detectPosition, emailAppearsIn, extractEmails, hasCjk, isGrounded, isInstitutionalEmail,
  looksLikeChineseName, looksLikeEnglishName, nameKey, romanizeChineseName, stripHonorific,
} from './text';
import type { DepartmentInfo, ProfessorInfo, ResearchResult, SourceRef, Step, UniversityInfo, Verification } from './types';
import { canonicalKey, hostname, isOfficial, registrableDomain } from './url';

export interface ResearchOptions {
  maxProfessors: number;
  maxDepartments: number;
  maxFacultyListPages: number;
  allowNonInstitutionalEmails: boolean;
}

export const DEFAULT_RESEARCH_OPTIONS: ResearchOptions = {
  maxProfessors: 40,
  maxDepartments: 5,
  maxFacultyListPages: 4,
  allowNonInstitutionalEmails: false,
};

export interface ProgressHandlers {
  onStep?: (steps: Step[]) => void;
  onProfessor?: (p: ProfessorInfo) => void;
  isCancelled?: () => boolean;
}

export class FatalResearchError extends Error {}
class Cancelled extends Error {}

export function initialSteps(): Step[] {
  return [
    { key: 'university', label: 'University identified', status: 'pending', message: null },
    { key: 'departments', label: 'Relevant departments found', status: 'pending', message: null },
    { key: 'professors', label: 'Finding professors & emails', status: 'pending', message: null },
    { key: 'verification', label: 'Verifying emails & profiles', status: 'pending', message: null },
  ];
}

// ============================================================================ context

class Ctx {
  domain: string;
  pages = new Map<string, Page>();
  warnings: string[] = [];
  homepage: Page | null = null;
  englishHomepage: Page | null = null;

  constructor(public startUrl: string, public fields: FieldSpec[], public fetcher: Fetcher,
              public opts: ResearchOptions) {
    this.domain = registrableDomain(startUrl);
  }

  warn(msg: string): void {
    if (!this.warnings.includes(msg)) this.warnings.push(msg);
  }

  official(url: string): boolean {
    return isOfficial(url, this.domain);
  }

  async fetch(url: string): Promise<Page> {
    const p = await this.fetcher.fetch(url);
    if (p.ok) this.pages.set(p.finalUrl, p);
    return p;
  }

  allLinks(): Link[] {
    const seen = new Map<string, Link>();
    for (const p of this.pages.values()) {
      for (const ln of p.links) if (!seen.has(ln.url) && this.official(ln.url)) seen.set(ln.url, ln);
    }
    return [...seen.values()];
  }
}

const src = (page: Page, supports: string): SourceRef => ({ url: page.finalUrl, title: page.title || null, supports });

// ============================================================================ university

const CITIES: Record<string, string> = {
  北京: 'Beijing', 上海: 'Shanghai', 天津: 'Tianjin', 重庆: 'Chongqing', 广州: 'Guangzhou', 深圳: 'Shenzhen',
  杭州: 'Hangzhou', 南京: 'Nanjing', 武汉: 'Wuhan', 成都: 'Chengdu', 西安: "Xi'an", 长沙: 'Changsha', 合肥: 'Hefei',
  哈尔滨: 'Harbin', 大连: 'Dalian', 沈阳: 'Shenyang', 长春: 'Changchun', 济南: 'Jinan', 青岛: 'Qingdao', 厦门: 'Xiamen',
  福州: 'Fuzhou', 郑州: 'Zhengzhou', 兰州: 'Lanzhou', 昆明: 'Kunming', 南昌: 'Nanchang', 苏州: 'Suzhou', 无锡: 'Wuxi',
  宁波: 'Ningbo', 太原: 'Taiyuan', 石家庄: 'Shijiazhuang', 贵阳: 'Guiyang', 南宁: 'Nanning', 海口: 'Haikou',
  乌鲁木齐: 'Urumqi', 呼和浩特: 'Hohhot', 珠海: 'Zhuhai', 镇江: 'Zhenjiang', 徐州: 'Xuzhou', 威海: 'Weihai',
  香港: 'Hong Kong', 澳门: 'Macau',
};
const ADDRESS_RE = /(?:地址|校址|通讯地址|Address|ADDRESS|Add)\s*[:：]\s*([^\n|]{4,140})/;
const ADDR_STOP = /\s*(?:邮编|邮政编码|电话|传真|邮箱|版权|E-?mail|Tel|Fax|Phone|Copyright|©|ICP|Postcode|Zip)|\s{2,}/i;
const TITLE_SPLIT = /\s*[|｜\-–—_·:：]\s*/;

function nameFromTitle(title: string): [string | null, string | null] {
  let en: string | null = null;
  let zh: string | null = null;
  for (const raw of (title || '').split(TITLE_SPLIT)) {
    const seg = raw.trim();
    if (!seg) continue;
    if (hasCjk(seg) && /(大学|学院)$/.test(seg) && seg.length <= 20 && !zh) zh = seg;
    else if (/\b(University|Institute of Technology|College|Academy)\b/.test(seg) && seg.length <= 90 && !en) en = seg;
  }
  return [en, zh];
}

async function discoverUniversity(ctx: Ctx): Promise<UniversityInfo> {
  const home = await ctx.fetch(ctx.startUrl);
  if (home.blocked) {
    throw new FatalResearchError('The university website is protected by a CAPTCHA / anti-bot check, so it cannot be ' +
      'read automatically. Try the address of a specific school or faculty directory instead.');
  }
  if (!home.ok) throw new FatalResearchError(`Could not load the university website (${home.error ?? 'empty page'}).`);
  ctx.homepage = home;
  const newDomain = registrableDomain(home.finalUrl);
  if (newDomain !== ctx.domain) ctx.domain = newDomain;
  const info: UniversityInfo = { officialUrl: home.finalUrl, domain: ctx.domain, name: null, nameChinese: null,
    location: null, verified: false, sources: [src(home, 'homepage')] };

  for (const [link] of topLinks(home.links, 'english_site', 2, 3)) {
    if (ctx.official(link.url) && link.url !== home.finalUrl) {
      const en = await ctx.fetch(link.url);
      if (en.ok) {
        ctx.englishHomepage = en;
        info.sources.push(src(en, 'english homepage'));
        break;
      }
    }
  }
  const pages = [home, ctx.englishHomepage].filter((p): p is Page => !!p);
  for (const p of pages) {
    const [en, zh] = nameFromTitle(p.title);
    info.name ??= en;
    info.nameChinese ??= zh;
  }
  for (const p of pages) {
    const m = ADDRESS_RE.exec(p.text);
    if (m) {
      const addr = m[1].split(ADDR_STOP)[0].replace(/^[ ,，;；]+|[ ,，;；]+$/g, '');
      const city = Object.entries(CITIES).find(([zh, en]) => addr.includes(zh) || addr.toLowerCase().includes(en.toLowerCase()));
      info.location = city ? `${city[1]} — ${addr}` : addr;
      break;
    }
  }
  if (!info.name) info.name = info.nameChinese ?? hostname(home.finalUrl);
  info.verified = pages.some((p) => isGrounded(info.name, p.title + p.text) || isGrounded(info.nameChinese, p.title + p.text));
  return info;
}

// ============================================================================ departments

const UNIT_RE = /学院|学系|系$|研究院|研究所|School|College|Department|Faculty|Institute|Academy/i;
const URL_HINTS = new Set(['cs', 'cse', 'scs', 'sse', 'soft', 'software', 'ai', 'jsj', 'cst', 'ise', 'sist', 'seie', 'it',
  'cyber', 'cybersec', 'infosec', 'iiis', 'sice', 'scse', 'csse', 'ics', 'icst', 'ss', 'sai', 'dsai', 'computer',
  'computing', 'informatics', 'nlp', 'cv', 'iot']);
const MORE_RE = /\s*(?:查看更多|更多|MORE|More|more|>>|»)\s*$/;
const HEADLINE_RE = /举办|举行|召开|会议|论坛|讲座|报告会|开幕|新闻|通知|公告|喜报|荣获|\d{4}|news|event|seminar|workshop|conference|lecture|announce/i;
const NEWSY_PATH = /\/(?:info|view|content|article|news|s|detail|show)\/|\/\d{3,}[/.]|\.jsp\?|[?&]id=/i;
const EN_TITLE_SEG = /(School|College|Department|Faculty|Institute)\s+of\s+[A-Z][\w &,-]+/;

function isSubdomainRoot(url: string, domain: string): boolean {
  const u = new URL(url);
  return u.hostname !== domain && u.hostname !== 'www.' + domain &&
    ['', '/', '/index.htm', '/index.html', '/main.htm', '/index.jsp', '/index.php'].includes(u.pathname);
}

function urlHintScore(url: string): number {
  const u = new URL(url);
  const labels = new Set(u.hostname.split('.').slice(0, -2));
  if ([...labels].some((l) => URL_HINTS.has(l))) return 2;
  const tokens = u.pathname.toLowerCase().split(/[/._-]+/);
  return tokens.some((t) => URL_HINTS.has(t)) ? 1 : 0;
}

function candidateScore(ctx: Ctx, ln: Link): [number, string[]] {
  const text = ln.text.trim().replace(MORE_RE, '');
  if (!text || text.length > 45 || HEADLINE_RE.test(text) || /^[【[]/.test(text)) return [0, []];
  const matches = matchFields(text, ctx.fields);
  const low = text.toLowerCase();
  const computing = COMPUTING_HINTS_EN.some((h) => low.includes(h)) || COMPUTING_HINTS_ZH.some((h) => text.includes(h));
  let score = 3 * matches.length + (computing ? 2 : 0) + urlHintScore(ln.url);
  if (isSubdomainRoot(ln.url, ctx.domain)) score += 2.5;
  else if (NEWSY_PATH.test(ln.url)) score -= 3;
  if (UNIT_RE.test(text)) score += 1.5;
  else if (!matches.length || score < 4 || text.length > 16) return [0, []];
  return [score, matches.map((m) => m.label)];
}

async function discoverDepartments(ctx: Ctx): Promise<DepartmentInfo[]> {
  for (const [ln] of topLinks(ctx.allLinks(), 'schools', 2)) await ctx.fetch(ln.url);
  const links = ctx.allLinks();
  const scored = new Map<string, [Link, number, string[]]>();
  for (const ln of links) {
    const [s, m] = candidateScore(ctx, ln);
    const key = canonicalKey(ln.url);
    if (s >= 3.5 && (!scored.has(key) || scored.get(key)![1] < s)) scored.set(key, [ln, s, m]);
  }
  const cands = [...scored.values()].sort((a, b) => b[1] - a[1]).slice(0, 30);
  // The same unit is often linked from both the Chinese and English sites.
  const aliases = new Map<string, string[]>();
  for (const p of ctx.pages.values()) {
    for (const ln of p.links) {
      const t = ln.text.trim();
      if (t && t.length <= 45) aliases.set(canonicalKey(ln.url), [...(aliases.get(canonicalKey(ln.url)) ?? []), t]);
    }
  }

  const depts: DepartmentInfo[] = [];
  const blocked: string[] = [];
  const seen = new Set<string>();
  for (const [ln, score, matches] of cands) {
    if (depts.length >= ctx.opts.maxDepartments) break;
    const label = ln.text.replace(MORE_RE, '').trim();
    const page = await ctx.fetch(ln.url);
    if (!page.ok) {
      if (page.blocked) blocked.push(`${label} (${page.finalUrl})`);
      else ctx.warn(`Department page unavailable: ${label} (${page.error ?? 'empty page'})`);
      continue;
    }
    if (!ctx.official(page.finalUrl)) continue; // e.g. admissions cards redirecting to WeChat articles
    const key = canonicalKey(page.finalUrl);
    if (seen.has(key)) continue;
    seen.add(key);
    const alt = [...(aliases.get(canonicalKey(ln.url)) ?? []), ...(aliases.get(key) ?? [])];
    const nameZh = hasCjk(label) ? label : alt.find((t) => hasCjk(t) && UNIT_RE.test(t)) ?? null;
    let name = !hasCjk(label) ? label : alt.find((t) => !hasCjk(t) && UNIT_RE.test(t)) ?? null;
    if (!name) name = EN_TITLE_SEG.exec(page.title + '\n' + page.text.slice(0, 1500))?.[0].trim() ?? label;
    const pageMatches = matchFields(`${label} ${page.title} ${page.text.slice(0, 2500)}`, ctx.fields).map((m) => m.label);
    const faculty = topLinks(page.links, 'faculty', ctx.opts.maxFacultyListPages).map(([f]) => f.url)
      .filter((u) => ctx.official(u));
    depts.push({ name, nameChinese: nameZh !== name ? nameZh : null, url: page.finalUrl, facultyListUrls: faculty,
      matchedFields: [...new Set([...matches, ...pageMatches])].sort(),
      relevance: Math.round((score + 0.5 * pageMatches.length) * 100) / 100 });
  }
  if (blocked.length) {
    ctx.warn(`${blocked.length} relevant school website(s) are protected by anti-bot checks and could not be read ` +
      `automatically — please check them manually: ${blocked.slice(0, 6).join('; ')}`);
  }
  if (!depts.length) {
    ctx.warn('No relevant school/department could be identified from the website navigation.');
    const faculty = topLinks(ctx.allLinks(), 'faculty', 3).map(([f]) => f.url);
    if (faculty.length && ctx.homepage) {
      depts.push({ name: 'University-wide faculty directory', nameChinese: null, url: ctx.homepage.finalUrl,
        facultyListUrls: faculty, matchedFields: [], relevance: 0 });
    }
  }
  return depts.sort((a, b) => b.relevance - a.relevance);
}

// ============================================================================ professors

const GENERIC_LOCALPARTS = /^(?:office|admin|webmaster|web|info|contact|service|support|yjs|yjsy|zsb|zs|jwc|gs|grad|international|intl|iso|admission|admissions|recruit|hr|rsc|xb|dean|news|cs|cse|school|college|dept|department|lab|postmaster|noreply|no-reply)\d*$/i;
const FACULTY_PAGE = /师资|教师|导师|教授|名录|faculty|people|staff|teacher|szdw|jsml|dsdw|researchers|专任|队伍|人才|研究员|members/i;
const NEWS_TITLE = /新闻|公告|通知|报道|发表|举行|召开|举办|喜报|讲座|会议|动态|news|event/i;
const POSITION_CONTEXT = /教授|副教授|讲师|研究员|Professor|Lecturer|Researcher|博导|硕导/i;

interface Candidate {
  nameText: string;
  url: string;
  department: DepartmentInfo;
  listing: Page;
  context: string;
  priority: number;
}

function personLinks(ctx: Ctx, page: Page): [string, string, string][] {
  const out: [string, string, string][] = [];
  for (const ln of page.links) {
    const name = cleanPersonText(ln.text);
    if (!(looksLikeChineseName(name) || looksLikeEnglishName(name))) continue;
    if (!ctx.official(ln.url) || canonicalKey(ln.url) === canonicalKey(page.finalUrl)) continue;
    out.push([name, ln.url, ln.context]);
  }
  return out;
}

async function collectCandidates(ctx: Ctx, depts: DepartmentInfo[], onNote: (m: string) => void): Promise<Candidate[]> {
  const cands = new Map<string, Candidate>();
  for (const dept of depts) {
    const queue = dept.facultyListUrls.length ? [...dept.facultyListUrls] : [dept.url];
    const visited = new Set<string>();
    let budget = ctx.opts.maxFacultyListPages + 3;
    while (queue.length && budget > 0) {
      const url = queue.shift()!;
      if (visited.has(canonicalKey(url))) continue;
      visited.add(canonicalKey(url));
      budget--;
      const page = await ctx.fetch(url);
      if (!page.ok) {
        ctx.warn(`Faculty list unavailable: ${url} (${page.error})`);
        continue;
      }
      const listingLike = FACULTY_PAGE.test(page.title + ' ' + page.finalUrl);
      if (NEWS_TITLE.test(page.title) && !listingLike) continue; // a news article, not a directory
      let people = personLinks(ctx, page);
      if (people.length < 3 && !listingLike) people = []; // stray name-like links are not evidence
      onNote(`${people.length} people listed on ${page.title || url}`);
      for (const [name, purl, context] of people) {
        const key = canonicalKey(purl);
        if (cands.has(key)) continue;
        cands.set(key, { nameText: name, url: purl, department: dept, listing: page, context,
          priority: (POSITION_CONTEXT.test(context) ? 1 : 0) + dept.relevance / 10 });
      }
      const sameHost = hostname(page.finalUrl);
      for (const ln of paginationLinks(page.links)) {
        if (hostname(ln.url) === sameHost && !visited.has(canonicalKey(ln.url))) queue.push(ln.url);
      }
      if (!people.length) {
        for (const [ln] of topLinks(page.links, 'faculty', 3)) {
          if (hostname(ln.url) === sameHost && !visited.has(canonicalKey(ln.url))) queue.push(ln.url);
        }
      }
    }
  }
  return [...cands.values()].sort((a, b) => b.priority - a.priority);
}

function genericEmails(ctx: Ctx, cand: Candidate): Set<string> {
  const out = new Set(extractEmails(cand.listing.text, cand.listing.mailtos));
  const deptPage = ctx.pages.get(cand.department.url);
  if (deptPage) extractEmails(deptPage.text, deptPage.mailtos).forEach((e) => out.add(e));
  return out;
}

function chooseEmail(ctx: Ctx, emails: string[], generic: Set<string>): string | null {
  const usable = emails.filter((e) => !generic.has(e) && !GENERIC_LOCALPARTS.test(e.split('@')[0]) &&
    (ctx.opts.allowNonInstitutionalEmails || isInstitutionalEmail(e, ctx.domain)));
  usable.sort((a, b) => Number(!isInstitutionalEmail(a, ctx.domain)) - Number(!isInstitutionalEmail(b, ctx.domain)));
  return usable[0] ?? null;
}

function positionNearName(text: string, name: string, fallback: string): [string | null, string | null] {
  const idx = name ? text.indexOf(name) : -1;
  if (idx >= 0) {
    const r = detectPosition(text.slice(Math.max(0, idx - 200), idx + 600));
    if (r[0]) return r;
  }
  return detectPosition(fallback);
}

let nextId = 1;

async function extractProfile(ctx: Ctx, cand: Candidate): Promise<ProfessorInfo> {
  const page = await ctx.fetch(cand.url);
  const isCn = hasCjk(cand.nameText);
  const prof: ProfessorInfo = {
    id: nextId++, name: stripHonorific(cand.nameText), nameChinese: isCn ? cand.nameText : null, nameIsRomanized: false,
    position: null, positionOriginal: null, department: cand.department.name, email: null, emailVerified: false,
    profileUrl: page.ok ? page.finalUrl : cand.url, listingUrl: cand.listing.finalUrl, profileOk: false,
    verification: 'NOT VERIFIED', checks: {}, notes: [], sources: [src(cand.listing, 'listed_on_faculty_page')],
    profileText: '', profileMailtos: [],
  };
  if (!page.ok) {
    prof.notes.push(`Profile page could not be loaded (${page.error}); details not verified.`);
    [prof.position, prof.positionOriginal] = detectPosition(cand.context);
  } else {
    prof.profileOk = true;
    prof.profileText = page.text;
    prof.profileMailtos = page.mailtos;
    prof.sources.push(src(page, 'profile'));
    const generic = genericEmails(ctx, cand);
    prof.email = chooseEmail(ctx, extractEmails(page.text, page.mailtos), generic);
    if (!prof.email) {
      // VSB/Tsites faculty systems publish the email as an encrypted token decoded by the site itself.
      const decoded = await ctx.fetcher.decodeTsitesFields(page);
      if (decoded.length) {
        prof.profileText += '\n' + decoded.join('\n');
        prof.email = chooseEmail(ctx, extractEmails(decoded.join('\n')), generic);
        if (prof.email) prof.notes.push('Email shown on the profile via the faculty system\'s decoder.');
      }
    }
    [prof.position, prof.positionOriginal] = positionNearName(page.text, cand.nameText, cand.context);
  }
  if (prof.nameChinese && hasCjk(prof.name)) {
    const rom = romanizeChineseName(prof.nameChinese);
    if (rom) {
      prof.name = rom;
      prof.nameIsRomanized = true;
    } else prof.notes.push('Romanisation of the Chinese name is ambiguous; Chinese name preserved.');
  }
  if (prof.profileOk && !prof.email) {
    const personal = extractEmails(prof.profileText, prof.profileMailtos).filter((e) => !isInstitutionalEmail(e, ctx.domain));
    prof.notes.push(personal.length && !ctx.opts.allowNonInstitutionalEmails
      ? 'The profile lists only a personal (non-university) email, which is hidden. Open the profile to see it.'
      : 'Email not publicly listed on the profile page.');
  }
  return prof;
}

async function discoverProfessors(ctx: Ctx, depts: DepartmentInfo[], h: ProgressHandlers,
                                  onNote: (m: string) => void): Promise<ProfessorInfo[]> {
  const cands = await collectCandidates(ctx, depts, onNote);
  if (!cands.length) {
    ctx.warn('No faculty profiles could be located on the department websites.');
    return [];
  }
  const todo = cands.slice(0, ctx.opts.maxProfessors);
  onNote(`Found ${cands.length} faculty links; reading up to ${todo.length} profiles`);
  let done = 0;
  const results = await Promise.all(todo.map(async (c) => {
    if (h.isCancelled?.()) throw new Cancelled();
    let p: ProfessorInfo;
    try {
      p = await extractProfile(ctx, c);
    } catch (err) {
      ctx.warn(`Profile extraction failed for ${c.nameText}: ${(err as Error).message}`);
      p = { id: nextId++, name: c.nameText, nameChinese: null, nameIsRomanized: false, position: null,
        positionOriginal: null, department: c.department.name, email: null, emailVerified: false, profileUrl: c.url,
        listingUrl: c.listing.finalUrl, profileOk: false, verification: 'NOT VERIFIED', checks: {},
        notes: ['Extraction failed.'], sources: [], profileText: '', profileMailtos: [] };
    }
    done++;
    onNote(`Read ${done} of ${todo.length} profiles`);
    h.onProfessor?.(p);
    return p;
  }));
  return results.filter((p) => p.profileOk || p.email || p.notes.some((n) => n.includes('could not be loaded')));
}

// ============================================================================ dedup + verification

function keys(p: ProfessorInfo): string[] {
  const k: string[] = [];
  if (p.email) k.push('e:' + p.email.toLowerCase());
  if (p.profileUrl) k.push('u:' + canonicalKey(p.profileUrl));
  if (p.nameChinese) k.push('zh:' + p.nameChinese);
  const nk = nameKey(p.name);
  if (nk && !p.nameChinese) k.push(`n:${nk}|${(p.department ?? '').toLowerCase()}`);
  return k;
}

function merge(a: ProfessorInfo, b: ProfessorInfo): ProfessorInfo {
  const [base, other] = a.profileOk || !b.profileOk ? [a, b] : [b, a];
  base.nameChinese ??= other.nameChinese;
  base.position ??= other.position;
  base.positionOriginal ??= other.positionOriginal;
  base.email ??= other.email;
  base.department ??= other.department;
  if (base.nameIsRomanized && other.name && !other.nameIsRomanized && other.name !== other.nameChinese) {
    base.name = other.name;
    base.nameIsRomanized = false;
  }
  const seen = new Set(base.sources.map((s) => s.url + s.supports));
  base.sources.push(...other.sources.filter((s) => !seen.has(s.url + s.supports)));
  if (other.profileText && !base.profileText.includes(other.profileText)) base.profileText += '\n' + other.profileText;
  base.profileMailtos = [...new Set([...base.profileMailtos, ...other.profileMailtos])];
  base.profileOk ||= other.profileOk;
  base.notes = [...new Set([...base.notes, ...other.notes])];
  return base;
}

/** Transitive merge: the same professor on Chinese + English pages becomes one record. */
export function deduplicate(profs: ProfessorInfo[]): ProfessorInfo[] {
  const result: ProfessorInfo[] = [];
  for (const p of profs) {
    const ks = new Set(keys(p));
    const hits = result.map((r, i) => (keys(r).some((k) => ks.has(k)) ? i : -1)).filter((i) => i >= 0);
    if (!hits.length) {
      result.push(p);
      continue;
    }
    let merged = p;
    for (const i of hits) merged = merge(result[i], merged);
    for (const i of [...hits].reverse()) result.splice(i, 1);
    result.splice(hits[0], 0, merged);
  }
  return result;
}

export function verifyProfessor(p: ProfessorInfo, domain: string): void {
  const text = p.profileText;
  const nameFound = !!text && (isGrounded(p.nameChinese, text) || (!p.nameIsRomanized && isGrounded(p.name, text)));
  const association = !!((p.profileUrl && isOfficial(p.profileUrl, domain)) || (p.listingUrl && isOfficial(p.listingUrl, domain)));
  const emailPublic = !!(p.email && text && emailAppearsIn(p.email, text, p.profileMailtos));
  if (p.email && !emailPublic) {
    p.notes.push('Email could not be re-verified on the profile page and was removed.');
    p.email = null;
  }
  p.emailVerified = emailPublic;
  p.checks = {
    name_found: nameFound,
    university_association: association,
    profile_url_valid: p.profileOk,
    email_public: emailPublic,
    email_institutional: !!(p.email && isInstitutionalEmail(p.email, domain)),
    romanized_name: p.nameIsRomanized,
  };
  let v: Verification = 'NOT VERIFIED';
  if (nameFound && association && p.profileOk && emailPublic) v = 'VERIFIED';
  else if (nameFound && association && p.profileOk) v = 'PARTIALLY VERIFIED';
  p.verification = v;
}

// ============================================================================ orchestrator

export async function runResearch(universityUrl: string, userFields: string[], fetcher: Fetcher,
                                  options: Partial<ResearchOptions> = {}, h: ProgressHandlers = {}): Promise<ResearchResult> {
  const opts = { ...DEFAULT_RESEARCH_OPTIONS, ...options };
  const ctx = new Ctx(universityUrl, resolveFields(userFields), fetcher, opts);
  const steps = initialSteps();
  const result: ResearchResult = { university: null, departments: [], professors: [], warnings: ctx.warnings,
    pagesFetched: 0, error: null };
  const emit = () => h.onStep?.(steps.map((s) => ({ ...s })));
  const set = (key: Step['key'], status: Step['status'], message: string | null = null) => {
    const s = steps.find((x) => x.key === key)!;
    s.status = status;
    if (message !== null) s.message = message;
    emit();
  };
  const note = (key: Step['key']) => (m: string) => set(key, 'running', m);
  const check = () => {
    if (h.isCancelled?.()) throw new Cancelled();
  };

  try {
    set('university', 'running');
    result.university = await discoverUniversity(ctx);
    const u = result.university;
    set('university', 'done', (u.name ?? '') + (u.nameChinese && u.nameChinese !== u.name ? ` (${u.nameChinese})` : ''));
    check();

    set('departments', 'running');
    result.departments = await discoverDepartments(ctx);
    set('departments', 'done', `${result.departments.length} relevant schools/departments`);
    check();

    set('professors', 'running');
    const found = deduplicate(await discoverProfessors(ctx, result.departments, h, note('professors')));
    set('professors', 'done', `${found.length} professors found`);
    check();

    set('verification', 'running');
    for (const p of found) verifyProfessor(p, ctx.domain);
    const order: Record<Verification, number> = { 'VERIFIED': 0, 'PARTIALLY VERIFIED': 1, 'NOT VERIFIED': 2 };
    found.sort((a, b) => order[a.verification] - order[b.verification]);
    result.professors = found;
    set('verification', 'done', `${found.filter((p) => p.email).length} of ${found.length} with a public email`);
  } catch (err) {
    const running = steps.find((s) => s.status === 'running');
    if (err instanceof Cancelled) {
      result.error = 'Search cancelled.';
    } else {
      result.error = err instanceof FatalResearchError ? err.message : `Unexpected error: ${(err as Error).message}`;
    }
    if (running) running.status = err instanceof Cancelled ? 'skipped' : 'failed';
    steps.filter((s) => s.status === 'pending').forEach((s) => (s.status = 'skipped'));
    emit();
  }
  result.pagesFetched = fetcher.networkFetches;
  return result;
}
