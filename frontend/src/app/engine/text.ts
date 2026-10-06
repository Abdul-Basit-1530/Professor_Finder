/**
 * Text helpers: Chinese detection, email extraction, names, positions.
 * Everything here is deterministic. These functions never invent data — they only find,
 * normalise or reject what is present in retrieved text.
 */
import { pinyin } from 'pinyin-pro';

const CJK_RE = /[一-鿿㐀-䶿]/;
const WS_RE = /[ \t　 ]+/g;

export function hasCjk(text: string | null | undefined): boolean {
  return !!text && CJK_RE.test(text);
}

export function normalizeSpace(text: string): string {
  const lines = text.normalize('NFKC').split(/\r?\n/).map((l) => l.replace(WS_RE, ' ').trim());
  const out: string[] = [];
  for (const l of lines) if (l || (out.length && out[out.length - 1])) out.push(l);
  return out.join('\n').trim();
}

/** Collapse all whitespace — used for robust "is this literally on the page" checks. */
export function squash(text: string | null | undefined): string {
  return (text ?? '').normalize('NFKC').replace(/\s+/g, '').toLowerCase();
}

export function isGrounded(fragment: string | null | undefined, source: string): boolean {
  const f = squash(fragment);
  return !!f && squash(source).includes(f);
}

// --------------------------------------------------------------------------- emails

