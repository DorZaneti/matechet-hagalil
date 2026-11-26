import { notFound } from "next/navigation";
import OrderCard from "@/components/OrderCard.tsx";
import NewOrderForm from "@/components/NewOrderForm.tsx";
import AskBox from "@/components/AskBox.tsx";
import { getClientByToken, getOrdersForClient, isWellFormedToken } from "@/lib/monday.ts";

// הדף נבנה בשרת בכל בקשה. הנתונים מגיעים מ-monday דרך cache קצר שה-webhook מנקה (lib/monday.ts).
export const dynamic = "force-dynamic";

export default async function ClientPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  if (!isWellFormedToken(token)) notFound();

  const client = await getClientByToken(token);
  if (!client) notFound();

  const orders = await getOrdersForClient(client);
  const active = orders.filter((o) => o.status !== "סופקה" && o.status !== "בוטלה");
  const past = orders.filter((o) => !active.includes(o));
  const updated = new Date().toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jerusalem" });

  return (
    <>
      <h1>שלום, {client.name}</h1>
      <p className="lead">
        כאן רואים את ההזמנות שלכם ואיפה כל פריט נמצא בייצור. <span className="updated">עודכן ב-{updated}</span>
      </p>

      <h2>הזמנות פעילות ({active.length})</h2>
      {active.length === 0 ? <div className="card empty">אין כרגע הזמנות פעילות</div> : active.map((o) => <OrderCard key={o.id} order={o} />)}

      <h2>שאלה על הזמנה</h2>
      <AskBox token={token} />

      <h2>הזמנה חדשה</h2>
      <NewOrderForm token={token} />

      {past.length > 0 && (
        <>
          <h2>הזמנות קודמות ({past.length})</h2>
          {past.map((o) => <OrderCard key={o.id} order={o} />)}
        </>
      )}
    </>
  );
}
