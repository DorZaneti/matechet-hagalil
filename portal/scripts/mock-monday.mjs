// שרת monday מדומה לבדיקה מקומית. מחזיר תשובות בצורה שהתקבלה מה-API האמיתי (נובמבר 2026).
// הרצה: node scripts/mock-monday.mjs  ואז  MONDAY_API_URL=http://localhost:4010/v2 MONDAY_TOKEN=x npm run dev
import http from "node:http";

const HASH_ROTEM = "568752501d644d387e116ac968f251ae1c66cda05e05b6778cf8f5f24a959557"; // הקישור של קבוצת רותם
const rel = (ids) => ({ id: "board_relation_mm9f8ktk", text: null, linked_item_ids: ids });
const t = (id, text) => ({ id, text });
const line = (id, name, stage, qty, color, delivered = "") => ({
  id, name, column_values: [t("color_mm9f11w5", stage), t("numeric_mm9ffjg8", qty), t("numeric_mm9fxwb7", delivered), t("dropdown_mm9fatep", color)],
});
const ord = (id, num, date, status, project, lines, client = "3388890160") => ({
  id, name: `${num} · קבוצת רותם יזמות`,
  column_values: [rel([client]), t("date_mm9fn9v5", date), t("date_mm9fypm1", ""), t("color_mm9fthcm", status), t("boolean_mm9f3eq4", ""), t("text_mm9f717x", project), t("text_mm9fczvm", num)],
  subitems: lines,
});
const ORDERS = {
  "3388890749": ord("3388890749", "1043", "2026-11-05", "פתוחה", "", [line("3388902306", "מעקה מדרגות לפי תכנית", "חיתוך", "12", "RAL 7016")]),
  "3388898579": ord("3388898579", "1049", "2026-11-17", "פתוחה", "חדרה", [line("3388894758", "מעקה מרפסת 90x100", "בצבע", "30", "RAL 7016")]),
  "3388902308": ord("3388902308", "1044", "2026-11-06", "פתוחה", "", [line("3388881311", "מעקה מרפסת 90x100", "ממתין", "8", "RAL 7016")]),
  // הזמנה של לקוח אחר שהוכנסה בכוונה לרשימה, כדי לבדוק שהסינון הכפול חוסם אותה
  "3388878408": ord("3388878408", "1041", "2026-11-03", "סופקה חלקית", "", [line("x", "מעקה מרפסת 120x100", "בצבע", "40", "RAL 9005", "25")], "3388889795"),
};
const log = [];

http.createServer((req, res) => {
  let body = [];
  req.on("data", (c) => body.push(c));
  req.on("end", () => {
    const raw = Buffer.concat(body).toString("utf8");
    const reply = (data) => { res.writeHead(200, { "Content-Type": "application/json" }); res.end(JSON.stringify({ data })); };
    if (req.url === "/v2/file") { log.push("file"); return reply({ add_file_to_column: { id: "f1" } }); }
    if (req.url === "/log") { res.end(JSON.stringify(log)); return; }
    const { query, variables } = JSON.parse(raw || "{}");
    if (!req.headers.authorization) { res.writeHead(401); return res.end(JSON.stringify({ errors: [{ message: "no auth" }] })); }
    if (query.includes("items_page_by_column_values")) {
      const ok = variables.h === HASH_ROTEM;
      return reply({ items_page_by_column_values: { items: ok ? [{ id: "3388890160", name: "קבוצת רותם יזמות", column_values: [{ linked_item_ids: [...Object.keys(ORDERS)] }] }] : [] } });
    }
    if (query.includes("create_item")) { log.push(["create_item", JSON.parse(variables.v)]); return reply({ create_item: { id: "999" } }); }
    if (query.includes("items(ids")) return reply({ items: variables.ids.map((i) => ORDERS[i]).filter(Boolean) });
    res.writeHead(400); res.end(JSON.stringify({ errors: [{ message: "unknown" }] }));
  });
}).listen(4010, () => console.log("mock monday on :4010"));
