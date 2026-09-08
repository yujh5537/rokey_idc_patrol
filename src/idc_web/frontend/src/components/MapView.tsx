import { useEffect, useMemo, useRef, useState } from 'react';
import type { Rack, Robot } from '../data/mock';
import { DEMO_MAP_SIZE, TESTBED_RENDER_SPEC } from '../data/testbed';
import type { MapMeta } from '../lib/coordinates';
import type { PgmImage } from '../lib/pgm';

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
  robots: Robot[];
  racks: Rack[];
  events: SecurityEvent[];
}

interface SurfaceSize {
  width: number;
  height: number;
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

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

  const left = width * 0.08;
  const right = width * 0.92;
  const top = height * 0.09;
  const bottom = height * 0.91;
  const wall = Math.max(4, width * 0.008);

  ctx.fillStyle = '#075b70';
  ctx.fillRect(left, top, wall, bottom - top);
  ctx.fillRect(right - wall, top, wall, bottom - top);
  ctx.fillRect(left, top, right - left, wall);
  ctx.fillRect(left, bottom - wall, right - left, wall);

  ctx.fillStyle = '#102c37';
  ctx.fillRect(0, 0, width, height * 0.035);
  ctx.fillRect(0, height * 0.965, width, height * 0.035);
}

function paintMap(canvas: HTMLCanvasElement, map: PgmImage | undefined, meta: MapMeta) {
  if (!map) {
    canvas.width = DEMO_MAP_SIZE.width;
    canvas.height = DEMO_MAP_SIZE.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    paintDemo(ctx, canvas.width, canvas.height);
    return;
  }

  const rotatePortrait = map.height > map.width;
  const outputWidth = rotatePortrait ? map.height : map.width;
  const outputHeight = rotatePortrait ? map.width : map.height;
  canvas.width = outputWidth;
  canvas.height = outputHeight;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, outputWidth, outputHeight);

  const sourceCanvas = document.createElement('canvas');
  sourceCanvas.width = map.width;
  sourceCanvas.height = map.height;
  const sourceCtx = sourceCanvas.getContext('2d');
  if (!sourceCtx) return;

  const image = sourceCtx.createImageData(map.width, map.height);
  for (let i = 0; i < map.pixels.length; i += 1) {
    const color = occupancyColor(map.pixels[i], map.maxValue, meta);
    const offset = i * 4;
    image.data[offset] = Number.parseInt(color.slice(1, 3), 16);
    image.data[offset + 1] = Number.parseInt(color.slice(3, 5), 16);
    image.data[offset + 2] = Number.parseInt(color.slice(5, 7), 16);
    image.data[offset + 3] = 255;
  }
  sourceCtx.putImageData(image, 0, 0);

  if (rotatePortrait) {
    // The source SLAM PGM is portrait. Rotate the actual pixel map 90deg left
    // and apply the exact same transform to rack/robot overlays below.
    ctx.save();
    ctx.translate(0, outputHeight);
    ctx.rotate(-Math.PI / 2);
    ctx.drawImage(sourceCanvas, 0, 0);
    ctx.restore();
  } else {
    ctx.drawImage(sourceCanvas, 0, 0);
  }

  const gradient = ctx.createRadialGradient(
    outputWidth / 2,
    outputHeight / 2,
    Math.min(outputWidth, outputHeight) * 0.08,
    outputWidth / 2,
    outputHeight / 2,
    Math.max(outputWidth, outputHeight) * 0.72,
  );
  gradient.addColorStop(0, 'rgba(0, 220, 255, 0.03)');
  gradient.addColorStop(1, 'rgba(1, 8, 14, 0.35)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, outputWidth, outputHeight);
}

function rackPalette(state: Rack['state']) {
  if (state === 'DOOR_OPEN') {
    return {
      border: '#ff304f',
      background: 'rgba(91,17,32,.92)',
      glow: '0 0 18px rgba(255,48,79,.55)',
      face: '#ff6b80',
      label: '#ffd0d9',
    };
  }

  if (state === 'LED_RED') {
    return {
      border: '#ffae52',
      background: 'rgba(92,55,14,.92)',
      glow: '0 0 18px rgba(255,174,82,.5)',
      face: '#ffc173',
      label: '#ffe1b0',
    };
  }

  return {
    border: 'rgba(83,163,186,.58)',
    background: 'rgba(3,21,31,.9)',
    glow: '0 0 8px rgba(0,219,255,.08)',
    face: '#43ddff',
    label: '#7db5c2',
  };
}