const EMAIL_RE = /[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/g;
// Only explicit, unambiguous markers count. A bare " at " is NOT "@": ordinary prose like
// "works at cs.xx.edu.cn" would otherwise become a fake email.
const OBFUSCATED_RE =
  /(?<![\w/.#@])([A-Za-z0-9][A-Za-z0-9._-]{0,63})\s*(?:\[at\]|\(at\)|\{at\}|<at>|＠|#)\s*([A-Za-z0-9-]+(?:\s*(?:\.|\[dot\]|\(dot\))\s*[A-Za-z0-9-]+)+)/gi;
const DOT_RE = /\s*(?:\[dot\]|\(dot\))\s*/gi;
const OBFUSCATED_TLDS = /\.(?:cn|com|edu|org|net|hk|mo|tw)$/i;
const BAD_HINTS = ['example.com', 'domain.com', 'xxx', 'email.com', 'yourname', '@2x.'];

/** Emails literally present (or explicitly obfuscated) in the text / mailto links. */
export function extractEmails(text: string, mailtos: string[] = []): string[] {
  const found: string[] = [];
  for (const m of text.matchAll(EMAIL_RE)) found.push(m[0]);
  for (const m of text.matchAll(OBFUSCATED_RE)) {
    const domain = m[2].replace(DOT_RE, '.').replace(/\s+/g, '');
    if (domain.includes('.') && OBFUSCATED_TLDS.test(domain)) found.push(`${m[1]}@${domain}`);
  }
  for (const mt of mailtos) {
    const addr = mt.split('?')[0].trim();
    if (new RegExp(`^${EMAIL_RE.source}$`).test(addr)) found.push(addr);
  }
  const out: string[] = [];
  for (let e of found) {
    e = e.replace(/^[.;,，。]+|[.;,，。]+$/g, '').toLowerCase();
    if (BAD_HINTS.some((h) => e.includes(h))) continue;
    if (!out.includes(e)) out.push(e);
  }
  return out;
}

const ACADEMIC_SUFFIXES = ['.edu.cn', '.ac.cn', '.edu', '.edu.hk', '.edu.tw', '.edu.mo', '.ac.uk'];

export function isInstitutionalEmail(email: string, universityDomain: string): boolean {
  const dom = email.split('@').pop()!.toLowerCase();
  if (dom === universityDomain || dom.endsWith('.' + universityDomain)) return true;
  return ACADEMIC_SUFFIXES.some((s) => dom.endsWith(s));
}

export function emailAppearsIn(email: string, text: string, mailtos: string[] = []): boolean {
  return extractEmails(text, mailtos).includes(email.toLowerCase());
}

// --------------------------------------------------------------------------- names

export const COMPOUND_SURNAMES = new Set([
  '欧阳', '司马', '诸葛', '上官', '东方', '皇甫', '尉迟', '公孙', '慕容', '令狐', '长孙', '宇文', '司徒', '夏侯',
  '端木', '澹台', '轩辕', '西门', '南宫', '申屠', '闻人', '呼延',
]);
const SINGLE_SURNAMES = new Set(
  ('王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈' +
    '姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤' +
    '常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季' +
    '裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦' +
    '戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻' +
    '苑迟邝官封谈匡鞠惠荆乐冀郁胥南班储原栗燕楚鄢劳谌奚皮粟冼蔺楼盘满闻位厉伊仝区郜海阚花权强帅屠豆朴盖练' +
    '廉禹井祖漆巴丰支卿国狄平计索宣晋相初门云容敬来扈晁芮都普阙浦戈伏鹿薄邸雍辜羊阿乌母裘亓修邰赫杭况那宿' +
    '鲜印逯隆茹诸战慕危玉银亢嵇公哈湛宾戎勾茅利於呼居揭干但尉冶斯元束檀衣信展阴昝智幸奉植衡富尧闭由').split(''),
);
const NAME_STOP = new Set([
  '首页', '教授', '学院', '更多', '师资', '导师', '简介', '概况', '新闻', '通知', '招生', '联系', '主页', '副教授', '讲师',
  '研究员', '博导', '硕导', '返回', '下一页', '上一页', '末页', '尾页', '中文', '英文', '登录', '查看', '详细', '详情', '全部',
  '党建', '工会', '校友', '高等', '高级', '王牌', '黄页', '常见', '安全', '管理', '国际', '教学', '科研', '张贴', '方向', '白皮',
  '公告', '公示', '公开', '关于', '文化', '文件', '时间', '毕业', '成果', '项目', '党委', '团委', '校历', '下载', '规章', '制度',
  '学术', '邮箱', '信箱', '地图', '简历', '主讲', '孔子', '金课', '黄河', '长江', '江南', '海外', '海南', '云端', '云上', '雷锋',
  '石油', '钱学', '华为', '方案',
]);
const NAME_PARTS_STOP = ['学院', '教授', '老师', '中心', '实验', '研究', '大学', '专业', '系统', '计算', '软件', '信息', '网络',
  '智能', '数据', '工程', '科学', '技术', '管理', '服务', '办公', '概况', '介绍', '招生', '就业', '学生', '教师', '队伍', '人才', '成果'];
const CN_NAME_RE = /^[一-鿿]{2,4}$/;
const EN_NAME_RE =
  /^(?:(?:Prof\.?|Professor|Dr\.?|Assoc\.?\s+Prof\.?)\s+)?[A-Z][a-z]+(?:[-'][A-Za-z][a-z]+)?(?:\s+[A-Z][a-z]*\.?(?:[-'][A-Za-z][a-z]+)?){1,3}$/;
const EN_NAME_STOP = new Set(
  ('school department college faculty news about home contact research admission admissions international graduate ' +
    'program programs more people students student centre center lab laboratory institute university events science ' +
    'engineering computer notice notices office alumni library campus english chinese overview introduction staff ' +
    'teaching learning academics scholarship scholarships privacy policy sitemap login search next previous read view ' +
    'all the and for of in on with our study apply').split(' '),
);

export function cleanPersonText(text: string): string {
  let t = (text ?? '').normalize('NFKC').trim();
  // "王  伟" -> "王伟" (pages pad two-character names with spaces)
  if (hasCjk(t)) t = t.replace(/(?<=[一-鿿])\s+(?=[一-鿿])/g, '');
  return t.replace(WS_RE, ' ').trim().replace(/^[ :：,，|·-]+|[ :：,，|·-]+$/g, '');
}

export function looksLikeChineseName(text: string): boolean {
  const t = cleanPersonText(text);
  if (!CN_NAME_RE.test(t) || NAME_STOP.has(t)) return false;
  if (NAME_PARTS_STOP.some((s) => t.includes(s))) return false;
  if (COMPOUND_SURNAMES.has(t.slice(0, 2))) return t.length === 3 || t.length === 4;
  return SINGLE_SURNAMES.has(t[0]) && t.length <= 3;
}

export function looksLikeEnglishName(text: string): boolean {
  const t = cleanPersonText(text);
  if (t.length > 40 || !EN_NAME_RE.test(t)) return false;
  return !t.split(/\s+/).some((w) => EN_NAME_STOP.has(w.replace(/\./g, '').toLowerCase()));
}

export function stripHonorific(name: string): string {
  return name.trim().replace(/^(?:Prof\.?|Professor|Dr\.?|Assoc\.?\s+Prof\.?)\s+/, '').trim();
}

// Characters whose reading in a *given* name is genuinely ambiguous (乐 le/yue, 长 chang/zhang, …).
// Surnames are handled by pinyin-pro's surname mode (单 -> Shan, 曾 -> Zeng).
const AMBIGUOUS_GIVEN_CHARS = new Set('乐长行重朝都和茜晟蔚折句能曾单解区查仇朴覃盖尉召秘种繁员翟缪俟隗宓逄'.split(''));

/** "张伟" -> "Zhang Wei"; null when the reading is ambiguous (then the Chinese name is kept). */
export function romanizeChineseName(nameCn: string): string | null {
  const name = cleanPersonText(nameCn);
  if (!CN_NAME_RE.test(name)) return null;
  const split = COMPOUND_SURNAMES.has(name.slice(0, 2)) && name.length >= 3 ? 2 : 1;
  if ([...name.slice(split)].some((c) => AMBIGUOUS_GIVEN_CHARS.has(c))) return null;
  const syllables = pinyin(name, { toneType: 'none', type: 'array', mode: 'surname' }) as string[];
  if (syllables.length !== name.length) return null;
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  return `${cap(syllables.slice(0, split).join(''))} ${cap(syllables.slice(split).join(''))}`.trim();
}

/** Order-insensitive key for English names: "Wei Zhang" == "ZHANG Wei". */
export function nameKey(name: string | null | undefined): string {
  if (!name) return '';
  return (stripHonorific(name).toLowerCase().match(/[a-z]+/g) ?? []).sort().join(' ');
}

// --------------------------------------------------------------------------- positions

const POSITION_PATTERNS: [string, string][] = [
  ['助理教授', 'Assistant Professor'], ['副教授', 'Associate Professor'], ['特聘教授', 'Distinguished Professor'],
  ['讲席教授', 'Chair Professor'], ['教授', 'Professor'], ['副研究员', 'Associate Research Fellow'],
  ['助理研究员', 'Assistant Research Fellow'], ['研究员', 'Research Fellow / Professor'], ['讲师', 'Lecturer'],
  ['Distinguished Professor', 'Distinguished Professor'], ['Chair Professor', 'Chair Professor'],
  ['Associate Professor', 'Associate Professor'], ['Assistant Professor', 'Assistant Professor'],
  ['Full Professor', 'Professor'], ['Professor', 'Professor'], ['Senior Lecturer', 'Senior Lecturer'],
  ['Lecturer', 'Lecturer'], ['Research Fellow', 'Research Fellow'], ['Researcher', 'Researcher'],
];

/** [english, original] for the first position title in the text. */
export function detectPosition(text: string): [string | null, string | null] {
  const head = text.slice(0, 3000);
  const lower = head.toLowerCase();
  let best: [number, string, string] | null = null;
  for (const [pat, en] of POSITION_PATTERNS) {
    const idx = hasCjk(pat) ? head.indexOf(pat) : lower.indexOf(pat.toLowerCase());
    if (idx >= 0 && (!best || idx < best[0] || (idx === best[0] && pat.length > best[1].length))) best = [idx, pat, en];
  }
  return best ? [best[2], best[1]] : [null, null];
}
