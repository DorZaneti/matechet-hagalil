import { test } from "node:test";
import assert from "node:assert/strict";
import { sortOrders, stepFor, toCustomerOrder, type RawOrder } from "./mapping.ts";
import { COLS } from "./config.ts";

const order = (id: string, clientId: string, status: string, date: string, extra: Partial<RawOrder> = {}): RawOrder => ({
  id,
  name: `${id} · לקוח`,
  column_values: [
    { id: COLS.orders.client, text: null, linked_item_ids: [clientId] },
    { id: COLS.orders.status, text: status },
    { id: COLS.orders.receivedAt, text: date },
    { id: COLS.orders.sourceNumber, text: id },
    { id: COLS.orders.urgent, text: "" },
    { id: COLS.orders.project, text: "" },
  ],
  subitems: [],
  ...extra,
});

test("הזמנה של לקוח אחר לא מוצגת, גם אם הגיעה ברשימה", () => {
  assert.equal(toCustomerOrder(order("1041", "999", "פתוחה", "2026-11-03"), "123"), null);
  assert.ok(toCustomerOrder(order("1041", "123", "פתוחה", "2026-11-03"), "123"));
});

test("שלבי רצפה ממופים ל-5 שלבים ללקוח", () => {
  assert.equal(stepFor("ממתין"), 0);
  assert.equal(stepFor("ריתוך"), 1);
  assert.equal(stepFor("בייצור"), 1);
  assert.equal(stepFor("בצבע"), 2);
  assert.equal(stepFor("מוכן"), 3);
  assert.equal(stepFor("נשלח"), 4);
  assert.equal(stepFor(null), 0);
  assert.equal(stepFor("משהו חדש"), 0);
});

test("שורה עם אספקה חלקית וכמות", () => {
  const o = order("1041", "1", "סופקה חלקית", "2026-11-03", {
    subitems: [{
      id: "s1", name: "מעקה מרפסת 120x100",
      column_values: [
        { id: COLS.lines.stage, text: "בצבע" },
        { id: COLS.lines.qty, text: "40" },
        { id: COLS.lines.delivered, text: "25" },
        { id: COLS.lines.color, text: "RAL 9005" },
      ],
    }],
  });
  const c = toCustomerOrder(o, "1")!;
  assert.equal(c.statusText, "חלק מהפריטים כבר סופקו");
  assert.deepEqual([c.lines[0].qty, c.lines[0].delivered, c.lines[0].step], [40, 25, 2]);
});

test("פעילות קודם, ובתוך כל קבוצה החדשות קודם", () => {
  const list = [
    toCustomerOrder(order("1045", "1", "סופקה", "2026-11-10"), "1")!,
    toCustomerOrder(order("1041", "1", "פתוחה", "2026-11-03"), "1")!,
    toCustomerOrder(order("1049", "1", "פתוחה", "2026-11-17"), "1")!,
  ];
  assert.deepEqual(sortOrders(list).map((o) => o.number), ["1049", "1041", "1045"]);
});

test("השדות שהלקוח מקבל לא כוללים מחיר, חיוב או הערות פנימיות", () => {
  const c = toCustomerOrder(order("1041", "1", "פתוחה", "2026-11-03"), "1")!;
  assert.deepEqual(Object.keys(c).sort(), ["dueAt", "id", "lines", "number", "project", "receivedAt", "status", "statusText", "urgent"]);
});
