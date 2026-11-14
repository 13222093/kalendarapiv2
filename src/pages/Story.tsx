// KalenderApi (new file, not from Fire Harmony): the cinematic landing "Under the Smoke".
// Real data only: harmonized hotspots per level 4 hexagon from the same files the explorer reads (mapData.ts), and
// NASA GIBS Suomi NPP VIIRS true-colour photos of two days. Nothing is interpolated or invented.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Deck, FlyToInterpolator, MapView } from '@deck.gl/core';
import { H3HexagonLayer, TileLayer } from '@deck.gl/geo-layers';
import { BitmapLayer } from '@deck.gl/layers';
import { cellToLatLng } from 'h3-js';
import { loadFrame, loadUniverse } from '../components/explorer/mapData';

const CLEAR_DAY = '2019-08-12';
const SMOKY_DAY = '2019-09-15';
const MONTH_A = 201908;
const MONTH_B = 201909;
const BORNEO = { w: 108.5, s: -4.6, e: 119.5, n: 4.6 };
const FAR = { longitude: 116, latitude: -1, zoom: 3.4, pitch: 0, bearing: 0 };
const NEAR = { longitude: 112.6, latitude: -1.6, zoom: 5.7, pitch: 52, bearing: -14 };
// VIIRS true colour: a 3000 km swath leaves fewer black gaps between passes than MODIS over Borneo
const PHOTO_LAYER = 'VIIRS_SNPP_CorrectedReflectance_TrueColor';

interface Hex { h3: string; a: number; b: number }

function gibs(date: string, id: string, opacity: number) {
  return new TileLayer({
    id, opacity,
    data: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${PHOTO_LAYER}/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
    minZoom: 0, maxZoom: 9, tileSize: 256,
    renderSubLayers: (props) => {
      const { boundingBox } = props.tile as unknown as { boundingBox: [[number, number], [number, number]] };
      return new BitmapLayer(props, {
        data: undefined, image: props.data as never,
        bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
      });
    },
  });
}

const BEATS = [
  { t: 0, title: 'Borneo, Indonesia.', body: 'Twenty-five years of satellite fire records start here.' },
  { t: 3.2, title: 'August 2019. The satellites see the fires.', body: '{a} harmonized hotspots across these hexagons.' },
  { t: 7.5, title: 'September 2019. Smoke covers the peat.', body: 'The record still counts {b} hotspots. The photo of 15 September shows smoke over much of the peat: where the ground is hidden, a low count does not mean nothing burned.' },
  { t: 12, title: 'A zero is not always a zero.', body: 'Under smoke or cloud, a zero can mean the ground was hidden. KalenderApi puts each day\'s NASA photo under that day\'s hotspots, so you can see where.' },
];
const END = 14;

function fmt(n: number) { return Math.round(n).toLocaleString('en-US'); }

