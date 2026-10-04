"""University Discovery Agent — identity and location of the university."""

from __future__ import annotations

import re

from app.agents.context import ResearchContext, SourceRef, UniversityInfo
from app.agents.schemas import UniversityExtraction
from app.enums import Verification
from app.services.link_classifier import top_links
from app.services.llm import truncate_for_llm
from app.services.text_utils import has_cjk, is_grounded
from app.services.url_utils import registrable_domain


class FatalResearchError(Exception):
    """Raised when the job cannot continue (e.g. the university site is unreachable)."""


CITIES = {
    "北京": "Beijing", "上海": "Shanghai", "天津": "Tianjin", "重庆": "Chongqing", "广州": "Guangzhou",
    "深圳": "Shenzhen", "杭州": "Hangzhou", "南京": "Nanjing", "武汉": "Wuhan", "成都": "Chengdu",
    "西安": "Xi'an", "长沙": "Changsha", "合肥": "Hefei", "哈尔滨": "Harbin", "大连": "Dalian",
    "沈阳": "Shenyang", "长春": "Changchun", "济南": "Jinan", "青岛": "Qingdao", "厦门": "Xiamen",
    "福州": "Fuzhou", "郑州": "Zhengzhou", "兰州": "Lanzhou", "昆明": "Kunming", "南昌": "Nanchang",
    "苏州": "Suzhou", "无锡": "Wuxi", "宁波": "Ningbo", "太原": "Taiyuan", "石家庄": "Shijiazhuang",
    "贵阳": "Guiyang", "南宁": "Nanning", "海口": "Haikou", "乌鲁木齐": "Urumqi", "呼和浩特": "Hohhot",
    "银川": "Yinchuan", "西宁": "Xining", "拉萨": "Lhasa", "珠海": "Zhuhai", "镇江": "Zhenjiang",
    "徐州": "Xuzhou", "秦皇岛": "Qinhuangdao", "威海": "Weihai", "烟台": "Yantai", "温州": "Wenzhou",
    "扬州": "Yangzhou", "常州": "Changzhou", "南通": "Nantong", "绵阳": "Mianyang", "桂林": "Guilin",
    "香港": "Hong Kong", "澳门": "Macau",
}
_COUNTRY_BY_SUFFIX = [(".hk", "Hong Kong SAR, China"), (".mo", "Macau SAR, China"),
                      (".tw", "Taiwan"), (".cn", "China")]
_ADDRESS_RE = re.compile(r"(?:地址|校址|通讯地址|Address|ADDRESS|Add)\s*[:：]\s*([^\n|]{4,140})")
_ADDR_STOP = re.compile(r"\s*(?:邮编|邮政编码|电话|传真|邮箱|版权|E-?mail|Tel|Fax|Phone|Copyright|©|ICP|Postcode|Zip)"
                        r"|\s{2,}", re.I)
_TITLE_SPLIT = re.compile(r"\s*[|｜\-–—_·:：]\s*")


def _name_from_title(title: str) -> tuple[str | None, str | None]:
    en, zh = None, None
    for seg in _TITLE_SPLIT.split(title or ""):
        seg = seg.strip()
        if not seg:
            continue
        if has_cjk(seg) and re.search(r"(大学|学院)$", seg) and len(seg) <= 20 and not zh:
            zh = seg
        elif re.search(r"\b(University|Institute of Technology|College|Academy)\b", seg) and len(seg) <= 90 and not en:
            en = seg
    return en, zh


async def discover_university(ctx: ResearchContext) -> UniversityInfo:
    home = await ctx.fetch(ctx.start_url)
    if home.blocked:
        raise FatalResearchError(
            "The university website returned a CAPTCHA/access-denied page. Automated research cannot "
            "continue without bypassing it, which this tool does not do."
        )
    if not home.ok:
        raise FatalResearchError(f"Could not load the university website ({home.error or 'empty page'}).")

    ctx.homepage = home
    new_domain = registrable_domain(home.final_url)
    if new_domain != ctx.domain:
        ctx.note(f"Site redirected to {new_domain}; using it as the official domain")
        ctx.domain = new_domain
    info = UniversityInfo(official_url=home.final_url, domain=ctx.domain)
    info.sources.append(SourceRef.from_page(home, "homepage", ctx.domain))
    ctx.note(f"Fetched homepage ({home.lang})")

    # English version of the site, if linked.
    for link, _ in top_links(home.links, "english_site", limit=2, min_score=3):
        if ctx.official(link.url) and link.url != home.final_url:
            en = await ctx.fetch(link.url)
            if en.ok:
                ctx.english_homepage = en
                info.sources.append(SourceRef.from_page(en, "english homepage", ctx.domain))
                ctx.note("Found English version of the website")
                break

    pages = [p for p in (home, ctx.english_homepage) if p]

    # ---- Name ---------------------------------------------------------------
    for p in pages:
        en, zh = _name_from_title(p.title)
        info.name = info.name or en
        info.name_chinese = info.name_chinese or zh

    combined = "\n".join(f"TITLE: {p.title}\n{p.text[:3000]}\n…\n{p.text[-2500:]}" for p in pages)
    llm_out = await ctx.llm.extract(
        "university_identity",
        "Identify the university that owns this website: official English name, Chinese name, city, "
        "province, country, and quote the postal address if present.",
        truncate_for_llm(combined, ctx.settings.llm_max_input_chars),
        UniversityExtraction,
    )
    if llm_out:
        if llm_out.name_english and is_grounded(llm_out.name_english, combined):
            info.name = info.name or llm_out.name_english
        if llm_out.name_chinese and is_grounded(llm_out.name_chinese, combined):
            info.name_chinese = info.name_chinese or llm_out.name_chinese
        if llm_out.address_quote and is_grounded(llm_out.address_quote, combined):
            info.location = llm_out.address_quote.strip()
            if llm_out.city:
                info.location = f"{llm_out.city}" + (f", {llm_out.province}" if llm_out.province else "") + \
                                f" — {llm_out.address_quote.strip()}"

    # ---- Location (deterministic fallback) ----------------------------------
    if not info.location:
        for p in pages:
            m = _ADDRESS_RE.search(p.text)
            if m:
                addr = _ADDR_STOP.split(m.group(1))[0].strip(" ,，;；")
                city = next((en for zh, en in CITIES.items() if zh in addr or en.lower() in addr.lower()), None)
                info.location = f"{city} — {addr}" if city else addr
                break

    # ---- Country ------------------------------------------------------------
    for suffix, country in _COUNTRY_BY_SUFFIX:
        if ctx.domain.endswith(suffix):
            info.country = country
            break
    if not info.country and llm_out and llm_out.country and is_grounded(llm_out.country, combined):
        info.country = llm_out.country

    if not info.name:
        info.name = info.name_chinese or "Not Found"

    # ---- Verification ---------------------------------------------------------
    name_on_site = any(
        (info.name and is_grounded(info.name, p.title + p.text)) or
        (info.name_chinese and is_grounded(info.name_chinese, p.title + p.text))
        for p in pages
    )
    if name_on_site:
        info.verification_status = Verification.VERIFIED.value
    elif info.name and info.name != "Not Found":
        info.verification_status = Verification.PARTIALLY_VERIFIED.value

    ctx.university = info
    ctx.note(f"University identified: {info.name}" + (f" ({info.name_chinese})" if info.name_chinese else ""))
    return info
