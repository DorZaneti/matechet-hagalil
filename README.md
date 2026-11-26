# מתכת הגליל: מטלת בית

| חלק | תיקייה | איפה רץ |
| --- | --- | --- |
| א' ניתוח מקרה ואפיון | מסמך נפרד (Claude Docs) | — |
| ב' מערכת monday + סקריפט ייבוא | `part-b-monday/` | workspace "מתכת הגליל" ב-monday |
| ג' פורטל לקוח | `portal/` | Vercel (Root Directory = `portal`) |
| ד' סוכן קליטת הזמנות + "איפה ההזמנה שלי?" | `agent/` | Render (`render.yaml`) |

## סדר הפריסה

1. **Render:** New → Blueprint → הריפו הזה. מזינים `ANTHROPIC_API_KEY` ו-`MONDAY_TOKEN`. בסוף מעתיקים את `AGENT_SHARED_SECRET` שנוצר ואת כתובת השירות.
2. **Vercel:** Import → הריפו הזה, עם Root Directory = `portal`. משתני סביבה: `MONDAY_TOKEN`, `MONDAY_WEBHOOK_SECRET`, `AGENT_URL` (הכתובת מ-Render), ו-`AGENT_SHARED_SECRET` (אותו ערך כמו ב-Render).
3. **webhook ב-monday:** הפקודה ב-`portal/README.md`.
4. **קישורי לקוח:** `node portal/scripts/portal-link.mjs <client item id>`.

כל חלק כולל README משלו עם ההחלטות, הבדיקות והמגבלות.
