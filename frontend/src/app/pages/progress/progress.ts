import { DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, of, switchMap, takeWhile, timer } from 'rxjs';

import { ApiService, apiError } from '../../core/api.service';
import { Job } from '../../core/models';
import { JobNav, StatusBadge } from '../../shared/ui';

@Component({
  selector: 'app-progress',
  imports: [RouterLink, JobNav, StatusBadge, DecimalPipe],
  templateUrl: './progress.html',
})
export class Progress implements OnInit {
  jobId = input.required<string>();
  private api = inject(ApiService);
  private destroyRef = inject(DestroyRef);

  job = signal<Job | null>(null);
  error = signal<string | null>(null);
  cancelling = signal(false);

  ngOnInit(): void {
    // Poll every 2s until the job reaches a terminal state (last value included).
    timer(0, 2000)
      .pipe(
        switchMap(() =>
          this.api.job(this.jobId()).pipe(
            catchError((e) => {
              this.error.set(apiError(e));
              return of(null);
            }),
          ),
        ),
        takeWhile((j) => j === null || j.status === 'queued' || j.status === 'running', true),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((j) => {
        if (j) {
          this.job.set(j);
          this.error.set(null);
        }
      });
  }

  cancel(): void {
    this.cancelling.set(true);
    this.api.cancel(this.jobId()).subscribe({
      next: (j) => this.job.set(j),
      error: (e) => this.error.set(apiError(e)),
    });
  }

  active(j: Job): boolean {
    return j.status === 'queued' || j.status === 'running';
  }

  elapsed(j: Job): number {
    if (!j.started_at) return 0;
    const end = j.completed_at ? new Date(j.completed_at).getTime() : Date.now();
    return Math.max(0, (end - new Date(j.started_at).getTime()) / 1000);
  }
}
