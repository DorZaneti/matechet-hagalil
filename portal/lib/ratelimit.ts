// הגבלת קצב בזיכרון: עד 5 הזמנות ב-10 דקות לכל קישור.
// ב-serverless כל instance סופר לבד, אז זו רק שכבת הגנה ראשונה. בייצור צריך מונה משותף (למשל Upstash Redis).
const WINDOW_MS = 10 * 60 * 1000;
const LIMIT = 5;
const hits = new Map<string, number[]>();

export function allow(key: string, now = Date.now()): boolean {
  const recent = (hits.get(key) ?? []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= LIMIT) {
    hits.set(key, recent);
    return false;
  }
  recent.push(now);
  hits.set(key, recent);
  return true;
}
