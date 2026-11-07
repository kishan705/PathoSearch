import { Crosshair, Search } from 'lucide-react';
import { api, fmtInt } from '../api';
import { navigate } from '../router';

// Grid of matching patches. For text searches the raw scores are small
// (~0.2-0.45), so the bar is drawn relative to the best match.
export default function ResultGrid({ results, mode, onFindSimilar }) {
  if (!results.length) return null;
  const best = Math.max(...results.map((r) => r.cosine), 1e-6);

  return (
    <ul className="results" aria-label="Matching regions">
      {results.map((r) => {
        const width = mode === 'text' ? (r.cosine / best) * 100 : Math.max(0, r.similarity);
        return (
          <li key={`${r.slide_id}-${r.x}-${r.y}`} className="result">
            <img
              className="result-img"
              src={api.patchUrl(r.slide_id, r.x, r.y, r.size)}
              alt={`Tissue from ${r.filename} at x ${r.x}, y ${r.y}`}
              loading="lazy"
              width="256"
              height="256"
            />
            <div className="score" aria-label={mode === 'text' ? `Match score ${r.cosine.toFixed(2)}` : `${r.similarity}% similar`}>
              <span className="score-bar" style={{ width: `${width}%` }} />
            </div>
            <div className="result-meta">
              <span className="result-score">
                {mode === 'text' ? `Score ${r.cosine.toFixed(2)}` : `${r.similarity}% similar`}
              </span>
              <span className="result-file" title={r.filename}>{r.filename}</span>
              <span className="result-xy">x {fmtInt(r.x)}, y {fmtInt(r.y)}</span>
            </div>
            <div className="result-actions">
              <button type="button" className="btn btn-small" onClick={() => onFindSimilar(r)}>
                <Search size={14} /> Find similar
              </button>
              <button
                type="button"
                className="btn btn-small btn-soft"
                onClick={() => navigate(`/slides/${r.slide_id}?x=${r.x}&y=${r.y}`)}
              >
                <Crosshair size={14} /> Show on slide
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
