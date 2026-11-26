import { NextResponse } from "next/server";
import { getClientByToken, hashToken, isWellFormedToken } from "@/lib/monday.ts";
import { askAgent } from "@/lib/agent.ts";
import { allow } from "@/lib/ratelimit.ts";

export const runtime = "nodejs";
export const maxDuration = 60; // Vercel: lets the agent wake up on Render free

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const token = String(body.token ?? "");
  const question = String(body.question ?? "").trim().slice(0, 500);
  if (!isWellFormedToken(token)) return NextResponse.json({ ok: false, error: "הקישור לא תקין" }, { status: 401 });
  const client = await getClientByToken(token).catch(() => null);
  if (!client) return NextResponse.json({ ok: false, error: "הקישור לא תקין" }, { status: 401 });
  if (!question) return NextResponse.json({ ok: false, error: "מה תרצו לשאול?" }, { status: 400 });
  if (!allow(`ask:${hashToken(token)}`)) {
    return NextResponse.json({ ok: false, error: "הרבה שאלות בזמן קצר. נסו שוב בעוד כמה דקות" }, { status: 429 });
  }

  const res = await askAgent(client.id, client.name, question);
  if (!res) {
    return NextResponse.json({ ok: true, answer: "לא הצלחתי לענות כרגע. אפשר לראות את מצב ההזמנות למעלה, או לדבר עם רינה.", needsHuman: true });
  }
  return NextResponse.json({ ok: true, answer: res.answer, needsHuman: res.needsHuman });
}
