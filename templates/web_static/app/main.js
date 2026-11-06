// Hash router: each screen is a function (data) => HTMLElement. Screens register in ROUTES.
import { load } from './store.js';

export const ROUTES = {
  '/': { title: '홈', render: () => { const s = document.createElement('section'); s.innerHTML = '<h2>홈</h2><p class="muted">준비 중</p>'; return s; } },
};

function nav(current) {
  const el = document.getElementById('nav');
  el.replaceChildren(...Object.entries(ROUTES).map(([path, r]) => {
    const a = document.createElement('a'); a.href = '#' + path; a.textContent = r.title;
    if (path === current) a.setAttribute('aria-current', 'page');
    return a;
  }));
}

export function render() {
  const path = (location.hash || '#/').slice(1) || '/';
  const route = ROUTES[path] || ROUTES['/'];
  nav(ROUTES[path] ? path : '/');
  document.getElementById('view').replaceChildren(route.render(load()));
  document.title = route.title;
}

if (typeof window !== 'undefined') { addEventListener('hashchange', render); render(); }
