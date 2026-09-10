import { rackLayout } from './rackLayout';

export type RobotState =
  | 'INIT'
  | 'UNDOCK'
  | 'NAVIGATE'
  | 'FACE'
  | 'INSPECT'
  | 'MARKER_CHECK'
  | 'RESUME'
  | 'RETURN'
  | 'DOCK'
  | 'DONE'
  | 'ERROR'
  | 'IDLE'
  | 'PATROL'
  | 'RETURNING';
export type RackState = 'NORMAL' | 'DOOR_OPEN' | 'LED_RED';

export interface Robot {
  id: 'robot5' | 'robot11';
  label: string;
  state: RobotState;
  battery: number;
  x: number;
  y: number;
  yaw: number;
  zone: string;
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

// MAP-02 racks.yaml docks are the only fallback positions shown when live pose
// telemetry is unavailable. They are reference/AMCL initial poses, not a claim
// that the robot is currently at the dock.
export const robots: Robot[] = [
  {
    id: 'robot5',
    label: 'AMR 05',
    state: 'IDLE',
    battery: 0,
    x: 0.27,
    y: 0.33,
    yaw: 3.1416,
    zone: '',
  },
  {
    id: 'robot11',
    label: 'AMR 11',
    state: 'IDLE',
    battery: 0,
    x: 0.27,
    y: 4.92,
    yaw: 3.1416,
    zone: '',
  },
];

// Rack mock state is kept only for isolated visual development.
// Position/rotation comes from the approved 56-rack CSV layout.
export const racks: Rack[] = rackLayout.map((layout) => {
  const common = {
    id: layout.rackId,
    arucoId: layout.arucoId,
    zone: '',
    x: layout.xM,
    y: layout.yM,
    screenXFrac: layout.screenXFrac,
    screenYFrac: layout.screenYFrac,
    screenRotateDeg: layout.screenRotateDeg,
  };

  if (layout.rackId === 'R12') {
    return { ...common, state: 'DOOR_OPEN', severity: 3, updatedAt: '16:07:31' };
  }
  if (layout.rackId === 'R27') {
    return { ...common, state: 'LED_RED', severity: 2, updatedAt: '16:09:04' };
  }
  return { ...common, state: 'NORMAL' };
});

export const alerts = racks.filter((rack) => rack.state !== 'NORMAL');
