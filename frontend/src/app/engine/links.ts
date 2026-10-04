/** Scores links into crawl categories using bilingual anchor-text and URL cues (keeps crawling targeted). */
import type { Link } from './html';

type Category = 'schools' | 'faculty' | 'english_site';

const CATEGORIES: Record<Category, { text: string[]; url: string[] }> = {
  schools: {
    text: ['schools', 'colleges', 'faculties', 'departments', '院系', '院系设置', '学院设置', '教学单位', '院系导航',
      'academics', 'schools & departments', 'schools and departments', 'academic units', '院系部门', '机构设置',
      '学院部门', '教学科研单位', '院部设置', '学部', 'schools & colleges', 'academic schools', 'colleges & schools'],
    url: ['yxsz', 'yxdh', 'school', 'college', 'department', 'academics', 'faculties', 'jxdw', 'yx', 'xybm'],
  },
  faculty: {
    text: ['faculty', 'people', '师资', '师资队伍', '教师', '导师', '教职工', '研究生导师', '博士生导师', '硕士生导师',
      '导师介绍', '教授', '教师名录', 'faculty members', 'academic staff', 'researchers', 'our team', 'staff directory',
      '专任教师', '全职教师', '教师队伍', '人才队伍', '研究团队', '教师主页'],
    url: ['faculty', 'people', 'szdw', 'teacher', 'teachers', 'jsml', 'ds', 'dsdw', 'staff', 'szll', 'jszy', 'rcdw',
      'team', 'members', 'szgk'],
  },
  english_site: { text: ['english', 'english version', 'eng'], url: ['/en', 'english', 'en.'] },
};

const SPLIT = /[/._\-?=&]+/;

export function scoreLink(link: Link, category: Category): number {
  const cfg = CATEGORIES[category];
  const text = link.text.toLowerCase().trim();
  const url = link.url.toLowerCase();
  let score = 0;
  if (category === 'english_site') {
    if (cfg.text.includes(text)) score += 3;
  } else {
    for (const kw of cfg.text) {
      if (text.includes(kw)) {
        score += kw.length > 3 ? 3 : 2;
        if (text === kw) score += 1;
      }
    }
  }
  const tokens = new Set(url.split('://').pop()!.split(SPLIT));
  for (const kw of cfg.url) {
    if (kw.startsWith('/') || kw.includes('.')) {
      if (url.includes(kw)) score += 1.5;
    } else if (tokens.has(kw)) score += 1.5;
  }
  if (link.text.length > 40) score *= 0.4; // long anchors are news headlines, not navigation
  if (/news|新闻|通知|公告|动态/.test(text)) score *= 0.5;
  return score;
}

export function topLinks(links: Link[], category: Category, limit = 5, minScore = 2): [Link, number][] {
  const best = new Map<string, [Link, number]>();
  for (const ln of links) {
    const s = scoreLink(ln, category);
    if (s >= minScore && (!best.has(ln.url) || best.get(ln.url)![1] < s)) best.set(ln.url, [ln, s]);
  }
  return [...best.values()].sort((a, b) => b[1] - a[1]).slice(0, limit);
}

const PAGINATION = new Set(['下一页', '下页', 'next', 'next page', '»', '>', '更多', 'more']);

export function paginationLinks(links: Link[]): Link[] {
  return links.filter((ln) => {
    const t = ln.text.trim().toLowerCase();
    return PAGINATION.has(t) || /^\d{1,2}$/.test(t);
  });
}
