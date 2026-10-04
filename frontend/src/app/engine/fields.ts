/**
 * Bilingual research-field taxonomy. Used only to decide which schools/departments to search:
 * "计算机视觉", "CV" and "computer vision" all map to Computer Vision.
 */

export interface FieldSpec {
  key: string;
  label: string;
  labelZh: string | null;
  en: string[];
  zh: string[];
  acronyms: string[];
  custom: boolean;
}

function f(key: string, label: string, labelZh: string, en: string[], zh: string[], acronyms: string[] = []): FieldSpec {
  return { key, label, labelZh, en, zh, acronyms, custom: false };
}

export const TAXONOMY: FieldSpec[] = [
  f('computer_science', 'Computer Science', '计算机科学', ['computer science', 'computing', 'algorithms'], ['计算机科学', '计算机', '计算科学']),
  f('artificial_intelligence', 'Artificial Intelligence', '人工智能', ['artificial intelligence', 'intelligent systems', 'large language model'],
    ['人工智能', '智能科学', '智能系统', '大模型'], ['AI']),
  f('machine_learning', 'Machine Learning', '机器学习', ['machine learning', 'deep learning', 'neural network', 'pattern recognition'],
    ['机器学习', '深度学习', '神经网络', '模式识别'], ['ML']),
  f('information_technology', 'Information Technology', '信息技术', ['information technology', 'information systems', 'information science'],
    ['信息技术', '信息系统', '信息科学', '信息工程'], ['IT']),
  f('software_engineering', 'Software Engineering', '软件工程', ['software engineering', 'software'], ['软件工程', '软件']),
  f('data_science', 'Data Science', '数据科学', ['data science', 'big data', 'data mining'], ['数据科学', '大数据', '数据挖掘']),
  f('computer_engineering', 'Computer Engineering', '计算机工程', ['computer engineering', 'computer architecture', 'embedded systems'],
    ['计算机工程', '计算机体系结构', '嵌入式', '集成电路', '微电子']),
  f('computer_networks', 'Computer Networks', '计算机网络', ['computer networks', 'networking', 'communication engineering'],
    ['计算机网络', '网络通信', '通信工程', '信息与通信']),
  f('cybersecurity', 'Cybersecurity', '网络安全', ['cybersecurity', 'cyber security', 'information security', 'cyberspace security'],
    ['网络安全', '信息安全', '网络空间安全', '网安', '密码']),
  f('iot', 'Internet of Things', '物联网', ['internet of things'], ['物联网', '传感网'], ['IoT']),
  f('cloud_computing', 'Cloud Computing', '云计算', ['cloud computing'], ['云计算']),
  f('distributed_systems', 'Distributed Systems', '分布式系统', ['distributed systems', 'parallel computing', 'high performance computing'],
    ['分布式系统', '并行计算', '高性能计算']),
  f('nlp', 'Natural Language Processing', '自然语言处理', ['natural language processing', 'computational linguistics'],
    ['自然语言处理', '计算语言学', '语言智能'], ['NLP']),
  f('computer_vision', 'Computer Vision', '计算机视觉', ['computer vision', 'image processing'], ['计算机视觉', '图像处理', '视觉'], ['CV']),
  f('robotics', 'Robotics', '机器人', ['robotics', 'automation', 'control'], ['机器人', '自动化', '控制']),
  f('electrical_engineering', 'Electrical Engineering', '电气工程', ['electrical engineering', 'electronic engineering', 'electronics'],
    ['电气工程', '电子工程', '电子科学', '电子信息']),
  f('mathematics', 'Mathematics', '数学', ['mathematics', 'statistics'], ['数学', '统计']),
];

const BY_KEY = new Map(TAXONOMY.map((t) => [t.key, t]));
const ALIASES = new Map<string, string>();
for (const t of TAXONOMY) {
  for (const s of [t.label, t.key.replace(/_/g, ' '), t.en[0], ...t.acronyms, t.labelZh ?? '']) {
    if (s) ALIASES.set(s.toLowerCase(), t.key);
  }
}
[['cs', 'computer_science'], ['networks', 'computer_networks'], ['security', 'cybersecurity'],
  ['cloud', 'cloud_computing'], ['vision', 'computer_vision'], ['deep learning', 'machine_learning']]
  .forEach(([a, k]) => ALIASES.set(a, k));

export const DEFAULT_FIELDS = [
  'Computer Science', 'Artificial Intelligence', 'Machine Learning', 'Information Technology', 'Software Engineering',
  'Data Science', 'Computer Engineering', 'Computer Networks', 'Cybersecurity', 'Internet of Things', 'Cloud Computing',
  'Distributed Systems', 'Natural Language Processing', 'Computer Vision',
];

/** Map user-entered field names (English / Chinese / acronyms / custom) to FieldSpecs. */
export function resolveFields(userFields: string[]): FieldSpec[] {
  const out: FieldSpec[] = [];
  const seen = new Set<string>();
  for (const raw of userFields) {
    for (const part of raw.split(/[,，;；\n]/)) {
      const name = part.trim();
      if (!name) continue;
      let key = ALIASES.get(name.toLowerCase());
      if (!key) key = TAXONOMY.find((t) => t.en.includes(name.toLowerCase()) || t.zh.includes(name))?.key;
      const zh = /[一-鿿]/.test(name);
      const spec: FieldSpec = key
        ? BY_KEY.get(key)!
        : { key: 'custom_' + name.toLowerCase().replace(/\W+/g, '_'), label: name, labelZh: null,
            en: zh ? [] : [name.toLowerCase()], zh: zh ? [name] : [], acronyms: [], custom: true };
      if (!seen.has(spec.key)) {
        seen.add(spec.key);
        out.push(spec);
      }
    }
  }
  return out;
}

export interface FieldMatch {
  key: string;
  label: string;
  keywords: string[];
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Fields with literal keyword evidence in the text. */
export function matchFields(text: string, fields: FieldSpec[]): FieldMatch[] {
  if (!text) return [];
  const out: FieldMatch[] = [];
  for (const fs of fields) {
    const hits: string[] = [];
    for (const kw of [fs.label.toLowerCase(), ...fs.en]) {
      if (kw && new RegExp(`(?<![A-Za-z])${escapeRe(kw)}(?![A-Za-z])`, 'i').test(text) && !hits.includes(kw)) hits.push(kw);
    }
    for (const kw of fs.zh) if (text.includes(kw) && !hits.includes(kw)) hits.push(kw);
    for (const ac of fs.acronyms) {
      if (new RegExp(`(?<![A-Za-z])${escapeRe(ac)}(?![A-Za-z])`).test(text) && !hits.includes(ac)) hits.push(ac);
    }
    if (hits.length) out.push({ key: fs.key, label: fs.label, keywords: hits });
  }
  return out;
}

// Department-level hints (independent of the user's fields): a computing-related unit.
export const COMPUTING_HINTS_EN = ['computer', 'computing', 'software', 'information', 'artificial intelligence',
  'data science', 'cyber', 'electronic', 'intelligence', 'informatics', 'network'];
export const COMPUTING_HINTS_ZH = ['计算机', '软件', '信息', '人工智能', '网络', '数据', '智能', '电子', '通信', '网安'];
