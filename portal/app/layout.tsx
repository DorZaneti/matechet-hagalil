import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "מתכת הגליל · מעקב הזמנות",
  description: "מעקב הזמנות ללקוחות מתכת הגליל",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1f3a5f",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body>
        <header className="topbar">
          <div className="wrap">
            <span className="brand">מתכת הגליל</span>
            <span className="brand-sub">מעקב הזמנות</span>
          </div>
        </header>
        <main className="wrap">{children}</main>
        <footer className="wrap footer">שאלות על הזמנה? דברו עם רינה במשרד</footer>
      </body>
    </html>
  );
}
