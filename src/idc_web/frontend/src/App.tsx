import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import MapView, { type SecurityEvent, type ViewMode } from './components/MapView';
import { racks as rackSeed, robots as robotSeed, type Rack, type Robot } from './data/mock';
import type { MapMeta } from './lib/coordinates';
import { loadSlamMap, parseMapYaml, parsePgm, type PgmImage } from './lib/pgm';

const DEFAULT_META: MapMeta = {
  resolution: 0.05,
  origin: [-3.384, -4.489, 0],
  negate: 0,
  occupiedThresh: 0.65,
  freeThresh: 0.196,
};

const INITIAL_EVENTS: SecurityEvent[] = [
  { id: 'evt-r12', type: 'E5', label: 'DOOR OPEN', rackId: 'R12', severity: 3, time: '16:07:31' },
  { id: 'evt-r27', type: 'E7', label: 'LED RED', rackId: 'R27', severity: 2, time: '16:09:04' },
];

function sanitizeName(value: string) {
  return value.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 80);
}

function ratioToWorld(ratioX: number, ratioY: number, meta: MapMeta, width: number, height: number) {
  return {
    x: meta.origin[0] + width * ratioX * meta.resolution,
    y: meta.origin[1] + (height - height * ratioY) * meta.resolution,
  };
}

export default function App() {
  const [map, setMap] = useState<PgmImage>();
  const [meta, setMeta] = useState<MapMeta>(DEFAULT_META);
  const [mapName, setMapName] = useState('MAP-DEMO');
  const [imageStatus, setImageStatus] = useState('DEMO');
  const [yamlStatus, setYamlStatus] = useState('DEFAULT');
  const [viewMode, setViewMode] = useState<ViewMode>('portrait');
  const [events, setEvents] = useState<SecurityEvent[]>(INITIAL_EVENTS);

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

  const sourceWidth = map?.width ?? 120;
  const sourceHeight = map?.height ?? 180;

  const robots = useMemo<Robot[]>(() => {
    const positions = [
      { x: 0.35, y: 0.65 },
      { x: 0.68, y: 0.72 },
    ];

    return robotSeed.map((robot, index) => {
      const world = ratioToWorld(
        positions[index]?.x ?? 0.5,
        positions[index]?.y ?? 0.5,
        meta,
        sourceWidth,
        sourceHeight,
      );

      return { ...robot, x: world.x, y: world.y };
    });
  }, [meta, sourceHeight, sourceWidth]);

  const racks = useMemo<Rack[]>(() => {
    const rowRatios = [0.24, 0.38, 0.62, 0.76];

    return rackSeed.map((rack, index) => {
      const row = Math.floor(index / 7);
      const col = index % 7;
      const world = ratioToWorld(
        0.25 + col * 0.083,
        rowRatios[row] ?? 0.5,
        meta,
        sourceWidth,
        sourceHeight,
      );
      const event = events.find((item) => item.rackId === rack.id);

      return {
        ...rack,
        x: world.x,
        y: world.y,
        state: event?.type === 'E5' ? 'DOOR_OPEN' : event?.type === 'E7' ? 'LED_RED' : 'NORMAL',
        severity: event?.severity,
        updatedAt: event?.time,
      };
    });
  }, [events, meta, sourceHeight, sourceWidth]);

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
        <button className={`view-btn ${viewMode === 'portrait' ? 'active' : ''}`} onClick={() => setViewMode('portrait')}>PORTRAIT</button>
        <button className={`view-btn ${viewMode === 'landscape' ? 'active' : ''}`} onClick={() => setViewMode('landscape')}>LANDSCAPE</button>
      </section>

      <main className="layout">
        <MapView
          map={map}
          meta={meta}
          mapName={mapName}
          viewMode={viewMode}
          robots={robots}
          racks={racks}
          events={events}
        />

        <aside className="side-panel">
          <section className="panel">
            <div className="panel-title">ROBOT STATUS</div>
            {robots.map((robot) => (
              <div className="robot-card" key={robot.id}>
                <div className="robot-name">
                  <strong className={robot.id}>{robot.id}</strong>
                  <strong className={robot.id}>{robot.state}</strong>
                </div>
                <div className="robot-info"><span>BATTERY</span><span>{robot.battery}%</span></div>
                <div className="robot-info"><span>X</span><span>{robot.x.toFixed(2)}</span></div>
                <div className="robot-info"><span>Y</span><span>{robot.y.toFixed(2)}</span></div>
              </div>
            ))}
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
            <div className="integrity-row"><span>Coordinate</span><strong className="ok">VALID</strong></div>
            <div className="integrity-row"><span>Overlay</span><strong className="ok">HIGH-DPI</strong></div>
          </section>
        </aside>
      </main>
    </div>
  );
}
