import { useEffect, useMemo, useRef, useState } from 'react';
import { Crosshair, Layers3, Maximize2 } from 'lucide-react';
import type { Rack, Robot } from '../data/mock';
import { worldToPercent, type MapMeta } from '../lib/coordinates';
import { loadSlamMap, type PgmImage } from '../lib/pgm';

const fallbackMeta: MapMeta = { resolution: 0.05, origin: [-3, -3.5, 0] };
const fallbackSize = { width: 200, height: 150 };

function paintMap(canvas: HTMLCanvasElement, map?: PgmImage) {
  const width = map?.width ?? 1000;
  const height = map?.height ?? 700;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  ctx.fillStyle = '#07111d';
  ctx.fillRect(0, 0, width, height);

  if (map) {
    const image = ctx.createImageData(map.width, map.height);
    for (let i = 0; i < map.pixels.length; i += 1) {
      const value = map.pixels[i];
      const offset = i * 4;
      let rgb: [number, number, number];
      if (value < 70) rgb = [49, 72, 93];
      else if (value > 220) rgb = [9, 25, 39];
      else rgb = [13, 32, 47];
      image.data[offset] = rgb[0];
      image.data[offset + 1] = rgb[1];
      image.data[offset + 2] = rgb[2];
      image.data[offset + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
  } else {
    ctx.strokeStyle = 'rgba(88, 202, 255, .12)';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 50) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    }
    for (let y = 0; y < height; y += 50) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
    }

    ctx.fillStyle = '#18293a';
    const rows = [140, 245, 440, 545];
    rows.forEach((y) => {
      for (let x = 165; x < 835; x += 92) ctx.fillRect(x, y, 58, 55);
    });
    ctx.strokeStyle = '#355067';
    ctx.lineWidth = 12;
    ctx.strokeRect(70, 70, width - 140, height - 140);
    ctx.strokeStyle = 'rgba(50, 183, 255, .15)';
    ctx.lineWidth = 2;
    ctx.strokeRect(90, 90, width - 180, height - 180);
  }

  const gradient = ctx.createRadialGradient(width / 2, height / 2, 50, width / 2, height / 2, width / 1.4);
  gradient.addColorStop(0, 'rgba(31, 171, 255, .04)');
  gradient.addColorStop(1, 'rgba(3, 8, 17, .44)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
}

export default function MapView({ robots, racks }: { robots: Robot[]; racks: Rack[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [meta, setMeta] = useState(fallbackMeta);
  const [size, setSize] = useState(fallbackSize);
  const [map, setMap] = useState<PgmImage>();
  const [source, setSource] = useState<'mock' | 'slam'>('mock');

  useEffect(() => {
    loadSlamMap().then(({ image, meta: loadedMeta }) => {
      setMap(image);
      setMeta(loadedMeta);
      setSize({ width: image.width, height: image.height });
      setSource('slam');
    }).catch(() => setSource('mock'));
  }, []);

  useEffect(() => {
    if (canvasRef.current) paintMap(canvasRef.current, map);
  }, [map]);

  const rackMarkers = useMemo(() => racks.map((rack) => ({ rack, pos: worldToPercent(rack.x, rack.y, meta, size.width, size.height) })), [racks, meta, size]);
  const robotMarkers = useMemo(() => robots.map((robot) => ({ robot, pos: worldToPercent(robot.x, robot.y, meta, size.width, size.height) })), [robots, meta, size]);

  return (
    <section className="map-panel panel">
      <div className="map-toolbar">
        <div>
          <span className="eyebrow">FACILITY DIGITAL FLOOR</span>
          <h2>IDC Patrol Map</h2>
        </div>
        <div className="map-tools">
          <span className={`source-chip ${source}`}><Layers3 size={13} /> {source === 'slam' ? 'SLAM MAP' : 'STYLE PREVIEW'}</span>
          <button aria-label="center map"><Crosshair size={16} /></button>
          <button aria-label="maximize map"><Maximize2 size={16} /></button>
        </div>
      </div>

      <div className="map-stage">
        <canvas ref={canvasRef} />
        <div className="scan-line" />
        {rackMarkers.map(({ rack, pos }) => (
          <div key={rack.id} className={`rack-marker ${rack.state.toLowerCase()}`} style={pos} title={`${rack.id} · ${rack.state}`}>
            <span>{rack.id}</span>
          </div>
        ))}
        {robotMarkers.map(({ robot, pos }) => (
          <div key={robot.id} className={`robot-marker ${robot.id}`} style={{ ...pos, '--yaw': `${robot.yaw}rad` } as React.CSSProperties}>
            <div className="robot-ping" />
            <div className="robot-body"><span className="robot-arrow">▲</span></div>
            <div className="robot-label"><strong>{robot.label}</strong><small>{robot.state} · {robot.battery}%</small></div>
          </div>
        ))}
        <div className="map-legend">
          <span><i className="legend-dot normal" />Normal</span>
          <span><i className="legend-dot l2" />L2 LED</span>
          <span><i className="legend-dot l3" />L3 Door</span>
        </div>
      </div>
    </section>
  );
}
