import { CUSTOMER_STEPS, formatDate, type CustomerLine, type CustomerOrder } from "@/lib/mapping.ts";

function badgeClass(status: string) {
  if (status === "סופקה") return "badge done";
  if (status === "סופקה חלקית") return "badge partial";
  if (status === "בוטלה") return "badge cancel";
  return "badge";
}

function Line({ line, cancelled }: { line: CustomerLine; cancelled: boolean }) {
  const parts = [
    line.qty !== null ? `${line.qty} יח'` : null,
    line.color,
    line.delivered !== null && line.qty !== null && line.delivered > 0 && line.delivered < line.qty
      ? `סופקו ${line.delivered} מתוך ${line.qty}`
      : null,
  ].filter(Boolean);
  return (
    <div className="line">
      <div className="line-title">{line.title}</div>
      {parts.length > 0 && <div className="line-sub">{parts.join(" · ")}</div>}
      {!cancelled && (
        <>
          <div className="steps" aria-hidden>
            {CUSTOMER_STEPS.map((_, i) => (
              <div key={i} className={`step${i <= line.step ? " on" : ""}${i === CUSTOMER_STEPS.length - 1 ? " last" : ""}`} />
            ))}
          </div>
          <div className="step-labels">
            {CUSTOMER_STEPS.map((s, i) => (
              <span key={s} className={i === line.step ? "cur" : undefined}>{s}</span>
            ))}
          </div>
          <span className="sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
            שלב נוכחי: {line.stepLabel}
          </span>
        </>
      )}
    </div>
  );
}

export default function OrderCard({ order }: { order: CustomerOrder }) {
  const meta = [
    order.receivedAt ? `התקבלה ${formatDate(order.receivedAt)}` : null,
    order.dueAt ? `אספקה מתוכננת ${formatDate(order.dueAt)}` : null,
    order.project ? `פרויקט ${order.project}` : null,
  ].filter(Boolean);
  const cancelled = order.status === "בוטלה";
  return (
    <article className="card">
      <div className="order-head">
        <div>
          <div className="order-num">הזמנה {order.number}</div>
          {meta.length > 0 && <div className="order-meta">{meta.join(" · ")}</div>}
        </div>
        <div>
          <span className={badgeClass(order.status)}>{order.statusText}</span>
          {order.urgent && !cancelled && <span className="badge urgent">דחוף</span>}
        </div>
      </div>
      {order.lines.length === 0 && order.status === "טיוטה" && (
        <div className="line line-sub">קיבלנו את ההזמנה. נעבור עליה ונעדכן כאן את הפריטים.</div>
      )}
      {order.lines.map((l) => <Line key={l.id} line={l} cancelled={cancelled} />)}
    </article>
  );
}
