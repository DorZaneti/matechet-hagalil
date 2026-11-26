import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";
import { UPLOAD } from "@/lib/config.ts";
import { attachFile, createDraftOrder, getClientByToken, hashToken, isWellFormedToken } from "@/lib/monday.ts";
import { forwardToAgent } from "@/lib/agent.ts";
import { allow } from "@/lib/ratelimit.ts";

export const runtime = "nodejs";

const fail = (status: number, error: string) => NextResponse.json({ ok: false, error }, { status });

export async function POST(req: Request) {
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return fail(400, "הבקשה לא תקינה");
  }

  // הזיהוי מתבצע מחדש בשרת בכל בקשה, ולא סומכים על שום מזהה לקוח שמגיע מהדפדפן.
  const rawToken = String(form.get("token") ?? "");
  if (!isWellFormedToken(rawToken)) return fail(401, "הקישור לא תקין");
  const client = await getClientByToken(rawToken).catch(() => null);
  if (!client) return fail(401, "הקישור לא תקין");

  if (!allow(hashToken(rawToken))) return fail(429, "נשלחו הרבה הזמנות בזמן קצר. נסו שוב בעוד כמה דקות");

  const text = String(form.get("text") ?? "").trim();
  const fileEntry = form.get("file");
  const file = fileEntry instanceof File && fileEntry.size > 0 ? fileEntry : null;

  if (!text && !file) return fail(400, "צריך לכתוב את ההזמנה או לצרף קובץ");
  if (text.length > UPLOAD.maxTextChars) return fail(400, "הטקסט ארוך מדי");
  if (file) {
    if (file.size > UPLOAD.maxBytes) return fail(400, "הקובץ גדול מ-10MB");
    if (!UPLOAD.allowedTypes.includes(file.type)) return fail(400, "סוג הקובץ לא נתמך. אפשר PDF, תמונה, Excel או Word");
  }

  let orderItemId: string;
  try {
    orderItemId = await createDraftOrder(client, text);
  } catch {
    return fail(502, "לא הצלחנו לשמור את ההזמנה. נסו שוב, או התקשרו למשרד");
  }

  let fileSaved = true;
  if (file) {
    try {
      await attachFile(orderItemId, file);
    } catch {
      fileSaved = false; // ההזמנה כבר נשמרה. מחזירים הצלחה, ומבקשים לשלוח את הקובץ בדרך אחרת
    }
  }

  const agent = await forwardToAgent({
    orderItemId, clientId: client.id, clientName: client.name, text,
    fileName: file && fileSaved ? file.name : null, source: "portal",
  });

  revalidateTag(`client:${client.id}`);
  revalidateTag("monday"); // ההזמנה החדשה נוספה לרשימת ההזמנות המקושרות של הלקוח
  return NextResponse.json({ ok: true, fileSaved, agent });
}
