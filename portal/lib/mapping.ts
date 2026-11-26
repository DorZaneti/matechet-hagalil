// לוגיקה טהורה, בלי קריאות רשת: הופכת את התשובה של monday למה שהלקוח רואה.
// בנפרד מ-monday.ts כדי שאפשר לבדוק אותה (lib/mapping.test.ts).
import { COLS } from "./config.ts";

export type RawColumn = { id: string; text: string | null; linked_item_ids?: string[] };
export type RawLine = { id: string; name: string; column_values: RawColumn[] };
export type RawOrder = { id: string; name: string; column_values: RawColumn[]; subitems?: RawLine[] };

export type CustomerLine = {
  id: string;
  title: string;
  qty: number | null;
  delivered: number | null;
  color: string | null;
  stage: string | null;
  step: number;          // 0..4 לפס ההתקדמות
  stepLabel: string;
};

export type CustomerOrder = {
  id: string;
  number: string;
  receivedAt: string | null;
  dueAt: string | null;
  status: string;
  statusText: string;
  urgent: boolean;
  project: string | null;
  lines: CustomerLine[];
};

// 5 שלבים פשוטים ללקוח. הפירוט הפנימי של הרצפה (חיתוך / כיפוף / ריתוך) מעניין את אבי, לא את הקבלן.
export const CUSTOMER_STEPS = ["התקבל", "בייצור", "בצבע", "מוכן", "נשלח"] as const;

const STAGE_TO_STEP: Record<string, number> = {
  "ממתין": 0,
  "חיתוך": 1, "כיפוף": 1, "ריתוך": 1, "בייצור": 1,
  "בצבע": 2,
  "אריזה": 3, "מוכן": 3,
  "נשלח": 4,
};

const STATUS_TEXT: Record<string, string> = {
  "טיוטה": "התקבלה, בבדיקה אצלנו",
  "פתוחה": "בעבודה",
  "סופקה חלקית": "חלק מהפריטים כבר סופקו",
  "סופקה": "סופקה",
  "בוטלה": "בוטלה",
  "הצעת מחיר": "ממתינה להצעת מחיר",
};

const col = (cols: RawColumn[], id: string) => cols.find((c) => c.id === id);
const text = (cols: RawColumn[], id: string) => {
  const t = col(cols, id)?.text;
  return t && t.trim() ? t.trim() : null;
};
const num = (cols: RawColumn[], id: string) => {
  const t = text(cols, id);
  if (t === null) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

export function stepFor(stage: string | null): number {
  return stage && stage in STAGE_TO_STEP ? STAGE_TO_STEP[stage] : 0;
}

export function toCustomerLine(l: RawLine): CustomerLine {
  const stage = text(l.column_values, COLS.lines.stage);
  const step = stepFor(stage);
  return {
    id: l.id,
    title: l.name,
    qty: num(l.column_values, COLS.lines.qty),
    delivered: num(l.column_values, COLS.lines.delivered),
    color: text(l.column_values, COLS.lines.color),
    stage,
    step,
    stepLabel: CUSTOMER_STEPS[step],
  };
}

/**
 * ממיר הזמנה לתצוגת לקוח. מחזיר null אם ההזמנה לא מקושרת ללקוח הזה:
 * בדיקה כפולה, גם אחרי שהרשימה הגיעה מהחיבור ההפוך בכרטיס הלקוח.
 */
export function toCustomerOrder(o: RawOrder, clientId: string): CustomerOrder | null {
  const linked = col(o.column_values, COLS.orders.client)?.linked_item_ids ?? [];
  if (!linked.map(String).includes(String(clientId))) return null;
  const status = text(o.column_values, COLS.orders.status) ?? "פתוחה";
  const number = text(o.column_values, COLS.orders.sourceNumber) ?? o.name.split("·")[0].trim();
  return {
    id: o.id,
    number,
    receivedAt: text(o.column_values, COLS.orders.receivedAt),
    dueAt: text(o.column_values, COLS.orders.dueAt),
    status,
    statusText: STATUS_TEXT[status] ?? status,
    urgent: text(o.column_values, COLS.orders.urgent) === "v",
    project: text(o.column_values, COLS.orders.project),
    lines: (o.subitems ?? []).map(toCustomerLine),
  };
}

/** הזמנות פעילות קודם, ובתוך כל קבוצה החדשות קודם. */
export function sortOrders(orders: CustomerOrder[]): CustomerOrder[] {
  const done = (s: string) => s === "סופקה" || s === "בוטלה";
  return [...orders].sort((a, b) => {
    if (done(a.status) !== done(b.status)) return done(a.status) ? 1 : -1;
    return (b.receivedAt ?? "").localeCompare(a.receivedAt ?? "");
  });
}

export function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${Number(d)}.${Number(m)}.${y}` : iso;
}
