// Local storage with JSON backup/restore. Pure functions take an injectable storage (tests use a Map).
export const KEY = 'app-data-v1';

export function emptyData() { return { version: 1 }; }

export function load(storage = globalThis.localStorage) {
  try {
    const raw = storage && storage.getItem(KEY);
    const data = raw ? JSON.parse(raw) : emptyData();
    return data && typeof data === 'object' && data.version === 1 ? data : emptyData();
  } catch { return emptyData(); }
}

export function save(data, storage = globalThis.localStorage) {
  storage.setItem(KEY, JSON.stringify(data));
  return data;
}

export function exportJson(data) { return JSON.stringify(data, null, 2); }

// Restore never damages current data: invalid input throws and nothing is written.
export function importJson(text, storage = globalThis.localStorage) {
  const data = JSON.parse(text);
  if (!data || typeof data !== 'object' || data.version !== 1) throw new Error('백업 파일 형식이 맞지 않습니다');
  return save(data, storage);
}

export function memoryStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
}
