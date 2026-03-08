export function buildGapFill(history, keys) {
  const hasNulls = keys.some(k => history.some(h => h[k] == null));
  if (!hasNulls) return history;

  const lastKnown = Object.fromEntries(keys.map(k => [k, null]));

  return history.map(point => {
    const fills = {};
    for (const k of keys) {
      if (point[k] != null) lastKnown[k] = point[k];
      fills[`${k}_fill`] = lastKnown[k];
    }
    return { ...point, ...fills };
  });
}
