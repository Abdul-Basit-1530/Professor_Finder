import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiService, apiError } from '../../core/api.service';
import { FieldOption, Job, PublicConfig } from '../../core/models';
import { StatusBadge } from '../../shared/ui';

const FALLBACK_FIELDS: FieldOption[] = [
  ['Computer Science', '计算机科学'], ['Artificial Intelligence', '人工智能'], ['Machine Learning', '机器学习'],
  ['Information Technology', '信息技术'], ['Software Engineering', '软件工程'], ['Data Science', '数据科学'],
  ['Computer Engineering', '计算机工程'], ['Computer Networks', '计算机网络'], ['Cybersecurity', '网络安全'],
  ['Internet of Things', '物联网'], ['Cloud Computing', '云计算'], ['Distributed Systems', '分布式系统'],
  ['Natural Language Processing', '自然语言处理'], ['Computer Vision', '计算机视觉'],
].map(([label, zh]) => ({ key: label, label, label_zh: zh, custom: false }));

@Component({
  selector: 'app-home',
  imports: [RouterLink, DatePipe, StatusBadge],
  templateUrl: './home.html',
})
export class Home implements OnInit {
  private api = inject(ApiService);
  private router = inject(Router);

  config = signal<PublicConfig | null>(null);
  fields = signal<FieldOption[]>(FALLBACK_FIELDS);
  selected = signal<Set<string>>(new Set(FALLBACK_FIELDS.map((f) => f.label)));
  customFields = signal<string[]>([]);
  url = signal('');
  customInput = signal('');
  maxProfessors = signal(40);
  forceRefresh = signal(false);
  submitting = signal(false);
  error = signal<string | null>(null);
  touched = signal(false);
  recent = signal<Job[]>([]);

  urlError = computed(() => {
    const v = this.url().trim();
    if (!v) return 'Enter the university website URL.';
    const candidate = /^https?:\/\//i.test(v) ? v : `https://${v}`;
    try {
      const u = new URL(candidate);
      if (!u.hostname.includes('.')) return 'That does not look like a website address.';
      if (/^(localhost|\d+\.\d+\.\d+\.\d+)$/.test(u.hostname)) return 'Use the university domain name.';
      return null;
    } catch {
      return 'That does not look like a valid URL.';
    }
  });
  selectedCount = computed(() => this.selected().size + this.customFields().length);
  canSubmit = computed(() => !this.urlError() && this.selectedCount() > 0 && !this.submitting());

  ngOnInit(): void {
    this.api.config().subscribe({
      next: (cfg) => {
        this.config.set(cfg);
        if (cfg.default_fields?.length) {
          this.fields.set(cfg.default_fields);
          this.selected.set(new Set(cfg.default_fields.map((f) => f.label)));
        }
        this.maxProfessors.set(cfg.max_professors || 40);
      },
      error: () => this.error.set('Cannot reach the research server. Is the backend running?'),
    });
    this.api.jobs(6).subscribe({ next: (j) => this.recent.set(j), error: () => {} });
  }

  toggle(label: string): void {
    const next = new Set(this.selected());
    if (next.has(label)) next.delete(label);
    else next.add(label);
    this.selected.set(next);
  }

  selectAll(on: boolean): void {
    this.selected.set(on ? new Set(this.fields().map((f) => f.label)) : new Set());
  }

  addCustom(): void {
    const parts = this.customInput()
      .split(/[,，;\n]/)
      .map((s) => s.trim())
      .filter((s) => s && s.length <= 80);
    const known = new Set(this.fields().map((f) => f.label.toLowerCase()));
    const next = [...this.customFields()];
    for (const p of parts) {
      if (known.has(p.toLowerCase())) {
        const label = this.fields().find((f) => f.label.toLowerCase() === p.toLowerCase())!.label;
        this.selected.set(new Set([...this.selected(), label]));
      } else if (!next.some((x) => x.toLowerCase() === p.toLowerCase())) {
        next.push(p);
      }
    }
    this.customFields.set(next);
    this.customInput.set('');
  }

  removeCustom(f: string): void {
    this.customFields.set(this.customFields().filter((x) => x !== f));
  }

  onCustomKey(ev: KeyboardEvent): void {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      this.addCustom();
    }
  }

  start(): void {
    this.touched.set(true);
    if (this.customInput().trim()) this.addCustom();
    if (!this.canSubmit()) return;
    this.submitting.set(true);
    this.error.set(null);
    this.api
      .startResearch({
        university_url: this.url().trim(),
        fields: [...this.selected()],
        custom_fields: this.customFields(),
        max_professors: this.maxProfessors(),
        force_refresh: this.forceRefresh(),
      })
      .subscribe({
        next: (r) => this.router.navigate(['/research', r.job_id, 'progress']),
        error: (e) => {
          this.error.set(apiError(e));
          this.submitting.set(false);
        },
      });
  }

  value(ev: Event): string {
    return (ev.target as HTMLInputElement).value;
  }
}
