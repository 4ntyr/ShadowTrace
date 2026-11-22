import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { StateLink } from "../lib/api";
import { RELATION_LABEL, cap } from "../lib/format";
import { IconStar } from "../lib/icons";
import { useAuth, useFavourite } from "../lib/auth";
import type { Scope } from "../lib/scope";

export function Card({ title, sub, actions, children, className = "" }: { title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>{title && <h2>{title}</h2>}{sub && <p>{sub}</p>}</div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card stat">
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Loading({ h = 200 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} aria-busy="true" aria-label="Loading" />;
}

export function ErrorBox({ error }: { error: unknown }) {
  return <div className="error-box" role="alert">{error instanceof Error ? error.message : "Something went wrong."}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ConfidenceBadge({ level }: { level: string }) {
  const labels: Record<string, string> = { confirmed: "Confirmed", high: "High confidence", medium: "Medium confidence", low: "Low confidence" };
  return <span className={`badge conf-${level}`} title="Attribution confidence"><span className="dot" />{labels[level] ?? cap(level)}</span>;
}

export function AttributionLine({ link }: { link: StateLink | null }) {
  if (!link) return <span className="muted">Unattributed</span>;
  return (
    <span className="secondary">
      {RELATION_LABEL[link.relation] ?? cap(link.relation)} <strong style={{ color: "var(--text-primary)" }}>{link.country.name}</strong>
      {link.agency ? <> · {link.agency}</> : null}
    </span>
  );
}

export function FavStar({ slug, on, name }: { slug: string; on: boolean; name: string }) {
  const { user } = useAuth();
  const fav = useFavourite();
  if (!user) {
    return <Link className="star" to="/login" title="Log in to save favourites" aria-label={`Log in to favourite ${name}`}><IconStar /></Link>;
  }
  return (
    <button
      className="star" aria-pressed={on} disabled={fav.isPending}
      aria-label={on ? `Remove ${name} from favourites` : `Add ${name} to favourites`}
      title={on ? "Remove from favourites" : "Add to favourites"}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); fav.mutate({ slug, on: !on }); }}
    >
      <IconStar filled={on} />
    </button>
  );
}

export function ScopeToggle({ scope, setScope }: { scope: Scope; setScope: (s: Scope) => void }) {
  const { user } = useAuth();
  return (
    <div className="segmented" role="group" aria-label="Scope">
      <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>All groups</button>
      <button
        aria-pressed={scope === "favourites"} disabled={!user}
        title={user ? "Only your favourite groups" : "Log in to use favourites"}
        onClick={() => setScope("favourites")}
      >★ Favourites</button>
    </div>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => <button key={String(o.value)} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>)}
    </div>
  );
}

export function FavouritesEmpty() {
  return <Empty>No favourites yet. Open <Link to="/groups">Groups</Link> and star the actors you want to follow.</Empty>;
}
