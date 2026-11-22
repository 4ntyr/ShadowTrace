import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type User } from "../lib/api";
import { Card, ErrorBox } from "../components/ui";

export default function Auth({ mode }: { mode: "login" | "register" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api<User>(`/api/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify(mode === "login" ? { email, password } : { email, password, display_name: name }),
    }),
    onSuccess: () => { qc.clear(); nav("/groups"); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };

  return (
    <div className="auth-wrap">
      <Card title={mode === "login" ? "Log in" : "Create an account"} sub="An account lets you follow favourite groups across devices.">
        <form className="form" onSubmit={submit}>
          {mode === "register" && (
            <label>Display name<input className="input" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} autoComplete="nickname" /></label>
          )}
          <label>Email<input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
          <label>Password
            <input className="input" type="password" required minLength={mode === "register" ? 10 : 1} maxLength={128} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "register" && <span className="subtle">At least 10 characters.</span>}
          </label>
          {m.error && <ErrorBox error={m.error} />}
          <button className="btn primary" type="submit" disabled={m.isPending}>{mode === "login" ? "Log in" : "Create account"}</button>
          <p className="subtle" style={{ margin: 0 }}>
            {mode === "login" ? <>No account? <Link to="/register">Sign up</Link></> : <>Already registered? <Link to="/login">Log in</Link></>}
          </p>
        </form>
      </Card>
    </div>
  );
}
