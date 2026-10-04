import { Component, computed, signal } from '@angular/core';

import { LocalExtractor, SourceLink } from '../../core/local-extractor';
import type { ProfessorInfo } from '../../engine/types';

interface DisplayContact {
  name: string;
  position: string | null;
  department: string | null;
  email: string | null;
  emailVerified: boolean;
  verification: string;
  context: string;
  profileUrl: string | null;
  pageTitle: string;
  sourceUrl: string;
}

const FACULTY_LINK = /faculty|professor|teacher|staff|people|team|师资|教师|教授|导师|人才/i;

@Component({
  selector: 'app-home',
  templateUrl: './home.html',
})
export class Home {
  private extractor = new LocalExtractor();

  url = signal('');
  pastedContent = signal('');
  contacts = signal<DisplayContact[]>([]);
  pageLinks = signal<SourceLink[]>([]);
  scannedPages = signal<SourceLink[]>([]);
  warnings = signal<string[]>([]);
  pagesFetched = signal(0);
  busy = signal(false);
  touched = signal(false);
  error = signal<string | null>(null);
  notice = signal('');
  clipboardStatus = signal('');

  urlError = computed(() => {
    if (!this.url().trim()) return 'Enter the URL of the official page.';
    try {
      this.extractor.normalizeUrl(this.url());
      return null;
    } catch {
      return 'Enter a valid HTTP or HTTPS page URL.';
    }
  });
  relevantLinks = computed(() => this.pageLinks().filter((link) => FACULTY_LINK.test(`${link.label} ${link.url}`)).slice(0, 30));
  canExtract = computed(() => !this.busy() && !this.urlError());

  async extract(): Promise<void> {
    this.touched.set(true);
    if (!this.canExtract()) return;

    this.busy.set(true);
    this.error.set(null);
    this.notice.set('');
    this.clipboardStatus.set('');

    try {
      const sourceUrl = this.extractor.normalizeUrl(this.url());
      const pasted = this.pastedContent().trim();
      const result = pasted ? null : await this.extractor.scanSite(sourceUrl, (message) => this.notice.set(message));
      if (result?.error) throw new Error(result.error);
      const pastedScan = pasted ? await this.extractor.parse(pasted, sourceUrl) : null;
      const additions: DisplayContact[] = result
        ? result.professors.map((professor) => this.toContact(professor))
        : (pastedScan?.contacts ?? []).map((contact) => ({
            name: 'Name not identified', position: null, department: null, email: contact.email, emailVerified: false,
            verification: 'UNVERIFIED', context: contact.context, profileUrl: contact.profileUrl,
            pageTitle: pastedScan!.title, sourceUrl: pastedScan!.sourceUrl,
          }));
      const scanned = result
        ? this.resultPages(result, sourceUrl)
        : [{ label: pastedScan!.title, url: pastedScan!.sourceUrl }];
      const discoveredLinks = result
        ? result.departments.flatMap((department) => department.facultyListUrls.map((url) => ({ label: department.name, url })))
        : (pastedScan?.links ?? []);

      this.contacts.update((current) => {
        const keyFor = (contact: DisplayContact) => contact.email ?? contact.profileUrl ?? `${contact.name}|${contact.department}`;
        const byEmail = new Map(current.map((contact) => [keyFor(contact), contact]));
        for (const contact of additions) {
          const key = keyFor(contact);
          const existing = byEmail.get(key);
          byEmail.set(key, existing
            ? { ...existing, context: existing.context || contact.context, profileUrl: existing.profileUrl || contact.profileUrl }
            : contact);
        }
        return [...byEmail.values()];
      });
      this.pageLinks.update((current) => {
        const byUrl = new Map(current.map((link) => [link.url, link]));
        for (const link of discoveredLinks) byUrl.set(link.url, link);
        return [...byUrl.values()];
      });
      this.scannedPages.update((current) => {
        const byUrl = new Map(current.map((page) => [page.url, page]));
        for (const page of scanned) byUrl.set(page.url, page);
        return [...byUrl.values()];
      });
      this.warnings.set(result?.warnings ?? []);
      this.pagesFetched.set(result?.pagesFetched ?? 1);
      this.notice.set(`${this.contacts().length} faculty entr${this.contacts().length === 1 ? 'y' : 'ies'} found; ` +
        `${this.contacts().filter((contact) => contact.email).length} with a published email, across ${this.pagesFetched()} pages.`);
      if (pasted) this.pastedContent.set('');
    } catch (error) {
      this.notice.set('');
      this.error.set(error instanceof Error ? error.message : 'Could not read this page. Paste its content to extract locally.');
    } finally {
      this.busy.set(false);
    }
  }

  async copyEmails(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.contacts().flatMap((contact) => contact.email ? [contact.email] : []).join('\n'));
      this.clipboardStatus.set('Copied');
    } catch {
      this.clipboardStatus.set('Clipboard access is unavailable in this browser.');
    }
  }

  downloadCsv(): void {
    const rows = [
      ['Name', 'Position', 'Department', 'Email', 'Verification', 'Profile URL', 'Source page', 'Notes'],
      ...this.contacts().map((contact) => [contact.name, contact.position ?? '', contact.department ?? '', contact.email ?? '',
        contact.verification, contact.profileUrl ?? '', contact.sourceUrl, contact.context]),
    ];
    const csv = rows.map((row) => row.map((value) => this.csvCell(value)).join(',')).join('\r\n');
    const objectUrl = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = 'professor-emails.csv';
    link.click();
    URL.revokeObjectURL(objectUrl);
  }

  clearResults(): void {
    this.contacts.set([]);
    this.pageLinks.set([]);
    this.scannedPages.set([]);
    this.warnings.set([]);
    this.pagesFetched.set(0);
    this.pastedContent.set('');
    this.notice.set('');
    this.error.set(null);
    this.clipboardStatus.set('');
  }

  useLink(link: SourceLink): void {
    this.url.set(link.url);
    this.pastedContent.set('');
    this.touched.set(false);
  }

  value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  }

  private csvCell(value: string): string {
    const safe = /^[=+\-@]/.test(value) ? `'${value}` : value;
    return `"${safe.replace(/"/g, '""')}"`;
  }

  private toContact(professor: ProfessorInfo): DisplayContact {
    const sourceUrl = professor.profileUrl ?? professor.listingUrl ?? this.url();
    return {
      name: professor.nameChinese && professor.name !== professor.nameChinese
        ? `${professor.name} (${professor.nameChinese})`
        : professor.name,
      position: professor.position,
      department: professor.department,
      email: professor.email,
      emailVerified: professor.emailVerified,
      verification: professor.verification,
      context: professor.notes.join(' '),
      profileUrl: professor.profileUrl,
      pageTitle: professor.name,
      sourceUrl,
    };
  }

  private resultPages(result: Awaited<ReturnType<LocalExtractor['scanSite']>>, fallbackUrl: string): SourceLink[] {
    const pages: SourceLink[] = [{ label: result.university?.name ?? 'University homepage', url: result.university?.officialUrl ?? fallbackUrl }];
    pages.push(...result.departments.map((department) => ({ label: department.name, url: department.url })));
    pages.push(...result.professors
      .filter((professor) => professor.profileUrl)
      .map((professor) => ({ label: professor.name, url: professor.profileUrl! })));
    return [...new Map(pages.map((page) => [page.url, page])).values()];
  }
}
