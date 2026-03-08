import { describe, it, expect } from 'vitest';
import { buildGapFill } from './gapFill';

describe('buildGapFill', () => {
  it('all-null: fill fields remain null (no prior value)', () => {
    const result = buildGapFill([{ ttft: null }, { ttft: null }], ['ttft']);
    expect(result[0].ttft_fill).toBeNull();
    expect(result[1].ttft_fill).toBeNull();
  });

  it('leading-null: null until first real value, then carry forward', () => {
    const result = buildGapFill([{ ttft: null }, { ttft: 80 }, { ttft: null }], ['ttft']);
    expect(result[0].ttft_fill).toBeNull();
    expect(result[1].ttft_fill).toBe(80);
    expect(result[2].ttft_fill).toBe(80);
  });

  it('trailing-null: carry-forward last value', () => {
    const result = buildGapFill([{ ttft: 80 }, { ttft: null }], ['ttft']);
    expect(result[0].ttft_fill).toBe(80);
    expect(result[1].ttft_fill).toBe(80);
  });

  it('mixed gaps filled correctly', () => {
    const result = buildGapFill([{ ttft: 80 }, { ttft: null }, { ttft: null }, { ttft: 95 }], ['ttft']);
    expect(result[1].ttft_fill).toBe(80);
    expect(result[2].ttft_fill).toBe(80);
    expect(result[3].ttft_fill).toBe(95);
  });

  it('no-null: _fill fields NOT added (returns same reference)', () => {
    const input = [{ ttft: 80 }, { ttft: 90 }];
    const result = buildGapFill(input, ['ttft']);
    expect(result).toBe(input);
    expect(result[0].ttft_fill).toBeUndefined();
  });

  it('does not mutate input objects', () => {
    const input = [{ ttft: 80 }, { ttft: null }];
    const orig0 = input[0];
    buildGapFill(input, ['ttft']);
    expect(input[0]).toBe(orig0);
    expect('ttft_fill' in input[0]).toBe(false);
  });

  it('handles multiple keys independently', () => {
    const result = buildGapFill(
      [{ ttft: 80, lat_p99: 500 }, { ttft: null, lat_p99: null }],
      ['ttft', 'lat_p99']
    );
    expect(result[1].ttft_fill).toBe(80);
    expect(result[1].lat_p99_fill).toBe(500);
  });
});
