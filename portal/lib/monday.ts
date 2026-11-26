import "server-only"; // אם קובץ מצד הלקוח ינסה לייבא את המודול הזה, ה-build ייכשל
import { createHash } from "node:crypto";
import { unstable_cache } from "next/cache";
import { BOARDS, COLS, LINE_READ_COLUMNS, ORDER_READ_COLUMNS } from "./config.ts";
import { sortOrders, toCustomerOrder, type CustomerOrder, type RawOrder } from "./mapping.ts";

// ניתן להחלפה רק לבדיקות מקומיות (scripts/mock-monday.mjs). בייצור לא מגדירים את המשתנה.
const API = process.env.MONDAY_API_URL ?? "https://api.monday.com/v2";

function token(): string {
  const t = process.env.MONDAY_TOKEN;
  if (!t) throw new Error("MONDAY_TOKEN is not set");
  return t;
}

async function gql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(API, {
    method: "POST",
    headers: { Authorization: token(), "Content-Type": "application/json", "API-Version": "2025-04" },
    body: JSON.stringify({ query, variables }),
    cache: "no-store", // שכבת ה-cache היא unstable_cache למטה, עם tag שה-webhook מנקה
  });
  const body = await res.json();
  if (!res.ok || body.errors || body.error_message) {
    // לא מחזירים ללקוח את הודעת השגיאה של monday, רק רושמים אותה בלוג של השרת
    console.error("monday API error", res.status, JSON.stringify(body.errors ?? body.error_message));
    throw new Error("monday API error");
  }
  return body.data as T;
}

export const hashToken = (t: string) => createHash("sha256").update(t).digest("hex");

/** קישור אישי בפורמט base64url באורך 24 עד 64 תווים. בדיקה זולה לפני כל קריאה ל-monday. */
export const isWellFormedToken = (t: string) => /^[A-Za-z0-9_-]{24,64}$/.test(t);

export type PortalClient = { id: string; name: string; orderIds: string[] };

async function findClientUncached(tokenHash: string): Promise<PortalClient | null> {
  const data = await gql<{ items_page_by_column_values: { items: { id: string; name: string; column_values: { linked_item_ids?: string[] }[] }[] } }>(
    `query ($b: ID!, $h: String!) {
      items_page_by_column_values(board_id: $b, limit: 2, columns: [{column_id: "${COLS.clients.portalHash}", column_values: [$h]}]) {
        items { id name column_values(ids: ["${COLS.clients.orders}"]) { ... on BoardRelationValue { linked_item_ids } } }
      }
    }`,
    { b: BOARDS.clients, h: tokenHash },
  );
  const items = data.items_page_by_column_values.items;
  if (items.length !== 1) return null; // לא נמצא, או התנגשות: במקרה כזה לא מציגים כלום
  const c = items[0];
  return { id: c.id, name: c.name, orderIds: c.column_values[0]?.linked_item_ids ?? [] };
}

async function ordersUncached(clientId: string, orderIds: string[]): Promise<CustomerOrder[]> {
  if (orderIds.length === 0) return [];
  const data = await gql<{ items: RawOrder[] }>(
    `query ($ids: [ID!]) {
      items(ids: $ids, limit: 100) {
        id name
        column_values(ids: ${JSON.stringify(ORDER_READ_COLUMNS)}) { id text ... on BoardRelationValue { linked_item_ids } }
        subitems { id name column_values(ids: ${JSON.stringify(LINE_READ_COLUMNS)}) { id text } }
      }
    }`,
    { ids: orderIds },
  );
  const mine = data.items.map((o) => toCustomerOrder(o, clientId)).filter((o): o is CustomerOrder => o !== null);
  return sortOrders(mine);
}

// cache קצר (30 שניות) ששומר על monday מעומס. ה-webhook מנקה את ה-tag מיד כשמשהו משתנה, ולכן התצוגה חיה.
export const getClientByToken = (rawToken: string) =>
  unstable_cache(() => findClientUncached(hashToken(rawToken)), ["client", hashToken(rawToken)], {
    revalidate: 30, tags: ["monday"],
  })();

export const getOrdersForClient = (client: PortalClient) =>
  unstable_cache(() => ordersUncached(client.id, client.orderIds), ["orders", client.id, client.orderIds.join(",")], {
    revalidate: 30, tags: ["monday", `client:${client.id}`],
  })();

/** הזמנה חדשה מהפורטל: נכנסת לטיוטה. בטיוטה הסוכן (חלק ד') מפרק אותה לפריטים, ורינה מאשרת. */
export async function createDraftOrder(client: PortalClient, text: string): Promise<string> {
  const now = new Date();
  const values = {
    [COLS.orders.client]: { item_ids: [Number(client.id)] },
    [COLS.orders.status]: { label: "טיוטה" },
    [COLS.orders.channel]: { label: "פורטל" },
    [COLS.orders.receivedAt]: { date: now.toISOString().slice(0, 10) },
    ...(text ? { [COLS.orders.notes]: { text: `מהפורטל:\n${text}` } } : {}),
  };
  const data = await gql<{ create_item: { id: string } }>(
    `mutation ($b: ID!, $n: String!, $v: JSON) {
      create_item(board_id: $b, item_name: $n, column_values: $v, create_labels_if_missing: true) { id }
    }`,
    { b: BOARDS.orders, n: `טיוטה מהפורטל · ${client.name}`, v: JSON.stringify(values) },
  );
  return data.create_item.id;
}

/** העלאת קובץ לעמודת "קבצי מקור" של ההזמנה (multipart ל-/v2/file, נבדק מול monday). */
export async function attachFile(itemId: string, file: File): Promise<void> {
  const form = new FormData();
  form.append(
    "query",
    `mutation ($file: File!) { add_file_to_column(item_id: ${Number(itemId)}, column_id: "${COLS.orders.files}", file: $file) { id } }`,
  );
  form.append("variables[file]", file, file.name);
  const res = await fetch(`${API}/file`, { method: "POST", headers: { Authorization: token() }, body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.errors) {
    console.error("monday file upload error", res.status, JSON.stringify(body.errors));
    throw new Error("file upload failed");
  }
}
