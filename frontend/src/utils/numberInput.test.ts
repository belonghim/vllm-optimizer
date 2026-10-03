import { describe, expect, it } from 'vitest';
import { parseNumberInput } from './numberInput';

describe('parseNumberInput', () => {
  it('parses numeric strings', () => {
    expect(parseNumberInput('42', 1)).toBe(42);
    expect(parseNumberInput('0.5', 1)).toBe(0.5);
    expect(parseNumberInput('0', 7)).toBe(0);
  });

  it('keeps the previous value for empty input instead of coercing to 0', () => {
    expect(parseNumberInput('', 7)).toBe(7);
  });

  it('keeps the previous value for non-numeric input', () => {
    expect(parseNumberInput('abc', 7)).toBe(7);
  });
});
