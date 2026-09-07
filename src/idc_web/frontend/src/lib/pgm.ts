import yaml from 'js-yaml';
import type { MapMeta } from './coordinates';

export interface PgmImage {
  width: number;
  height: number;
  pixels: Uint8Array;
  maxValue: number;
}

function isWhitespace(byte: number) {
  return byte === 9 || byte === 10 || byte === 13 || byte === 32;
}

function readToken(bytes: Uint8Array, cursor: { value: number }): string {
  while (cursor.value < bytes.length) {
    if (bytes[cursor.value] === 35) {
      while (cursor.value < bytes.length && bytes[cursor.value] !== 10) cursor.value += 1;
    } else if (isWhitespace(bytes[cursor.value])) {
      cursor.value += 1;
    } else break;
  }
  const start = cursor.value;
  while (cursor.value < bytes.length && !isWhitespace(bytes[cursor.value])) cursor.value += 1;
  return new TextDecoder().decode(bytes.slice(start, cursor.value));
}

export function parsePgm(buffer: ArrayBuffer): PgmImage {
  const bytes = new Uint8Array(buffer);
  const cursor = { value: 0 };
  const magic = readToken(bytes, cursor);
  const width = Number(readToken(bytes, cursor));
  const height = Number(readToken(bytes, cursor));
  const maxValue = Number(readToken(bytes, cursor));

  if (!['P2', 'P5'].includes(magic) || !width || !height || !maxValue) {
    throw new Error('Unsupported or invalid PGM map');
  }

  if (magic === 'P2') {
    const pixels = new Uint8Array(width * height);
    for (let i = 0; i < pixels.length; i += 1) {
      pixels[i] = Math.round((Number(readToken(bytes, cursor)) / maxValue) * 255);
    }
    return { width, height, pixels, maxValue };
  }

  while (cursor.value < bytes.length && isWhitespace(bytes[cursor.value])) cursor.value += 1;
  const raw = bytes.slice(cursor.value, cursor.value + width * height);
  if (raw.length !== width * height) throw new Error('PGM pixel payload is incomplete');
  return { width, height, pixels: raw, maxValue };
}

export async function loadSlamMap(base = '/maps/map') {
  const [pgmResponse, yamlResponse] = await Promise.all([
    fetch(`${base}.pgm`),
    fetch(`${base}.yaml`),
  ]);
  if (!pgmResponse.ok || !yamlResponse.ok) throw new Error('SLAM map files are not available yet');

  const image = parsePgm(await pgmResponse.arrayBuffer());
  const parsed = yaml.load(await yamlResponse.text()) as { resolution?: number; origin?: number[] };
  const meta: MapMeta = {
    resolution: Number(parsed.resolution ?? 0.05),
    origin: [Number(parsed.origin?.[0] ?? -4), Number(parsed.origin?.[1] ?? -4), Number(parsed.origin?.[2] ?? 0)],
  };
  return { image, meta };
}
