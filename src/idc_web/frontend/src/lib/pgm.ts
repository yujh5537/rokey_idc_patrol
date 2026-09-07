import yaml from 'js-yaml';
import type { MapMeta } from './coordinates';

export interface PgmImage {
  width: number;
  height: number;
  pixels: Uint8Array;
  maxValue: number;
}

function isWhitespace(byte: number) {
  return byte === 9 || byte === 10 || byte === 11 || byte === 12 || byte === 13 || byte === 32;
}

function readToken(bytes: Uint8Array, cursor: { value: number }): string {
  while (cursor.value < bytes.length) {
    if (bytes[cursor.value] === 35) {
      while (cursor.value < bytes.length && bytes[cursor.value] !== 10 && bytes[cursor.value] !== 13) cursor.value += 1;
    } else if (isWhitespace(bytes[cursor.value])) {
      cursor.value += 1;
    } else {
      break;
    }
  }

  const start = cursor.value;
  while (cursor.value < bytes.length && !isWhitespace(bytes[cursor.value]) && bytes[cursor.value] !== 35) cursor.value += 1;
  return new TextDecoder('ascii').decode(bytes.slice(start, cursor.value));
}

export function parsePgm(buffer: ArrayBuffer): PgmImage {
  const bytes = new Uint8Array(buffer);
  const cursor = { value: 0 };
  const magic = readToken(bytes, cursor);
  const width = Number(readToken(bytes, cursor));
  const height = Number(readToken(bytes, cursor));
  const maxValue = Number(readToken(bytes, cursor));

  if (!['P2', 'P5'].includes(magic) || !Number.isFinite(width) || !Number.isFinite(height) || !Number.isFinite(maxValue)) {
    throw new Error('Unsupported or invalid PGM map.');
  }
  if (width <= 0 || height <= 0 || maxValue <= 0 || maxValue > 255) {
    throw new Error('Only 8-bit PGM maps are supported.');
  }

  if (magic === 'P2') {
    const pixels = new Uint8Array(width * height);
    for (let i = 0; i < pixels.length; i += 1) {
      const value = Number(readToken(bytes, cursor));
      if (!Number.isFinite(value)) throw new Error('PGM pixel data is incomplete.');
      pixels[i] = Math.round((value / maxValue) * 255);
    }
    return { width, height, pixels, maxValue: 255 };
  }

  if (bytes[cursor.value] === 13 && bytes[cursor.value + 1] === 10) {
    cursor.value += 2;
  } else if (isWhitespace(bytes[cursor.value])) {
    cursor.value += 1;
  } else {
    throw new Error('Invalid PGM header delimiter.');
  }

  const raw = bytes.slice(cursor.value, cursor.value + width * height);
  if (raw.length !== width * height) throw new Error('PGM pixel data is incomplete.');
  return { width, height, pixels: raw, maxValue };
}

export function parseMapYaml(text: string): Partial<MapMeta> {
  const parsed = yaml.load(text);
  if (!parsed || typeof parsed !== 'object') throw new Error('Invalid map YAML.');

  const data = parsed as Record<string, unknown>;
  const result: Partial<MapMeta> = {};

  if (data.resolution !== undefined) {
    const resolution = Number(data.resolution);
    if (!Number.isFinite(resolution) || resolution <= 0) throw new Error('YAML resolution must be a positive number.');
    result.resolution = resolution;
  }

  if (data.origin !== undefined) {
    if (!Array.isArray(data.origin) || data.origin.length < 2) throw new Error('YAML origin must be [x, y, yaw].');
    const origin: [number, number, number] = [
      Number(data.origin[0]),
      Number(data.origin[1]),
      Number(data.origin[2] ?? 0),
    ];
    if (origin.some((value) => !Number.isFinite(value))) throw new Error('YAML origin contains an invalid number.');
    result.origin = origin;
  }

  if (data.negate !== undefined) result.negate = Number(data.negate);
  if (data.occupied_thresh !== undefined) result.occupiedThresh = Number(data.occupied_thresh);
  if (data.free_thresh !== undefined) result.freeThresh = Number(data.free_thresh);

  return result;
}

export async function loadSlamMap(base = '/maps/map') {
  const [pgmResponse, yamlResponse] = await Promise.all([
    fetch(`${base}.pgm`),
    fetch(`${base}.yaml`),
  ]);
  if (!pgmResponse.ok || !yamlResponse.ok) throw new Error('SLAM map files are not available yet.');

  const image = parsePgm(await pgmResponse.arrayBuffer());
  const parsedMeta = parseMapYaml(await yamlResponse.text());
  const meta: MapMeta = {
    resolution: parsedMeta.resolution ?? 0.05,
    origin: parsedMeta.origin ?? [-4, -4, 0],
    negate: parsedMeta.negate ?? 0,
    occupiedThresh: parsedMeta.occupiedThresh ?? 0.65,
    freeThresh: parsedMeta.freeThresh ?? 0.196,
  };

  return { image, meta };
}
