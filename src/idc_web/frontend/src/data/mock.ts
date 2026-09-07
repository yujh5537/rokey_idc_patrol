export type RobotState = string;
export type RackState = 'NORMAL' | 'DOOR_OPEN' | 'LED_RED';

export interface Robot {
  id: string;
  label: string;
  state: RobotState;
  battery: number | null;
  x: number | null;
  y: number | null;
  yaw: number | null;
  zone: string;
  lastSeen?: string | null;
}

export interface Rack {
  id: string;
  arucoId?: number;
  zone: string;
  x: number;
  y: number;
  state: RackState;
  screenXFrac?: number;
  screenYFrac?: number;
  screenRotateDeg?: number;
  severity?: 2 | 3;
  updatedAt?: string;
}

// Robot mock data is kept only for isolated visual development.
export const robots: Robot[] = [
  { id: 'robot5', label: 'AMR 05', state: 'PATROL', battery: 82, x: 1.3, y: 1.7, yaw: 0.55, zone: 'Z2' },
  { id: 'robot11', label: 'AMR 11', state: 'IDLE', battery: 67, x: 5.7, y: -1.2, yaw: 2.25, zone: 'Z4' },
];
