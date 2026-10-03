/**
 * Number inputs report an empty string when cleared; coercing it with +value
 * would silently turn the field into 0, so keep the previous value instead.
 */
export function parseNumberInput(value: string, previous: number): number {
  if (value === '') return previous;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? previous : parsed;
}
