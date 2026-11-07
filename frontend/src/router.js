// Tiny hash router: #/search, #/slides, #/slides/<id>?x=..&y=.., #/upload
// Hash URLs work everywhere (Vite dev server, the FastAPI static server, any host)
// without server rewrite rules.
import { useEffect, useState } from 'react';

function parse() {
  const raw = window.location.hash.replace(/^#/, '') || '/search';
  const [path, query = ''] = raw.split('?');
  const parts = path.split('/').filter(Boolean);
  return { path, parts, params: new URLSearchParams(query) };
}

export function useRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export function navigate(to) {
  window.location.hash = to;
}
