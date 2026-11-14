// KalenderApi v1.1 (new file, not from Fire Harmony): the zero inspector (#/zero), PRD v1.1 section 6.4.
// One district, one day: every 1 km cell-day as fire detected (F), trusted zero (T, ground seen clearly), untrusted
// zero (U, cloud or smoke on every pass) or no data (N), from the NASA daily FireMask, built by
// pipeline/build_states.py (PREREGISTRATION.md, section 3), drawn over that day's NASA GIBS true-colour photo.
// Every number on screen comes from the data files. Data outside the registered period carries a ribbon that says so.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Deck, MapView, WebMercatorViewport, type Layer } from '@deck.gl/core';
import { TileLayer } from '@deck.gl/geo-layers';
import { BitmapLayer, PathLayer } from '@deck.gl/layers';
import '../styles/zero.css';

const BASE = `${import.meta.env.BASE_URL}ka-data/states/d/pulang-pisau/`;
const PHOTO = 'VIIRS_SNPP_CorrectedReflectance_TrueColor';
// MODIS/VIIRS sinusoidal grid (the grid of MOD14A1, MYD14A1, VNP14A1), as in pipeline/kapi/grid.py
const R = 6371007.181, TILE = 1111950.5197665, X0 = -20015109.354, Y0 = 10007554.677, SIZE = TILE / 1200;
const DEG_PER_PX = 0.0012;     // canvas resolution of the state layer (a cell is about 7 px wide)
const SENSOR_NAMES: Record<string, string> = { terra_modis: 'Terra (MODIS)', aqua_modis: 'Aqua (MODIS)', snpp_viirs: 'Suomi NPP (VIIRS)' };

type Letter = 'F' | 'T' | 'U' | 'N' | 'W';
interface Counts { F: number; T: number; U: number; N: number; W: number }
interface SensorInfo { id: string; has_data: boolean; reason?: string }
interface DayRow {
  date: string; k: number; cells: Counts; cells_k2: Counts; blind_share: number | null; firms_only_fire: number;
  states: string; sensors: SensorInfo[];
}
interface MonthFile { district: string; month: string; days: DayRow[] }
interface GridFile { district: string; tile: [number, number]; n_cells: number; cells: [number, number, number, number][] }
interface IndexFile {
  district: string; start: string; end: string; k: number; months: string[];
  registered_release: { tag: string; published_at: string; url?: string } | null; note: string | null;
}
interface Boundary { features: { geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: unknown } }[] }
interface Data { index: IndexFile; grid: GridFile; days: DayRow[]; corners: Float64Array; bbox: [number, number, number, number]; outline: [number, number][][] }

const pct = (x: number | null) => (x === null ? 'n/a' : `${(100 * x).toFixed(1)}%`);
const fmt = (n: number) => Math.round(n).toLocaleString('en-US');

/** The four corners (lon, lat) of every cell, 8 numbers per cell, and their box. */
function cellCorners(grid: GridFile): { corners: Float64Array; bbox: [number, number, number, number] } {
  const [h, v] = grid.tile;
  const out = new Float64Array(grid.cells.length * 8);
  let w = 180, s = 90, e = -180, n = -90;
  const ll = (row: number, col: number): [number, number] => {
    const x = X0 + h * TILE + col * SIZE;
    const y = Y0 - v * TILE - row * SIZE;
    const lat = y / R;
    return [((x / (R * Math.cos(lat))) * 180) / Math.PI, (lat * 180) / Math.PI];
  };
  grid.cells.forEach(([row, col], i) => {
    const pts = [ll(row, col), ll(row, col + 1), ll(row + 1, col + 1), ll(row + 1, col)];
    pts.forEach(([lo, la], k) => {
      out[i * 8 + k * 2] = lo;
      out[i * 8 + k * 2 + 1] = la;
      w = Math.min(w, lo); e = Math.max(e, lo); s = Math.min(s, la); n = Math.max(n, la);
    });
  });
  return { corners: out, bbox: [w, s, e, n] };
}

