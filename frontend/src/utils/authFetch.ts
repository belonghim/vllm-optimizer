let isRedirecting = false;

function handleAuthError(): never {
  if (isRedirecting) return undefined as never;
  isRedirecting = true;
  window.location.reload(); // OAuth Proxy redirects to login
  return undefined as never;
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 403) {
    handleAuthError();
  }
  return response;
}
