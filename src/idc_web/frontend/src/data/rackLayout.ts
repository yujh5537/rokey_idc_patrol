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

function toFiniteNumber(value: string, field: string, row: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Invalid ${field} at rack CSV row ${row}`);
  }
  return parsed;
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
    const screenXFrac = toFiniteNumber(cells[4], 'pixel_x_frac', index + 2);
    const screenYFrac = toFiniteNumber(cells[5], 'pixel_y_frac', index + 2);
    const screenRotateDeg = toFiniteNumber(cells[6], 'screen_rotate_deg', index + 2);

    if (!Number.isInteger(arucoId) || arucoId < 1 || arucoId > 56 || seen.has(arucoId)) {
      throw new Error(`Invalid or duplicate rack_id ${cells[0]}`);
    }
    if (screenXFrac < 0 || screenXFrac > 1 || screenYFrac < 0 || screenYFrac > 1) {
      throw new Error(`Rack ${arucoId} screen fractions must be within 0..1`);
    }

    seen.add(arucoId);

    return {
      rackId: `R${String(arucoId).padStart(2, '0')}`,
      arucoId,
      xM: xMm / 1000,
      yM: yMm / 1000,
      yawRad: yawDeg * Math.PI / 180,
      // The generalized CSV is already expressed for the landscape
      // 5700 x 3500 control-screen canvas. Do not swap these axes again.
      screenXFrac,
      screenYFrac,
      screenRotateDeg,
    };
  });

  if (rows.length !== 56) {
    throw new Error(`Expected 56 racks, received ${rows.length}`);
  }

  return rows;
}

export const rackLayout = parseRackLayout(rackCsv);
