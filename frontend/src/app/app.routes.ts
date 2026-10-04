import { Routes } from '@angular/router';

import { Home } from './pages/home/home';

export const routes: Routes = [
  { path: '', component: Home, title: 'Professor Finder' },
  {
    path: 'research/:jobId',
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'progress' },
      { path: 'progress', loadComponent: () => import('./pages/progress/progress').then((m) => m.Progress), title: 'Research progress' },
      { path: 'overview', loadComponent: () => import('./pages/overview/overview').then((m) => m.Overview), title: 'University overview' },
      { path: 'professors', loadComponent: () => import('./pages/professors/professors').then((m) => m.Professors), title: 'Professors' },
      { path: 'export', loadComponent: () => import('./pages/export/export').then((m) => m.Export), title: 'Export' },
    ],
  },
  {
    path: 'professors/:id',
    loadComponent: () => import('./pages/professor-detail/professor-detail').then((m) => m.ProfessorDetail),
    title: 'Professor',
  },
  {
    path: 'professors/:id/email',
    loadComponent: () => import('./pages/email/email').then((m) => m.EmailGenerator),
    title: 'Email generator',
  },
  { path: 'settings', loadComponent: () => import('./pages/settings/settings').then((m) => m.Settings), title: 'Settings' },
  { path: '**', redirectTo: '' },
];
