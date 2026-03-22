import { describe, it, expect } from 'vitest';
import { calcGpuEfficiency } from './metrics';

describe('calcGpuEfficiency', () => {
  it('valid case: calculates efficiency correctly', () => {
    const result = calcGpuEfficiency({
      gpu_utilization_avg: 50,
      tps: { mean: 100 }
    });
    expect(result).toEqual({
      value: 2,
      display: '2.0',
      mismatch: false
    });
  });

  it('null tps: returns null value with dash display', () => {
    const result = calcGpuEfficiency({
      gpu_utilization_avg: 50,
      tps: null
    });
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });

  it('null tps.mean: returns null value with dash display', () => {
    const result = calcGpuEfficiency({
      gpu_utilization_avg: 50,
      tps: { mean: null }
    });
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });

  it('undefined tps: returns null value with dash display', () => {
    const result = calcGpuEfficiency({
      gpu_utilization_avg: 50,
      tps: undefined
    });
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });

  it('missing gpu_utilization_avg: returns null value with dash display', () => {
    const result = calcGpuEfficiency({
      gpu_utilization_avg: undefined,
      tps: { mean: 100 }
    });
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });

  it('zero gpu_utilization_avg: returns null value with dash display', () => {
    const result = calcGpuEfficiency({
      gpu_utilization_avg: 0,
      tps: { mean: 100 }
    });
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });

  it('metrics_target_matched=false: returns N/A mismatch', () => {
    const result = calcGpuEfficiency({
      metrics_target_matched: false,
      gpu_utilization_avg: 50,
      tps: { mean: 100 }
    });
    expect(result).toEqual({
      value: null,
      display: 'N/A',
      mismatch: true
    });
  });

  it('null input: returns null value with dash display', () => {
    const result = calcGpuEfficiency(null);
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });

  it('undefined input: returns null value with dash display', () => {
    const result = calcGpuEfficiency(undefined);
    expect(result).toEqual({
      value: null,
      display: '—',
      mismatch: false
    });
  });
});
