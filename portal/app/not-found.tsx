// הודעה אחת לכל מקרה של קישור שלא נמצא, כדי שלא יהיה אפשר להסיק ממנה אם קישור מסוים קיים.
export default function NotFound() {
  return (
    <section className="card" style={{ marginTop: 24 }}>
      <h1 style={{ marginTop: 0 }}>הקישור לא תקין</h1>
      <p className="lead">ייתכן שהקישור הוחלף או הועתק חלקית. בקשו קישור חדש מהמשרד.</p>
    </section>
  );
}
