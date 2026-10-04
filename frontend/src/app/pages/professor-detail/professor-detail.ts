import { Component, OnInit, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService, apiError } from '../../core/api.service';
import { ProfessorDetail as Detail } from '../../core/models';
import { SourceList, StatusBadge, copyText } from '../../shared/ui';

const CHECK_LABELS: Record<string, string> = {
  name_found: 'Name found on profile page',
  university_association: 'Listed on the official university domain',
  profile_url_valid: 'Profile page loads',
  email_public: 'Email publicly listed on profile',
  email_institutional: 'Institutional email domain',
  romanized_name: 'English name romanised from Chinese (not stated on page)',
};

@Component({
  selector: 'app-professor-detail',
  imports: [RouterLink, StatusBadge, SourceList],
  templateUrl: './professor-detail.html',
})
export class ProfessorDetail implements OnInit {
  id = input.required<string>();
  private api = inject(ApiService);

  prof = signal<Detail | null>(null);
  error = signal<string | null>(null);
  copied = signal(false);
  labels = CHECK_LABELS;

  ngOnInit(): void {
    this.api.professor(+this.id()).subscribe({
      next: (p) => this.prof.set(p),
      error: (e) => this.error.set(apiError(e)),
    });
  }

  checks(p: Detail): { key: string; ok: boolean; label: string }[] {
    return Object.entries(p.verification_checks).map(([key, ok]) => ({ key, ok, label: CHECK_LABELS[key] ?? key }));
  }

  async copyEmail(email: string): Promise<void> {
    if (await copyText(email)) {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    }
  }
}
