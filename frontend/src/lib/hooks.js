import { useCallback, useEffect, useState } from "react";

/** Current time, refreshed every `interval` ms, so "5s ago" labels keep moving. */
export function useNow(interval = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), interval);
    return () => clearInterval(timer);
  }, [interval]);
  return now;
}

/** Route stored in the URL hash: #/page/sub. Links, reloads and the back button all work. */
export function useRoute(pages, fallback) {
  const read = () => {
    const [page = "", ...rest] = window.location.hash.replace(/^#\/?/, "").split("/");
    return pages.includes(page) ? { page, sub: rest.join("/") || null } : { page: fallback, sub: null };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  });
  const go = useCallback((page, sub) => {
    window.location.hash = `/${page}${sub ? `/${sub}` : ""}`;
  }, []);
  return [route, go];
}
