import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { apiError } from '../core/api.service';
import { StatusBadge } from './ui';

function render(status: string | null) {
  const fixture = TestBed.createComponent(StatusBadge);
  fixture.componentRef.setInput('status', status);
  fixture.detectChanges();
  return fixture.nativeElement.querySelector('.status-badge') as HTMLElement;
}

describe('StatusBadge', () => {
  it('colours verified / partial / negative / unknown states distinctly', () => {
    expect(render('VERIFIED').className).toContain('ok');
    expect(render('AVAILABLE').className).toContain('ok');
    expect(render('PARTIALLY VERIFIED').className).toContain('partial');
    expect(render('NOT AVAILABLE').className).toContain('bad');
    expect(render('NOT FOUND').className).toContain('none');
  });

  it('never shows an empty badge', () => {
    expect(render(null).textContent?.trim()).toBe('NOT VERIFIED');
  });

  it('explains that NOT FOUND is not the same as unavailable', () => {
    expect(render('NOT FOUND').title).toContain('does not mean unavailable');
  });
});

describe('apiError', () => {
  it('maps network, validation and auth errors to readable messages', () => {
    expect(apiError({ status: 0 })).toContain('Cannot reach');
    expect(apiError({ status: 422, error: { detail: [{ msg: 'Value error, Only http(s) URLs are supported.' }] } })).toBe(
      'Only http(s) URLs are supported.',
    );
    expect(apiError({ status: 404, error: { detail: 'Research job not found.' } })).toBe('Research job not found.');
    expect(apiError({ status: 401, error: {} })).toContain('access token');
  });
});