function outlineOf(b: Boundary): [number, number][][] {
  const g = b.features[0]?.geometry;
  if (!g) return [];
  const polys = (g.type === 'Polygon' ? [g.coordinates] : g.coordinates) as [number, number][][][];
  return polys.flatMap((p) => p);
}

function pattern(draw: (c: CanvasRenderingContext2D, size: number) => void, size: number): CanvasPattern | null {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  if (!ctx) return null;
  draw(ctx, size);
  return ctx.createPattern(c, 'repeat');
}

/** The day's states drawn on a canvas in plain lon/lat over the cells' box. */
function drawStates(d: Data, states: string): HTMLCanvasElement {
  const [w, s, e, n] = d.bbox;
  const cv = document.createElement('canvas');
  cv.width = Math.ceil((e - w) / DEG_PER_PX);
  cv.height = Math.ceil((n - s) / DEG_PER_PX);
  const ctx = cv.getContext('2d');
  if (!ctx) return cv;
  const hatch = pattern((c, p) => {
    c.fillStyle = 'rgba(16, 24, 32, 0.58)';
    c.fillRect(0, 0, p, p);
    c.strokeStyle = 'rgba(236, 242, 246, 0.95)';
    c.lineWidth = 1.6;
    c.beginPath();
    for (const o of [-p, 0, p]) { c.moveTo(o, p); c.lineTo(o + p, 0); }
    c.stroke();
  }, 7);
  const dots = pattern((c) => {
    c.fillStyle = 'rgba(210, 214, 218, 0.8)';
    c.beginPath();
    c.arc(3, 3, 1, 0, Math.PI * 2);
    c.fill();
  }, 6);
  const style: Partial<Record<Letter, string | CanvasPattern | null>> = {
    F: '#ff7a2f', T: 'rgba(255, 255, 255, 0.14)', U: hatch, N: dots,
  };
  for (const letter of ['T', 'N', 'U', 'F'] as const) {
    const fill = style[letter];
    if (!fill) continue;
    ctx.fillStyle = fill;
    ctx.beginPath();
    for (let i = 0; i < states.length; i++) {
      if (states[i] !== letter) continue;
      for (let k = 0; k < 4; k++) {
        const x = (d.corners[i * 8 + k * 2]! - w) / DEG_PER_PX;
        const y = (n - d.corners[i * 8 + k * 2 + 1]!) / DEG_PER_PX;
        if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
    }
    ctx.fill();
  }
  return cv;
}

function renderPhotoTile(props: Record<string, unknown> & { tile: unknown; data: unknown }) {
  const { boundingBox } = props.tile as { boundingBox: [[number, number], [number, number]] };
  return new BitmapLayer(props as never, {
    data: undefined, image: props.data as never, tintColor: [205, 214, 212],
    bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
  });
}

function dayFromHash(): string | null {
  const q = window.location.hash.split('?')[1];
  const d = q ? new URLSearchParams(q).get('d') : null;
  return d && /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null;
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export function Zero() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [showPhoto, setShowPhoto] = useState(true);
  const [showStates, setShowStates] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const deck = useRef<Deck<MapView> | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      const index = await getJson<IndexFile>('index.json');
      const [grid, boundary, ...months] = await Promise.all([
        getJson<GridFile>('grid.json'), getJson<Boundary>('boundary.geojson'),
        ...index.months.map((m) => getJson<MonthFile>(`m/${m}.json`)),
      ]) as [GridFile, Boundary, ...MonthFile[]];
      const { corners, bbox } = cellCorners(grid);
      const days = months.flatMap((m) => m.days);
      if (!live) return;
      setData({ index, grid, days, corners, bbox, outline: outlineOf(boundary) });
      const want = dayFromHash();
      const at = want ? days.findIndex((d) => d.date === want) : -1;
      setIdx(at >= 0 ? at : 0);
    })().catch((e: unknown) => { if (live) setError(String(e instanceof Error ? e.message : e)); });
    return () => { live = false; };
  }, []);

  // the map, fitted to the district once the data is in
  useEffect(() => {
    if (!data || !box.current) return;
    const el = box.current;
    const [w, s, e, n] = data.bbox;
    const vp = new WebMercatorViewport({ width: el.clientWidth || 800, height: el.clientHeight || 600 })
      .fitBounds([[w, s], [e, n]], { padding: { top: 40, bottom: 130, left: Math.min(400, el.clientWidth * 0.45), right: 40 } });
    const d = new Deck<MapView>({
      parent: el, views: new MapView({ repeat: false }), controller: true,
      initialViewState: { longitude: vp.longitude, latitude: vp.latitude, zoom: vp.zoom, pitch: 0, bearing: 0 },
      layers: [],
    });
    deck.current = d;
    return () => { d.finalize(); deck.current = null; };
  }, [data]);

  const day = data?.days[idx] ?? null;
  const statesCanvas = useMemo(() => (data && day ? drawStates(data, day.states) : null), [data, day]);

  useEffect(() => {
    const d = deck.current;
    if (!d || !data || !day) return;
    const [w, s, e, n] = data.bbox;
    const layers: Layer[] = [];
    layers.push(new TileLayer({
      id: `photo-${day.date}`, visible: showPhoto,
      data: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${PHOTO}/default/${day.date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
      minZoom: 0, maxZoom: 9, tileSize: 256, extent: [w - 0.5, s - 0.5, e + 0.5, n + 0.5],
      renderSubLayers: renderPhotoTile as never,
    }));
    if (statesCanvas) {
      layers.push(new BitmapLayer({
        id: `states-${day.date}`, image: statesCanvas, bounds: [w, s, e, n], visible: showStates,
        textureParameters: { minFilter: 'linear', magFilter: 'nearest' },
      }));
    }
    layers.push(new PathLayer<[number, number][]>({
      id: 'outline', data: data.outline, getPath: (x) => x, getColor: [143, 227, 208, 220], getWidth: 1.5,
      widthUnits: 'pixels',
    }));
    d.setProps({ layers });
  }, [data, day, statesCanvas, showPhoto, showStates]);

  const go = useCallback((i: number) => {
    if (!data) return;
    const j = Math.max(0, Math.min(data.days.length - 1, i));
    setIdx(j);
    const date = data.days[j]?.date;
    if (date) window.history.replaceState(null, '', `#/zero?d=${date}`);
  }, [data]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') { e.preventDefault(); go(idx - 1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); go(idx + 1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, idx]);

  const dev = data ? !data.index.registered_release : false;
  const c = day?.cells;

  return (
    <div className="ka-zero">
      <div ref={box} className="ka-zero-canvas" aria-hidden="true" />
      <section className="ka-zero-panel" aria-label="The day shown">
        <div className="ka-zero-top">
          <a className="ka-zero-brand" href="#/story">KalenderApi</a>
          <a href="#/calendar">District calendar</a>
          <a href="#/season">Play the season</a>
          <a href="#/?area=state:IDN-1931&tab=calendar">Explorer</a>
        </div>
        {dev ? (
          <p className="ka-zero-ribbon" role="note">
            <b>Development data, not a result.</b>
            {data?.index.start.slice(0, 7)} is outside the pre-registered season (August to October 2019). The registered
            analysis appears here after the plan is published.
          </p>
        ) : null}
        {error ? <p className="ka-zero-error" role="alert">The data could not be loaded ({error}).</p> : null}
        {!data || !day || !c ? (!error ? <p className="ka-zero-kicker" role="status">Loading the cell-days...</p> : null) : (
          <>
            <p className="ka-zero-kicker">Zero inspector . {data.index.district}</p>
            <h1 className="ka-zero-title"><time dateTime={day.date}>{day.date}</time></h1>
            <p className="ka-zero-q">What could the satellites see? {fmt(data.grid.n_cells)} cells of about 1 km.</p>
            <ul className="ka-zero-states">
              <li><span className="ka-zero-sw ka-zero-sw-F" aria-hidden="true" /><span>Fire detected<small>a satellite saw at least one hotspot</small></span><span className="num">{fmt(c.F)}</span></li>
              <li><span className="ka-zero-sw ka-zero-sw-T" aria-hidden="true" /><span>Trusted zero<small>no hotspot, ground seen clearly</small></span><span className="num">{fmt(c.T)}</span></li>
              <li><span className="ka-zero-sw ka-zero-sw-U" aria-hidden="true" /><span>Untrusted zero<small>no hotspot, cloud or smoke on every pass</small></span><span className="num">{fmt(c.U)}</span></li>
              <li><span className="ka-zero-sw ka-zero-sw-N" aria-hidden="true" /><span>No data<small>no usable look</small></span><span className="num">{fmt(c.N)}</span></li>
            </ul>
            <div className="ka-zero-blind">
              Zeros never seen: <span className="big">{pct(day.blind_share)}</span>
              <small>untrusted ÷ (trusted + untrusted), one clear satellite is enough</small>
              <small>with at least two clear satellites: {pct((c2 => (c2.T + c2.U ? c2.U / (c2.T + c2.U) : null))(day.cells_k2))}</small>
              <small>{fmt(c.W)} water cells left out</small>
            </div>
            <ul className="ka-zero-sensors" aria-label="Satellites in this day">
              {day.sensors.map((s) => (
                <li key={s.id} className={s.has_data ? '' : 'off'}>
                  {s.has_data ? 'Has data' : 'No data'}: {SENSOR_NAMES[s.id] ?? s.id}
                  {!s.has_data && s.id === 'snpp_viirs' ? ' (VIIRS file not downloaded yet)' : ''}
                </li>
              ))}
            </ul>
            <div className="ka-zero-toggles">
              <button type="button" aria-pressed={showStates} onClick={() => setShowStates((v) => !v)}>Cell states</button>
              <button type="button" aria-pressed={showPhoto} onClick={() => setShowPhoto((v) => !v)}>NASA photo</button>
            </div>
            <p className="ka-zero-src">
              States: NASA MOD14A1 and MYD14A1 v6.1 daily FireMask (public copy on Microsoft Planetary Computer), with
              VNP14A1 where available. A daily mask keeps the highest class of all passes, night included. Photo: NASA GIBS
              VIIRS true colour of the same day. Boundary: geoBoundaries (BPS, WFP, OCHA ROAP), CC BY 3.0 IGO.
            </p>
          </>
        )}
      </section>

      {data ? (
        <section className="ka-zero-dock" aria-label="Days">
          <div className="ka-zero-dock-head">
            <span>Each bar is one day: fire, trusted zero, untrusted zero, no data</span>
            <span>Left and right arrows: one day</span>
          </div>
          <div className="ka-zero-strip">
            {data.days.map((d, i) => {
              const k = d.cells;
              const total = k.F + k.T + k.U + k.N || 1;
              return (
                <button key={d.date} type="button" className="ka-zero-bar" aria-current={i === idx ? 'date' : undefined}
                  aria-label={`${d.date}: ${pct(d.blind_share)} of zeros never seen`} onClick={() => go(i)}>
                  {(['F', 'T', 'U', 'N'] as const).map((L) => (
                    <span key={L} className={L} style={{ height: `${(100 * k[L]) / total}%` }} />
                  ))}
                </button>
              );
            })}
          </div>
          <div className="ka-zero-axis"><span>{data.days[0]?.date}</span><span>{data.days[data.days.length - 1]?.date}</span></div>
        </section>
      ) : null}
    </div>
  );
}
