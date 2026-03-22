export const fmt = (n: number | null | undefined, d: number = 1): string =>
  n == null ? "—" : Number(n).toFixed(d);
