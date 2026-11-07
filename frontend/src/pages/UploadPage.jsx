import { useEffect, useRef, useState } from 'react';
import { AlertCircle, AlertTriangle, Loader2, Upload } from 'lucide-react';
import { api, fmtBytes, fmtInt, getAdminKey, setAdminKey } from '../api';

const DETAIL = [
  { value: 500, label: 'Quick', note: '500 patches' },
  { value: 2000, label: 'Standard', note: '2,000 patches' },
  { value: 5000, label: 'Detailed', note: '5,000 patches' },
  { value: 20000, label: 'Everything', note: 'up to 20,000' },
];

const ACCEPT = '.svs,.tif,.tiff,.ndpi,.scn,.svslide,.bif,.vsi,.dcm,.png,.jpg,.jpeg';

export default function UploadPage({ health }) {
  const [file, setFile] = useState(null);
  const [detail, setDetail] = useState(2000);
  const [phase, setPhase] = useState('idle'); // idle | uploading | indexing | done | failed
  const [sent, setSent] = useState(0);
  const [slide, setSlide] = useState(null);
  const [error, setError] = useState('');
  const [adminKey, setAdminKeyState] = useState(getAdminKey);
  const input = useRef(null);
  const needsKey = Boolean(health && health.read_only);

  // Follow the indexing job until it finishes
  useEffect(() => {
    if (phase !== 'indexing' || !slide) return undefined;
    let alive = true;
    let timer;
    const poll = async () => {
      try {
        const s = await api.getSlide(slide.id);
        if (!alive) return;
        setSlide(s);
        if (s.status === 'done') setPhase('done');
        else if (s.status === 'failed') {
          setError(s.error || 'Indexing failed');
          setPhase('failed');
        } else timer = setTimeout(poll, 1500);
      } catch {
        if (alive) timer = setTimeout(poll, 3000);
      }
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [phase, slide?.id]);

  const start = async () => {
    if (!file) return;
    setError('');
    setSent(0);
    setPhase('uploading');
    try {
      const s = await api.uploadSlide(file, detail, setSent);
      setSlide(s);
      setPhase(s.status === 'done' ? 'done' : 'indexing');
    } catch (e) {
      setError(e.message);
      setPhase('failed');
    }
  };

  const reset = () => {
    setFile(null);
    setSlide(null);
    setPhase('idle');
    setError('');
  };

  const pct = Math.round((slide?.progress || 0) * 100);

  return (
    <div className="upload-page">
      <h1 className="headline headline-small">Upload a slide</h1>
      <p className="lede">
        PathoSearch finds the tissue on your slide, cuts it into 128 µm patches at 20×, and indexes
        them so you can search them. Large whole-slide files can take a few minutes.
      </p>

      {health && !health.openslide && (
        <p className="warning">
          <AlertTriangle size={16} /> OpenSlide isn't installed on the backend, so only PNG and JPEG
          images can be read. Install it with <code>pip install openslide-python openslide-bin</code>.
        </p>
      )}

      {phase === 'idle' && (
        <>
          {needsKey && (
            <div className="admin-key">
              <label htmlFor="admin-key">Admin key</label>
              <input
                id="admin-key"
                type="password"
                className="query-input"
                value={adminKey}
                autoComplete="off"
                placeholder="Needed to upload on this public site"
                onChange={(e) => {
                  setAdminKeyState(e.target.value);
                  setAdminKey(e.target.value.trim());
                }}
              />
              <p className="hint">
                Anyone can search this library. Uploading, re-indexing and deleting need the key set on
                the server. It's saved in this browser only.
              </p>
            </div>
          )}

          <div
            className={`dropzone ${file ? 'dropzone-filled' : ''}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
            }}
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Choose a slide file"
          >
            <span className="dropzone-frost" aria-hidden="true" />
            {file ? (
              <span className="dropzone-text">
                <strong>{file.name}</strong>
                <span className="muted">{fmtBytes(file.size)}. Click to choose another file.</span>
              </span>
            ) : (
              <span className="dropzone-text">
                <strong>Drop a slide here, or click to choose one</strong>
                <span className="muted">.svs, .ndpi, .tiff, .scn, .bif, .vsi, .dcm, or PNG/JPEG</span>
              </span>
            )}
            <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </div>

          <fieldset className="detail">
            <legend>How much of the slide to index</legend>
            <div className="detail-options">
              {DETAIL.map((d) => (
                <label key={d.value} className={`detail-option ${detail === d.value ? 'detail-active' : ''}`}>
                  <input
                    type="radio"
                    name="detail"
                    value={d.value}
                    checked={detail === d.value}
                    onChange={() => setDetail(d.value)}
                  />
                  <span className="detail-label">{d.label}</span>
                  <span className="muted">{d.note}</span>
                </label>
              ))}
            </div>
            <p className="hint">Patches are spread evenly over all the tissue. More patches mean finer search but slower indexing.</p>
          </fieldset>

          <button
            className="btn btn-primary btn-large"
            type="button"
            disabled={!file || (needsKey && !adminKey.trim())}
            onClick={start}
          >
            <Upload size={18} /> Upload and index
          </button>
        </>
      )}

      {phase === 'uploading' && (
        <div className="job">
          <p><Loader2 size={16} className="spin" /> Uploading {file?.name}… {Math.round(sent * 100)}%</p>
          <span className="progress progress-large"><span className="progress-bar" style={{ width: `${Math.max(sent * 100, 2)}%` }} /></span>
        </div>
      )}

      {phase === 'indexing' && slide && (
        <div className="job">
          <p>
            <Loader2 size={16} className="spin" />{' '}
            {slide.status === 'queued' ? 'Waiting for the indexer' : `Indexing ${slide.filename}… ${pct}%`}
          </p>
          <span className="progress progress-large"><span className="progress-bar" style={{ width: `${Math.max(pct, 2)}%` }} /></span>
          {slide.patches_planned ? (
            <p className="muted">
              {fmtInt(slide.patches_indexed)} of about {fmtInt(slide.patches_planned)} patches
              {slide.tissue_cells ? `, chosen from ${fmtInt(slide.tissue_cells)} tissue areas` : ''}.
            </p>
          ) : null}
          <p className="muted">You can leave this page; indexing continues in the background.</p>
        </div>
      )}

      {phase === 'done' && slide && (
        <div className="job job-done">
          <p>
            {slide.duplicate
              ? `${slide.filename} is already in your library.`
              : `Indexed ${fmtInt(slide.patches_indexed)} patches from ${slide.filename}.`}
          </p>
          <div className="row">
            <a className="btn btn-primary" href={`#/slides/${slide.id}`}>Open slide</a>
            <a className="btn" href="#/search">Search</a>
            <button className="btn btn-quiet" type="button" onClick={reset}>Upload another</button>
          </div>
        </div>
      )}

      {phase === 'failed' && (
        <div className="job">
          <p className="error"><AlertCircle size={16} /> {error}</p>
          <button className="btn" type="button" onClick={reset}>Try another file</button>
        </div>
      )}
    </div>
  );
}
