"use client";
import { useState } from "react";

type Turn = { q: string; a?: string; human?: boolean };

const SUGGESTIONS = ["איפה ההזמנה האחרונה שלי?", "מה עוד בצבע?", "מתי האספקה?"];

export default function AskBox({ token }: { token: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setQ("");
    setTurns((t) => [...t, { q: text }]);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, question: text }),
      });
      const body = await res.json().catch(() => ({}));
      const a = body.ok ? body.answer : body.error ?? "משהו השתבש";
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a, human: body.needsHuman } : x)));
    } catch {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a: "אין חיבור. נסו שוב" } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card ask">
      {turns.length === 0 && (
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
      )}
      {turns.map((t, i) => (
        <div key={i} className="turn">
          <div className="q">{t.q}</div>
          <div className="a" aria-live="polite">
            {t.a ?? "בודק…"}
            {t.human && <div className="human">העברנו את השאלה לרינה במשרד.</div>}
          </div>
        </div>
      ))}
      <form
        className="ask-row"
        onSubmit={(e) => {
          e.preventDefault();
          send(q);
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          maxLength={500}
          placeholder="שאלה על ההזמנות שלכם…"
          aria-label="שאלה על ההזמנות"
        />
        <button className="primary small" type="submit" disabled={busy || !q.trim()}>שאל</button>
      </form>
    </section>
  );
}
