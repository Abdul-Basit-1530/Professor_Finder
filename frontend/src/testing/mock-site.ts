/**
 * A self-contained mock Chinese university website for tests (no network).
 * Deliberately awkward, like real sites: obfuscated emails (name#domain, [at]), a site-wide office
 * email in the footer, paginated faculty lists, a duplicate English profile, a broken profile link,
 * a gmail-only professor, an ambiguous given-name romanisation, a robots.txt-disallowed path and a
 * VSB/Tsites profile whose email is an encrypted token decoded by the site's own endpoint.
 */
import type { RawResponse, Transport } from '../app/engine/fetcher';

export const ROOT = 'https://www.mocku.edu.cn';
const CS = 'https://cs.mocku.edu.cn';
const SSE = 'https://sse.mocku.edu.cn';

const PAGES: Record<string, string> = {};
const page = (title: string, body: string) => `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title></head><body>${body}</body></html>`;
const add = (url: string, title: string, body: string) => (PAGES[url] = page(title, body));

add(ROOT + '/', '模拟大学 | Mock University', `
<nav><a href="/">首页</a> <a href="/en/">English</a> <a href="https://iso.mocku.edu.cn/">国际学生</a>
<a href="/yxsz.htm">院系设置</a> <a href="/private/secret.htm">内部</a></nav>
<h1>模拟大学</h1><p>模拟大学是一所综合性研究型大学。</p>
<ul><li><a href="/news/1.htm">我校举办2025年国际学术会议暨人工智能前沿论坛开幕式隆重举行</a></li></ul>
<footer>地址：北京市海淀区学院路1号 邮编：100000 邮箱：office@mocku.edu.cn 版权所有 模拟大学</footer>`);

add(ROOT + '/en/', 'Mock University', `
<a href="/en/schools.html">Schools &amp; Departments</a>
<h1>Welcome to Mock University</h1><footer>Address: No.1 Xueyuan Road, Haidian District, Beijing</footer>`);

add(ROOT + '/yxsz.htm', '院系设置-模拟大学', `<ul>
<li><a href="https://cs.mocku.edu.cn/">计算机科学与技术学院</a></li>
<li><a href="https://sse.mocku.edu.cn/">软件学院</a></li>
<li><a href="https://fl.mocku.edu.cn/">外国语学院</a></li>
<li><a href="https://chem.mocku.edu.cn/">化学学院</a></li></ul>`);

add(ROOT + '/en/schools.html', 'Schools - Mock University', `
<a href="https://cs.mocku.edu.cn/">School of Computer Science and Technology</a>
<a href="https://sse.mocku.edu.cn/">School of Software Engineering</a>
<a href="https://fl.mocku.edu.cn/">School of Foreign Languages</a>`);

add(CS + '/', '计算机科学与技术学院', `
<a href="/szdw/index.htm">师资队伍</a> <a href="/en/faculty.html">Faculty</a> <a href="/xwzx.htm">新闻中心</a>
<h1>计算机科学与技术学院</h1><p>学院研究方向包括人工智能、机器学习、计算机视觉与分布式系统。</p>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>`);

add(CS + '/szdw/index.htm', '师资队伍-计算机学院', `<ul>
<li><a href="zhangwei.htm">张伟</a> 教授</li>
<li><a href="lina.htm">李娜</a> 副教授</li>
<li><a href="lele.htm">王乐</a> 讲师</li>
<li><a href="missing.htm">王强</a> 教授</li>
<li><a href="zhaolei.htm">赵磊</a> 教授</li>
<li><a href="/szdw/notice.htm">学院通知</a></li></ul>
<a href="index_2.htm">下一页</a>
<footer>学院办公室邮箱：cs@mocku.edu.cn</footer>`);

add(CS + '/szdw/index_2.htm', '师资队伍-计算机学院', `
<ul><li><a href="liuyang.htm">刘洋</a> 研究员</li><li><a href="./zhangwei.htm">张伟</a> 教授</li></ul>`);

add(CS + '/szdw/zhangwei.htm', '张伟-计算机学院', `
<h2>张伟</h2><p>职称：教授，博士生导师</p><p>电子邮件：zhangwei#mocku.edu.cn（#换成@）</p>
<h3>研究方向</h3><p>自然语言处理、大语言模型、机器学习</p><footer>学院办公室邮箱：cs@mocku.edu.cn</footer>`);

