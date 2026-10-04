"""Scores links into crawl categories using bilingual anchor-text and URL cues.

This is what keeps the crawler targeted: instead of crawling everything, each
agent asks for the top links of the category it needs.
"""

from __future__ import annotations

import re

from app.services.html_utils import Link

CATEGORIES: dict[str, dict[str, list[str]]] = {
    "international": {
        "text": ["international student", "international students", "foreign student", "study in", "留学生",
                 "国际学生", "来华留学", "国际教育学院", "国际学院", "international education", "international college",
                 "international office", "global", "international admission", "外国留学生", "海外学生"],
        "url": ["international", "intl", "iso", "lxs", "lxsb", "cie", "sie", "ice", "studyin", "admission", "oia",
                "global", "liuxue", "foreign"],
    },
    "graduate": {
        "text": ["graduate school", "graduate admission", "graduate admissions", "postgraduate", "graduate studies",
                 "研究生院", "研究生招生", "研究生教育", "master", "硕士", "graduate programs", "研招"],
        "url": ["graduate", "grad", "yjs", "yjsy", "gs", "yz", "postgraduate", "gradschool"],
    },
    "scholarship": {
        "text": ["scholarship", "scholarships", "奖学金", "financial aid", "funding", "csc", "chinese government",
                 "政府奖学金", "fees and scholarships", "tuition"],
        "url": ["scholarship", "jxj", "csc", "funding", "fees"],
    },
    "admissions": {
        "text": ["admission", "admissions", "apply", "application", "how to apply", "招生", "申请", "入学",
                 "招生简章", "admission guide", "prospectus"],
        "url": ["admission", "apply", "zs", "zsxx", "enroll", "recruit"],
    },
    "programs": {
        "text": ["english-taught", "english taught", "taught in english", "programs", "programmes", "degree programs",
                 "majors", "英文授课", "英语授课", "全英文", "专业目录", "招生专业", "学科专业", "专业设置", "program catalog",
                 "master's programs", "master programs", "graduate programs"],
        "url": ["program", "programme", "major", "zyml", "catalog", "english-taught", "degree"],
    },
    "schools": {
        "text": ["schools", "colleges", "faculties", "departments", "院系", "院系设置", "学院设置", "教学单位",
                 "院系导航", "academics", "schools & departments", "schools and departments", "academic units",
                 "院系部门", "机构设置", "学院部门", "教学科研单位", "院部设置", "学部", "schools & colleges",
                 "academic schools", "colleges & schools", "faculties & schools"],
        "url": ["yxsz", "yxdh", "school", "college", "department", "academics", "faculties", "jxdw", "yx"],
    },
    "faculty": {
        "text": ["faculty", "people", "师资", "师资队伍", "教师", "导师", "教职工", "研究生导师", "博士生导师",
                 "硕士生导师", "导师介绍", "教授", "教师名录", "faculty members", "academic staff", "researchers",
                 "our team", "staff directory", "专任教师", "全职教师", "教师队伍", "人才队伍", "研究团队"],
        "url": ["faculty", "people", "szdw", "teacher", "teachers", "jsml", "ds", "dsdw", "staff", "szll", "jszy",
                "rcdw", "team", "members", "szgk"],
    },
    "english_site": {
        "text": ["english", "english version", "en", "eng"],
        "url": ["/en", "english", "en."],
    },
}

_WORD_SPLIT = re.compile(r"[/._\-?=&]+")


def score_link(link: Link, category: str) -> float:
    cfg = CATEGORIES[category]
    text = link.text.lower().strip()
    url = link.url.lower()
    score = 0.0
    for kw in cfg["text"]:
        if not kw:
            continue
        if category == "english_site":
            if text == kw or text in ("english", "english version", "eng"):
                score += 3
            continue
        if kw in text:
            score += 3 if len(kw) > 3 else 2
            if text == kw:
                score += 1
    tokens = set(_WORD_SPLIT.split(url.split("://", 1)[-1]))
    for kw in cfg["url"]:
        if kw.startswith("/") or "." in kw:
            if kw in url:
                score += 1.5
        elif kw in tokens:
            score += 1.5
    # Long anchor texts are usually news headlines, not navigation.
    if len(link.text) > 40:
        score *= 0.4
    if any(n in text for n in ("news", "新闻", "通知", "公告", "动态")) and category != "scholarship":
        score *= 0.5
    return score


def top_links(links: list[Link], category: str, limit: int = 5, min_score: float = 2.0) -> list[tuple[Link, float]]:
    scored: dict[str, tuple[Link, float]] = {}
    for ln in links:
        s = score_link(ln, category)
        if s >= min_score and (ln.url not in scored or scored[ln.url][1] < s):
            scored[ln.url] = (ln, s)
    return sorted(scored.values(), key=lambda t: t[1], reverse=True)[:limit]


PAGINATION_TEXT = ("下一页", "下页", "next", "next page", "»", ">", "更多", "more")


def pagination_links(links: list[Link]) -> list[Link]:
    out = []
    for ln in links:
        t = ln.text.strip().lower()
        if t in PAGINATION_TEXT or re.fullmatch(r"\d{1,2}", t):
            out.append(ln)
    return out
