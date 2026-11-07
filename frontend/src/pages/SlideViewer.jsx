import { useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowLeft, Loader2, RefreshCw, Search, Trash2 } from 'lucide-react';
import { api, apiUrl, fmtBytes, fmtDate, fmtInt, getAdminKey, patchMicrons } from '../api';
import { navigate } from '../router';
import ResultGrid from '../components/ResultGrid.jsx';

const STATUS_TEXT = { queued: 'Waiting to index', processing: 'Indexing', done: 'Indexed', failed: 'Failed' };

export default function SlideViewer({ slideId, params, health }) {
  const [slide, setSlide] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [showCoverage, setShowCoverage] = useState(true);
  const [error, setError] = useState('');
  const [spot, setSpot] = useState(null); // {x, y}
  const [search, setSearch] = useState({ loading: false, error: '', results: null, source: null });
  const [busyAction, setBusyAction] = useState('');
  const [pollKey, setPollKey] = useState(0);
  const imgRef = useRef(null);
  const requestId = useRef(0);

  // Slide record, polled while it is being indexed
  useEffect(() => {
    let alive = true;
    let timer;
    const load = async () => {
      try {
        const s = await api.getSlide(slideId);
        if (!alive) return;
        setSlide(s);
        setError('');
        if (s.status === 'queued' || s.status === 'processing') timer = setTimeout(load, 2000);
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [slideId, pollKey]);

  // Where the indexed patches are
  useEffect(() => {
    if (!slide || !slide.width) return;
    api.slidePatches(slideId).then(setCoverage).catch(() => setCoverage(null));
  }, [slideId, slide?.width, slide?.status, slide?.patches_indexed]);

  // Spot passed in the URL ("Show on slide")
  const px = params.get('x');
  const py = params.get('y');
  useEffect(() => {
    if (px != null && py != null) {
      setSpot({ x: Number(px), y: Number(py) });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [px, py, slideId]);

  const size0 = slide?.patch_size0 || 256;

  const pickSpot = (e) => {
    if (!slide?.width || !imgRef.current) return;
    const r = imgRef.current.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width;
    const fy = (e.clientY - r.top) / r.height;
    // Snap to the patch grid so the spot matches an indexed patch
    const x = Math.min(Math.max(Math.floor((fx * slide.width) / size0) * size0, 0), Math.max(slide.width - size0, 0));
    const y = Math.min(Math.max(Math.floor((fy * slide.height) / size0) * size0, 0), Math.max(slide.height - size0, 0));
    setSpot({ x, y });
    setSearch({ loading: false, error: '', results: null, source: null });
  };

  const findSimilar = async (src) => {
    const id = ++requestId.current;
    setSearch({ loading: true, error: '', results: null, source: src });
    try {
      const data = await api.searchSimilar(src.slide_id, src.x, src.y);
      if (id === requestId.current) setSearch({ loading: false, error: '', results: data.results, source: src });
    } catch (e) {
      if (id === requestId.current) setSearch({ loading: false, error: e.message, results: null, source: src });
    }
  };

  const reindex = async () => {
    setBusyAction('reindex');
    try {
      const s = await api.reindexSlide(slideId);
      setSlide(s);
      setCoverage(null);
      setPollKey((k) => k + 1); // start following the new job
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyAction('');
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete ${slide.filename}? Its file and all its indexed patches will be removed.`)) return;
    setBusyAction('delete');
    try {
      await api.deleteSlide(slideId);
      navigate('/slides');
    } catch (e) {
      setError(e.message);
      setBusyAction('');
    }
  };

  if (error && !slide) {
    return (
      <div className="viewer">
        <a className="back" href="#/slides"><ArrowLeft size={16} /> All slides</a>
        <p className="error"><AlertCircle size={16} /> {error}</p>
      </div>
    );
  }
  if (!slide) return <p className="note"><Loader2 size={16} className="spin" /> Loading slide…</p>;

  const busy = slide.status === 'queued' || slide.status === 'processing';
  const pct = Math.round((slide.progress || 0) * 100);
  const microns = patchMicrons(slide);
  const ready = health && health.model_ready;
  // On a public site, only people with the admin key see Re-index / Delete
  const canManage = !(health && health.read_only) || Boolean(getAdminKey());

  return (
    <div className="viewer">
      <a className="back" href="#/slides"><ArrowLeft size={16} /> All slides</a>

      <div className="viewer-grid">
        <section className="stage" aria-label="Slide">
          {slide.thumbnail_url ? (
            <div className="stage-frame">
              <img
                ref={imgRef}
                src={apiUrl(slide.thumbnail_url)}
                alt={`Overview of ${slide.filename}`}
                className="stage-img"
                onClick={pickSpot}
              />
              {slide.width ? (
                <svg
                  className="stage-overlay"
                  viewBox={`0 0 ${slide.width} ${slide.height}`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  {showCoverage && coverage?.coords.map(([x, y]) => (
                    <rect key={`${x}-${y}`} x={x} y={y} width={size0} height={size0} className="cov" />
                  ))}
                  {spot && (() => {
                    const unit = Math.max(slide.width, slide.height);
                    const cx = spot.x + size0 / 2;
                    const cy = spot.y + size0 / 2;
                    const ring = Math.max(size0 * 2, unit / 45);
                    const sw = unit / 400;
                    return (
                      <g key={`spot-${spot.x}-${spot.y}`} className="spot" style={{ strokeWidth: sw }}>
                        <rect x={spot.x} y={spot.y} width={size0} height={size0} />
                        <circle cx={cx} cy={cy} r={ring} fill="none" />
                        <line x1={cx - ring * 1.6} y1={cy} x2={cx - ring} y2={cy} />
                        <line x1={cx + ring} y1={cy} x2={cx + ring * 1.6} y2={cy} />
                        <line x1={cx} y1={cy - ring * 1.6} x2={cx} y2={cy - ring} />
                        <line x1={cx} y1={cy + ring} x2={cx} y2={cy + ring * 1.6} />
                      </g>
                    );
                  })()}
                </svg>
              ) : null}
            </div>
          ) : (
            <div className="stage-empty">{busy ? 'Preparing the slide overview…' : 'No overview available'}</div>
          )}
          <div className="stage-tools">
            <label className="toggle">
              <input type="checkbox" checked={showCoverage} onChange={(e) => setShowCoverage(e.target.checked)} />
              Show indexed patches
            </label>
            <span className="muted">Click the tissue to pick a spot.</span>
          </div>
        </section>

        <aside className="facts" aria-label="Slide details">
          <h1 className="facts-title" title={slide.filename}>{slide.filename}</h1>
          <p className={`slide-status status-${slide.status}`}>
            {STATUS_TEXT[slide.status] || slide.status}{busy ? ` ${pct}%` : ''}
          </p>
          {busy && (
            <span className="progress"><span className="progress-bar" style={{ width: `${Math.max(pct, 3)}%` }} /></span>
          )}
          {slide.status === 'failed' && <p className="error"><AlertCircle size={16} /> {slide.error}</p>}
          {error && <p className="error"><AlertCircle size={16} /> {error}</p>}

          <dl className="fact-list">
            <dt>Size</dt>
            <dd>{slide.width ? `${fmtInt(slide.width)} × ${fmtInt(slide.height)} px` : '–'}</dd>
            <dt>Sampled at</dt>
            <dd>{slide.magnification || '–'}</dd>
            <dt>One patch</dt>
            <dd>{microns ? `${microns} (${fmtInt(size0)} px)` : `${fmtInt(size0)} px`}</dd>
            <dt>Patches indexed</dt>
            <dd>
              {fmtInt(slide.patches_indexed)}
              {slide.tissue_cells ? ` of ${fmtInt(slide.tissue_cells)} tissue areas` : ''}
            </dd>
            <dt>File</dt>
            <dd>{fmtBytes(slide.file_size)}</dd>
            <dt>Uploaded</dt>
            <dd>{fmtDate(slide.created_at)}</dd>
          </dl>

          {spot && (
            <div className="spot-panel">
              <img
                key={`${spot.x}-${spot.y}`}
                className="spot-img"
                src={api.patchUrl(slideId, spot.x, spot.y, size0)}
                alt={`Patch at x ${spot.x}, y ${spot.y}`}
                width="256"
                height="256"
              />
              <p className="muted">x {fmtInt(spot.x)}, y {fmtInt(spot.y)}</p>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!ready || slide.status !== 'done'}
                onClick={() => findSimilar({ slide_id: slideId, x: spot.x, y: spot.y, size: size0, filename: slide.filename })}
              >
                <Search size={16} /> Find similar tissue
              </button>
            </div>
          )}

          {canManage && (
            <div className="row actions">
              <button type="button" className="btn" onClick={reindex} disabled={busy || busyAction !== ''}>
                <RefreshCw size={16} /> Re-index
              </button>
              <button type="button" className="btn btn-danger" onClick={remove} disabled={busy || busyAction !== ''}>
                <Trash2 size={16} /> Delete
              </button>
            </div>
          )}
        </aside>
      </div>

      {(search.loading || search.error || search.results) && (
        <section className="results-area" aria-live="polite">
          <h2 className="results-title">
            Regions that look like {search.source?.slide_id === slideId ? 'the selected spot' : 'this patch'}
          </h2>
          {search.loading && <p className="note"><Loader2 size={16} className="spin" /> Searching…</p>}
          {search.error && <p className="error"><AlertCircle size={16} /> {search.error}</p>}
          {search.results && search.results.length === 0 && <p className="note">No other similar patches found.</p>}
          {search.results && <ResultGrid results={search.results} mode="similar" onFindSimilar={findSimilar} />}
        </section>
      )}
    </div>
  );
}