add(CS + '/szdw/lina.htm', '李娜-计算机学院', `
<h2>李娜</h2><p>副教授 硕士生导师</p><p>邮箱：lina@mocku.edu.cn</p><footer>学院办公室邮箱：cs@mocku.edu.cn</footer>`);

add(CS + '/szdw/lele.htm', '王乐-计算机学院', `
<h2>王乐</h2><p>讲师</p><p>研究方向：分布式系统</p><footer>学院办公室邮箱：cs@mocku.edu.cn</footer>`);

add(CS + '/szdw/liuyang.htm', '刘洋-计算机学院', `
<h2>刘洋</h2><p>研究员</p><p>Email: liuyang@gmail.com</p><footer>学院办公室邮箱：cs@mocku.edu.cn</footer>`);

add(CS + '/szdw/zhaolei.htm', '赵磊-计算机学院', `
<h2>赵磊</h2><p>教授</p>
<ul><li>电子邮箱：<span _tsites_encrypt_field="_tsites_encrypt_field" id="_tsites_encryp_tsteacher_tsemail" style="display:none;">73a51c2682ff5a415ab2247b3275b597</span></li></ul>
<script> var _tsites_com_view_mode_type_=8;</script>
<script language="javascript" src="/system/resource/tsites/tsitesencrypt.js"></script>`);

add(CS + '/szdw/notice.htm', '学院通知', '<p>通知内容</p>');

add(CS + '/en/faculty.html', 'Faculty - School of Computer Science', `
<ul><li><a href="/en/people/wei-zhang.html">Wei Zhang</a> Professor</li></ul>`);

add(CS + '/en/people/wei-zhang.html', 'Wei Zhang - School of Computer Science', `
<h1>Wei Zhang</h1><p>Professor, School of Computer Science and Technology</p>
<p>Email: <a href="mailto:zhangwei@mocku.edu.cn">zhangwei@mocku.edu.cn</a></p>`);

add(SSE + '/', 'School of Software Engineering - Mock University', `
<a href="/people.html">Faculty</a> <a href="/news.html">News</a><h1>School of Software Engineering</h1>`);

add(SSE + '/people.html', 'People - School of Software Engineering', `
<ul><li><a href="/people/smith.html">Prof. John Smith</a> Professor</li><li><a href="/people/chen.html">陈静</a> 副教授</li></ul>`);

add(SSE + '/people/smith.html', 'John Smith', `
<h1>John Smith</h1><p>Professor of Software Engineering</p><p>Contact: jsmith [at] sse.mocku.edu.cn</p>`);

add(SSE + '/people/chen.html', '陈静', '<h2>陈静</h2><p>副教授</p><p>E-mail: chenjing@sse.mocku.edu.cn</p>');

const ROBOTS: Record<string, string> = { [ROOT]: 'User-agent: *\nDisallow: /private/\n' };
const TSITES: Record<string, string> = {
  [`${CS}|_tsites_encryp_tsteacher_tsemail|73a51c2682ff5a415ab2247b3275b597`]: 'zhaolei@mocku.edu.cn',
};

const enc = new TextEncoder();
const res = (status: number, body: string, type = 'text/html', finalUrl = ''): RawResponse =>
  ({ status, finalUrl, contentType: type, bytes: enc.encode(body) });

/** All page HTML (used to assert no email was invented). */
export function allSiteText(): string {
  return Object.values(PAGES).join('\n') + '\n' + Object.values(TSITES).join('\n');
}

export function mockTransport(log: string[] = []): Transport {
  return async (url: string) => {
    log.push(url);
    const u = new URL(url);
    if (u.pathname === '/robots.txt') {
      return ROBOTS[u.origin] ? res(200, ROBOTS[u.origin], 'text/plain', url) : res(404, 'not found', 'text/html', url);
    }
    if (u.pathname === '/system/resource/tsites/tsitesencrypt.jsp') {
      const key = `${u.origin}|${u.searchParams.get('id')}|${u.searchParams.get('content')}`;
      return TSITES[key] ? res(200, JSON.stringify({ content: TSITES[key] }), 'text/html;charset=UTF-8', url)
        : res(200, '{}', 'text/html', url);
    }
    const key = u.origin + u.pathname;
    if (PAGES[key]) return res(200, PAGES[key], 'text/html', key);
    return res(404, 'Not Found', 'text/html', url);
  };
}
