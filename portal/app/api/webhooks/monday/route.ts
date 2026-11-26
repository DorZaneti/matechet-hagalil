import { NextResponse } from "next/server";
import { revalidateTag } from "next/cache";
import { timingSafeEqual } from "node:crypto";

export const runtime = "nodejs";

/**
 * בונוס: webhook מ-monday. כשסטטוס של הזמנה או שלב של פריט משתנה, monday שולח לכאן אירוע,
 * ואנחנו מנקים את ה-cache. בפעם הבאה שהלקוח פותח את הדף (או אחרי רענון), הוא רואה את המצב העדכני מיד,
 * בלי לחכות 30 שניות.
 *
 * webhook רגיל של monday (לא של אפליקציה) לא חתום, ולכן מאמתים עם סוד בכתובת:
 *   https://<domain>/api/webhooks/monday?secret=<MONDAY_WEBHOOK_SECRET>
 */
function secretOk(given: string | null): boolean {
  const expected = process.env.MONDAY_WEBHOOK_SECRET;
  if (!expected || !given) return false;
  const a = Buffer.from(given), b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(req: Request) {
  if (!secretOk(new URL(req.url).searchParams.get("secret"))) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
  const body = await req.json().catch(() => ({}));

  // כשיוצרים webhook, monday שולח challenge ומצפה לקבל אותו בחזרה כמו שהוא
  if (body && typeof body.challenge === "string") {
    return NextResponse.json({ challenge: body.challenge });
  }

  const ev = body?.event ?? {};
  // אנחנו לא מנסים להבין לאיזה לקוח שייך כל אירוע: עם 60 לקוחות, לנקות את כל ה-cache זה זול ובטוח יותר
  revalidateTag("monday");
  console.log("monday webhook", ev.type, ev.boardId, ev.pulseId, ev.columnId);
  return NextResponse.json({ ok: true });
}
