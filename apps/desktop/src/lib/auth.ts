const TOKEN_KEY = "personalops_auth_token";

export type AuthUser = {
  id: string;
  email: string;
  created_at: string;
};

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string | null): void {
  if (!token) {
    localStorage.removeItem(TOKEN_KEY);
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthSession(): void {
  localStorage.removeItem(TOKEN_KEY);
}
