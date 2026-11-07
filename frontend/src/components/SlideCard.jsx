import { apiUrl, fmtInt, patchMicrons } from '../api';

const STATUS_TEXT = {
  queued: 'Waiting to index',
  processing: 'Indexing',
  done: 'Indexed',
  failed: 'Failed',
};

// A slide drawn like a real 75 x 25 mm glass slide: frosted label end on the
// left, the tissue thumbnail on the glass.
export default function SlideCard({ slide }) {
  const pct = Math.round((slide.progress || 0) * 100);
  const busy = slide.status === 'queued' || slide.status === 'processing';
  const microns = patchMicrons(slide);

  return (
    <a className="glass-slide" href={`#/slides/${slide.id}`} aria-label={`Open ${slide.filename}`}>
      <div className="slide-label">
        <span className="slide-name" title={slide.filename}>{slide.filename}</span>
        <span className={`slide-status status-${slide.status}`}>
          {STATUS_TEXT[slide.status] || slide.status}
          {slide.status === 'processing' ? ` ${pct}%` : ''}
        </span>
        <span className="slide-facts">
          {slide.status === 'done' && <>{fmtInt(slide.patches_indexed)} patches</>}
          {slide.status === 'failed' && <>{slide.error}</>}
          {busy && slide.patches_planned ? <>{fmtInt(slide.patches_planned)} planned</> : null}
        </span>
        {microns && slide.status === 'done' && <span className="slide-facts">{microns} per patch</span>}
        {busy && (
          <span className="progress" aria-label={`${pct}% indexed`}>
            <span className="progress-bar" style={{ width: `${Math.max(pct, 3)}%` }} />
          </span>
        )}
      </div>
      <div className="slide-glass">
        {slide.thumbnail_url ? (
          <img src={apiUrl(slide.thumbnail_url)} alt="" className="slide-thumb" loading="lazy" />
        ) : (
          <span className="slide-empty">{busy ? 'Preparing preview' : 'No preview'}</span>
        )}
      </div>
    </a>
  );
}
