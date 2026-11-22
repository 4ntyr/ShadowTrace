import { Component, type ReactNode } from "react";

/** Keeps one broken view (e.g. a chart choking on unexpected data) from blanking the whole app. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("View crashed:", error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card" role="alert" style={{ maxWidth: 560 }}>
        <h2>This view failed to load</h2>
        <p className="secondary">{this.state.error.message || "Unexpected error."}</p>
        <button className="btn" onClick={() => window.location.reload()}>Reload page</button>
      </div>
    );
  }
}
