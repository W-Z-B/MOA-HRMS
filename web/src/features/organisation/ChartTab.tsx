import { useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { errorMessage, get } from "../../api/client";
import type { ChartPost, ChartTotals, ChartUnit, OrgChart } from "../../api/types";
import { Messages } from "./Messages";

/** "3 posts: 1 filled, 1 vacant, 1 frozen", leaving out what is not there. */
function counted(t: ChartTotals): string {
  if (t.posts === 0) return "no posts";
  const parts = [`${t.filled} filled`];
  if (t.vacant) parts.push(`${t.vacant} vacant`);
  if (t.frozen) parts.push(`${t.frozen} frozen`);
  return `${t.posts} ${t.posts === 1 ? "post" : "posts"}: ${parts.join(", ")}`;
}

const found = (text: string | null, q: string) => text !== null && text.toLocaleLowerCase().includes(q);
const postFound = (p: ChartPost, q: string) => [p.number, p.title, p.holder, p.acting].some((t) => found(t, q));
const unitFound = (u: ChartUnit, q: string) => [u.name, u.code, u.head].some((t) => found(t, q));

/** The branch the search leads to: a unit that matches keeps all it holds; otherwise only the posts and
 * units below that match, and nothing at all when none do. */
function trimmed(unit: ChartUnit, q: string): ChartUnit | null {
  if (!q || unitFound(unit, q)) return unit;
  const units = unit.units.map((u) => trimmed(u, q)).filter((u): u is ChartUnit => u !== null);
  const posts = unit.posts.filter((p) => postFound(p, q));
  return posts.length || units.length ? { ...unit, posts, units } : null;
}

function matches(units: ChartUnit[], q: string): number {
  return units.reduce(
    (n, u) => n + (unitFound(u, q) ? 1 : 0) + u.posts.filter((p) => postFound(p, q)).length + matches(u.units, q),
    0,
  );
}

/** The text with what the search found marked. */
function Marked({ text, q }: { text: string; q: string }) {
  const at = q ? text.toLocaleLowerCase().indexOf(q) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + q.length)}</mark>
      {text.slice(at + q.length)}
    </>
  );
}

function PostLine({ post, q }: { post: ChartPost; q: string }) {
  const frozen = post.status === "frozen";
  return (
    <li>
      <span>
        <strong>
          <Marked text={post.number} q={q} />
        </strong>{" "}
        <Marked text={post.title} q={q} />
      </span>
      <span className="muted small">
        {post.grade_name}
        {post.fte !== "1.00" ? ` · ${Number(post.fte)} of full time` : ""}
      </span>
      <span className="org-holder">
        {post.holder ? (
          <Marked text={post.holder} q={q} />
        ) : post.filled ? (
          <span className="muted">Filled</span>
        ) : frozen ? null : (
          <span className="chip chip-vacant">Vacant</span>
        )}
        {frozen && <span className="chip">Frozen</span>}
        {post.has_acting && (
          <span className="chip chip-acting">
            {post.acting ? (
              <>
                Acting: <Marked text={post.acting} q={q} />
              </>
            ) : (
              "Someone acting"
            )}
          </span>
        )}
      </span>
    </li>
  );
}

interface NodeProps {
  unit: ChartUnit;
  q: string;
  closed: Set<number>;
  onToggle: (id: number, open: boolean) => void;
}

