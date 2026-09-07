import { useEffect, useMemo, useRef } from 'react';
import type { CSSProperties } from 'react';
import type { Rack, Robot } from '../data/mock';
import { worldToPercent, type MapMeta } from '../lib/coordinates';
import type { PgmImage } from '../lib/pgm';

export type ViewMode = 'portrait' | 'landscape';

export interface SecurityEvent {
  id: string;
  type: 'E5' | 'E7';
  label: string;
  rackId: string;
  severity: 2 | 3;
  time: string;
}

interface Props {
  map?: PgmImage;
  meta: MapMeta;
  mapName: string;
  viewMode: ViewMode;
  robots: Robot[];
  racks: Rack[];
  events: SecurityEvent[];
}

const DEMO_SIZE = { width: 120, height: 180 };

function occupancyColor(value: number, maxValue: number, meta: MapMeta) {
  const normalized = Math.max(0, Math.min(1, value / maxValue));
  const occupancy = (meta.negate ?? 0) === 0 ? 1 - normalized : normalized;
  const occupied = meta.occupiedThresh ?? 0.65;
  const free = meta.freeThresh ?? 0.196;

  if (occupancy > occupied) return '#075b70';
  if (occupancy < free) return '#04141f';
  return '#102c37';
}

function paintDemo(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.fillStyle = '#04141f';
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = '#075b70';
  ctx.fillRect(17, 18, 5, 144);
  ctx.fillRect(98, 18, 5, 144);
  ctx.fillRect(17, 18, 86, 5);
  ctx.fillRect(17, 157, 86, 5);

  ctx.fillStyle = '#0d3542';
  const rows = [42, 64, 108, 130];
  rows.forEach((y) => {
    for (let x = 30; x <= 82; x += 9) ctx.fillRect(x, y, 5, 11);
  });

  ctx.fillStyle = '#102c37';
  ctx.fillRect(0, 0, width, 10);
  ctx.fillRect(0, height - 10, width, 10);
}

