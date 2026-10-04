import type { ResearchResult } from '../engine/types';

export interface ExtractedContact {
  email: string;
  context: string;
  profileUrl: string | null;
}

export interface SourceLink {
  label: string;
  url: string;
}

export interface PageScan {
  title: string;
  sourceUrl: string;
  contacts: ExtractedContact[];
  links: SourceLink[];
}

export class LocalExtractor {
  async scanSite(source: string, report: (message: string) => void = () => {}): Promise<ResearchResult> {
    const [{ Fetcher }, { DEFAULT_FIELDS }, { runResearch }, { validateUniversityUrl }] = await Promise.all([
      import('../engine/fetcher'),
      import('../engine/fields'),
      import('../engine/research'),
      import('../engine/url'),
    ]);
    const universityUrl = validateUniversityUrl(this.normalizeUrl(source));
    const fetcher = new Fetcher();
    return runResearch(universityUrl, DEFAULT_FIELDS, fetcher, {}, {
      onStep: (steps) => {
        const active = steps.find((step) => step.status === 'running');
        if (active) report(active.message || active.label);
      },
      onProfessor: (professor) => report(`Checking ${professor.name}…`),
    });
  }

  async parse(content: string, source: string): Promise<PageScan> {
    const [{ parseHtml }, { extractEmails }] = await Promise.all([
      import('../engine/html'),
      import('../engine/text'),
    ]);
    const sourceUrl = this.normalizeUrl(source);
    const parsed = parseHtml(content, sourceUrl);
    const contacts = extractEmails(parsed.text, parsed.mailtos).map((email) => {
      const profile = parsed.links.find((link) => link.context.toLowerCase().includes(email));
      const index = parsed.text.toLowerCase().indexOf(email);
      const context = index >= 0
        ? parsed.text.slice(Math.max(0, index - 90), Math.min(parsed.text.length, index + email.length + 90)).replace(/\s+/g, ' ').trim()
        : profile?.context ?? '';
      return { email, context, profileUrl: profile?.url ?? null };
    });
    return {
      title: parsed.title || sourceUrl,
      sourceUrl,
      contacts,
      links: parsed.links.map((link) => ({ label: link.text || new URL(link.url).hostname, url: link.url })),
    };
  }

  normalizeUrl(source: string): string {
    const candidate = /^https?:\/\//i.test(source.trim()) ? source.trim() : `https://${source.trim()}`;
    const url = new URL(candidate);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('Enter a valid HTTP or HTTPS URL.');
    return url.href;
  }

}