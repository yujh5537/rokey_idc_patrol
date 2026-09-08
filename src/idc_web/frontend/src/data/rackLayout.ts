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
const RACK_THICKNESS_MM = 85;
const R08_R49_LEFT_SHIFT_MM = RACK_THICKNESS_MM * 3;

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

    // Base transform supplied by the mechanical-team CSV for the 90deg-left
    // landscape view of the original portrait testbed.
    const baseScreenXFrac = (TESTBED_LENGTH_MM - yMm) / TESTBED_LENGTH_MM;
    const baseScreenYFrac = (TESTBED_WIDTH_MM - xMm) / TESTBED_WIDTH_MM;

    if (
      baseScreenXFrac < 0 || baseScreenXFrac > 1 ||
      baseScreenYFrac < 0 || baseScreenYFrac > 1
    ) {
      throw new Error(`Rack ${arucoId} transformed screen fractions must be within 0..1`);
    }

    // Verify that the supplied generalized CSV still matches the mechanical
    // coordinate transform before applying UI-only corrections.
    const tolerance = 0.002;
    if (
      Math.abs(baseScreenXFrac - csvXFrac) > tolerance ||
      Math.abs(baseScreenYFrac - csvYFrac) > tolerance
    ) {
      throw new Error(`Rack ${arucoId} generalized fractions do not match the 90deg-left map transform`);
    }

    // Requested display correction #1: keep left/right as-is and flip top/bottom.
    // MapView's real-PGM path uses xM for the vertical screen axis, so mirror xM
    // across the 3500mm testbed width as well. This produces the same Y flip there.
    const displayXMm = TESTBED_WIDTH_MM - xMm;
    const displayScreenYFrac = 1 - baseScreenYFrac;

    // Requested display correction #2: move R08 through R49 three rack-width
    // cells to the left. One cell is the rack thickness (85mm), so 3 cells = 255mm.
    // In the 90deg-left landscape transform, increasing the source y coordinate
    // moves the marker left. Keep both preview fractions and real-PGM yM aligned.
    const leftShiftMm = arucoId >= 8 && arucoId <= 49 ? R08_R49_LEFT_SHIFT_MM : 0;
    const displayYMm = yMm + leftShiftMm;
    const displayScreenXFrac = baseScreenXFrac - leftShiftMm / TESTBED_LENGTH_MM;

    if (displayScreenXFrac < 0 || displayScreenXFrac > 1) {
      throw new Error(`Rack ${arucoId} shifted screen X must be within 0..1`);
    }

    seen.add(arucoId);

    return {
      rackId: `R${String(arucoId).padStart(2, '0')}`,
      arucoId,
      xM: displayXMm / 1000,
      yM: displayYMm / 1000,
      yawRad: yawDeg * Math.PI / 180,
      screenXFrac: displayScreenXFrac,
      screenYFrac: displayScreenYFrac,
      // MapView applies the glyph +90deg compensation. Keep the CSV direction
      // untouched here so the final 85x210mm rack footprint stays vertical '|'.
      screenRotateDeg: normalizeDeg(csvRotateDeg),
    };
  });

  if (rows.length !== 56) {
    throw new Error(`Expected 56 racks, received ${rows.length}`);
  }

  return rows;
}

export const rackLayout = parseRackLayout(rackCsv);
