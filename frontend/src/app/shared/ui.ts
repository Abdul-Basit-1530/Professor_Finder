import { Component, computed, input, signal } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Source } from '../core/models';

/** Colour-coded verification / availability badge. */
@Component({
  selector: 'app-status-badge',
  template: `<span class="status-badge" [class]="'status-badge ' + tone()" [title]="hint()">
    <i class="bi" [class]="'bi ' + icon()"></i>{{ label() }}</span>`,
})
export class StatusBadge {
  status = input.required<string | null | undefined>();
  label = computed(() => this.status() || 'NOT VERIFIED');
  tone = computed(() => {
    switch (this.status()) {
      case 'VERIFIED':
      case 'AVAILABLE':
      case 'VERIFIED EMAIL':
      case 'completed':
        return 'ok';
      case 'PARTIALLY VERIFIED':
      case 'running':
      case 'queued':
        return 'partial';
      case 'NOT AVAILABLE':
      case 'failed':
        return 'bad';
      default:
        return 'none';
    }
  });
  icon = computed(
    () => ({ ok: 'bi-patch-check-fill', partial: 'bi-patch-exclamation', bad: 'bi-x-octagon', none: 'bi-question-circle' })[this.tone()],
  );
  hint = computed(
    () =>
      ({
        VERIFIED: 'Confirmed on an official source',
        'PARTIALLY VERIFIED': 'Some evidence found; confirm before relying on it',
        'NOT VERIFIED': 'Could not be confirmed from the sources examined',
        'NOT FOUND': 'Not found on the pages examined — this does not mean unavailable',
        AVAILABLE: 'Explicitly stated by the source',
        'NOT AVAILABLE': 'An authoritative source explicitly says it is not available',
      })[this.status() ?? ''] ?? '',
  );
}

/** Compact list of source links with type + retrieval time. */
@Component({
  selector: 'app-source-list',
  template: `
    @if (sources().length) {
      <ul class="source-list">
        @for (s of visible(); track s.id) {
          <li>
            <a [href]="s.source_url" target="_blank" rel="noopener noreferrer">
              <i class="bi bi-box-arrow-up-right"></i>{{ s.title || s.source_url }}
            </a>
            <span class="source-meta">{{ s.source_type.replace('_', ' ') }}{{ s.supports ? ' · ' + s.supports.replaceAll('_', ' ') : '' }} · {{ s.retrieved_at.slice(0, 10) }}</span>
          </li>
        }
      </ul>
      @if (sources().length > limit && !expanded()) {
        <button class="btn btn-link btn-sm p-0" (click)="expanded.set(true)">Show all {{ sources().length }} sources</button>
      }
    } @else {
      <p class="text-muted small mb-0">No sources recorded.</p>
    }
  `,
})
export class SourceList {
  sources = input<Source[]>([]);
  limit = 4;
  expanded = signal(false);
  visible = computed(() => (this.expanded() ? this.sources() : this.sources().slice(0, this.limit)));
}

/** Tab navigation shared by all pages of one research job. */
@Component({
  selector: 'app-job-nav',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav class="job-nav" aria-label="Research sections">
      <a [routerLink]="['/research', jobId(), 'progress']" routerLinkActive="active"><i class="bi bi-activity"></i>Progress</a>
      <a [routerLink]="['/research', jobId(), 'overview']" routerLinkActive="active"><i class="bi bi-bank"></i>University</a>
      <a [routerLink]="['/research', jobId(), 'professors']" routerLinkActive="active"><i class="bi bi-people"></i>Professors</a>
      <a [routerLink]="['/research', jobId(), 'export']" routerLinkActive="active"><i class="bi bi-download"></i>Export</a>
    </nav>
  `,
})
export class JobNav {
  jobId = input.required<string>();
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
