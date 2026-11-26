// אין דף כניסה כללי ואין רשימת לקוחות. כל לקוח נכנס רק דרך הקישור האישי שלו.
export default function Home() {
  return (
    <section className="card" style={{ marginTop: 24 }}>
      <h1 style={{ marginTop: 0 }}>מעקב הזמנות</h1>
      <p className="lead">
        הכניסה היא דרך הקישור האישי שקיבלתם מהמשרד. אם אין לכם קישור, או שהוא לא עובד, דברו עם רינה.
      </p>
    </section>
  );
}