function paintMap(canvas: HTMLCanvasElement, map: PgmImage | undefined, meta: MapMeta, rotated: boolean) {
  const sourceWidth = map?.width ?? DEMO_SIZE.width;
  const sourceHeight = map?.height ?? DEMO_SIZE.height;
  const sourceCanvas = document.createElement('canvas');
  sourceCanvas.width = sourceWidth;
  sourceCanvas.height = sourceHeight;
  const sourceCtx = sourceCanvas.getContext('2d');
  if (!sourceCtx) return;

  if (!map) {
    paintDemo(sourceCtx, sourceWidth, sourceHeight);
  } else {
    const image = sourceCtx.createImageData(sourceWidth, sourceHeight);
    for (let i = 0; i < map.pixels.length; i += 1) {
      const color = occupancyColor(map.pixels[i], map.maxValue, meta);
      const offset = i * 4;
      image.data[offset] = Number.parseInt(color.slice(1, 3), 16);
      image.data[offset + 1] = Number.parseInt(color.slice(3, 5), 16);
      image.data[offset + 2] = Number.parseInt(color.slice(5, 7), 16);
      image.data[offset + 3] = 255;
    }
    sourceCtx.putImageData(image, 0, 0);
  }

  canvas.width = rotated ? sourceHeight : sourceWidth;
  canvas.height = rotated ? sourceWidth : sourceHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (rotated) {
    ctx.save();
    ctx.translate(canvas.width, 0);
    ctx.rotate(Math.PI / 2);
    ctx.drawImage(sourceCanvas, 0, 0);
    ctx.restore();
  } else {
    ctx.drawImage(sourceCanvas, 0, 0);
  }

  const gradient = ctx.createRadialGradient(
    canvas.width / 2,
    canvas.height / 2,
    Math.min(canvas.width, canvas.height) * 0.08,
    canvas.width / 2,
    canvas.height / 2,
    Math.max(canvas.width, canvas.height) * 0.72,
  );
  gradient.addColorStop(0, 'rgba(0, 220, 255, 0.03)');
  gradient.addColorStop(1, 'rgba(1, 8, 14, 0.35)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function rotatePercent(position: { left: string; top: string }, rotated: boolean) {
  if (!rotated) return position;
  const x = Number.parseFloat(position.left);
  const y = Number.parseFloat(position.top);
  return { left: `${100 - y}%`, top: `${x}%` };
}

export default function MapView({ map, meta, mapName, viewMode, robots, racks, events }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceWidth = map?.width ?? DEMO_SIZE.width;
  const sourceHeight = map?.height ?? DEMO_SIZE.height;
  const sourcePortrait = sourceHeight > sourceWidth;
  const rotated = (viewMode === 'landscape' && sourcePortrait) || (viewMode === 'portrait' && !sourcePortrait);

  useEffect(() => {
    if (canvasRef.current) paintMap(canvasRef.current, map, meta, rotated);
  }, [map, meta, rotated]);

  const rackMarkers = useMemo(() => racks.map((rack) => ({
    rack,
    pos: rotatePercent(worldToPercent(rack.x, rack.y, meta, sourceWidth, sourceHeight), rotated),
  })), [racks, meta, sourceWidth, sourceHeight, rotated]);

  const robotMarkers = useMemo(() => robots.map((robot) => ({
    robot,
    pos: rotatePercent(worldToPercent(robot.x, robot.y, meta, sourceWidth, sourceHeight), rotated),
  })), [robots, meta, sourceWidth, sourceHeight, rotated]);

  const eventMarkers = useMemo(() => events.flatMap((event) => {
    const rack = racks.find((item) => item.id === event.rackId);
    if (!rack) return [];
    return [{
      event,
      pos: rotatePercent(worldToPercent(rack.x, rack.y, meta, sourceWidth, sourceHeight), rotated),
    }];
  }), [events, racks, meta, sourceWidth, sourceHeight, rotated]);

  return (
    <section className="map-card">
      <div className="map-card-header">
        <div><span className="status-dot" />SECURITY MAP</div>
        <div>{mapName}</div>
      </div>

      <div className={`map-stage ${viewMode}`}>
        <canvas ref={canvasRef} className="map-canvas" />
        <div className="grid-overlay" />
        <div className="scan-line" />
        <div className="corner tl" />
        <div className="corner tr" />
        <div className="corner bl" />
        <div className="corner br" />
        <div className="map-label label-top-left">SECTOR MONITORING</div>
        <div className="map-label label-bottom-right">SECURE AREA</div>

        {rackMarkers.map(({ rack, pos }) => (
          <div
            key={rack.id}
            className={`rack-marker ${rack.state.toLowerCase()}`}
            style={pos}
            title={`${rack.id} · ${rack.state}`}
          >
            {rack.id}
          </div>
        ))}

        {eventMarkers.map(({ event, pos }) => (
          <div key={event.id} className={`event-marker l${event.severity}`} style={pos}>
            <span className="event-triangle">!</span>
            <div><strong>{event.type}</strong><small>{event.rackId}</small></div>
          </div>
        ))}

        {robotMarkers.map(({ robot, pos }) => {
          const yaw = robot.yaw + (rotated ? Math.PI / 2 : 0);
          return (
            <div
              key={robot.id}
              className={`robot-marker ${robot.id}`}
              style={{ ...pos, '--yaw': `${-yaw}rad` } as CSSProperties}
            >
              <div className="robot-radar" />
              <div className="robot-body" />
              <div className="robot-heading" />
              <div className="robot-label">
                <strong>{robot.id.toUpperCase()}</strong>
                <small>{robot.state} · BAT {robot.battery}%</small>
              </div>
            </div>
          );
        })}
      </div>

      <div className="map-footer">
        <span>RES <strong>{meta.resolution} m/px</strong></span>
        <span>ORIGIN <strong>{meta.origin[0].toFixed(3)}, {meta.origin[1].toFixed(3)}</strong></span>
        <span>ROBOTS <strong>{robots.length}</strong></span>
        <span>EVENTS <strong>{events.length}</strong></span>
        <span>VIEW <strong>{viewMode.toUpperCase()}</strong></span>
      </div>
    </section>
  );
}