function containedSurfaceSize(containerWidth: number, containerHeight: number): SurfaceSize {
  const gutter = 24;
  const availableWidth = Math.max(0, containerWidth - gutter);
  const availableHeight = Math.max(0, containerHeight - gutter);
  const aspect = TESTBED_RENDER_SPEC.aspectRatio;

  if (availableWidth === 0 || availableHeight === 0) return { width: 0, height: 0 };

  if (availableWidth / availableHeight > aspect) {
    const height = availableHeight;
    return { width: height * aspect, height };
  }

  const width = availableWidth;
  return { width, height: width / aspect };
}

function worldToDisplayPercent(
  x: number,
  y: number,
  meta: MapMeta,
  sourceWidth: number,
  sourceHeight: number,
  rotatePortrait: boolean,
) {
  const px = (x - meta.origin[0]) / meta.resolution;
  const pyFromBottom = (y - meta.origin[1]) / meta.resolution;
  const sourceXFrac = clamp01(px / sourceWidth);
  const sourceYFrac = clamp01((sourceHeight - pyFromBottom) / sourceHeight);

  if (rotatePortrait) {
    // Same 90deg-left transform as paintMap(): (u, v) -> (v, 1-u).
    return {
      left: `${sourceYFrac * 100}%`,
      top: `${(1 - sourceXFrac) * 100}%`,
    };
  }

  return {
    left: `${sourceXFrac * 100}%`,
    top: `${sourceYFrac * 100}%`,
  };
}

function rackScreenPosition(
  rack: Rack,
  map: PgmImage | undefined,
  meta: MapMeta,
  sourceWidth: number,
  sourceHeight: number,
  rotatePortrait: boolean,
) {
  if (map && rotatePortrait) {
    // rack x/y are local testbed coordinates (metres): 3500 x 5700 mm.
    // rb11auto2.pgm is 75 x 119 px at 0.05m/px = 3.75 x 5.95m.
    // Therefore the real PGM contains 0.25m more on each physical axis.
    // Place the 3.5 x 5.7m testbed in the centre of that real PGM first,
    // then apply exactly the same 90deg-left transform used by paintMap().
    const mapWidthM = sourceWidth * meta.resolution;
    const mapHeightM = sourceHeight * meta.resolution;
    const testbedWidthM = TESTBED_RENDER_SPEC.widthMm / 1000;
    const testbedLengthM = TESTBED_RENDER_SPEC.lengthMm / 1000;
    const padXM = Math.max(0, (mapWidthM - testbedWidthM) / 2);
    const padYM = Math.max(0, (mapHeightM - testbedLengthM) / 2);

    const sourceXFrac = clamp01((rack.x + padXM) / mapWidthM);
    const sourceYFrac = clamp01(1 - (rack.y + padYM) / mapHeightM);

    return {
      left: `${sourceYFrac * 100}%`,
      top: `${(1 - sourceXFrac) * 100}%`,
    };
  }

  // Without the real PGM, keep the generalized 5700 x 3500 preview layout.
  if (rack.screenXFrac !== undefined && rack.screenYFrac !== undefined) {
    return {
      left: `${rack.screenXFrac * 100}%`,
      top: `${rack.screenYFrac * 100}%`,
    };
  }

  return worldToDisplayPercent(rack.x, rack.y, meta, sourceWidth, sourceHeight, rotatePortrait);
}

