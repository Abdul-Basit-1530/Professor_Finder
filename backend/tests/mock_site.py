"""A self-contained mock Chinese university website.

Served through httpx.MockTransport, so the full research pipeline can be tested
without touching the internet. It deliberately includes real-world awkwardness:
GBK-encoded Chinese pages, obfuscated emails (name#domain), a site-wide office
email in the footer, paginated faculty lists, a duplicate English profile, a
broken profile link, a non-institutional email, an ambiguous name romanisation,
a robots.txt-disallowed page and a PDF-free English program table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

Y = datetime.now(timezone.utc).year  # keep "recent" publications recent forever

ROOT = "https://www.mocku.edu.cn"
ISO = "https://iso.mocku.edu.cn"
GS = "https://gs.mocku.edu.cn"
CS = "https://cs.mocku.edu.cn"
SSE = "https://sse.mocku.edu.cn"


def page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset=\"{{charset}}\"><title>{title}</title></head><body>{body}</body></html>"


PAGES: dict[str, tuple[str, str]] = {}  # url -> (html, charset)


def add(url: str, title: str, body: str, charset: str = "utf-8") -> None:
    PAGES[url] = (page(title, body).replace("{charset}", charset), charset)


add(ROOT + "/", "模拟大学 | Mock University", """
<nav><a href="/">首页</a> <a href="/en/">English</a> <a href="https://iso.mocku.edu.cn/">国际学生</a>
<a href="https://gs.mocku.edu.cn/">研究生院</a> <a href="/yxsz.htm">院系设置</a> <a href="/private/secret.htm">内部</a></nav>
<h1>模拟大学</h1><p>模拟大学是一所综合性研究型大学。</p>
<ul><li><a href="/news/1.htm">我校举办2025年国际学术会议暨人工智能前沿论坛开幕式隆重举行</a></li></ul>
<footer>地址：北京市海淀区学院路1号 邮编：100000 邮箱：office@mocku.edu.cn 版权所有 模拟大学</footer>
""", charset="gbk")

add(ROOT + "/en/", "Mock University", """
<a href="https://iso.mocku.edu.cn/">International Students</a> <a href="/en/schools.html">Schools &amp; Departments</a>
<h1>Welcome to Mock University</h1><p>Mock University is a research university in Beijing, China.</p>
<footer>Address: No.1 Xueyuan Road, Haidian District, Beijing</footer>
""")

add(ROOT + "/yxsz.htm", "院系设置-模拟大学", """
<ul>
<li><a href="https://cs.mocku.edu.cn/">计算机科学与技术学院</a></li>
<li><a href="https://sse.mocku.edu.cn/">软件学院</a></li>
<li><a href="https://fl.mocku.edu.cn/">外国语学院</a></li>
<li><a href="https://chem.mocku.edu.cn/">化学学院</a></li>
</ul>""", charset="gbk")

add(ROOT + "/en/schools.html", "Schools - Mock University", """
<a href="https://cs.mocku.edu.cn/">School of Computer Science and Technology</a>
<a href="https://sse.mocku.edu.cn/">School of Software Engineering</a>
<a href="https://fl.mocku.edu.cn/">School of Foreign Languages</a>""")

add(ISO + "/", "International Students Office - Mock University", """
<a href="/scholarships.html">Scholarships</a> <a href="/programs.html">English-taught Programs</a>
<a href="/apply.html">How to Apply</a>
<h1>Study at Mock University</h1>
<p>Mock University welcomes international students. We are a host university of the
Chinese Government Scholarship (CSC) for international students.</p>""")

add(ISO + "/scholarships.html", "Scholarships for International Students", f"""
<h1>Chinese Government Scholarship</h1>
<p>Mock University accepts applications for the Chinese Government Scholarship - Chinese University Program (Type B)
for international students pursuing Master's and doctoral degrees.</p>
<p>Agency Number: 10099</p>
<p>Applicants must apply online at the CSC Online Application System (studyinchina.csc.edu.cn) and then submit
documents to the university.</p>
<p>Application deadline: March 31, {Y + 1}</p>
<p>中国政府奖学金 高校研究生项目 来华留学生</p>""")

add(ISO + "/programs.html", "English-taught Master's Programs", """
<h1>English-taught Master's Programs</h1>
<p>The following Master's degree programs are taught in English for international students.</p>
<table>
<tr><th>Program</th><th>Degree</th><th>Language</th><th>Duration</th><th>School</th></tr>
<tr><td>Computer Science and Technology</td><td>Master of Engineering</td><td>English</td><td>2.5 years</td><td>School of Computer Science and Technology</td></tr>
<tr><td>Software Engineering</td><td>Master of Engineering</td><td>English</td><td>2 years</td><td>School of Software Engineering</td></tr>
<tr><td>Artificial Intelligence</td><td>Master of Science</td><td>Chinese</td><td>3 years</td><td>School of Computer Science and Technology</td></tr>
<tr><td>International Business</td><td>Master of Business</td><td>English</td><td>2 years</td><td>Business School</td></tr>
</table>""")

add(ISO + "/apply.html", "How to Apply", "<p>Submit your application online. Contact admission@mocku.edu.cn</p>")

add(GS + "/", "研究生院", """<p>研究生招生信息。硕士研究生招生专业目录。</p>
<a href="/zsml.htm">招生专业目录</a>""", charset="gbk")
add(GS + "/zsml.htm", "招生专业目录", "<p>计算机科学与技术 硕士 学术学位</p><p>软件工程 硕士 专业学位</p>", charset="gbk")

# ---------------------------------------------------------------- School of CS
add(CS + "/", "计算机科学与技术学院", """
<a href="/szdw/index.htm">师资队伍</a> <a href="/en/faculty.html">Faculty</a> <a href="/xwzx.htm">新闻中心</a>
<h1>计算机科学与技术学院</h1><p>学院研究方向包括人工智能、机器学习、计算机视觉与分布式系统。</p>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>""", charset="gbk")

add(CS + "/szdw/index.htm", "师资队伍-计算机学院", """
<ul>
<li><a href="zhangwei.htm">张伟</a> 教授 研究方向：自然语言处理</li>
<li><a href="lina.htm">李娜</a> 副教授</li>
<li><a href="zenghua.htm">曾华</a> 讲师</li>
<li><a href="missing.htm">王强</a> 教授</li>
<li><a href="/szdw/notice.htm">学院通知</a></li>
</ul>
<a href="index_2.htm">下一页</a>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>""", charset="gbk")

add(CS + "/szdw/index_2.htm", "师资队伍-计算机学院", """
<ul><li><a href="liuyang.htm">刘洋</a> 研究员</li><li><a href="./zhangwei.htm">张伟</a> 教授</li></ul>""", charset="gbk")

add(CS + "/szdw/zhangwei.htm", "张伟-计算机学院", f"""
<h2>张伟</h2><p>职称：教授，博士生导师</p>
<p>电子邮件：zhangwei#mocku.edu.cn（#换成@）</p>
<h3>研究方向</h3><p>自然语言处理、大语言模型、机器学习</p>
<p>所在团队：智能信息处理实验室</p>
<h3>代表性论文</h3>
<p>[1] Wei Zhang, Na Li. "Efficient Instruction Tuning for Chinese Large Language Models". ACL, {Y - 1}.</p>
<p>[2] Wei Zhang, Hua Zeng. "Graph Neural Networks for Code Search". AAAI, {Y}.</p>
<p>[3] Wei Zhang. "A Survey of Statistical Machine Translation". Journal of Old Things, 2015.</p>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>""", charset="gbk")

add(CS + "/szdw/lina.htm", "李娜-计算机学院", """
<h2>李娜</h2><p>副教授 硕士生导师</p><p>邮箱：lina@mocku.edu.cn</p>
<p>研究领域：计算机视觉，图像处理，目标检测</p>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>""", charset="gbk")

add(CS + "/szdw/zenghua.htm", "曾华-计算机学院", """
<h2>曾华</h2><p>讲师</p><p>研究方向：分布式系统、云计算</p>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>""", charset="gbk")

add(CS + "/szdw/liuyang.htm", "刘洋-计算机学院", """
<h2>刘洋</h2><p>研究员</p><p>Email: liuyang@gmail.com</p><p>研究方向：化学催化、材料合成</p>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>""", charset="gbk")

add(CS + "/szdw/notice.htm", "学院通知", "<p>通知内容</p>", charset="gbk")

add(CS + "/en/faculty.html", "Faculty - School of Computer Science", """
<ul><li><a href="/en/people/wei-zhang.html">Wei Zhang</a> Professor</li></ul>""")

add(CS + "/en/people/wei-zhang.html", "Wei Zhang - School of Computer Science", """
<h1>Wei Zhang</h1><p>Professor, School of Computer Science and Technology</p>
<p>Email: <a href="mailto:zhangwei@mocku.edu.cn">zhangwei@mocku.edu.cn</a></p>
<h2>Research Interests</h2><p>Natural Language Processing; Large Language Models</p>""")

# ---------------------------------------------------------------- School of Software
add(SSE + "/", "School of Software Engineering - Mock University", """
<a href="/people.html">Faculty</a> <a href="/news.html">News</a>
<h1>School of Software Engineering</h1><p>Software engineering education and research.</p>""")

add(SSE + "/people.html", "People - School of Software Engineering", """
<ul><li><a href="/people/smith.html">Prof. John Smith</a> Professor</li>
<li><a href="/people/chen.html">陈静</a> 副教授</li></ul>""")

add(SSE + "/people/smith.html", "John Smith", """
<h1>John Smith</h1><p>Professor of Software Engineering</p>
<p>Contact: jsmith [at] sse.mocku.edu.cn</p>
<h2>Research Interests</h2><ul><li>Software Engineering</li><li>Program Analysis</li><li>Software Testing</li></ul>
<h2>Publications</h2><p>J. Smith. Fuzzing at scale. ICSE 2016.</p>""")

add(SSE + "/people/chen.html", "陈静", """<h2>陈静</h2><p>副教授</p><p>研究方向：软件测试、程序分析</p>
<p>E-mail: chenjing@sse.mocku.edu.cn</p>""", charset="gbk")

ROBOTS = {ROOT: "User-agent: *\nDisallow: /private/\n"}

def _site_handler(request: httpx.Request) -> httpx.Response:
    parts = urlsplit(str(request.url))
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/"
    if path == "/robots.txt":
        if origin in ROBOTS:
            return httpx.Response(200, text=ROBOTS[origin], headers={"content-type": "text/plain"})
        return httpx.Response(404)
    url = origin + path
    if url not in PAGES and path.endswith("/") is False and url + "/" in PAGES:
        return httpx.Response(301, headers={"location": url + "/"})
    if url not in PAGES:
        return httpx.Response(404, text="Not Found", headers={"content-type": "text/html"})
    html, charset = PAGES[url]
    return httpx.Response(200, content=html.encode(charset if charset != "gbk" else "gb18030"),
                          headers={"content-type": "text/html"})  # no charset header: tests meta sniffing


def site_transport() -> httpx.MockTransport:
    return httpx.MockTransport(_site_handler)


def all_site_text() -> str:
    return "\n".join(h for h, _ in PAGES.values())


__all__ = ["site_transport", "ROOT", "PAGES", "Y", "all_site_text"]
