import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAuth, useTitle } from "../lib/auth";
import { Card, ErrorBox, Loading } from "../components/ui";

export default function Account() {
  useTitle("Account");
  const { user, loading } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [next2, setNext2] = useState("");
  const [delPw, setDelPw] = useState("");
  const [done, setDone] = useState(false);

  const change = useMutation({
    mutationFn: () => api("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password: cur, new_password: next }) }),
    onSuccess: () => { setCur(""); setNext(""); setNext2(""); setDone(true); },
  });
  const del = useMutation({
    mutationFn: () => api("/api/auth/delete-account", { method: "POST", body: JSON.stringify({ password: delPw }) }),
    onSuccess: () => { qc.clear(); nav("/"); },
  });

  if (loading) return <Loading h={300} />;
  if (!user) return <Navigate to="/login" replace />;

  const mismatch = next2.length > 0 && next !== next2;
  const submitChange = (e: FormEvent) => { e.preventDefault(); setDone(false); if (!mismatch) change.mutate(); };
  const submitDelete = (e: FormEvent) => {
    e.preventDefault();
    if (window.confirm("Delete your account and all favourites? This cannot be undone.")) del.mutate();
  };

  return (
    <>
      <div className="page-head"><div><h1>Account</h1><p>{user.display_name} · {user.email}</p></div></div>
      <div className="grid grid-2" style={{ maxWidth: 900 }}>
        <Card title="Change password" sub="Other devices are signed out when you change it.">
          <form className="form" onSubmit={submitChange}>
            <label>Current password<input className="input" type="password" required value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></label>
            <label>New password<input className="input" type="password" required minLength={10} maxLength={128} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></label>
            <label>Repeat new password<input className="input" type="password" required value={next2} onChange={(e) => setNext2(e.target.value)} autoComplete="new-password" /></label>
            {mismatch && <span className="subtle" role="alert">Passwords do not match.</span>}
            {change.error && <ErrorBox error={change.error} />}
            {done && <div className="notice" role="status">Password changed.</div>}
            <button className="btn primary" type="submit" disabled={change.isPending || mismatch}>Change password</button>
          </form>
        </Card>
        <Card title="Delete account" sub="Removes your account and favourites. Tracker data is not affected.">
          <form className="form" onSubmit={submitDelete}>
            <label>Confirm with your password<input className="input" type="password" required value={delPw} onChange={(e) => setDelPw(e.target.value)} autoComplete="current-password" /></label>
            {del.error && <ErrorBox error={del.error} />}
            <button className="btn danger" type="submit" disabled={del.isPending}>Delete my account</button>
          </form>
        </Card>
      </div>
    </>
  );
}
