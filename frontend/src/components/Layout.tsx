import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth, useLogout } from "../lib/auth";
import ErrorBoundary from "./ErrorBoundary";
import { useTheme } from "../lib/theme";
import { IconActivity, IconDashboard, IconGraph, IconGroups, IconHybrid, IconMenu, IconSources } from "../lib/icons";

const NAV = [
  { to: "/", label: "Dashboard", icon: IconDashboard, end: true },
  { to: "/groups", label: "Groups", icon: IconGroups },
  { to: "/graph", label: "Relations", icon: IconGraph },
  { to: "/activity", label: "Activity feed", icon: IconActivity },
  { to: "/hybrid", label: "Hybrid warfare", icon: IconHybrid },
];

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--surface-3)" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="var(--cyber)" strokeWidth="2.5" />
      <circle cx="16" cy="16" r="3.5" fill="var(--kinetic)" />
      <path d="M16 3v5M16 24v5M3 16h5M24 16h5" stroke="var(--cyber)" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { user, registrationOpen } = useAuth();
  const logout = useLogout();
  const { theme, setTheme } = useTheme();
  const loc = useLocation();
  const keep = new URLSearchParams(loc.search).get("scope") === "favourites" ? "?scope=favourites" : "";

  return (
    <div className="shell">
      <div className="mobile-bar">
        <button className="btn ghost" onClick={() => setOpen(!open)} aria-label="Toggle navigation"><IconMenu className="" /></button>
        <strong>ShadowTrace</strong>
      </div>
      <nav className={`sidebar ${open ? "open" : ""}`} aria-label="Main" onClick={() => setOpen(false)}>
        <Link to="/" className="brand" style={{ color: "inherit", textDecoration: "none" }}>
          <Logo />
          <span>ShadowTrace<small>APT &amp; hybrid tracker</small></span>
        </Link>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to + (to === "/hybrid" ? "" : keep)} end={end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <Icon />{label}
          </NavLink>
        ))}
        <div className="nav-section">System</div>
        <NavLink to="/sources" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><IconSources />Data sources</NavLink>
        <div className="sidebar-foot">
          {user ? (
            <>
              <Link to="/account" style={{ fontSize: 13, minWidth: 0, color: "inherit", textDecoration: "none" }} title="Account settings">
                <div style={{ fontWeight: 600 }}>{user.display_name} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>· Account</span></div>
                <div className="muted" style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.email}</div>
              </Link>
              <button className="btn" onClick={() => logout.mutate()}>Log out</button>
            </>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <Link className="btn primary" to="/login">Log in</Link>
              {registrationOpen && <Link className="btn" to="/register">Sign up</Link>}
            </div>
          )}
          <button className="btn ghost" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle colour theme">
            {theme === "dark" ? "☀ Light theme" : "☾ Dark theme"}
          </button>
        </div>
      </nav>
      <main className="main"><ErrorBoundary key={loc.pathname}>{children}</ErrorBoundary></main>
    </div>
  );
}