export default function MapView({ map, meta, mapName, robots, racks, events }: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [surfaceSize, setSurfaceSize] = useState<SurfaceSize>({ width: 0, height: 0 });

  const sourceWidth = map?.width ?? DEMO_MAP_SIZE.width;
  const sourceHeight = map?.height ?? DEMO_MAP_SIZE.height;
  const rotatePortrait = Boolean(map && map.height > map.width);

  useEffect(() => {
    if (canvasRef.current) paintMap(canvasRef.current, map, meta);
  }, [map, meta, surfaceSize.width]);

  useEffect(() => {
    const element = stageRef.current;
    if (!element) return undefined;

    const updateSize = () => {
      setSurfaceSize(containedSurfaceSize(element.clientWidth, element.clientHeight));
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  const rackMarkers = useMemo(() => racks.map((rack) => ({
    rack,
    pos: rackScreenPosition(rack, map, meta, sourceWidth, sourceHeight, rotatePortrait),
  })), [racks, map, meta, sourceWidth, sourceHeight, rotatePortrait]);

  const robotMarkers = useMemo(() => robots.flatMap((robot) => {
    if (robot.x === null || robot.y === null) return [];
    return [{
      robot,
      pos: worldToDisplayPercent(
        robot.x,
        robot.y,
        meta,
        sourceWidth,
        sourceHeight,
        rotatePortrait,
      ),
    }];
  }), [robots, meta, sourceWidth, sourceHeight, rotatePortrait]);

  const eventMarkers = useMemo(() => events.flatMap((event) => {
    const rack = racks.find((item) => item.id === event.rackId);
    if (!rack) return [];
    return [{
      event,
      pos: rackScreenPosition(rack, map, meta, sourceWidth, sourceHeight, rotatePortrait),
    }];
  }), [events, racks, map, meta, sourceWidth, sourceHeight, rotatePortrait]);

  const amrDiameterPx = surfaceSize.width * TESTBED_RENDER_SPEC.amrDiameterFrac;
  const rackThinPx = surfaceSize.width * TESTBED_RENDER_SPEC.rackWidthFrac;
  const rackLongPx = surfaceSize.width * TESTBED_RENDER_SPEC.rackHeightFrac;
  const robotHeadingOffset = rotatePortrait ? -Math.PI / 2 : 0;

  return (
    <section className="map-card">
      <div className="map-card-header">
        <div><span className="status-dot" />SECURITY MAP</div>
        <div>{mapName}</div>
      </div>

      <div
        ref={stageRef}
        className="map-stage"
        style={{ display: 'grid', placeItems: 'center' }}
      >
        {surfaceSize.width > 0 && (
          <div
            style={{
              position: 'relative',
              width: `${surfaceSize.width}px`,
              height: `${surfaceSize.height}px`,
              flex: '0 0 auto',
              overflow: 'hidden',
              background: '#031018',
              border: '1px solid rgba(0,220,255,.16)',
              boxShadow: '0 0 35px rgba(0,0,0,.32)',
            }}
          >
            <canvas ref={canvasRef} className="map-canvas" />
            <div className="grid-overlay" />
            <div className="scan-line" />
            <div className="corner tl" />
            <div className="corner tr" />
            <div className="corner bl" />
            <div className="corner br" />
            <div className="map-label label-top-left">SECTOR MONITORING</div>
            <div className="map-label label-bottom-right">SECURE AREA</div>

            {rackMarkers.map(({ rack, pos }) => {
              const palette = rackPalette(rack.state);
              // CSV front direction is 90/270deg for its horizontal icon convention.
              // Our rack body is drawn as a vertical 85 x 210mm footprint, so add
              // 90deg to preserve front/back direction while keeping the body '|'.
              const rotation = ((rack.screenRotateDeg ?? 0) + 90) % 360;

              return (
                <div
                  key={rack.id}
                  className="rack-marker"
                  style={{
                    ...pos,
                    minWidth: 0,
                    width: 0,
                    height: 0,
                    padding: 0,
                    border: 'none',
                    background: 'transparent',
                    boxShadow: 'none',
                    display: 'block',
                  }}
                  title={`${rack.id} · ARUCO ${rack.arucoId ?? '--'} · ${rack.state} · ${rotation}°`}
                >
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      width: `${rackThinPx}px`,
                      height: `${rackLongPx}px`,
                      transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
                      transformOrigin: '50% 50%',
                      border: `1px solid ${palette.border}`,
                      borderRadius: '2px',
                      background: palette.background,
                      boxShadow: palette.glow,
                    }}
                  >
                    <span
                      style={{
                        position: 'absolute',
                        right: '-2px',
                        top: '18%',
                        width: '3px',
                        height: '64%',
                        borderRadius: '2px',
                        background: palette.face,
                        boxShadow: `0 0 7px ${palette.face}`,
                      }}
                    />
                  </div>

                  <span
                    style={{
                      position: 'absolute',
                      left: `${rackLongPx / 2 + 5}px`,
                      top: '-5px',
                      color: palette.label,
                      font: '700 7px monospace',
                      whiteSpace: 'nowrap',
                      textShadow: '0 0 4px #020910',
                    }}
                  >
                    {rack.id}
                  </span>
                </div>
              );
            })}

            {eventMarkers.map(({ event, pos }) => (
              <div key={event.id} className={`event-marker l${event.severity}`} style={pos}>
                <span className="event-triangle">!</span>
                <div><strong>{event.type}</strong><small>{event.rackId}</small></div>
              </div>
            ))}

            {robotMarkers.map(({ robot, pos }) => {
              const radarSize = amrDiameterPx * 1.55;
              const headingLength = amrDiameterPx * 0.95;

              return (
                <div
                  key={robot.id}
                  className={`robot-marker ${robot.id}`}
                  style={{ ...pos, width: 0, height: 0 }}
                >
                  <div
                    className="robot-radar"
                    style={{
                      left: `${-radarSize / 2}px`,
                      top: `${-radarSize / 2}px`,
                      width: `${radarSize}px`,
                      height: `${radarSize}px`,
                    }}
                  />
                  <div
                    className="robot-body"
                    style={{
                      left: `${-amrDiameterPx / 2}px`,
                      top: `${-amrDiameterPx / 2}px`,
                      width: `${amrDiameterPx}px`,
                      height: `${amrDiameterPx}px`,
                    }}
                  />
                  <div
                    className="robot-heading"
                    style={{
                      left: 0,
                      top: '-1.5px',
                      width: `${headingLength}px`,
                      height: '3px',
                      transform: `rotate(${-(robot.yaw ?? 0) + robotHeadingOffset}rad)`,
                      transformOrigin: '0 50%',
                    }}
                  />
                  <div
                    className="robot-label"
                    style={{
                      left: `${amrDiameterPx / 2 + 10}px`,
                      top: `${-amrDiameterPx / 2 - 6}px`,
                    }}
                  >
                    <strong>{robot.id.toUpperCase()}</strong>
                    <small>{robot.state} · BAT {robot.battery === null ? '--' : robot.battery.toFixed(1)}%</small>
                  </div>
                </div>
              );
            })}

            <div
              className="map-label"
              style={{ left: '22px', bottom: '22px', top: 'auto' }}
            >
              SCALE LOCK · {TESTBED_RENDER_SPEC.lengthMm} × {TESTBED_RENDER_SPEC.widthMm} mm
            </div>
          </div>
        )}
      </div>

      <div className="map-footer">
        <span>RES <strong>{meta.resolution} m/px</strong></span>
        <span>ORIGIN <strong>{meta.origin[0].toFixed(3)}, {meta.origin[1].toFixed(3)}</strong></span>
        <span>CANVAS <strong>{TESTBED_RENDER_SPEC.lengthMm}:{TESTBED_RENDER_SPEC.widthMm}</strong></span>
        <span>MAP <strong>{rotatePortrait ? 'PORTRAIT→LEFT 90°' : 'LANDSCAPE'}</strong></span>
        <span>PGM <strong>{map ? `${map.width}×${map.height}` : 'DEMO'}</strong></span>
        <span>AMR <strong>Ø{TESTBED_RENDER_SPEC.amrDiameterMm}mm</strong></span>
        <span>RACK <strong>{TESTBED_RENDER_SPEC.rackWidthMm}×{TESTBED_RENDER_SPEC.rackHeightMm}mm</strong></span>
        <span>RACKS <strong>{racks.length}</strong></span>
        <span>EVENTS <strong>{events.length}</strong></span>
      </div>
    </section>
  );
}