export function Story() {
  const box = useRef<HTMLDivElement>(null);
  const deck = useRef<Deck<MapView> | null>(null);
  const [hexes, setHexes] = useState<Hex[] | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const reduced = useMemo(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false, []);

  // real hexagons of Borneo for the two months
  useEffect(() => {
    let live = true;
    Promise.all([loadUniverse(4), loadFrame(4, MONTH_A), loadFrame(4, MONTH_B)]).then(([u, fa, fb]) => {
      const out: Hex[] = [];
      u.h3.forEach((h3, i) => {
        const a = fa.h[i] || 0, b = fb.h[i] || 0;
        if (a <= 0 && b <= 0) return;
        const [lat, lng] = cellToLatLng(h3);
        if (lng < BORNEO.w || lng > BORNEO.e || lat < BORNEO.s || lat > BORNEO.n) return;
        out.push({ h3, a, b });
      });
      if (live) setHexes(out);
    }).catch(() => { if (live) setHexes([]); });
    return () => { live = false; };
  }, []);

  const totals = useMemo(() => hexes ? {
    a: hexes.reduce((s, x) => s + x.a, 0), b: hexes.reduce((s, x) => s + x.b, 0),
  } : null, [hexes]);

  // the clock
  useEffect(() => {
    if (reduced) { setT(END); return; }
    if (!playing || !hexes) return;
    let raf = 0; const start = performance.now() - t * 1000;
    const tick = (now: number) => {
      const s = (now - start) / 1000;
      setT(Math.min(s, END));
      if (s < END) raf = requestAnimationFrame(tick); else setPlaying(false);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, hexes, reduced]); // eslint-disable-line react-hooks/exhaustive-deps

  // deck.gl, created once
  useEffect(() => {
    if (!box.current) return;
    const d = new Deck<MapView>({
      parent: box.current, views: new MapView({ repeat: false }), controller: false,
      initialViewState: reduced ? NEAR : FAR, layers: [],
      style: { position: 'absolute', inset: '0' },
    });
    deck.current = d;
    return () => { d.finalize(); deck.current = null; };
  }, [reduced]);

  // camera: fly in at 0.4 s, then a slow orbit
  const flown = useRef(false);
  useEffect(() => {
    const d = deck.current;
    if (!d || reduced) return;
    if (t > 0.4 && !flown.current) {
      flown.current = true;
      d.setProps({ initialViewState: { ...NEAR, transitionDuration: 2800, transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }) } });
    }
    if (t >= 3.4) {
      d.setProps({ initialViewState: { ...NEAR, bearing: NEAR.bearing + (t - 3.4) * 2.2 } });
    }
  }, [t, reduced]);

  // layers for the current time
  useEffect(() => {
    const d = deck.current;
    if (!d || !hexes) return;
    const grow = (from: number, dur: number) => Math.max(0, Math.min(1, (t - from) / dur));
    const smoke = grow(7.2, 1.6);
    const riseA = grow(3.2, 1.8) * (1 - smoke);
    const riseB = smoke;
    d.setProps({
      layers: [
        gibs(CLEAR_DAY, 'clear', 1 - smoke * 0.999),
        gibs(SMOKY_DAY, 'smoky', smoke),
        new H3HexagonLayer<Hex>({
          id: 'fires', data: hexes, getHexagon: (x) => x.h3, extruded: true, coverage: 0.86,
          elevationScale: 1, opacity: 0.78, wireframe: false, pickable: false,
          getElevation: (x) => Math.sqrt(riseA * x.a + riseB * x.b) * 650,
          getFillColor: (x) => {
            const v = riseA * x.a + riseB * x.b;
            return v > 2000 ? [255, 214, 120, 235] : v > 400 ? [244, 140, 60, 225] : v > 60 ? [210, 80, 35, 210] : [140, 40, 30, 190];
          },
          material: { ambient: 0.55, diffuse: 0.6, shininess: 24 },
          updateTriggers: { getElevation: [riseA, riseB], getFillColor: [riseA, riseB] },
        }),
      ],
    });
  }, [t, hexes]);

  const beat = [...BEATS].reverse().find((b) => t >= b.t) ?? BEATS[0];
  const body = totals ? beat.body.replace('{a}', fmt(totals.a)).replace('{b}', fmt(totals.b)) : beat.body;
  const done = t >= END;

  return (
    <div className="ka-story">
      <div ref={box} className="ka-story-canvas" aria-hidden="true" />
      <div className="ka-story-vignette" />
      <header className="ka-story-top">
        <a className="ka-story-brand" href="#/">KalenderApi</a>
        <span className="ka-story-tag">Indonesian for "fire calendar" . NASA Space Apps 2026</span>
        <a className="ka-story-skip" href="#/zero">Skip story</a>
      </header>
      <section className="ka-story-copy" aria-live="polite">
        <p className="ka-story-kicker">{done ? 'How much can you trust a zero?' : `${Math.min(BEATS.indexOf(beat) + 1, 4)} / 4`}</p>
        <h1 key={beat.title}>{beat.title}</h1>
        <p key={body} className="ka-story-body">{hexes === null ? 'Loading real hotspot data...' : body}</p>
        {done && (
          <div className="ka-story-cta">
            {/* KalenderApi v1.1 (user flow): the main step after the story is the zero inspector, our core view */}
            <a className="ka-btn-primary" href="#/zero">Inspect every zero, cell by cell</a>
            <a className="ka-btn-ghost" style={{ textDecoration: 'none' }} href="#/season">Play the season</a>
            <a className="ka-btn-ghost" style={{ textDecoration: 'none' }} href="#/?area=state:IDN-1931&month=201909&tab=calendar">Explore the map</a>
            <button type="button" className="ka-btn-ghost" onClick={() => { flown.current = false; deck.current?.setProps({ initialViewState: FAR }); setT(0); setPlaying(true); }}>Replay</button>
          </div>
        )}
      </section>
      <footer className="ka-story-foot">
        Hexagons: harmonized hotspots per month (NASA FIRMS MODIS and VIIRS, Fire Harmony v1.0, CC BY 4.0), height grows with count.
        Imagery: NASA GIBS / Worldview, Suomi NPP VIIRS true colour, {CLEAR_DAY} and {SMOKY_DAY}.
      </footer>
      <div className="ka-story-progress" style={{ width: `${(t / END) * 100}%` }} />
    </div>
  );
}
