import type { SearchResult } from "@spatial/map-core";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useSession } from "../session";
import { Icon } from "./Icon";

const WAIT_MS = 250;

/** Find any application, case, request, property, street or project by its
 * number or name, from anywhere. "/" puts the cursor in it. */
export function QuickSearch() {
  const { api, districtId } = useSession();
  const navigate = useNavigate();
  const box = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        box.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const text = q.trim();
    if (text.length < 2) {
      setResults(null);
      return;
    }
    let current = true;
    const timer = setTimeout(() => {
      api
        .search(text)
        .then((found) => {
          if (current) {
            setResults(found.results);
            setActive(0);
          }
        })
        .catch(() => {
          if (current) setResults([]);
        });
    }, WAIT_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [api, q, districtId]);

  function go(result: SearchResult) {
    setOpen(false);
    setQ("");
    setResults(null);
    navigate(result.link);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!results?.length) {
      if (e.key === "Escape") box.current?.blur();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((n) => (n + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((n) => (n - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = results[active];
      if (chosen) go(chosen);
    } else if (e.key === "Escape") {
      setOpen(false);
      box.current?.blur();
    }
  }

  const showing = open && results !== null;
  return (
    <div className="quick-search">
      <Icon name="search" size={16} />
      <input
        ref={box}
        type="search"
        role="combobox"
        aria-label="Search the district"
        aria-expanded={showing}
        aria-controls="quick-search-results"
        aria-autocomplete="list"
        placeholder="Search numbers or names  /"
        value={q}
        onChange={(e) => (setQ(e.target.value), setOpen(true))}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {showing && (
        <ul id="quick-search-results" role="listbox" aria-label="Search results" className="quick-search-results">
          {results.length === 0 ? (
            <li className="none">Nothing found for “{q.trim()}”.</li>
          ) : (
            results.map((r, n) => (
              <li
                key={`${r.kind}-${r.id}`}
                role="option"
                aria-selected={n === active}
                className={n === active ? "active" : undefined}
                onMouseDown={(e) => (e.preventDefault(), go(r))}
                onMouseEnter={() => setActive(n)}
              >
                <span className="kind">{r.kind_label}</span>
                <strong>{r.title}</strong>
                {r.detail && <span className="muted">{r.detail}</span>}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
