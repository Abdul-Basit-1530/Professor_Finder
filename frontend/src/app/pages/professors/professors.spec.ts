import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { Professor } from '../../core/models';
import { Professors } from './professors';

function prof(p: Partial<Professor>): Professor {
  return {
    id: 1, job_id: 'j', name: 'X', name_chinese: null, name_is_romanized: false, position: null, position_original: null,
    department_id: null, department_name: 'CS', school: null, email: null, email_verified: false,
    email_status: 'EMAIL NOT FOUND', profile_url: null, verification_status: 'NOT VERIFIED', ...p,
  };
}

// Server order: verified-with-email first.
const DATA: Professor[] = [
  prof({ id: 1, name: 'Wei Zhang', name_chinese: '张伟', email: 'zw@x.edu.cn', profile_url: 'https://cs.x.edu.cn/zw.htm',
         verification_status: 'VERIFIED' }),
  prof({ id: 2, name: 'Li Na', name_chinese: '李娜', department_name: 'AI', profile_url: 'https://ai.x.edu.cn/ln.htm',
         verification_status: 'PARTIALLY VERIFIED' }),
  prof({ id: 3, name: 'Aaron Smith', email: 'as@x.edu.cn' }),
];

describe('Professors page', () => {
  let component: Professors;
  let element: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const fixture = TestBed.createComponent(Professors);
    fixture.componentRef.setInput('jobId', 'j');
    component = fixture.componentInstance;
    fixture.detectChanges();
    TestBed.inject(HttpTestingController).expectOne('/api/research/j/professors').flush(DATA);
    fixture.detectChanges();
    element = fixture.nativeElement;
  });

  it('keeps the server order by default (verified with email first)', () => {
    expect(component.filtered().map((p) => p.id)).toEqual([1, 2, 3]);
  });

  it('shows email and profile link on each card, and "Not publicly listed" otherwise', () => {
    const cards = element.querySelectorAll('.prof-card');
    expect(cards.length).toBe(3);
    expect(cards[0].textContent).toContain('zw@x.edu.cn');
    expect(cards[0].querySelector('.profile-row a')?.getAttribute('href')).toBe('https://cs.x.edu.cn/zw.htm');
    expect(cards[1].textContent).toContain('Not publicly listed');
  });

  it('searches names (English / Chinese) and emails', () => {
    component.q.set('李娜');
    expect(component.filtered().map((p) => p.id)).toEqual([2]);
    component.q.set('as@x');
    expect(component.filtered().map((p) => p.id)).toEqual([3]);
  });

  it('combines department, status and email filters', () => {
    component.hasEmail.set(true);
    expect(component.filtered().map((p) => p.id)).toEqual([1, 3]);
    component.reset();
    component.dept.set('AI');
    expect(component.filtered().map((p) => p.id)).toEqual([2]);
    component.reset();
    component.status.set('VERIFIED');
    expect(component.filtered().map((p) => p.id)).toEqual([1]);
  });

  it('sorts by name and reports stats', () => {
    component.sort.set('name');
    expect(component.filtered().map((p) => p.name)).toEqual(['Aaron Smith', 'Li Na', 'Wei Zhang']);
    expect(component.stats()).toEqual({ total: 3, verified: 1, withEmail: 2 });
    expect(component.deptOptions()).toEqual(['AI', 'CS']);
  });
});
