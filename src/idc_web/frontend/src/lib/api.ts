export interface RobotApiRecord {
  robot_id: string;
  name: string | null;
  last_seen: string | null;
  battery: number | null;
  battery_percent: number | null;
  state: string | null;
  x: number | null;
  y: number | null;
  yaw: number | null;
}

export interface RackApiRecord {
  rack_id: string;
  aruco_id: number | null;
  x: number | null;
  y: number | null;
  yaw: number | null;
  zone_id: string | null;
  state: 'NORMAL' | 'DOOR_OPEN' | 'LED_RED';
  severity: number | null;
  updated_at: string | null;
}

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();

export const API_BASE_URL = configuredBase
  ? configuredBase.replace(/\/$/, '')
  : `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    cache: 'no-store',
    signal,
  });

  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`);
  }

  return response.json() as Promise<T>;
}

export function fetchRobots(signal?: AbortSignal) {
  return getJson<RobotApiRecord[]>('/robots', signal);
}

export function fetchRacks(signal?: AbortSignal) {
  return getJson<RackApiRecord[]>('/racks', signal);
}
