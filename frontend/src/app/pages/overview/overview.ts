import { Component, OnInit, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiService, apiError } from '../../core/api.service';
import { Department, Job, University } from '../../core/models';
import { JobNav, SourceList, StatusBadge } from '../../shared/ui';

@Component({
  selector: 'app-overview',
  imports: [RouterLink, JobNav, SourceList, StatusBadge],
  templateUrl: './overview.html',
})
export class Overview implements OnInit {
  jobId = input.required<string>();
  private api = inject(ApiService);

  job = signal<Job | null>(null);
  uni = signal<University | null>(null);
  departments = signal<Department[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);

  ngOnInit(): void {
    const id = this.jobId();
    forkJoin({
      job: this.api.job(id),
      uni: this.api.university(id),
      departments: this.api.departments(id),
    }).subscribe({
      next: (r) => {
        this.job.set(r.job);
        this.uni.set(r.uni);
        this.departments.set(r.departments);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(apiError(e));
        this.loading.set(false);
      },
    });
  }

  stat(key: string): number {
    return Number(this.job()?.stats?.[key] ?? 0);
  }
}
