import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import MapView, { type SecurityEvent } from './components/MapView';
import { racks as rackSeed, robots as robotSeed, type Rack, type Robot } from './data/mock';
import { TESTBED_RENDER_SPEC } from './data/testbed';
import type { MapMeta } from './lib/coordinates';
import { loadCurrentSlamMap, parseMapYaml, parsePgm, type PgmImage } from './lib/pgm';

const DEFAULT_META: MapMeta = {
  resolution: 0.05,
  origin: [-0.5, -0.5, 0],
  negate: 0,
  occupiedThresh: 0.65,
  freeThresh: 0.25,
};

// Pose arrives at 2 Hz in the frozen MQTT contract. INT-00 treats a robot pose
// as live only while samples continue to arrive within this window.
const ROBOT_FRESHNESS_MS = 3000;

const DEMO_EVENTS: SecurityEvent[] = [
  { id: 'evt-r12', type: 'E5', label: 'DOOR OPEN', rackId: 'R12', severity: 3, time: '16:07:31' },
  { id: 'evt-r27', type: 'E7', label: 'LED RED', rackId: 'R27', severity: 2, time: '16:09:04' },
];

interface EventRow {
  event_id: number;
  type: string | null;
  severity: number | null;
  zone_id: string | null;
  rack_id: string | null;
  robot_id: string | null;
  x: number | null;
  y: number | null;
  first_ts: string | null;
  last_ts: string | null;
  detail_json: string | null;
}

interface RobotRow {
  robot_id: string;
  battery_percent: number | null;
  state: string | null;
  x: number | null;
  y: number | null;
  yaw: number | null;
  last_seen: string | null;
}

function sanitizeName(value: string) {
  return value.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 80);
}

function isRobotId(value: string): value is Robot['id'] {
  return value === 'robot5' || value === 'robot11';
}

function normalizeState(value: string | null | undefined): Robot['state'] {
  const allowed: Robot['state'][] = [
    'INIT', 'UNDOCK', 'NAVIGATE', 'FACE', 'INSPECT', 'MARKER_CHECK',
    'RESUME', 'RETURN', 'DOCK', 'DONE', 'ERROR', 'IDLE', 'PATROL', 'RETURNING',
  ];
  return allowed.includes(value as Robot['state']) ? value as Robot['state'] : 'IDLE';
}

function timestampIsFresh(value: string | null) {
  if (!value) return false;
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return false;
  const age = Date.now() - timestamp;
  return age >= -5000 && age <= ROBOT_FRESHNESS_MS;
}

function eventRowToUi(row: EventRow): SecurityEvent | null {
  if ((row.type !== 'E5' && row.type !== 'E7') || !row.rack_id) return null;

  let details: Record<string, unknown> = {};
  if (row.detail_json) {
    try {
      const parsed = JSON.parse(row.detail_json);
      if (parsed && typeof parsed === 'object') details = parsed as Record<string, unknown>;
    } catch {
      // detail_json is supplemental; the persisted event itself remains usable.
    }
  }

  const severity = row.severity === 2 || row.severity === 3 ? row.severity : undefined;
  const timestamp = row.first_ts ?? row.last_ts;
  const eventTime = timestamp
    ? new Date(timestamp).toLocaleTimeString()
    : '--:--:--';

  return {
    id: `event-${row.event_id}`,
    type: row.type,
    label: row.type === 'E5' ? 'DOOR OPEN' : 'LED RED',
    rackId: row.rack_id,
    severity,
    time: eventTime,
    robotId: row.robot_id ?? undefined,
    zoneId: row.zone_id ?? undefined,
    x: row.x ?? undefined,
    y: row.y ?? undefined,
    basis: typeof details.basis === 'string' ? details.basis : undefined,
    openRatio: typeof details.open_ratio === 'number' || details.open_ratio === null
      ? details.open_ratio as number | null
      : undefined,
    frames: typeof details.frames === 'number' ? details.frames : undefined,
    markerChecked: typeof details.marker_checked === 'boolean'
      ? details.marker_checked
      : undefined,
  };
}

