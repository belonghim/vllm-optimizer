interface HistoryPoint {
  [key: string]: number | null | string | undefined;
}

export function buildGapFill(history: HistoryPoint[], keys: string[]): HistoryPoint[] {
  const hasNulls = keys.some(k => history.some(h => h[k] == null));
  if (!hasNulls) return history;

  const lastKnown: Record<string, number | null> = Object.fromEntries(keys.map(k => [k, null]));

  return history.map(point => {
    const fills: Record<string, number | null> = {};
    for (const k of keys) {
      if (point[k] != null) lastKnown[k] = point[k] as number;
      fills[`${k}_fill`] = lastKnown[k];
    }
    return { ...point, ...fills };
  });
}
