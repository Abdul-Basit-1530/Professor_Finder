import { describe, expect, it } from 'vitest';

import { matchFields, resolveFields } from './fields';
import { decodeHtml, looksBlocked } from './html';
import { parseRobots } from './fetcher';
import {
  detectPosition, extractEmails, isGrounded, isInstitutionalEmail, looksLikeChineseName, looksLikeEnglishName,
  nameKey, romanizeChineseName,
} from './text';
import { canonicalKey, InvalidUrlError, isOfficial, registrableDomain, resolveLink, validateUniversityUrl } from './url';

describe('URLs', () => {
  it('normalises and validates university URLs', () => {
    expect(validateUniversityUrl('www.tsinghua.edu.cn')).toBe('https://www.tsinghua.edu.cn/');
    expect(validateUniversityUrl('https://WWW.PKU.EDU.CN/index.htm#top')).toBe('https://www.pku.edu.cn/index.htm');
    for (const bad of ['', 'ftp://x.edu.cn', 'http://127.0.0.1/', 'https://www.google.com', 'nodot']) {
      expect(() => validateUniversityUrl(bad)).toThrow(InvalidUrlError);
    }
  });

  it('handles domains and links', () => {
    expect(registrableDomain('https://cs.ustc.edu.cn/x')).toBe('ustc.edu.cn');
    expect(isOfficial('https://iso.mocku.edu.cn/a', 'mocku.edu.cn')).toBe(true);
    expect(isOfficial('https://mocku.edu.cn.evil.com/', 'mocku.edu.cn')).toBe(false);
    expect(resolveLink('https://www.x.edu.cn/a/b.htm', '../c.htm')).toBe('https://www.x.edu.cn/c.htm');
    expect(resolveLink('https://www.x.edu.cn/', 'mailto:a@b.cn')).toBeNull();
    expect(resolveLink('https://www.x.edu.cn/', '/logo.png')).toBeNull();
    expect(canonicalKey('https://www.x.edu.cn/a/')).toBe(canonicalKey('http://x.edu.cn/a'));
  });
});

describe('Chinese text', () => {
  it('decodes GBK pages (common on Chinese sites)', () => {
    const gbk = new Uint8Array([0xbc, 0xc6, 0xcb, 0xe3, 0xbb, 0xfa, 0xd1, 0xa7, 0xd4, 0xba]); // 计算机学院
    expect(decodeHtml(gbk, 'text/html; charset=gbk')).toBe('计算机学院');
    expect(decodeHtml(gbk, 'text/html')).toBe('计算机学院'); // no header: falls back to GB18030
    expect(decodeHtml(new TextEncoder().encode('计算机学院'), 'text/html; charset=gbk')).toBe('计算机学院'); // lying header
  });

  it('detects person names and rejects navigation words', () => {
    expect(looksLikeChineseName('张伟')).toBe(true);
    expect(looksLikeChineseName('欧阳明')).toBe(true);
    expect(looksLikeChineseName('王  伟')).toBe(true);
    for (const w of ['首页', '师资队伍', '学院新闻', '计算机', '教授', '公告']) expect(looksLikeChineseName(w)).toBe(false);
    expect(looksLikeEnglishName('Prof. John Smith')).toBe(true);
    expect(looksLikeEnglishName('School News')).toBe(false);
  });

  it('romanises names with surname readings and keeps ambiguous ones in Chinese', () => {
    expect(romanizeChineseName('张伟')).toBe('Zhang Wei');
    expect(romanizeChineseName('诸葛亮')).toBe('Zhuge Liang');
    expect(romanizeChineseName('单明')).toBe('Shan Ming'); // surname 单 = Shan
    expect(romanizeChineseName('曾华')).toBe('Zeng Hua'); // surname 曾 = Zeng
    expect(romanizeChineseName('王乐')).toBeNull(); // given-name 乐: le / yue
    expect(nameKey('Wei Zhang')).toBe(nameKey('ZHANG Wei'));
  });

  it('detects positions, preferring specific titles', () => {
    expect(detectPosition('李娜 副教授 硕士生导师')[0]).toBe('Associate Professor');
    expect(detectPosition('张伟，教授，博士生导师')[0]).toBe('Professor');
    expect(detectPosition('Assistant Professor of CS')[0]).toBe('Assistant Professor');
  });
});

describe('emails', () => {
  it('finds literal and explicitly obfuscated emails', () => {
    const t = '邮箱：zhangwei#ustc.edu.cn  Email: li [at] pku [dot] edu [dot] cn; wang(at)zju.edu.cn';
    expect(extractEmails(t)).toEqual(['zhangwei@ustc.edu.cn', 'li@pku.edu.cn', 'wang@zju.edu.cn']);
  });

  it('normalizes explicit obfuscation in mailto links', () => {
    expect(extractEmails('', ['wang [at] example.edu.cn', 'li%20%5Bat%5D%20example.edu.cn']))
      .toEqual(['wang@example.edu.cn', 'li@example.edu.cn']);
  });

  it('never invents an email from prose', () => {
    expect(extractEmails('He works at cs.ustc.edu.cn and studies C# programming.')).toEqual([]);
    expect(extractEmails('see page.html#section.top')).toEqual([]);
    expect(extractEmails('contact: name@example.com')).toEqual([]);
  });

  it('classifies institutional emails', () => {
    expect(isInstitutionalEmail('a@cs.mocku.edu.cn', 'mocku.edu.cn')).toBe(true);
    expect(isInstitutionalEmail('a@pku.edu.cn', 'mocku.edu.cn')).toBe(true);
    expect(isInstitutionalEmail('a@gmail.com', 'mocku.edu.cn')).toBe(false);
    expect(isInstitutionalEmail('a@163.com', 'mocku.edu.cn')).toBe(false);
  });

  it('checks grounding whitespace-insensitively', () => {
    expect(isGrounded('自然 语言处理', '研究方向：自然语言处理')).toBe(true);
    expect(isGrounded('量子计算', '研究方向：自然语言处理')).toBe(false);
  });
});

describe('fields, robots and blocking', () => {
  it('maps English, Chinese and acronyms to the same field', () => {
    const fields = resolveFields(['AI, NLP', '计算机视觉', 'Quantum Computing']);
    expect(fields.map((f) => f.label)).toEqual(['Artificial Intelligence', 'Natural Language Processing',
      'Computer Vision', 'Quantum Computing']);
    expect(matchFields('人工智能学院', fields).map((m) => m.label)).toEqual(['Artificial Intelligence']);
    expect(matchFields('Email and training rooms', resolveFields(['AI']))).toEqual([]);
  });

  it('parses robots.txt rules', () => {
    const rules = parseRobots('User-agent: Googlebot\nDisallow: /g\n\nUser-agent: *\nDisallow: /private/\n# x\n', 'ProfessorFinder');
    expect(rules).toEqual(['/private/']);
  });

  it('detects CAPTCHA / block pages', () => {
    expect(looksBlocked(403, '')).toBe(true);
    expect(looksBlocked(200, '请输入验证码以继续访问')).toBe(true);
    expect(looksBlocked(200, '计算机学院 '.repeat(400))).toBe(false);
  });
});
