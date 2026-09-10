export const TESTBED_RENDER_SPEC = {
  lengthMm: 5600,
  widthMm: 3500,
  aspectRatio: 5600 / 3500,
  amrDiameterMm: 340,
  rackWidthMm: 85,
  rackHeightMm: 210,
  amrDiameterFrac: 340 / 5600,
  rackWidthFrac: 85 / 5600,
  rackHeightFrac: 210 / 5600,
} as const;

export const DEMO_MAP_SIZE = {
  width: 560,
  height: 350,
} as const;
