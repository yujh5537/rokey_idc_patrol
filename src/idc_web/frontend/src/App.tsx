import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import MapView, { type SecurityEvent } from './components/MapView';
import { racks as rackSeed, robots as robotSeed, type Rack, type Robot } from './data/mock';
import { TESTBED_RENDER_SPEC } from './data/testbed';
import type { MapMeta } from './lib/coordinates';
import { loadSlamMap, parseMapYaml, parsePgm, type PgmImage } from './lib/pgm';

const DEFAULT_META: MapMeta = {
  resolution: 0.05,
  origin: [-0.5, -0.5, 0],
  negate: 0,
  occupiedThresh: 0.65,
  freeThresh: 0.25,
};

const INITIAL_EVENTS: SecurityEvent[] = [
  { id: 'evt-r12', type: 'E5', label: 'DOOR OPEN', rackId: 'R12', severity: 3, time: '16:07:31' },
  { id: 'evt-r27', type: 'E7', label: 'LED RED', rackId: 'R27', severity: 2, time: '16:09:04' },
];

function sanitizeName(value: string) {
  return value.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 80);
}

export default function App() {
  const [map, setMap] = useState<PgmImage>();
  const [meta, setMeta] = useState<MapMeta>(DEFAULT_META);
  const [mapName, setMapName] = useState('MAP-DEMO');
  const [imageStatus, setImageStatus] = useState('DEMO');
  const [yamlStatus, setYamlStatus] = useState('DEFAULT');
  const [events, setEvents] = useState<SecurityEvent[]>(INITIAL_EVENTS);
  const [robots, setRobots] = useState<Robot[]>([]);

  useEffect(() => {
    loadSlamMap('/maps/map')
      .then(({ image, meta: loadedMeta }) => {
        setMap(image);
        setMeta(loadedMeta);
        setMapName('map.pgm');
        setImageStatus('VALID PGM');
        setYamlStatus('VALID');
      })
      .catch(() => {
        // public/maps/map.pgm + map.yaml이 없으면 DEMO 화면을 유지한다.
      });
  }, []);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;

    const isRobotId = (value: string): value is Robot['id'] => (
      value === 'robot5' || value === 'robot11'
    );

    const normalizeState = (value: string): Robot['state'] => {
      if (value === 'PATROL' || value === 'IDLE' || value === 'RETURNING') {
        return value;
      }
      return 'IDLE';
    };

    const loadInitialRobots = async () => {
      try {
        const response = await fetch('/api/v1/robots');

        if (!response.ok) {
          throw new Error(`robots API returned ${response.status}`);
        }

        const rows = await response.json() as Array<{
          robot_id: string;
          battery_percent: number | null;
          state: string;
          x: number | null;
          y: number | null;
          yaw: number | null;
        }>;

        if (disposed) return;

        const liveRobots = rows.flatMap((row) => {
          if (
            !isRobotId(row.robot_id)
            || row.x === null
            || row.y === null
            || row.yaw === null
          ) {
            return [];
          }

          const seed = robotSeed.find((robot) => robot.id === row.robot_id);

          return [{
            id: row.robot_id,
            label: seed?.label ?? row.robot_id.toUpperCase(),
            state: normalizeState(row.state),
            battery: Math.round(row.battery_percent ?? 0),
            x: row.x,
            y: row.y,
            yaw: row.yaw,
            zone: seed?.zone ?? '',
          } satisfies Robot];
        });

        setRobots(liveRobots);
      } catch (error) {
        console.error('robot API load failed', error);
      }
    };

    const connectWebSocket = () => {
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(
        `${scheme}://${window.location.host}/api/v1/ws`,
      );

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as {
            event: string;
            data: {
              robot_id: string;
              x: number;
              y: number;
              yaw: number;
            };
          };

          const rawRobotId = message.data.robot_id;

          if (
            message.event !== 'robot_pose'
            || !isRobotId(rawRobotId)
          ) {
            return;
          }

          const robotId: Robot['id'] = rawRobotId;

          setRobots((current) => {
            const exists = current.some(
              (robot) => robot.id === robotId,
            );

            if (exists) {
              return current.map((robot) => (
                robot.id === robotId
                  ? {
                      ...robot,
                      x: message.data.x,
                      y: message.data.y,
                      yaw: message.data.yaw,
                    }
                  : robot
              ));
            }

            const seed = robotSeed.find(
              (robot) => robot.id === robotId,
            );

            const newRobot: Robot = {
              id: robotId,
              label: seed?.label ?? robotId.toUpperCase(),
              state: seed?.state ?? 'IDLE',
              battery: seed?.battery ?? 0,
              zone: seed?.zone ?? '',
              x: message.data.x,
              y: message.data.y,
              yaw: message.data.yaw,
            };

            return [
              ...current,
              newRobot,
            ];
          });
        } catch (error) {
          console.error('robot pose websocket error', error);
        }
      };

      socket.onclose = () => {
        if (!disposed) {
          reconnectTimer = window.setTimeout(connectWebSocket, 1000);
        }
      };
    };

    void loadInitialRobots();
    connectWebSocket();

    return () => {
      disposed = true;

      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }

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
    setEvents(INITIAL_EVENTS);
  };

  const triggerE5 = () => {
    setEvents((current) => {
      if (current.some((event) => event.rackId === 'R03' && event.type === 'E5')) return current;
      return [
        ...current,
        {
          id: crypto.randomUUID(),
          type: 'E5',
          label: 'DOOR OPEN',
          rackId: 'R03',
          severity: 3,
          time: new Date().toLocaleTimeString(),
        },
      ];
    });
  };

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="eyebrow">IDC SECURITY CONTROL</div>
          <h1>Patrol Map Renderer</h1>
        </div>
        <div className="live-badge"><span className="live-dot" />LIVE</div>
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
          robots={robots}
          racks={racks}
          events={events}
        />

        <aside className="side-panel">
          <section className="panel">
            <div className="panel-title">ROBOT STATUS</div>

            {robotSeed.map((seed) => {
              const robot = robots.find((item) => item.id === seed.id);

              return (
                <div className="robot-card" key={seed.id}>
                  <div className="robot-name">
                    <strong className={seed.id}>{seed.id}</strong>
                    <strong className={seed.id}>
                      {robot?.state ?? 'NO DATA'}
                    </strong>
                  </div>

                  <div className="robot-info">
                    <span>BATTERY</span>
                    <span>{robot ? `${robot.battery}%` : '--'}</span>
                  </div>

                  <div className="robot-info">
                    <span>X</span>
                    <span>{robot ? robot.x.toFixed(2) : '--'}</span>
                  </div>

                  <div className="robot-info">
                    <span>Y</span>
                    <span>{robot ? robot.y.toFixed(2) : '--'}</span>
                  </div>
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
                <div className={`event-card l${event.severity}`} key={event.id}>
                  <div className="event-type">⚠ {event.type} {event.label}</div>
                  <div className="event-detail">{event.rackId}</div>
                  <div className="event-detail">{event.time}</div>
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
