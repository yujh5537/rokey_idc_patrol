import rackCsv from './rack_coords_generalized.csv?raw';

export interface RackLayoutRow {
  rackId: string;
  arucoId: number;
  xM: number;
  yM: number;
  yawRad: number;
  screenXFrac: number;
  screenYFrac: number;
  screenRotateDeg: number;
}

const TESTBED_LENGTH_MM = 5700;
const TESTBED_WIDTH_MM = 3500;

function toFiniteNumber(value: string, field: string, row: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Invalid ${field} at rack CSV row ${row}`);
  }
  return parsed;
}

function normalizeDeg(value: number) {
  return ((value % 360) + 360) % 360;
}

function parseRackLayout(csv: string): RackLayoutRow[] {
  const lines = csv.trim().split(/\r?\n/);
  const header = lines.shift()?.split(',') ?? [];
  const expected = [
    'rack_id',
    'x_mm',
    'y_mm',
    'yaw_deg',
    'pixel_x_frac',
    'pixel_y_frac',
    'screen_rotate_deg',
  ];

  if (header.length !== expected.length || header.some((value, index) => value !== expected[index])) {
    throw new Error('rack_coords_generalized.csv header does not match the renderer contract');
  }

  const seen = new Set<number>();
  const rows = lines.map((line, index) => {
    const cells = line.split(',');
    if (cells.length !== expected.length) {
      throw new Error(`Invalid rack CSV column count at row ${index + 2}`);
    }

    const arucoId = toFiniteNumber(cells[0], 'rack_id', index + 2);
    const xMm = toFiniteNumber(cells[1], 'x_mm', index + 2);
    const yMm = toFiniteNumber(cells[2], 'y_mm', index + 2);
    const yawDeg = toFiniteNumber(cells[3], 'yaw_deg', index + 2);
    const csvXFrac = toFiniteNumber(cells[4], 'pixel_x_frac', index + 2);
    const csvYFrac = toFiniteNumber(cells[5], 'pixel_y_frac', index + 2);
    const csvRotateDeg = toFiniteNumber(cells[6], 'screen_rotate_deg', index + 2);

    if (!Number.isInteger(arucoId) || arucoId < 1 || arucoId > 56 || seen.has(arucoId)) {
      throw new Error(`Invalid or duplicate rack_id ${cells[0]}`);
    }

    // Original map/testbed coordinates are portrait (3500 x 5700). The React
    // control screen rotates that map 90 degrees to the left (CCW), therefore:
    //   landscape X = 1 - y / 5700
    //   landscape Y = 1 - x / 3500
    // These are the same values stored in the generalized CSV, but deriving
    // them here makes the map/rack transform explicit and prevents accidental
    // axis swapping when the portrait PGM is rendered landscape.
    const screenXFrac = (TESTBED_LENGTH_MM - yMm) / TESTBED_LENGTH_MM;
    const screenYFrac = (TESTBED_WIDTH_MM - xMm) / TESTBED_WIDTH_MM;

    if (
      screenXFrac < 0 || screenXFrac > 1 ||
      screenYFrac < 0 || screenYFrac > 1
    ) {
      throw new Error(`Rack ${arucoId} transformed screen fractions must be within 0..1`);
    }

    // The provided fractions are rounded values of the same transform. Keep a
    // small validation guard so a future CSV with a different convention is
    // caught immediately instead of silently drawing racks in the wrong place.
    const tolerance = 0.002;
    if (
      Math.abs(screenXFrac - csvXFrac) > tolerance ||
      Math.abs(screenYFrac - csvYFrac) > tolerance
    ) {
      throw new Error(`Rack ${arucoId} generalized fractions do not match the 90deg-left map transform`);
    }

    seen.add(arucoId);

    return {
      rackId: `R${String(arucoId).padStart(2, '0')}`,
      arucoId,
      xM: xMm / 1000,
      yM: yMm / 1000,
      yawRad: yawDeg * Math.PI / 180,
      screenXFrac,
      screenYFrac,
      // The CSV rotation assumes an icon whose base direction is +X. Our rack
      // glyph is drawn as a vertical 85x210 rectangle, so add 90 degrees of
      // glyph-orientation compensation. 270->0 and 90->180 keeps the rack body
      // vertical (|) while preserving which side/front direction it represents.
      screenRotateDeg: normalizeDeg(csvRotateDeg + 90),
    };
  });

  if (rows.length !== 56) {
    throw new Error(`Expected 56 racks, received ${rows.length}`);
  }

  return rows;
}

export const rackLayout = parseRackLayout(rackCsv);
