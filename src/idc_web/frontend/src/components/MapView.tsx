import { useEffect, useMemo, useRef, useState } from 'react';
import { robots as robotDockSeeds, type Rack, type Robot } from '../data/mock';
import { DEMO_MAP_SIZE, TESTBED_RENDER_SPEC } from '../data/testbed';
import type { MapMeta } from '../lib/coordinates';
import type { PgmImage } from '../lib/pgm';

export interface SecurityEvent {
  id: string;
  type: 'E5' | 'E7';
  label: string;
  rackId: string;
  severity?: 2 | 3;
  time: string;
  robotId?: string;
  zoneId?: string;
  x?: number;
  y?: number;
  basis?: string;
  openRatio?: number | null;
  frames?: number;
  markerChecked?: boolean;
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
  const free = meta.freeThresh ?? 0.25;

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

  ctx.fillStyle = '#0d3542';
  const rows = [0.26, 0.39, 0.61, 0.74];
  rows.forEach((ratioY) => {
    for (let ratioX = 0.24; ratioX <= 0.76; ratioX += 0.075) {
      ctx.fillRect(width * ratioX, height * ratioY, width * 0.018, height * 0.065);
    }
  });
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

function containedSurfaceSize(
  containerWidth: number,
  containerHeight: number,
  aspect: number,
): SurfaceSize {
  const gutter = 24;
  const availableWidth = Math.max(0, containerWidth - gutter);
  const availableHeight = Math.max(0, containerHeight - gutter);

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
  // With a real PGM/YAML pair, rack and robot overlays use the exact same ROS
  // map-frame transform. No display-only offset is applied.
  if (map) {
    return worldToDisplayPercent(
      rack.x,
      rack.y,
      meta,
      sourceWidth,
      sourceHeight,
      rotatePortrait,
    );
  }

  // The generalized fractions exist only for the synthetic demo canvas.
  if (rack.screenXFrac !== undefined && rack.screenYFrac !== undefined) {
    return {
      left: `${rack.screenXFrac * 100}%`,
      top: `${rack.screenYFrac * 100}%`,
    };
  }

  return worldToDisplayPercent(rack.x, rack.y, meta, sourceWidth, sourceHeight, false);
}

export default function MapView({ map, meta, mapName, robots, racks, events }: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [surfaceSize, setSurfaceSize] = useState<SurfaceSize>({ width: 0, height: 0 });

  const sourceWidth = map?.width ?? DEMO_MAP_SIZE.width;
  const sourceHeight = map?.height ?? DEMO_MAP_SIZE.height;
  const rotatePortrait = Boolean(map && map.height > map.width);
  const renderAspect = map
    ? (rotatePortrait ? map.height / map.width : map.width / map.height)
    : TESTBED_RENDER_SPEC.aspectRatio;

  useEffect(() => {
    if (canvasRef.current) paintMap(canvasRef.current, map, meta);
  }, [map, meta, surfaceSize.width]);

  useEffect(() => {
    const element = stageRef.current;
    if (!element) return undefined;

    const updateSize = () => {
      setSurfaceSize(containedSurfaceSize(
        element.clientWidth,
        element.clientHeight,
        renderAspect,
      ));
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);
    return () => observer.disconnect();
  }, [renderAspect]);

  const rackMarkers = useMemo(() => racks.map((rack) => ({
    rack,
    pos: rackScreenPosition(rack, map, meta, sourceWidth, sourceHeight, rotatePortrait),
  })), [racks, map, meta, sourceWidth, sourceHeight, rotatePortrait]);

  const robotMarkers = useMemo(() => robotDockSeeds.map((seed) => {
    const liveRobot = robots.find((robot) => robot.id === seed.id);
    const robot = liveRobot ?? seed;

    return {
      robot,
      live: Boolean(liveRobot),
      pos: worldToDisplayPercent(
        robot.x,
        robot.y,
        meta,
        sourceWidth,
        sourceHeight,
        rotatePortrait,
      ),
    };
  }), [robots, meta, sourceWidth, sourceHeight, rotatePortrait]);

  const eventMarkers = useMemo(() => events.flatMap((event) => {
    const rack = racks.find((item) => item.id === event.rackId);
    if (!rack) return [];
    return [{
      event,
      pos: rackScreenPosition(rack, map, meta, sourceWidth, sourceHeight, rotatePortrait),
    }];
  }), [events, racks, map, meta, sourceWidth, sourceHeight, rotatePortrait]);

  const displayWidthM = map
    ? (rotatePortrait ? sourceHeight : sourceWidth) * meta.resolution
    : TESTBED_RENDER_SPEC.lengthMm / 1000;
  const pixelsPerMeter = displayWidthM > 0 ? surfaceSize.width / displayWidthM : 0;
  const amrDiameterPx = pixelsPerMeter * (TESTBED_RENDER_SPEC.amrDiameterMm / 1000);
  const rackWidthPx = pixelsPerMeter * (TESTBED_RENDER_SPEC.rackWidthMm / 1000);
  const rackHeightPx = pixelsPerMeter * (TESTBED_RENDER_SPEC.rackHeightMm / 1000);
  const robotHeadingOffset = rotatePortrait ? -Math.PI / 2 : 0;

  return (
    <section className="map-card">
      <div className="map-card-header">
        <div><span className="status-dot" />SECURITY MAP</div>
        <div>{mapName}</div>
      </div>

      <div ref={stageRef} className="map-stage" style={{ display: 'grid', placeItems: 'center' }}>
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
              const rotation = ((rack.screenRotateDeg ?? 0) + 90) % 360;
              const lightOnLeft = rotation === 180;

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
                  title={`${rack.id} · ${rack.state} · ${rotation}°`}
                >
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      width: `${rackWidthPx}px`,
                      height: `${rackHeightPx}px`,
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
                      left: lightOnLeft ? 'auto' : `${rackWidthPx / 2 + 5}px`,
                      right: lightOnLeft ? `${rackWidthPx / 2 + 5}px` : 'auto',
                      top: '0',
                      transform: 'translateY(-50%)',
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
              <div
                key={event.id}
                className={`event-marker ${event.severity ? `l${event.severity}` : ''}`}
                style={pos}
              >
                <span className="event-triangle">!</span>
                <div><strong>{event.type}</strong><small>{event.rackId}</small></div>
              </div>
            ))}

            {robotMarkers.map(({ robot, pos, live }) => {
              const radarSize = amrDiameterPx * 1.55;
              const headingLength = amrDiameterPx * 0.95;

              return (
                <div
                  key={robot.id}
                  className={`robot-marker ${robot.id}`}
                  style={{
                    ...pos,
                    width: 0,
                    height: 0,
                    opacity: live ? 1 : 0.45,
                    filter: live ? 'none' : 'grayscale(0.7)',
                  }}
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
                      transform: `rotate(${-robot.yaw + robotHeadingOffset}rad)`,
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
                    <small>
                      {live
                        ? `${robot.state} · BAT ${robot.battery}%`
                        : 'DOCK POSE · NO LIVE DATA'}
                    </small>
                  </div>
                </div>
              );
            })}

            <div className="map-label" style={{ left: '22px', bottom: '22px', top: 'auto' }}>
              SCALE LOCK · {TESTBED_RENDER_SPEC.lengthMm} × {TESTBED_RENDER_SPEC.widthMm} mm
            </div>
          </div>
        )}
      </div>

      <div className="map-footer">
        <span>RES <strong>{meta.resolution} m/px</strong></span>
        <span>ORIGIN <strong>{meta.origin[0].toFixed(3)}, {meta.origin[1].toFixed(3)}</strong></span>
        <span>CANVAS <strong>{map ? `${sourceHeight}:${sourceWidth}px` : `${TESTBED_RENDER_SPEC.lengthMm}:${TESTBED_RENDER_SPEC.widthMm}`}</strong></span>
        <span>AMR <strong>Ø{TESTBED_RENDER_SPEC.amrDiameterMm}mm</strong></span>
        <span>RACK <strong>{TESTBED_RENDER_SPEC.rackWidthMm}×{TESTBED_RENDER_SPEC.rackHeightMm}mm</strong></span>
        <span>EVENTS <strong>{events.length}</strong></span>
      </div>
    </section>
  );
}
