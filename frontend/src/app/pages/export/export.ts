import { Component, OnInit, inject, input, signal } from '@angular/core';

import { ApiService, apiError } from '../../core/api.service';
import { Job } from '../../core/models';
import { JobNav, saveBlob } from '../../shared/ui';

type Fmt = 'csv' | 'excel' | 'pdf';

@Component({
  selector: 'app-export',
  imports: [JobNav],
  template: `
    <div class="container-wide">
      <app-job-nav [jobId]="jobId()" />
      <div class="page-head">
        <div>
          <h1>Export results</h1>
          <p class="text-muted mb-0">{{ job()?.university_name || job()?.university_url }}</p>
        </div>
      </div>
      @if (job() && job()!.status !== 'completed') {
        <div class="alert alert-info small">The research job is {{ job()!.status }}; exports will contain the results so far.</div>
      }
      @if (error()) {
        <div class="alert alert-danger">{{ error() }}</div>
      }
      <div class="export-grid">
        @for (f of formats; track f.fmt) {
          <div class="card export-card">
            <div class="card-body">
              <i class="bi" [class]="'bi ' + f.icon"></i>
              <h2 class="h5">{{ f.title }}</h2>
              <p class="small text-muted">{{ f.desc }}</p>
            </div>
            <div class="card-footer">
              <button class="btn btn-primary w-100" (click)="download(f.fmt)" [disabled]="busy() === f.fmt">
                @if (busy() === f.fmt) {
                  <span class="spinner-border spinner-border-sm me-2"></span>Preparing…
                } @else {
                  <i class="bi bi-download me-1"></i>Download {{ f.label }}
                }
              </button>
            </div>
          </div>
        }
      </div>
      <p class="small text-muted mt-3">
        Exports include verification statuses and source URLs. "Not publicly listed" means no email was found on
        the professor's official page.
      </p>
    </div>
  `,
})
export class Export implements OnInit {
  jobId = input.required<string>();
  private api = inject(ApiService);
  job = signal<Job | null>(null);
  busy = signal<Fmt | null>(null);
  error = signal<string | null>(null);

  formats: { fmt: Fmt; label: string; title: string; icon: string; desc: string }[] = [
    { fmt: 'csv', label: 'CSV', title: 'Professors (CSV)', icon: 'bi-filetype-csv',
      desc: 'One row per professor: name, position, department, email, profile URL and source URL.' },
    { fmt: 'excel', label: 'Excel', title: 'Full workbook (Excel)', icon: 'bi-file-earmark-spreadsheet',
      desc: 'Sheets for Professors, University, Departments and Sources.' },
    { fmt: 'pdf', label: 'PDF', title: 'Contact list (PDF)', icon: 'bi-file-earmark-pdf',
      desc: 'A printable table of every professor with email and profile link.' },
  ];

  ngOnInit(): void {
    this.api.job(this.jobId()).subscribe({ next: (j) => this.job.set(j), error: (e) => this.error.set(apiError(e)) });
  }

  download(fmt: Fmt): void {
    this.busy.set(fmt);
    this.error.set(null);
    this.api.export(this.jobId(), fmt).subscribe({
      next: ({ blob, filename }) => {
        saveBlob(blob, filename);
        this.busy.set(null);
      },
      error: (e) => {
        this.error.set(apiError(e));
        this.busy.set(null);
      },
    });
  }
}