export default function App() {
  const [map, setMap] = useState<PgmImage>();
  const [meta, setMeta] = useState<MapMeta>(DEFAULT_META);
  const [mapName, setMapName] = useState('MAP-DEMO');
  const [imageStatus, setImageStatus] = useState('DEMO');
  const [yamlStatus, setYamlStatus] = useState('DEFAULT');
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [robots, setRobots] = useState<Robot[]>(() => robotSeed.map((robot) => ({ ...robot })));

  useEffect(() => {
    loadCurrentSlamMap()
      .then(({ image, meta: loadedMeta, mapName: loadedMapName }) => {
        setMap(image);
        setMeta(loadedMeta);
        setMapName(loadedMapName);
        setImageStatus('VALID PGM');
        setYamlStatus('VALID');
      })
      .catch(() => {
        // PC3 -> PC4 runtime map has not been synchronized yet.
        // Keep the synthetic demo canvas without fabricating live-map metadata.
      });
  }, []);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let statusTimer: number | undefined;
    let poseExpiryTimer: number | undefined;
    let lastEventId = 0;

    const loadRobotStatus = async () => {
      const response = await fetch('/api/v1/robots');
      if (!response.ok) throw new Error(`robots API returned ${response.status}`);

      const rows = await response.json() as RobotRow[];
      if (disposed) return;

      setRobots((current) => robotSeed.map((seed) => {
        const row = rows.find((item) => item.robot_id === seed.id);
        const existing = current.find((item) => item.id === seed.id);

        if (!row || !isRobotId(row.robot_id)) {
          return {
            ...seed,
            telemetryFresh: false,
            poseLive: existing?.poseLive ?? false,
            poseUpdatedAt: existing?.poseUpdatedAt,
            x: existing?.x ?? seed.x,
            y: existing?.y ?? seed.y,
            yaw: existing?.yaw ?? seed.yaw,
          };
        }

        return {
          ...seed,
          state: normalizeState(row.state),
          battery: Math.round(row.battery_percent ?? 0),
          telemetryFresh: timestampIsFresh(row.last_seen),
          poseLive: existing?.poseLive ?? false,
          poseUpdatedAt: existing?.poseUpdatedAt,
          x: existing?.poseLive ? existing.x : seed.x,
          y: existing?.poseLive ? existing.y : seed.y,
          yaw: existing?.poseLive ? existing.yaw : seed.yaw,
        };
      }));
    };

    const loadInitialEvents = async () => {
      const response = await fetch('/api/v1/events?limit=100');
      if (!response.ok) throw new Error(`events API returned ${response.status}`);

      const rows = await response.json() as EventRow[];
      if (disposed) return;

      lastEventId = rows.reduce((maxId, row) => Math.max(maxId, row.event_id), 0);
      const mapped = rows
        .map(eventRowToUi)
        .filter((event): event is SecurityEvent => event !== null);
      setEvents(mapped);
    };

    const connectWebSocket = () => {
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(
        `${scheme}://${window.location.host}/api/v1/ws?after_event_id=${lastEventId}`,
      );

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as {
            event: string;
            data: Record<string, unknown>;
          };

          if (message.event === 'robot_pose') {
            const rawRobotId = message.data.robot_id;
            if (typeof rawRobotId !== 'string' || !isRobotId(rawRobotId)) return;

            const x = Number(message.data.x);
            const y = Number(message.data.y);
            const yaw = Number(message.data.yaw);
            if (![x, y, yaw].every(Number.isFinite)) return;

            const robotId: Robot['id'] = rawRobotId;
            setRobots((current) => current.map((robot) => (
              robot.id === robotId
                ? {
                    ...robot,
                    x,
                    y,
                    yaw,
                    poseLive: true,
                    poseUpdatedAt: Date.now(),
                  }
                : robot
            )));
            return;
          }

          if (message.event === 'event_new') {
            const row = message.data as unknown as EventRow;
            const mapped = eventRowToUi(row);
            if (!mapped) return;

            lastEventId = Math.max(lastEventId, row.event_id);
            setEvents((current) => (
              current.some((item) => item.id === mapped.id)
                ? current
                : [mapped, ...current]
            ));
          }
        } catch (error) {
          console.error('websocket message error', error);
        }
      };

      socket.onclose = () => {
        if (!disposed) {
          reconnectTimer = window.setTimeout(connectWebSocket, 1000);
        }
      };
    };

    const bootstrap = async () => {
      try {
        await Promise.all([loadRobotStatus(), loadInitialEvents()]);
      } catch (error) {
        console.error('initial API load failed', error);
      }

      if (disposed) return;
      connectWebSocket();

      statusTimer = window.setInterval(() => {
        void loadRobotStatus().catch((error) => {
          console.error('robot status refresh failed', error);
        });
      }, 1000);

      poseExpiryTimer = window.setInterval(() => {
        const now = Date.now();
        setRobots((current) => current.map((robot) => {
          if (
            robot.poseLive
            && robot.poseUpdatedAt !== undefined
            && now - robot.poseUpdatedAt > ROBOT_FRESHNESS_MS
          ) {
            return { ...robot, poseLive: false };
          }
          return robot;
        }));
      }, 250);
    };

    void bootstrap();

    return () => {
      disposed = true;
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      if (statusTimer !== undefined) window.clearInterval(statusTimer);
      if (poseExpiryTimer !== undefined) window.clearInterval(poseExpiryTimer);
      socket?.close();
    };
  }, []);

  const racks = useMemo<Rack[]>(() => (
    rackSeed.map((rack) => {
      const event = events.find((item) => item.rackId === rack.id);
      return {
        ...rack,
        state: event?.type === 'E5' ? 'DOOR_OPEN' : event?.type === 'E7' ? 'LED_RED' : 'NORMAL',
        severity: event?.severity,
        updatedAt: event?.time,
      };
    })
  ), [events]);

  const handleMapImage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    if (file.size > 20 * 1024 * 1024) {
      window.alert('Map image is too large. Maximum size is 20 MB.');
      return;
    }
    if (!file.name.toLowerCase().endsWith('.pgm')) {
      window.alert('현재 프론트 렌더러는 PGM 지도만 지원합니다.');
      return;
    }

    try {
      const parsed = parsePgm(await file.arrayBuffer());
      setMap(parsed);
      setMapName(sanitizeName(file.name));
      setImageStatus('VALID PGM');
    } catch (error) {
      console.error(error);
      setImageStatus('INVALID');
      window.alert(`PGM ERROR: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const handleMapYaml = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    try {
      const parsed = parseMapYaml(await file.text());
      setMeta((current) => ({ ...current, ...parsed }));
      setYamlStatus('VALID');
    } catch (error) {
      console.error(error);
      setYamlStatus('INVALID');
      window.alert(error instanceof Error ? error.message : 'Invalid YAML');
    }
  };

  const loadDemo = () => {
    setMap(undefined);
    setMeta(DEFAULT_META);
    setMapName('MAP-DEMO');
    setImageStatus('DEMO');
    setYamlStatus('DEFAULT');
    setEvents(DEMO_EVENTS);
  };

  const triggerE5 = () => {
    setEvents((current) => {
      if (current.some((event) => event.rackId === 'R03' && event.type === 'E5')) return current;
      return [
        {
          id: crypto.randomUUID(),
          type: 'E5',
          label: 'DOOR OPEN',
          rackId: 'R03',
          severity: 3,
          time: new Date().toLocaleTimeString(),
        },
        ...current,
      ];
    });
  };

  const liveRobots = robots.filter((robot) => robot.poseLive);
  const robotLinkLive = robots.some((robot) => robot.telemetryFresh || robot.poseLive);

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="eyebrow">IDC SECURITY CONTROL</div>
          <h1>Patrol Map Renderer</h1>
        </div>
        <div className="live-badge">
          <span className="live-dot" />{robotLinkLive ? 'ROBOT LIVE' : 'NO ROBOT DATA'}
        </div>
      </header>

      <section className="toolbar">
        <label className="file-btn">
          MAP IMAGE
          <input type="file" accept=".pgm" onChange={handleMapImage} />
        </label>
        <label className="file-btn">
          MAP YAML
          <input type="file" accept=".yaml,.yml,text/yaml,text/plain" onChange={handleMapYaml} />
        </label>
        <button onClick={loadDemo}>LOAD DEMO</button>
        <button onClick={triggerE5}>TRIGGER E5</button>
        <button onClick={() => setEvents([])}>CLEAR EVENTS</button>
      </section>

      <main className="layout">
        <MapView
          map={map}
          meta={meta}
          mapName={mapName}
          robots={liveRobots}
          racks={racks}
          events={events}
        />

        <aside className="side-panel">
          <section className="panel">
            <div className="panel-title">ROBOT STATUS</div>

            {robotSeed.map((seed) => {
              const robot = robots.find((item) => item.id === seed.id);
              const telemetryFresh = robot?.telemetryFresh ?? false;
              const poseLive = robot?.poseLive ?? false;
              return (
                <div className="robot-card" key={seed.id}>
                  <div className="robot-name">
                    <strong className={seed.id}>{seed.id}</strong>
                    <strong className={seed.id}>{telemetryFresh ? robot?.state ?? 'NO DATA' : 'NO DATA'}</strong>
                  </div>
                  <div className="robot-info"><span>BATTERY</span><span>{telemetryFresh && robot ? `${robot.battery}%` : '--'}</span></div>
                  <div className="robot-info"><span>POSE</span><span>{poseLive ? 'LIVE' : 'DOCK FALLBACK'}</span></div>
                  <div className="robot-info"><span>X</span><span>{poseLive && robot ? robot.x.toFixed(2) : seed.x.toFixed(2)}</span></div>
                  <div className="robot-info"><span>Y</span><span>{poseLive && robot ? robot.y.toFixed(2) : seed.y.toFixed(2)}</span></div>
                </div>
              );
            })}
          </section>

          <section className="panel">
            <div className="panel-title">SECURITY EVENTS</div>
            {events.length === 0 ? (
              <div className="empty">NO ACTIVE EVENTS</div>
            ) : (
              events.map((event) => (
                <div className={`event-card ${event.severity ? `l${event.severity}` : ''}`} key={event.id}>
                  <div className="event-type">⚠ {event.type} {event.label}</div>
                  <div className="event-detail">{event.rackId}</div>
                  <div className="event-detail">{event.time}</div>
                  {event.basis && <div className="event-detail">{event.basis} · {event.frames ?? 0} frames</div>}
                </div>
              ))
            )}
          </section>

          <section className="panel">
            <div className="panel-title">MAP INTEGRITY</div>
            <div className="integrity-row"><span>Image</span><strong>{imageStatus}</strong></div>
            <div className="integrity-row"><span>YAML</span><strong>{yamlStatus}</strong></div>
            <div className="integrity-row"><span>Canvas</span><strong className="ok">5600:3500 LOCKED</strong></div>
            <div className="integrity-row"><span>AMR</span><strong>Ø {TESTBED_RENDER_SPEC.amrDiameterMm} mm</strong></div>
            <div className="integrity-row"><span>Rack</span><strong>{TESTBED_RENDER_SPEC.rackWidthMm} × {TESTBED_RENDER_SPEC.rackHeightMm} mm</strong></div>
            <div className="integrity-row"><span>Rack layout</span><strong className="ok">56 RACKS LOCKED</strong></div>
          </section>
        </aside>
      </main>
    </div>
  );
}
