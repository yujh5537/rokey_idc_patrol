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
  zone: string;
  x: number;
  y: number;
  state: RackState;
  screenRotateDeg?: number;
  severity?: 2 | 3;
  updatedAt?: string;
}

// Robot mock data is kept only for visual development; App.tsx does not use it
// for live monitoring once the FastAPI endpoint is available.
export const robots: Robot[] = [
  { id: 'robot5', label: 'AMR 05', state: 'PATROL', battery: 82, x: 1.3, y: 1.7, yaw: 0.55, zone: 'Z2' },
  { id: 'robot11', label: 'AMR 11', state: 'IDLE', battery: 67, x: 5.7, y: -1.2, yaw: 2.25, zone: 'Z4' },
];

// Frontend style-preview coordinates only.
// The final rack positions and rotations must come from the canonical rack data.
const rackCoords = [
  [-1.7, 2.7], [-0.8, 2.7], [0.1, 2.7], [1.0, 2.7], [1.9, 2.7], [2.8, 2.7], [3.7, 2.7],
  [-1.7, 1.8], [-0.8, 1.8], [0.1, 1.8], [1.0, 1.8], [1.9, 1.8], [2.8, 1.8], [3.7, 1.8],
  [-1.7, -0.2], [-0.8, -0.2], [0.1, -0.2], [1.0, -0.2], [1.9, -0.2], [2.8, -0.2], [3.7, -0.2],
  [-1.7, -1.1], [-0.8, -1.1], [0.1, -1.1], [1.0, -1.1], [1.9, -1.1], [2.8, -1.1], [3.7, -1.1],
];

export const racks: Rack[] = rackCoords.map(([x, y], index) => {
  const id = `R${String(index + 1).padStart(2, '0')}`;
  const zone = index < 7 ? 'Z1' : index < 14 ? 'Z2' : index < 21 ? 'Z3' : 'Z4';
  if (id === 'R12') return { id, zone, x, y, screenRotateDeg: 0, state: 'DOOR_OPEN', severity: 3, updatedAt: '16:07:31' };
  if (id === 'R27') return { id, zone, x, y, screenRotateDeg: 0, state: 'LED_RED', severity: 2, updatedAt: '16:09:04' };
  return { id, zone, x, y, screenRotateDeg: 0, state: 'NORMAL' };
});

export const alerts = racks.filter((rack) => rack.state !== 'NORMAL');
