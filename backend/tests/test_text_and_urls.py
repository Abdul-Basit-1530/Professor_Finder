"""Unit tests: URL validation, Chinese text handling, email extraction, fields."""

from __future__ import annotations

import pytest

from app.services.fields import match_fields, resolve_fields
from app.services.html_utils import decode_html, looks_blocked
from app.services.text_utils import (
    detect_language,
    detect_position,
    extract_emails,
    is_grounded,
    is_institutional_email,
    looks_like_chinese_name,
    looks_like_english_name,
    name_key,
    romanize_chinese_name,
)
from app.services.url_utils import (
    InvalidURLError,
    canonical_key,
    is_official,
    registrable_domain,
    resolve_link,
    validate_university_url,
)


# ------------------------------------------------------------------ URLs
@pytest.mark.parametrize("raw,expected", [
    ("www.tsinghua.edu.cn", "https://www.tsinghua.edu.cn/"),
    ("https://WWW.PKU.EDU.CN/index.htm#top", "https://www.pku.edu.cn/index.htm"),
    ("http://www.ustc.edu.cn:80/", "http://www.ustc.edu.cn/"),
])
def test_validate_url_normalises(raw, expected):
    assert validate_university_url(raw) == expected


@pytest.mark.parametrize("bad", ["", "ftp://x.edu.cn", "http://localhost:8000", "http://127.0.0.1/",
                                 "http://10.0.0.5", "https://nodot", "javascript:alert(1)"])
def test_validate_url_rejects(bad):
    with pytest.raises(InvalidURLError):
        validate_university_url(bad)


def test_registrable_domain_and_official():
    assert registrable_domain("https://cs.ustc.edu.cn/x") == "ustc.edu.cn"
    assert registrable_domain("https://www.hku.hk/") == "hku.hk"
    assert is_official("https://iso.mocku.edu.cn/a", "mocku.edu.cn")
    assert not is_official("https://mocku.edu.cn.evil.com/", "mocku.edu.cn")


def test_resolve_link_filters_non_pages():
    base = "https://www.x.edu.cn/a/b.htm"
    assert resolve_link(base, "../c.htm") == "https://www.x.edu.cn/c.htm"
    assert resolve_link(base, "mailto:a@b.cn") is None
    assert resolve_link(base, "javascript:void(0)") is None
    assert resolve_link(base, "/logo.png") is None
    assert canonical_key("https://www.x.edu.cn/a/") == canonical_key("http://x.edu.cn/a")


# ------------------------------------------------------------------ Chinese text
def test_language_detection():
    assert detect_language("计算机科学与技术学院师资队伍") == "zh"
    assert detect_language("School of Computer Science") == "en"


def test_gbk_decoding_via_meta_charset():
    html = '<html><head><meta charset="gb2312"></head><body>计算机学院</body></html>'
    assert "计算机学院" in decode_html(html.encode("gbk"), None)


def test_chinese_name_detection():
    assert looks_like_chinese_name("张伟")
    assert looks_like_chinese_name("欧阳明")
    assert looks_like_chinese_name("王  伟")  # padded two-character name
    for not_name in ("首页", "师资队伍", "学院新闻", "计算机", "教授"):
        assert not looks_like_chinese_name(not_name)


def test_english_name_detection():
    assert looks_like_english_name("Prof. John Smith")
    assert looks_like_english_name("Wei Zhang")
    assert not looks_like_english_name("School News")
    assert not looks_like_english_name("Research Areas")


def test_romanisation_never_guesses_ambiguous_readings():
    assert romanize_chinese_name("张伟") == "Zhang Wei"
    assert romanize_chinese_name("诸葛亮") == "Zhuge Liang"
    assert romanize_chinese_name("曾华") is None  # 曾: Zeng vs Ceng
    assert romanize_chinese_name("单明") is None  # 单: Shan vs Dan


def test_name_key_order_insensitive():
    assert name_key("Wei Zhang") == name_key("ZHANG Wei") == name_key("Prof. Zhang Wei")


def test_position_detection_prefers_specific_titles():
    assert detect_position("李娜 副教授 硕士生导师")[0] == "Associate Professor"
    assert detect_position("张伟，教授，博士生导师")[0] == "Professor"
    assert detect_position("Assistant Professor of CS")[0] == "Assistant Professor"


# ------------------------------------------------------------------ emails
def test_extract_emails_literal_and_obfuscated():
    text = "邮箱：zhangwei#ustc.edu.cn  Email: li [at] pku [dot] edu [dot] cn; wang(at)zju.edu.cn"
    assert extract_emails(text) == ["zhangwei@ustc.edu.cn", "li@pku.edu.cn", "wang@zju.edu.cn"]


def test_extract_emails_does_not_invent_from_prose():
    assert extract_emails("He works at cs.ustc.edu.cn and studies C# programming.") == []
    assert extract_emails("see page.html#section.top") == []
    assert extract_emails("contact: name@example.com") == []


def test_institutional_email():
    assert is_institutional_email("a@cs.mocku.edu.cn", "mocku.edu.cn")
    assert is_institutional_email("a@pku.edu.cn", "mocku.edu.cn")  # academic domain
    assert not is_institutional_email("a@gmail.com", "mocku.edu.cn")
    assert not is_institutional_email("a@163.com", "mocku.edu.cn")


def test_grounding_is_whitespace_insensitive():
    assert is_grounded("自然 语言处理", "研究方向：自然语言处理")
    assert not is_grounded("量子计算", "研究方向：自然语言处理")


# ------------------------------------------------------------------ fields
def test_bilingual_field_mapping():
    fields = resolve_fields(["AI, NLP", "Machine Learning", "计算机视觉", "Quantum Computing"])
    labels = [f.label for f in fields]
    assert labels == ["Artificial Intelligence", "Natural Language Processing", "Machine Learning",
                      "Computer Vision", "Quantum Computing"]
    found = {m["label"] for m in match_fields("研究方向：自然语言处理、深度学习、图像识别", fields)}
    assert found == {"Natural Language Processing", "Machine Learning", "Computer Vision"}


def test_field_matching_avoids_substring_false_positives():
    fields = resolve_fields(["Artificial Intelligence", "Cloud Computing", "Cybersecurity"])
    assert match_fields("Email and maintenance of training rooms", fields) == []  # 'AI' inside words
    assert match_fields("Food safety 食品安全", fields) == []  # bare 安全 is not cybersecurity
    assert match_fields("cloud physics", fields) == []


def test_block_detection():
    assert looks_blocked(403, "")
    assert looks_blocked(200, "请输入验证码以继续访问")
    assert not looks_blocked(200, "计算机学院 " * 400)
