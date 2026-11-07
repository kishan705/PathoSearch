import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Image as ImageIcon, Loader2, Search, Type, X } from 'lucide-react';
import { api, fmtInt } from '../api';
import ResultGrid from '../components/ResultGrid.jsx';

const EXAMPLES = [
  'tumor cells with large nuclei',
  'lymphocytes',
  'adipose tissue',
  'necrosis',
  'blood vessel',
  'mitotic figure',
  'gland',
  'muscle fibers',
];

export default function SearchPage({ health }) {
  const [mode, setMode] = useState('text');
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [state, setState] = useState({ loading: false, error: '', results: null, kind: '', title: '' });
  const [source, setSource] = useState(null); // patch used for "find similar"
  const requestId = useRef(0);
  const fileInput = useRef(null);

  const ready = health && health.model_ready;
  const empty = health && health.slides === 0;

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Paste a screenshot straight into image search
  useEffect(() => {
    if (mode !== 'image') return undefined;
    const onPaste = (e) => {
      const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith('image/'));
      if (item) setFile(item.getAsFile());
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [mode]);

  const run = async (kind, title, call) => {
    const id = ++requestId.current;
    setState({ loading: true, error: '', results: null, kind, title });
    try {
      const data = await call();
      if (id === requestId.current) setState({ loading: false, error: '', results: data.results, kind, title });
    } catch (e) {
      if (id === requestId.current) setState({ loading: false, error: e.message, results: null, kind, title });
    }
  };

  const searchText = (q) => {
    const query = q.trim();
    if (query.length < 2) return;
    setText(query);
    setSource(null);
    run('text', `Regions that match “${query}”`, () => api.searchText(query));
  };

  const searchImage = () => {
    if (!file) return;
    setSource(null);
    run('image', 'Regions that look like your image', () => api.searchImage(file));
  };

  const findSimilar = (r) => {
    setSource(r);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    run('similar', `Regions that look like this patch from ${r.filename}`, () =>
      api.searchSimilar(r.slide_id, r.x, r.y),
    );
  };

  const onDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith('image/')) setFile(f);
  };

  return (
    <div className="search-page">
      <section className="console" aria-label="Search">
        <h1 className="headline">Find tissue that looks like this.</h1>
        <p className="lede">
          Describe a structure or drop in a tissue image. PathoSearch compares it with every indexed
          patch across your slides and shows where each match sits.
        </p>

        <div className="mode-switch" role="tablist" aria-label="Search by">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'text'}
            className={`mode ${mode === 'text' ? 'mode-active' : ''}`}
            onClick={() => setMode('text')}
          >
            <Type size={16} /> Describe it
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'image'}
            className={`mode ${mode === 'image' ? 'mode-active' : ''}`}
            onClick={() => setMode('image')}
          >
            <ImageIcon size={16} /> Use an image
          </button>
        </div>

        {mode === 'text' ? (
          <>
            <form
              className="query"
              onSubmit={(e) => {
                e.preventDefault();
                searchText(text);
              }}
            >
              <label htmlFor="q" className="sr-only">Describe what you are looking for</label>
              <input
                id="q"
                className="query-input"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="e.g. clusters of lymphocytes around a vessel"
                maxLength={300}
                autoComplete="off"
              />
              <button className="btn btn-primary" type="submit" disabled={!ready || text.trim().length < 2}>
                <Search size={18} /> Search
              </button>
            </form>
            <div className="examples" aria-label="Example searches">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" className="chip" disabled={!ready} onClick={() => searchText(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="image-query">
            <div
              className={`dropzone dropzone-small ${preview ? 'dropzone-filled' : ''}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInput.current?.click()}
              role="button"
              tabIndex={0}
              aria-label="Choose a tissue image"
            >
              {preview ? (
                <img src={preview} alt="Your query" className="query-preview" />
              ) : (
                <span>Drop, paste or click to choose a PNG or JPEG</span>
              )}
              <input
                ref={fileInput}
                type="file"
                accept="image/png,image/jpeg"
                hidden
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>
            <div className="image-query-side">
              <p className="hint">
                Best results come from a crop about 128 µm wide, which is roughly 256 pixels at 20×.
                A whole-slide screenshot is too zoomed out to match single patches.
              </p>
              <div className="row">
                <button className="btn btn-primary" type="button" disabled={!ready || !file} onClick={searchImage}>
                  <Search size={18} /> Search with this image
                </button>
                {file && (
                  <button className="btn btn-quiet" type="button" onClick={() => setFile(null)}>
                    <X size={16} /> Clear
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {!ready && health && !health.model_error && (
          <p className="note"><Loader2 size={15} className="spin" /> The AI model is loading. Search unlocks when it's ready.</p>
        )}
        {empty && (
          <p className="note">
            Your library is empty. <a href="#/upload">Upload a slide</a> to start searching.
          </p>
        )}
      </section>

      <section className="results-area" aria-live="polite">
        {state.title && (
          <div className="results-head">
            {source && (
              <img
                className="source-thumb"
                src={api.patchUrl(source.slide_id, source.x, source.y, source.size)}
                alt="The patch you searched with"
              />
            )}
            <div>
              <h2 className="results-title">{state.title}</h2>
              {source && <p className="muted">x {fmtInt(source.x)}, y {fmtInt(source.y)}. Its own neighbourhood is left out.</p>}
            </div>
          </div>
        )}

        {state.loading && (
          <p className="note"><Loader2 size={16} className="spin" /> Searching…</p>
        )}
        {state.error && (
          <p className="error"><AlertCircle size={16} /> {state.error}</p>
        )}
        {state.results && state.results.length === 0 && (
          <p className="note">No indexed patches yet. Upload a slide and wait until it shows as indexed.</p>
        )}
        {state.results && (
          <ResultGrid results={state.results} mode={state.kind} onFindSimilar={findSimilar} />
        )}
      </section>
    </div>
  );
}
