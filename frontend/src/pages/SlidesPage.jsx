import { useEffect, useState } from 'react';
import { AlertCircle, Loader2, Upload } from 'lucide-react';
import { api, fmtInt } from '../api';
import SlideCard from '../components/SlideCard.jsx';

export default function SlidesPage() {
  const [slides, setSlides] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    let timer;
    const load = async () => {
      try {
        const data = await api.listSlides();
        if (!alive) return;
        setSlides(data);
        setError('');
        const busy = data.some((s) => s.status === 'queued' || s.status === 'processing');
        if (busy) timer = setTimeout(load, 2000); // only refresh while something is indexing
      } catch (e) {
        if (!alive) return;
        setError(e.message);
        timer = setTimeout(load, 5000);
      }
    };
    load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  const total = slides ? slides.reduce((n, s) => n + (s.patches_indexed || 0), 0) : 0;

  return (
    <div className="slides-page">
      <div className="page-head">
        <div>
          <h1 className="headline headline-small">Slide library</h1>
          {slides && slides.length > 0 && (
            <p className="muted">
              {slides.length} {slides.length === 1 ? 'slide' : 'slides'}, {fmtInt(total)} searchable patches
            </p>
          )}
        </div>
        <a className="btn btn-primary" href="#/upload"><Upload size={18} /> Upload a slide</a>
      </div>

      {error && <p className="error"><AlertCircle size={16} /> {error}</p>}
      {!slides && !error && <p className="note"><Loader2 size={16} className="spin" /> Loading slides…</p>}

      {slides && slides.length === 0 && (
        <div className="empty">
          <p>No slides yet.</p>
          <p className="muted">
            Upload a whole-slide image (.svs, .ndpi, .tiff and similar) or a PNG/JPEG of tissue.
            It's indexed in the background and becomes searchable when it shows as indexed.
          </p>
          <a className="btn btn-primary" href="#/upload"><Upload size={18} /> Upload a slide</a>
        </div>
      )}

      {slides && slides.length > 0 && (
        <div className="slide-rack">
          {slides.map((s) => <SlideCard key={s.id} slide={s} />)}
        </div>
      )}
    </div>
  );
}
