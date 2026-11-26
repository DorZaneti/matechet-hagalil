"use client";
// רכיב צד-לקוח. הוא שולח FormData רק ל-/api/orders של הפורטל עצמו,
// ואין לו גישה לטוקן של monday או למפתח ה-AI, שנשארים בשרת.
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

type State = { kind: "idle" } | { kind: "sending" } | { kind: "ok"; note?: string } | { kind: "err"; msg: string };

export default function NewOrderForm({ token }: { token: string }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [fileName, setFileName] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const text = String(fd.get("text") ?? "").trim();
    const file = fd.get("file");
    if (!text && !(file instanceof File && file.size > 0)) {
      setState({ kind: "err", msg: "צריך לכתוב את ההזמנה או לצרף קובץ" });
      return;
    }
    fd.set("token", token);
    setState({ kind: "sending" });
    try {
      const res = await fetch("/api/orders", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) {
        setState({ kind: "err", msg: body.error ?? "משהו השתבש. נסו שוב" });
        return;
      }
      formRef.current?.reset();
      setFileName("");
      setState({
        kind: "ok",
        note: body.fileSaved === false ? "ההזמנה נשמרה, אבל הקובץ לא עלה. שלחו אותו לרינה בוואטסאפ." : undefined,
      });
      router.refresh(); // ההזמנה החדשה מופיעה ברשימה כ"בבדיקה"
    } catch {
      setState({ kind: "err", msg: "אין חיבור. בדקו את האינטרנט ונסו שוב" });
    }
  }

  return (
    <form ref={formRef} className="card new-order" onSubmit={onSubmit}>
      <label htmlFor="text">מה להזמין?</label>
      <textarea
        id="text"
        name="text"
        maxLength={5000}
        placeholder="לדוגמה: 36 מעקות מרפסת 120x100 ו-4 מעקות 180x100, הכל RAL 7016, בניין B. צריך עד סוף החודש."
      />
      <div className="field-label">או צרפו קובץ: הזמנת רכש, תכנית או צילום סקיצה</div>
      <label className="file-pick">
        <input
          name="file"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.xlsx,.xls,.docx,.txt,image/*"
          onChange={(e) => setFileName(e.currentTarget.files?.[0]?.name ?? "")}
        />
        <span className="file-btn">בחירת קובץ</span>
        <span className="file-name">{fileName || "לא נבחר קובץ"}</span>
      </label>
      <div className="hint">עד 10MB. אפשר לצלם ישר מהטלפון.</div>
      <button className="primary" type="submit" disabled={state.kind === "sending"}>
        {state.kind === "sending" ? "שולח…" : "שליחת הזמנה"}
      </button>
      {state.kind === "ok" && (
        <div className="notice ok" role="status">
          ההזמנה התקבלה. נעבור עליה ונאשר מולכם את הפרטים. {state.note}
        </div>
      )}
      {state.kind === "err" && <div className="notice err" role="alert">{state.msg}</div>}
    </form>
  );
}