function UnitNode({ unit, q, closed, onToggle }: NodeProps) {
  return (
    <li>
      <details className="org-unit" open={!closed.has(unit.id)} onToggle={(e) => onToggle(unit.id, e.currentTarget.open)}>
        <summary>
          <span className="org-name">
            <Marked text={unit.name} q={q} />
          </span>
          <span className="chip">{unit.unit_type_name}</span>
          <span className="muted small org-count">
            {unit.head ? (
              <>
                Headed by <Marked text={unit.head} q={q} /> ·{" "}
              </>
            ) : null}
            {counted(unit.totals)}
          </span>
        </summary>
        {unit.posts.length > 0 && (
          <ul className="org-posts" aria-label={`Posts in ${unit.name}`}>
            {unit.posts.map((post) => (
              <PostLine key={post.id} post={post} q={q} />
            ))}
          </ul>
        )}
        {unit.units.length > 0 && (
          <ul className="org-chart" aria-label={`Units under ${unit.name}`}>
            {unit.units.map((child) => (
              <UnitNode key={child.id} unit={child} q={q} closed={closed} onToggle={onToggle} />
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

const asAt = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

/** The organisation chart (item 1.10): each campus's units as they nest, their posts, and who holds them. */
export function ChartTab({ campusId }: { campusId: number | null }) {
  const [chart, setChart] = useState<OrgChart | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [closed, setClosed] = useState<Set<number>>(() => new Set());

  useEffect(() => {
    get<OrgChart>(`/org/chart/${campusId ? `?campus=${campusId}` : ""}`)
      .then(setChart)
      .catch((err) => setError(errorMessage(err, "Could not load the organisation chart.")));
  }, [campusId]);

  // Printing, from the button or the browser's own menu, gives the whole chart open.
  useEffect(() => {
    const openAll = () => flushSync(() => setClosed(new Set()));
    window.addEventListener("beforeprint", openAll);
    return () => window.removeEventListener("beforeprint", openAll);
  }, []);

  const onToggle = useCallback((id: number, open: boolean) => {
    setClosed((was) => {
      if (open !== was.has(id)) return was; // the browser reporting the state already held
      const next = new Set(was);
      if (open) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const everyUnit = (units: ChartUnit[]): number[] => units.flatMap((u) => [u.id, ...everyUnit(u.units)]);
  const q = query.trim().toLocaleLowerCase();
  const campuses = (chart?.campuses ?? [])
    .map((c) => ({ ...c, units: c.units.map((u) => trimmed(u, q)).filter((u): u is ChartUnit => u !== null) }))
    .filter((c) => !q || c.units.length > 0);
  const hits = q ? matches(campuses.flatMap((c) => c.units), q) : 0;
  const hidden = chart?.campuses.some((c) => !c.names && c.units.length > 0);

  return (
    <section aria-labelledby="chart-heading">
      <h2 id="chart-heading" className="sr-only">
        Organisation chart
      </h2>
      <Messages error={error} notice={null} />
      {chart === null && !error && <p className="loading">Loading…</p>}
      {chart !== null && (
        <>
          <div className="filters no-print">
            <label className="grow">
              <span className="sr-only">Find a person, post or unit</span>
              <input
                type="search"
                placeholder="Find a person, post or unit"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setClosed(new Set()); // what the search finds is shown open
                }}
              />
            </label>
            <button className="secondary" onClick={() => setClosed(new Set())}>
              Open all
            </button>
            <button className="secondary" onClick={() => setClosed(new Set(everyUnit(chart.campuses.flatMap((c) => c.units))))}>
              Close all
            </button>
            <button
              className="secondary"
              onClick={() => {
                flushSync(() => setClosed(new Set()));
                window.print();
              }}
            >
              Print
            </button>
          </div>
          <p role="status" className="muted small">
            {q ? (hits === 0 ? "Nothing matches." : `${hits} ${hits === 1 ? "match" : "matches"}.`) : ""}
          </p>
          <p className="muted small">
            As it stands on {asAt(chart.as_at)}.
            {hidden ? " Who holds each post shows to the roles that read the staff directory, on their own campuses." : ""}
          </p>
          {!q && campuses.every((c) => c.units.length === 0) && <p className="muted">No units here yet.</p>}
          {campuses
            .filter((c) => c.units.length > 0)
            .map((campus) => (
              <section key={campus.id} className="org-campus" aria-labelledby={`chart-campus-${campus.id}`}>
                <h3 id={`chart-campus-${campus.id}`}>{campus.name}</h3>
                <p className="muted small">{counted(campus.totals)}</p>
                <ul className="org-chart" aria-label={`Units on ${campus.name}`}>
                  {campus.units.map((unit) => (
                    <UnitNode key={unit.id} unit={unit} q={q} closed={closed} onToggle={onToggle} />
                  ))}
                </ul>
              </section>
            ))}
        </>
      )}
    </section>
  );
}
