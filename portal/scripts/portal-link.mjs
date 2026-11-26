// מנפיק קישור אישי חדש ללקוח. אותה פקודה גם מבטלת את הקישור הקודם, כי היא מחליפה את ה-hash.
//   MONDAY_TOKEN=... PORTAL_URL=https://<domain> node scripts/portal-link.mjs <client item id>
// ב-monday נשמר רק ה-hash. את הקישור המלא רואים פעם אחת, כאן, ושולחים ללקוח.
import { createHash, randomBytes } from "node:crypto";

const [itemId] = process.argv.slice(2);
const { MONDAY_TOKEN, PORTAL_URL = "http://localhost:3000" } = process.env;
const BOARD = process.env.MONDAY_CLIENTS_BOARD_ID ?? "5108619489";
const COL = "text_mm9f53cb";
if (!itemId || !MONDAY_TOKEN) {
  console.error("usage: MONDAY_TOKEN=... node scripts/portal-link.mjs <client item id>");
  process.exit(1);
}

const token = randomBytes(24).toString("base64url"); // 192 ביט, 32 תווים
const hash = createHash("sha256").update(token).digest("hex");

const res = await fetch("https://api.monday.com/v2", {
  method: "POST",
  headers: { Authorization: MONDAY_TOKEN, "Content-Type": "application/json" },
  body: JSON.stringify({
    query: `mutation ($b: ID!, $i: ID!, $v: String) { change_simple_column_value(board_id: $b, item_id: $i, column_id: "${COL}", value: $v) { id name } }`,
    variables: { b: BOARD, i: itemId, v: hash },
  }),
});
const body = await res.json();
if (body.errors) {
  console.error(JSON.stringify(body.errors));
  process.exit(1);
}
console.log(`${body.data.change_simple_column_value.name}: ${PORTAL_URL}/c/${token}`);
