"""Text helpers: Chinese detection, email extraction, names, positions, snippets.

Everything here is deterministic. These functions never invent data — they only
find, normalise or reject what is present in retrieved text.
"""

from __future__ import annotations

import re
import unicodedata

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
WS_RE = re.compile(r"[ \t　\xa0]+")

# --------------------------------------------------------------------------- language


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if CJK_RE.match(c)) / len(letters)


def detect_language(text: str) -> str:
    r = cjk_ratio(text[:20000])
    if r > 0.5:
        return "zh"
    if r > 0.1:
        return "mixed"
    return "en"


def has_cjk(text: str | None) -> bool:
    return bool(text and CJK_RE.search(text))


def normalize_space(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    lines = [WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def squash(text: str) -> str:
    """Collapse all whitespace — used for robust substring (grounding) checks."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "")).lower()


def is_grounded(fragment: str | None, source_text: str) -> bool:
    """True if `fragment` literally appears in `source_text` (whitespace-insensitive)."""
    if not fragment:
        return False
    f = squash(fragment)
    return bool(f) and f in squash(source_text)


def snippet_around(text: str, start: int, end: int, radius: int = 220) -> str:
    s = max(0, start - radius)
    e = min(len(text), end + radius)
    snip = text[s:e].replace("\n", " ")
    snip = WS_RE.sub(" ", snip).strip()
    return ("…" if s > 0 else "") + snip + ("…" if e < len(text) else "")


def sentence_around(text: str, start: int, end: int, max_len: int = 320) -> str:
    """The sentence (or line) containing text[start:end], trimmed to `max_len`."""
    # Chinese punctuation always ends a sentence; English only when followed by whitespace
    # (so "studyinchina.csc.edu.cn" or "No. 5" are not split).
    s = 0
    for m in _SENT_END.finditer(text, 0, start):
        s = m.end()
    m = _SENT_END.search(text, end)
    e = m.end() if m else len(text)
    sent = WS_RE.sub(" ", text[s:e].replace("\n", " ")).strip()
    return sent if len(sent) <= max_len else snippet_around(text, start, end, max_len // 2)


_SENT_END = re.compile(r"[。！？；\n]|[.!?;](?=\s)")


# --------------------------------------------------------------------------- emails

EMAIL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
# Common anti-scraping obfuscations shown on Chinese faculty pages, e.g.
#   zhangwei#ustc.edu.cn   zhangwei(at)ustc.edu.cn   zhangwei [at] ustc [dot] edu [dot] cn
# Only explicit, unambiguous markers are accepted. A bare " at " is NOT treated as
# "@" because ordinary prose ("works at cs.xx.edu.cn") would become a fake email.
_OBFUSCATED_RE = re.compile(
    r"(?<![\w/.#@])([A-Za-z0-9][A-Za-z0-9._\-]{0,63})\s*(?:\[at\]|\(at\)|\{at\}|<at>|＠|#)\s*"
    r"([A-Za-z0-9\-]+(?:\s*(?:\.|\[dot\]|\(dot\))\s*[A-Za-z0-9\-]+)+)",
    re.IGNORECASE,
)
_DOT_RE = re.compile(r"\s*(?:\[dot\]|\(dot\))\s*", re.IGNORECASE)
_OBFUSCATED_TLDS = re.compile(r"\.(?:cn|com|edu|org|net|hk|mo|tw)$", re.IGNORECASE)
_BAD_EMAIL_HINTS = ("example.com", "domain.com", "xxx", "email.com", "yourname", "@2x.")


def extract_emails(text: str, mailtos: list[str] | None = None) -> list[str]:
    """Return emails that are literally present (or explicitly obfuscated) in `text`."""
    found: list[str] = []
    for m in EMAIL_RE.finditer(text):
        found.append(m.group(0))
    for m in _OBFUSCATED_RE.finditer(text):
        domain = _DOT_RE.sub(".", m.group(2)).replace(" ", "")
        if "." in domain and _OBFUSCATED_TLDS.search(domain):
            found.append(f"{m.group(1)}@{domain}")
    for mt in mailtos or []:
        addr = mt.split("?")[0].strip()
        if EMAIL_RE.fullmatch(addr):
            found.append(addr)
    out: list[str] = []
    seen: set[str] = set()
    for e in found:
        e = e.strip(".;,，。").lower()
        if any(h in e for h in _BAD_EMAIL_HINTS):
            continue
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


ACADEMIC_EMAIL_SUFFIXES = (".edu.cn", ".ac.cn", ".edu", ".edu.hk", ".edu.tw", ".edu.mo", ".ac.uk")


def is_institutional_email(email: str, university_domain: str) -> bool:
    dom = email.rsplit("@", 1)[-1].lower()
    if dom == university_domain or dom.endswith("." + university_domain):
        return True
    return dom.endswith(ACADEMIC_EMAIL_SUFFIXES)


def email_appears_in(email: str, text: str, mailtos: list[str] | None = None) -> bool:
    return email.lower() in extract_emails(text, mailtos)


# --------------------------------------------------------------------------- names

# Common Chinese surnames (single + compound). Used to recognise a link text
# such as "张伟" as a person name on a faculty listing page.
COMPOUND_SURNAMES = {
    "欧阳", "司马", "诸葛", "上官", "东方", "皇甫", "尉迟", "公孙", "慕容", "令狐", "长孙",
    "宇文", "司徒", "夏侯", "端木", "澹台", "轩辕", "西门", "南宫", "申屠", "闻人", "呼延",
}
SINGLE_SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈"
    "姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
    "常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季"
    "裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦"
    "戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻"
    "苑迟邝官封谈匡鞠惠荆乐冀郁胥南班储原栗燕楚鄢劳谌奚皮粟冼蔺楼盘满闻位厉伊仝区郜海阚花权强帅屠豆朴盖练"
    "廉禹井祖漆巴丰支卿国狄平计索宣晋相初门云容敬来扈晁芮都普阙浦戈伏鹿薄邸雍辜羊阿乌母裘亓修邰赫杭况那宿"
    "鲜印逯隆茹诸战慕危玉银亢嵇公哈湛宾戎勾茅利於呼居揭干但尉冶斯元束檀衣信展阴昝智幸奉植衡富尧闭由"
)
_NAME_STOP = {
    "首页", "教授", "学院", "更多", "师资", "导师", "简介", "概况", "新闻", "通知", "招生", "联系",
    "主页", "副教授", "讲师", "研究员", "博导", "硕导", "返回", "下一页", "上一页", "末页", "尾页",
    "中文", "英文", "登录", "查看", "详细", "详情", "全部", "党建", "工会", "校友", "高等", "高级",
    "王牌", "黄页", "常见", "安全", "管理", "国际", "教学", "科研", "张贴", "方向", "白皮",
    "公告", "公示", "公开", "关于", "高级", "文化", "文件", "时间", "毕业", "成果", "项目", "党委", "团委",
    "校历", "下载", "规章", "制度", "学术", "邮箱", "信箱", "地图", "简历", "主讲", "孔子", "金课",
    "黄河", "长江", "江南", "海外", "海南", "云端", "云上", "雷锋", "石油", "钱学", "华为", "方案",
}

_CN_NAME_RE = re.compile(r"^[一-鿿]{2,4}$")
_EN_NAME_RE = re.compile(
    r"^(?:(?:Prof\.?|Professor|Dr\.?|Assoc\.?\s+Prof\.?)\s+)?"
    r"[A-Z][a-z]+(?:[\-'][A-Za-z][a-z]+)?(?:\s+[A-Z][a-z]*\.?(?:[\-'][A-Za-z][a-z]+)?){1,3}$"
)
_EN_NAME_STOP = {
    "school", "department", "college", "faculty", "news", "about", "home", "contact", "research",
    "admission", "admissions", "international", "graduate", "program", "programs", "more", "people",
    "students", "student", "centre", "center", "lab", "laboratory", "institute", "university", "events",
    "science", "engineering", "computer", "notice", "notices", "office", "alumni", "library", "campus",
    "english", "chinese", "overview", "introduction", "staff", "teaching", "learning", "academics",
    "scholarship", "scholarships", "privacy", "policy", "sitemap", "login", "search", "next", "previous",
    "read", "view", "all", "the", "and", "for", "of", "in", "on", "with", "our", "study", "apply",
}


def clean_person_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").strip()
    # "王  伟" -> "王伟" (pages pad two-character names with spaces)
    if has_cjk(text):
        text = re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", text)
    return WS_RE.sub(" ", text).strip(" :：,，|·-")


def looks_like_chinese_name(text: str) -> bool:
    t = clean_person_text(text)
    if not _CN_NAME_RE.match(t) or t in _NAME_STOP:
        return False
    if any(stop in t for stop in ("学院", "教授", "老师", "中心", "实验", "研究", "大学", "专业", "系统", "计算",
                                  "软件", "信息", "网络", "智能", "数据", "工程", "科学", "技术", "管理", "服务",
                                  "办公", "概况", "介绍", "招生", "就业", "学生", "教师", "队伍", "人才", "成果")):
        return False
    if t[:2] in COMPOUND_SURNAMES:
        return len(t) in (3, 4)
    return t[0] in SINGLE_SURNAMES and len(t) <= 3


def looks_like_english_name(text: str) -> bool:
    t = clean_person_text(text)
    if len(t) > 40 or not _EN_NAME_RE.match(t):
        return False
    words = [w.strip(".").lower() for w in t.split()]
    return not any(w in _EN_NAME_STOP for w in words)


def strip_honorific(name: str) -> str:
    return re.sub(r"^(?:Prof\.?|Professor|Dr\.?|Assoc\.?\s+Prof\.?)\s+", "", name.strip()).strip()


# Characters whose pronunciation in personal names is genuinely ambiguous or
# differs from the everyday reading (mostly surnames).
AMBIGUOUS_NAME_CHARS = set("曾单解区查仇朴覃盖尉召秘种繁员乐长行重朝都和茜晟蔚翟缪折俟句隗宓逄能")


def romanize_chinese_name(name_cn: str) -> str | None:
    """Pinyin for a Chinese personal name — or None when the reading is ambiguous.

    Surname-first ("张伟" -> "Zhang Wei"). pypinyin's heteronym table lists archaic
    readings for most characters, so instead we flag the characters whose reading
    genuinely differs in personal names (e.g. surname 曾 Zeng/Ceng, 单 Shan/Dan,
    given-name 乐 Le/Yue). For those, the romanisation is uncertain and — per the
    product rules — only the Chinese name is kept.
    """
    name_cn = clean_person_text(name_cn)
    if not _CN_NAME_RE.match(name_cn):
        return None
    if any(c in AMBIGUOUS_NAME_CHARS for c in name_cn):
        return None
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:  # pragma: no cover
        return None
    syllables = lazy_pinyin(name_cn, style=Style.NORMAL, v_to_u=True, errors="ignore")
    if len(syllables) != len(name_cn):
        return None
    split = 2 if name_cn[:2] in COMPOUND_SURNAMES and len(name_cn) >= 3 else 1
    surname = "".join(syllables[:split]).capitalize()
    given = "".join(syllables[split:]).capitalize()
    return f"{surname} {given}".strip()


def name_key(name: str | None) -> str:
    """Order-insensitive key for English names: 'Wei Zhang' == 'ZHANG Wei'."""
    if not name:
        return ""
    toks = re.findall(r"[a-z]+", strip_honorific(name).lower())
    return " ".join(sorted(toks))


# --------------------------------------------------------------------------- positions

POSITION_PATTERNS: list[tuple[str, str]] = [
    # (pattern, English) — longer/more specific first
    ("助理教授", "Assistant Professor"),
    ("副教授", "Associate Professor"),
    ("特聘教授", "Distinguished Professor"),
    ("讲席教授", "Chair Professor"),
    ("教授", "Professor"),
    ("副研究员", "Associate Research Fellow"),
    ("助理研究员", "Assistant Research Fellow"),
    ("研究员", "Research Fellow / Professor"),
    ("讲师", "Lecturer"),
    ("Distinguished Professor", "Distinguished Professor"),
    ("Chair Professor", "Chair Professor"),
    ("Associate Professor", "Associate Professor"),
    ("Assistant Professor", "Assistant Professor"),
    ("Full Professor", "Professor"),
    ("Professor", "Professor"),
    ("Senior Lecturer", "Senior Lecturer"),
    ("Lecturer", "Lecturer"),
    ("Research Fellow", "Research Fellow"),
    ("Researcher", "Researcher"),
]
SUPERVISOR_PATTERNS = [("博士生导师", "PhD Supervisor"), ("博导", "PhD Supervisor"),
                       ("硕士生导师", "Master's Supervisor"), ("硕导", "Master's Supervisor")]


def detect_position(text: str) -> tuple[str | None, str | None]:
    """Return (english, original) for the first position title found in `text`."""
    head = text[:3000]
    best: tuple[int, str, str] | None = None
    for pat, en in POSITION_PATTERNS:
        idx = head.find(pat) if has_cjk(pat) else head.lower().find(pat.lower())
        if idx >= 0 and (best is None or idx < best[0] or (idx == best[0] and len(pat) > len(best[1]))):
            best = (idx, pat, en)
    if best is None:
        return None, None
    return best[2], best[1]


def detect_supervisor_roles(text: str) -> list[str]:
    roles = []
    for pat, en in SUPERVISOR_PATTERNS:
        if pat in text and en not in roles:
            roles.append(en)
    return roles
