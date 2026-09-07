export interface MapMeta {
  resolution: number;
  origin: [number, number, number];
  negate?: number;
  occupiedThresh?: number;
  freeThresh?: number;
}

export function worldToPercent(
  x: number,
  y: number,
  meta: MapMeta,
  width: number,
  height: number,
) {
  const px = (x - meta.origin[0]) / meta.resolution;
  const pyFromBottom = (y - meta.origin[1]) / meta.resolution;
  const py = height - pyFromBottom;

  return {
    left: `${Math.max(0, Math.min(100, (px / width) * 100))}%`,
    top: `${Math.max(0, Math.min(100, (py / height) * 100))}%`,
  };
}
