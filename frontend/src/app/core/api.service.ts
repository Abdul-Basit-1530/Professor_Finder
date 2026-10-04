import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  Department,
  EmailDraft,
  EmailRequest,
  Job,
  Professor,
  ProfessorDetail,
  PublicConfig,
  ResearchStartRequest,
  University,
} from './models';

/**
 * All calls go to a relative `/api` path. In development `proxy.conf.json` forwards
 * them to FastAPI; in production the Vercel rewrite / nginx proxy does. No backend
 * URL or secret is ever compiled into the bundle.
 */
const API = '/api';

export interface ProfessorQuery {
  department?: string;
  verification?: string;
  has_email?: boolean;
  q?: string;
  sort?: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  config(): Observable<PublicConfig> {
    return this.http.get<PublicConfig>(`${API}/meta/config`);
  }

  startResearch(body: ResearchStartRequest): Observable<{ job_id: string; status: string }> {
    return this.http.post<{ job_id: string; status: string }>(`${API}/research/start`, body);
  }

  jobs(limit = 10): Observable<Job[]> {
    return this.http.get<Job[]>(`${API}/research`, { params: { limit } });
  }

  job(id: string): Observable<Job> {
    return this.http.get<Job>(`${API}/research/${id}`);
  }

  cancel(id: string): Observable<Job> {
    return this.http.post<Job>(`${API}/research/${id}/cancel`, {});
  }

  university(id: string): Observable<University | null> {
    return this.http.get<University | null>(`${API}/research/${id}/university`);
  }

  departments(id: string): Observable<Department[]> {
    return this.http.get<Department[]>(`${API}/research/${id}/departments`);
  }

  professors(id: string, query: ProfessorQuery = {}): Observable<Professor[]> {
    let params = new HttpParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v));
    }
    return this.http.get<Professor[]>(`${API}/research/${id}/professors`, { params });
  }

  professor(id: number): Observable<ProfessorDetail> {
    return this.http.get<ProfessorDetail>(`${API}/professors/${id}`);
  }

  generateEmail(id: number, body: EmailRequest): Observable<EmailDraft> {
    return this.http.post<EmailDraft>(`${API}/professors/${id}/generate-email`, body);
  }

  emailDrafts(id: number): Observable<EmailDraft[]> {
    return this.http.get<EmailDraft[]>(`${API}/professors/${id}/email-drafts`);
  }

  /** Downloads via HttpClient (so the access-token header is sent) and returns blob + filename. */
  export(id: string, fmt: 'csv' | 'excel' | 'pdf'): Observable<{ blob: Blob; filename: string }> {
    return this.http
      .get(`${API}/research/${id}/export/${fmt}`, { responseType: 'blob', observe: 'response' })
      .pipe(
        map((res: HttpResponse<Blob>) => {
          const cd = res.headers.get('content-disposition') ?? '';
          const match = /filename="?([^"]+)"?/.exec(cd);
          const ext = fmt === 'excel' ? 'xlsx' : fmt;
          return { blob: res.body as Blob, filename: match?.[1] ?? `research-${id}.${ext}` };
        }),
      );
  }
}

export function apiError(err: unknown): string {
  const e = err as { status?: number; error?: { detail?: unknown } };
  if (e?.status === 0) return 'Cannot reach the research server. Is the backend running?';
  const detail = e?.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    return (first.msg ?? 'Invalid input').replace(/^Value error, /, '');
  }
  if (e?.status === 401) return 'An access token is required. Set it under Settings.';
  return 'Something went wrong. Please try again.';
}
