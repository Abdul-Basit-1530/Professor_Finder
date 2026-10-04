import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService, apiError } from '../../core/api.service';
import { Professor } from '../../core/models';
import { JobNav, StatusBadge, copyText } from '../../shared/ui';

type SortKey = 'default' | 'name' | 'department';

@Component({
  selector: 'app-professors',
  imports: [RouterLink, JobNav, StatusBadge],
  templateUrl: './professors.html',
})
export class Professors implements OnInit {
  jobId = input.required<string>();
  department = input<string>(); // optional ?department= query param
  private api = inject(ApiService);

  all = signal<Professor[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  view = signal<'cards' | 'table'>('cards');
  copied = signal<number | null>(null);
  copiedAll = signal(false);

  // filters
  q = signal('');
  dept = signal('');
  status = signal('');
  hasEmail = signal(false);
  sort = signal<SortKey>('default');

  deptOptions = computed(() => [...new Set(this.all().map((p) => p.department_name).filter(Boolean) as string[])].sort());

  filtered = computed(() => {
    const needle = this.q().trim().toLowerCase();
    const list = this.all().filter((p) => {
      if (this.dept() && p.department_name !== this.dept()) return false;
      if (this.status() && p.verification_status !== this.status()) return false;
      if (this.hasEmail() && !p.email) return false;
      if (needle) {
        const hay = [p.name, p.name_chinese, p.email, p.department_name, p.position].filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
    const s = this.sort();
    if (s === 'name') return [...list].sort((a, b) => a.name.localeCompare(b.name));
    if (s === 'department') return [...list].sort((a, b) => (a.department_name ?? '').localeCompare(b.department_name ?? ''));
    return list; // server order: verified with email first
  });

  stats = computed(() => {
    const a = this.all();
    return {
      total: a.length,
      verified: a.filter((p) => p.verification_status === 'VERIFIED').length,
      withEmail: a.filter((p) => p.email).length,
    };
  });

  activeFilters = computed(() => [this.q(), this.dept(), this.status()].filter(Boolean).length + +this.hasEmail());

  ngOnInit(): void {
    if (this.department()) this.dept.set(this.department()!);
    this.api.professors(this.jobId()).subscribe({
      next: (p) => {
        this.all.set(p);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiError(e));
        this.loading.set(false);
      },
    });
  }

  reset(): void {
    this.q.set('');
    this.dept.set('');
    this.status.set('');
    this.hasEmail.set(false);
  }

  async copy(p: Professor): Promise<void> {
    if (p.email && (await copyText(p.email))) {
      this.copied.set(p.id);
      setTimeout(() => this.copied.set(null), 1500);
    }
  }

  async copyAllEmails(): Promise<void> {
    const emails = this.filtered().map((p) => p.email).filter(Boolean).join('; ');
    if (emails && (await copyText(emails))) {
      this.copiedAll.set(true);
      setTimeout(() => this.copiedAll.set(false), 1500);
    }
  }

  val(ev: Event): string {
    return (ev.target as HTMLInputElement).value;
  }
}
