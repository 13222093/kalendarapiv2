// KalenderApi v1.1 (new file, not from Fire Harmony): the district calendar (#/calendar), PRD v1.1 section 6.3.
// One row per year, one tile per month: colour = fire cell-days, hatching = share of zero-fire cell-days that no
// satellite saw clearly (cloud or smoke on every pass). Built by pipeline/build_calendar.py from the NASA daily
// FireMask. Months inside the pre-registered period stay locked until the plan is published. Every number on screen
// comes from the data file.
import { useEffect, useMemo, useState } from 'react';
import '../styles/calendar.css';

const BASE = `${import.meta.env.BASE_URL}ka-data/states/d/pulang-pisau/`;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

interface MonthOk {
  ym: string; locked: false; days: number; F: number; T: number; U: number; N: number; blind_share: number | null;
  sensor_days: Record<string, number>;
}
interface MonthLocked { ym: string; locked: true }
type Month = MonthOk | MonthLocked;
interface CalendarFile {
  district: string; k: number; years: number[]; water_ref: [string, string]; water_cells: number; cells: number;
  fire_unit: string; exploratory: boolean; registered_release: { tag: string; published_at: string } | null; months: Month[];
}
interface IndexFile { months: string[] }

const fmt = (n: number) => Math.round(n).toLocaleString('en-US');
const pct = (x: number | null) => (x === null ? 'n/a' : `${(100 * x).toFixed(1)}%`);
const monthName = (ym: string) => `${LONG[Number(ym.slice(5, 7)) - 1] ?? ''} ${ym.slice(0, 4)}`;
const hatch = (b: number | null) => (b === null || b < 0.1 ? '' : b <= 0.4 ? 'h1' : 'h2');

