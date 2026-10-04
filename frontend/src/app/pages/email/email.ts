import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService, apiError } from '../../core/api.service';
import { EmailDraft, EmailRequest, ProfessorDetail } from '../../core/models';
import { StatusBadge, copyText } from '../../shared/ui';

const PROFILE_KEY = 'research-agent.student-profile';

@Component({
  selector: 'app-email',
  imports: [RouterLink, StatusBadge],
  templateUrl: './email.html',
})
export class EmailGenerator implements OnInit {
  id = input.required<string>();
  private api = inject(ApiService);

  prof = signal<ProfessorDetail | null>(null);
  form = signal<EmailRequest>({
    student_name: '',
    student_background: '',
    target_degree: "Master's",
    research_interest: '',
    scholarship: 'Chinese Government Scholarship (CSC)',
    extra_notes: '',
    tone: 'formal',
  });
  draft = signal<EmailDraft | null>(null);
  subject = signal('');
  body = signal('');
  generating = signal(false);
  error = signal<string | null>(null);
  copied = signal(false);
  reviewed = signal(false);

  valid = computed(() => {
    const f = this.form();
    return f.student_name.trim().length > 0 && f.student_background.trim().length >= 10 && f.research_interest.trim().length >= 2;
  });
  mailto = computed(() => {
    const p = this.prof();
    if (!p?.email) return null;
    return `mailto:${p.email}?subject=${encodeURIComponent(this.subject())}&body=${encodeURIComponent(this.body())}`;
  });

  ngOnInit(): void {
    try {
      const saved = localStorage.getItem(PROFILE_KEY);
      if (saved) this.form.set({ ...this.form(), ...JSON.parse(saved) });
    } catch {
      /* ignore */
    }
    this.api.professor(+this.id()).subscribe({
      next: (p) => {
        this.prof.set(p);
      },
      error: (e) => this.error.set(apiError(e)),
    });
  }

  patch<K extends keyof EmailRequest>(key: K, value: EmailRequest[K]): void {
    this.form.set({ ...this.form(), [key]: value });
  }

  generate(): void {
    if (!this.valid()) return;
    this.generating.set(true);
    this.error.set(null);
    this.reviewed.set(false);
    const f = this.form();
    try {
      const { student_name, student_background, target_degree } = f;
      localStorage.setItem(PROFILE_KEY, JSON.stringify({ student_name, student_background, target_degree }));
    } catch {
      /* ignore */
    }
    this.api.generateEmail(+this.id(), f).subscribe({
      next: (d) => {
        this.draft.set(d);
        this.subject.set(d.subject);
        this.body.set(d.body);
        this.generating.set(false);
      },
      error: (e) => {
        this.error.set(apiError(e));
        this.generating.set(false);
      },
    });
  }

  async copy(): Promise<void> {
    if (await copyText(`Subject: ${this.subject()}\n\n${this.body()}`)) {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    }
  }

  val(ev: Event): string {
    return (ev.target as HTMLInputElement).value;
  }
}
