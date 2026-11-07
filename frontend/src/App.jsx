import { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { api } from './api';
import { useRoute } from './router';
import SearchPage from './pages/SearchPage.jsx';
import SlidesPage from './pages/SlidesPage.jsx';
import SlideViewer from './pages/SlideViewer.jsx';
import UploadPage from './pages/UploadPage.jsx';

function useHealth() {
  const [health, setHealth] = useState(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let alive = true;
    let timer;
    // Poll only while the model is loading or the backend is unreachable.
    // Once it's ready we stop, so an open tab doesn't keep a cloud GPU awake.
    const tick = async () => {
      clearTimeout(timer);
      try {
        const h = await api.health();
        if (!alive) return;
        setHealth(h);
        setOffline(false);
        if (!h.model_ready && !h.model_error) timer = setTimeout(tick, 3000);
      } catch {
        if (!alive) return;
        setOffline(true);
        timer = setTimeout(tick, 5000);
      }
    };
    tick();
    window.addEventListener('focus', tick);
    return () => {
      alive = false;
      clearTimeout(timer);
      window.removeEventListener('focus', tick);
    };
  }, []);
  return { health, offline };
}

function ModelStatus({ health, offline }) {
  if (offline) {
    return (
      <span className="status status-bad" title="The backend isn't answering. If it's on Modal it may be starting up.">
        <AlertCircle size={15} /> Backend offline
      </span>
    );
  }
  if (!health) return null;
  if (health.model_error) {
    return (
      <span className="status status-bad" title={health.model_error}>
        <AlertCircle size={15} /> Model failed to load
      </span>
    );
  }
  if (!health.model_ready) {
    return (
      <span className="status">
        <Loader2 size={15} className="spin" /> Loading BiomedCLIP
      </span>
    );
  }
  return (
    <span className="status status-ok" title={`${health.patches.toLocaleString()} patches indexed`}>
      <span className="dot" /> Ready on {health.device.toUpperCase()}
    </span>
  );
}

const TABS = [
  { to: '/search', label: 'Search' },
  { to: '/slides', label: 'Slides' },
  { to: '/upload', label: 'Upload' },
];

export default function App() {
  const route = useRoute();
  const { health, offline } = useHealth();
  const section = route.parts[0] || 'search';

  let page;
  if (section === 'slides' && route.parts[1]) {
    page = <SlideViewer slideId={route.parts[1]} params={route.params} health={health} />;
  } else if (section === 'slides') {
    page = <SlidesPage />;
  } else if (section === 'upload') {
    page = <UploadPage health={health} />;
  } else {
    page = <SearchPage health={health} params={route.params} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/search" aria-label="PathoSearch home">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <rect x="1" y="9" width="30" height="14" rx="2" />
            <rect className="brand-frost" x="2" y="10" width="8" height="12" />
            <circle className="brand-stain" cx="21" cy="16" r="4.5" />
          </svg>
          PathoSearch
        </a>
        <nav className="tabs" aria-label="Main">
          {TABS.map((t) => (
            <a
              key={t.to}
              href={`#${t.to}`}
              className={`tab ${section === t.to.slice(1) ? 'tab-active' : ''}`}
              aria-current={section === t.to.slice(1) ? 'page' : undefined}
            >
              {t.label}
            </a>
          ))}
        </nav>
        <ModelStatus health={health} offline={offline} />
      </header>
      <main className="page">{page}</main>
    </div>
  );
}