export function Calendar() {
  const [cal, setCal] = useState<CalendarFile | null>(null);
  const [daily, setDaily] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetch(`${BASE}calendar.json`).then((r) => { if (!r.ok) throw new Error(`calendar.json: HTTP ${r.status}`); return r.json() as Promise<CalendarFile>; }),
      fetch(`${BASE}index.json`).then((r) => (r.ok ? (r.json() as Promise<IndexFile>) : { months: [] })),
    ]).then(([c, idx]) => {
      if (!live) return;
      setCal(c);
      setDaily(new Set(idx.months));
      const ok = c.months.filter((m): m is MonthOk => !m.locked);
      const top = ok.reduce<MonthOk | null>((a, m) => (!a || m.F > a.F ? m : a), null);
      setSel(top?.ym ?? null);
    }).catch((e: unknown) => { if (live) setError(String(e instanceof Error ? e.message : e)); });
    return () => { live = false; };
  }, []);

  const byYm = useMemo(() => new Map((cal?.months ?? []).map((m) => [m.ym, m])), [cal]);
  const maxF = useMemo(() => Math.max(1, ...(cal?.months ?? []).map((m) => (m.locked ? 0 : m.F))), [cal]);
  const level = (f: number) => (f <= 0 ? 0 : Math.max(1, Math.min(5, Math.ceil((5 * Math.log1p(f)) / Math.log1p(maxF)))));
  const selected = sel ? byYm.get(sel) ?? null : null;
  const anyLocked = cal?.months.some((m) => m.locked) ?? false;

  return (
    <div className="ka-cal">
      <div className="ka-cal-top">
        <a className="ka-cal-brand" href="#/story">KalenderApi</a>
        <a href="#/zero">Zero inspector</a>
        <a href="#/season">Play the season</a>
        <a href="#/?area=state:IDN-1931&tab=calendar">Explore the map</a>
      </div>
      {cal?.exploratory ? (
        <p className="ka-cal-ribbon" role="note">
          Exploratory view, not a pre-registered result. Fire is counted in cell-days from MODIS Terra and Aqua and is not
          harmonized yet.{anyLocked ? ' 2019 stays locked here: its numbers come from the pre-registered analysis, with Suomi NPP included.' : ''}
        </p>
      ) : null}
      <p className="ka-cal-kicker">District calendar . {cal?.district ?? 'Pulang Pisau'}</p>
      <h1 className="ka-cal-title">When does this district burn, and when can its zeros be trusted?</h1>
      <p className="ka-cal-sub">
        Each tile is one month. Colour shows fire cell-days. Hatching shows the share of zero-fire cell-days that no
        satellite saw clearly, because cloud or smoke covered every pass.
      </p>
      {error ? <p className="ka-cal-error" role="alert">The calendar could not be loaded ({error}). It is built by pipeline/build_calendar.py.</p> : null}
      {!cal ? (!error ? <p role="status">Loading the calendar...</p> : null) : (
        <div className="ka-cal-body">
          <div>
            <div className="ka-cal-grid" role="grid" aria-label={`Fire and trusted zeros by month, ${cal.district}`}>
              <span className="ka-cal-head" />
              {MONTHS.map((m) => <span key={m} className="ka-cal-head">{m}</span>)}
              <span className="ka-cal-head">Fire cell-days</span>
              {cal.years.map((y) => {
                const row = MONTHS.map((_, i) => byYm.get(`${y}-${String(i + 1).padStart(2, '0')}`) ?? null);
                const allLocked = row.every((m) => m?.locked);
                const total = row.reduce((s, m) => s + (m && !m.locked ? m.F : 0), 0);
                return (
                  <div key={y} role="row" style={{ display: 'contents' }}>
                    <span className="ka-cal-year" role="rowheader">{y}</span>
                    {allLocked ? (
                      <span className="ka-cal-lockrow ka-cal-tile locked" role="gridcell">
                        Locked: {y} is the pre-registered season. Its numbers come from the registered analysis.
                      </span>
                    ) : row.map((m, i) => {
                      const ym = `${y}-${String(i + 1).padStart(2, '0')}`;
                      if (!m) return <span key={ym} className="ka-cal-tile missing" role="gridcell" aria-label={`${monthName(ym)}: not built`} />;
                      if (m.locked) return <span key={ym} className="ka-cal-tile locked" role="gridcell" aria-label={`${monthName(ym)}: locked`} />;
                      const cls = `ka-cal-tile f${level(m.F)} ${hatch(m.blind_share)}`;
                      return (
                        <button key={ym} type="button" role="gridcell" className={cls} aria-pressed={sel === ym}
                          aria-label={`${monthName(ym)}: ${fmt(m.F)} fire cell-days, ${pct(m.blind_share)} of zeros never seen`}
                          title={`${monthName(ym)}: ${fmt(m.F)} fire cell-days, ${pct(m.blind_share)} of zeros never seen`}
                          onClick={() => setSel(ym)} />
                      );
                    })}
                    <span className="ka-cal-total">{allLocked ? 'locked' : fmt(total)}</span>
                  </div>
                );
              })}
            </div>
            <div className="ka-cal-legend" aria-label="Legend">
              <span>Fire cell-days
                <span className="ka-cal-ramp" aria-hidden="true">
                  {['#fbe3a0', '#f4ae55', '#df7230', '#b0401f', '#6a1c17'].map((c) => <i key={c} style={{ background: c }} />)}
                </span>
                (log scale)
              </span>
              <span><i className="ka-cal-sw" aria-hidden="true" />no fire</span>
              <span><i className="ka-cal-sw ka-cal-tile f0 h1" style={{ height: 14 }} aria-hidden="true" />10 to 40% of zeros unseen</span>
              <span><i className="ka-cal-sw ka-cal-tile f0 h2" style={{ height: 14 }} aria-hidden="true" />over 40% unseen</span>
              {anyLocked ? <span><i className="ka-cal-sw ka-cal-tile locked" style={{ height: 14 }} aria-hidden="true" />locked (pre-registered)</span> : null}
            </div>
          </div>
          <aside className="ka-cal-panel" aria-live="polite">
            {selected && !selected.locked ? (
              <>
                <h2>{monthName(selected.ym)}</h2>
                <dl>
                  <dt>Fire cell-days</dt><dd className="big">{fmt(selected.F)}</dd>
                  <dt>Zeros never seen</dt><dd className="big">{pct(selected.blind_share)}</dd>
                  <dt>Trusted zero cell-days</dt><dd>{fmt(selected.T)}</dd>
                  <dt>Untrusted zero cell-days</dt><dd>{fmt(selected.U)}</dd>
                  <dt>No-data cell-days</dt><dd>{fmt(selected.N)}</dd>
                  <dt>Days with Terra / Aqua / S-NPP</dt>
                  <dd>{selected.sensor_days.terra_modis ?? 0} / {selected.sensor_days.aqua_modis ?? 0} / {selected.sensor_days.snpp_viirs ?? 0}</dd>
                </dl>
                {daily.has(selected.ym) ? (
                  <a className="ka-cal-open" href={`#/zero?d=${selected.ym}-01`}>Open this month in the zero inspector</a>
                ) : (
                  <small>Day-by-day cells for this month are not built yet; the zero inspector has {[...daily].map(monthName).join(', ') || 'no month'}.</small>
                )}
                <small>
                  {fmt(cal.cells)} cells of about 1 km; {fmt(cal.water_cells)} water cells left out (water mask from
                  {' '}{cal.water_ref[0].slice(0, 4)}). "Never seen" = untrusted ÷ (trusted + untrusted), with k = {cal.k}.
                </small>
              </>
            ) : <p>Pick a month.</p>}
          </aside>
        </div>
      )}
      <p className="ka-cal-src">
        Source: NASA MOD14A1 and MYD14A1 v6.1 daily FireMask (public copy on Microsoft Planetary Computer). A daily mask
        keeps the highest class of all passes, night included. Fire cell-days are not added across sensors: a cell-day is
        fire if any sensor saw fire. District boundary: geoBoundaries (BPS, WFP, OCHA ROAP), CC BY 3.0 IGO.
      </p>
    </div>
  );
}
