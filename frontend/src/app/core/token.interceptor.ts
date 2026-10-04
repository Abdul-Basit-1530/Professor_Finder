import { HttpInterceptorFn } from '@angular/common/http';

export const TOKEN_KEY = 'research-agent.access-token';

export function readToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

export function writeToken(value: string): void {
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode) — token simply isn't remembered */
  }
}

/** Adds the optional shared access token the user entered under Settings. */
export const tokenInterceptor: HttpInterceptorFn = (req, next) => {
  const token = readToken();
  return next(token && req.url.startsWith('/api') ? req.clone({ setHeaders: { 'X-Access-Token': token } }) : req);
};
