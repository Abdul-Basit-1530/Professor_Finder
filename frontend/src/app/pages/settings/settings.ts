import { Component, signal } from '@angular/core';

import { readToken, writeToken } from '../../core/token.interceptor';

@Component({
  selector: 'app-settings',
  template: `
    <div class="container-narrow">
      <div class="page-head"><h1>Settings</h1></div>
      <form class="card" (submit)="$event.preventDefault(); save()">
        <div class="card-body">
          <label class="form-label fw-semibold" for="tok">Access token</label>
          <input id="tok" class="form-control" type="password" autocomplete="off" [value]="token()" (input)="token.set(val($event))" />
          <div class="form-text">
            Only needed if the server operator set <code>APP_ACCESS_TOKEN</code>. It is stored in this browser only and
            sent as the <code>X-Access-Token</code> header. API keys (OpenAI, search) are never stored in the browser.
          </div>
        </div>
        <div class="card-footer d-flex gap-2 justify-content-end align-items-center">
          @if (saved()) {
            <span class="text-success small me-auto"><i class="bi bi-check2"></i> Saved</span>
          }
          <button type="button" class="btn btn-outline-secondary" (click)="token.set(''); save()">Clear</button>
          <button type="submit" class="btn btn-primary">Save</button>
        </div>
      </form>
    </div>
  `,
})
export class Settings {
  token = signal(readToken());
  saved = signal(false);

  save(): void {
    writeToken(this.token().trim());
    this.saved.set(true);
    setTimeout(() => this.saved.set(false), 2000);
  }

  val(ev: Event): string {
    return (ev.target as HTMLInputElement).value;
  }
}
