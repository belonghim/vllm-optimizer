let isRedirecting = false;

function handleAuthError(): never {
  if (isRedirecting) return undefined as never;
  isRedirecting = true;
  window.location.href = '/oauth/sign_out';
  return undefined as never;
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 403) {
    handleAuthError();
  }
  return response;
}
