// מזהי הלוחות והעמודות ב-monday (workspace "מתכת הגליל").
// הפורטל קורא רק את העמודות שברשימה. מחיר, חיוב, הערות פנימיות ו"לבדיקה" לא נשלפים בכלל,
// ולכן לא יכולים לדלוף ללקוח גם בטעות.

export const BOARDS = {
  clients: process.env.MONDAY_CLIENTS_BOARD_ID ?? "5108619489",
  orders: process.env.MONDAY_ORDERS_BOARD_ID ?? "5108619492",
};

export const COLS = {
  clients: {
    portalHash: "text_mm9f53cb",       // SHA-256 של הקישור האישי
    orders: "board_relation_mm9fva76", // חיבור הפוך להזמנות
  },
  orders: {
    client: "board_relation_mm9f8ktk",
    receivedAt: "date_mm9fn9v5",
    dueAt: "date_mm9fypm1",
    status: "color_mm9fthcm",
    urgent: "boolean_mm9f3eq4",
    project: "text_mm9f717x",
    sourceNumber: "text_mm9fczvm",
    channel: "color_mm9f8wbp",
    notes: "long_text_mm9f691a",       // נכתב רק בהזמנה חדשה מהפורטל, לא נקרא חזרה
    files: "file_mm9fm1jr",
  },
  lines: {
    stage: "color_mm9f11w5",
    qty: "numeric_mm9ffjg8",
    delivered: "numeric_mm9fxwb7",
    color: "dropdown_mm9fatep",
  },
} as const;

export const ORDER_READ_COLUMNS = [
  COLS.orders.client, COLS.orders.receivedAt, COLS.orders.dueAt, COLS.orders.status,
  COLS.orders.urgent, COLS.orders.project, COLS.orders.sourceNumber,
];
export const LINE_READ_COLUMNS = [
  COLS.lines.stage, COLS.lines.qty, COLS.lines.delivered, COLS.lines.color,
];

export const UPLOAD = {
  maxBytes: 10 * 1024 * 1024,
  maxTextChars: 5000,
  allowedTypes: [
    "application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
  ],
};
