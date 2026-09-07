import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import MapView, { type SecurityEvent } from './components/MapView';
import { rackLayout } from './data/rackLayout';
import { type Rack, type Robot } from './data/mock';
import { TESTBED_RENDER_SPEC } from './data/testbed';
import { fetchRacks, fetchRobots, type RackApiRecord } from './lib/api';
import type { MapMeta } from './lib/coordinates';
import { loadSlamMap, parseMapYaml, parsePgm, type PgmImage } from './lib/pgm';

const DEFAULT_META: MapMeta = {
  resolution: 0.05,
  origin: [-3.384, -4.489, 0],
  negate: 0,
  occupiedThresh: 0.65,
  freeThresh: 0.196,
};

function sanitizeName(value: string) {
  return value.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 80);
}

function formatRackTime(value?: string) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

function formatNumber(value: number | null) {
  return value === null ? '--' : value.toFixed(2);
}

export default function App() {
  const [map, setMap] = useState<PgmImage>();
  const [meta, setMeta] = useState<MapMeta>(DEFAULT_META);
  const [mapName, setMapName] = useState('MAP-DEMO');
  const [imageStatus, setImageStatus] = useState('DEMO');
  const [yamlStatus, setYamlStatus] = useState('DEFAULT');
  const [robots, setRobots] = useState<Robot[]>([]);
  const [rackRows, setRackRows] = useState<RackApiRecord[]>([]);
  const [apiStatus, setApiStatus] = useState<'CONNECTING' | 'LIVE' | 'OFFLINE'>('CONNECTING');

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
        // Map asset is delivered by the map/SLAM workstream. Keep the demo surface until then.
      });
  }, []);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | undefined;

    const poll = async () => {
      controller?.abort();
      controller = new AbortController();

      try {
        const [robotRows, nextRackRows] = await Promise.all([
          fetchRobots(controller.signal),
          fetchRacks(controller.signal),
        ]);

        if (disposed) return;

        setRobots(robotRows.map((row) => ({
          id: row.robot_id,
          label: row.name ?? row.robot_id,
          state: row.state ?? 'UNKNOWN',
          battery: row.battery_percent,
          x: row.x,
          y: row.y,
          yaw: row.yaw,
          zone: '',
          lastSeen: row.last_seen,
        })));
        setRackRows(nextRackRows);
        setApiStatus('LIVE');
      } catch (error) {
        if (disposed || (error instanceof DOMException && error.name === 'AbortError')) return;
        console.error('Live API poll failed', error);
        setApiStatus('OFFLINE');
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 1000);

    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, []);

  const rackStatusById = useMemo(
    () => new Map(rackRows.map((row) => [row.rack_id, row])),
    [rackRows],
  );

  const racks = useMemo<Rack[]>(() => rackLayout.map((layout) => {
    const live = rackStatusById.get(layout.rackId);
    const severity = live?.severity === 3 ? 3 : live?.severity === 2 ? 2 : undefined;

    return {
      id: layout.rackId,
      arucoId: layout.arucoId,
      zone: live?.zone_id ?? '',
      x: layout.xM,
      y: layout.yM,
      state: live?.state ?? 'NORMAL',
      screenXFrac: layout.screenXFrac,
      screenYFrac: layout.screenYFrac,
      screenRotateDeg: layout.screenRotateDeg,
      severity,
      updatedAt: live?.updated_at ?? undefined,
    };
  }), [rackStatusById]);

  const events = useMemo<SecurityEvent[]>(() => racks.flatMap((rack) => {
    if (rack.state === 'NORMAL') return [];

    const type = rack.state === 'DOOR_OPEN' ? 'E5' : 'E7';
    const severity: 2 | 3 = rack.severity ?? (type === 'E5' ? 3 : 2);

    return [{
      id: `${type}-${rack.id}`,
      type,
      label: type === 'E5' ? 'DOOR OPEN' : 'LED RED',
      rackId: rack.id,
      severity,
      time: formatRackTime(rack.updatedAt),
    }];
  }), [racks]);

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
  };

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="eyebrow">IDC SECURITY CONTROL</div>
          <h1>Patrol Map Renderer</h1>
        </div>
        <div className="live-badge"><span className="live-dot" />{apiStatus}</div>
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
            {robots.length === 0 ? (
              <div className="empty">NO ROBOT TELEMETRY</div>
            ) : (
              robots.map((robot) => (
                <div className="robot-card" key={robot.id}>
                  <div className="robot-name">
                    <strong className={robot.id}>{robot.id}</strong>
                    <strong className={robot.id}>{robot.state}</strong>
                  </div>
                  <div className="robot-info">
                    <span>BATTERY</span>
                    <span>{robot.battery === null ? '--' : `${robot.battery.toFixed(1)}%`}</span>
                  </div>
                  <div className="robot-info"><span>X</span><span>{formatNumber(robot.x)}</span></div>
                  <div className="robot-info"><span>Y</span><span>{formatNumber(robot.y)}</span></div>
                  <div className="robot-info"><span>YAW</span><span>{formatNumber(robot.yaw)}</span></div>
                </div>
              ))
            )}
          </section>

          <section className="panel">
            <div className="panel-title">RACK STATUS</div>
            {events.length === 0 ? (
              <div className="empty">ALL RACKS NORMAL</div>
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
            <div className="panel-title">DATA STATUS</div>
            <div className="integrity-row"><span>Backend API</span><strong>{apiStatus}</strong></div>
            <div className="integrity-row"><span>Robots</span><strong>{robots.length}</strong></div>
            <div className="integrity-row"><span>Racks</span><strong>{racks.length}</strong></div>
            <div className="integrity-row"><span>Rack layout</span><strong>CSV · 56</strong></div>
            <div className="integrity-row"><span>Rack status</span><strong>{rackRows.length > 0 ? 'BACKEND' : 'NORMAL DEFAULT'}</strong></div>
            <div className="integrity-row"><span>Map image</span><strong>{imageStatus}</strong></div>
            <div className="integrity-row"><span>Map YAML</span><strong>{yamlStatus}</strong></div>
            <div className="integrity-row"><span>AMR</span><strong>Ø {TESTBED_RENDER_SPEC.amrDiameterMm} mm</strong></div>
          </section>
        </aside>
      </main>
    </div>
  );
}
