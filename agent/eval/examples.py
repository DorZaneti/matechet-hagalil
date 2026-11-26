"""The examples from Appendix B, verbatim, and the expected result for each.

The "expected" fields are my reading of the case, written before running the model, so that eval compares
against them. They are not model output.
"""
from pathlib import Path

RECEIVED_AT = "2026-11-26T09:00:00+02:00"  # fixed, so relative dates ("סוף החודש") give the same result every run
HERE = Path(__file__).parent

ROTEM, AB, SG = "3388890160", "3388889795", "3388876346"

EXAMPLES = [
    {
        "id": 1,
        "title": "מייל",
        "channel": "מייל",
        "text": ("שלום רינה, מצורפת הזמנה לפרויקט האלונים בעפולה, בניין B. 36 מעקות מרפסת 120x100 ו-4 מעקות "
                 "180x100, הכל RAL 7016. נצטרך עד סוף החודש, אפשר בשתי אספקות. בברכה, סהר בן דוד, קבוצת רותם."),
        "expected": {
            "status": "לבדיקה",
            "why": "כתוב 'מצורפת הזמנה' אבל אין קובץ. כל השאר ברור.",
            "client_id": ROTEM,
            "lines": [("מעקה מרפסת", 120, 100, 36, "RAL 7016"), ("מעקה מרפסת", 180, 100, 4, "RAL 7016")],
            "date": "2026-11-30",
        },
    },
    {
        "id": 2,
        "title": "וואטסאפ",
        "channel": "וואטסאפ",
        "text": "אחי תעשה לי עוד שער כמו פעם שעברה רק רחב יותר במטר שחור כמו תמיד דחוף לי לשבוע הבא מוטי",
        "expected": {
            "status": "לבדיקה",
            "why": "לקוח רק לפי שם פרטי; הפריט נבנה מהזמנה 1042 (400x180 ← 500x180); 'שחור' בלי קוד.",
            "client_id": AB,
            "lines": [("שער חניה", 500, 180, 1, "RAL 9005")],
            "date": "2026-12-03",
        },
    },
    {
        "id": 3,
        "title": "הזמנת רכש (טקסט מתוך PDF)",
        "channel": "הזמנת רכש",
        "text": ("ש.ג. עבודות עפר בע\"מ | הזמנת רכש מס' 2026-118 | ספק: מתכת הגליל\n"
                 "שורה 1: מסגרת פלדה מגולוונת 200x300 — כמות 8\n"
                 "שורה 2: מסגרת פלדה מגולוונת 250x300 — כמות 4\n"
                 "תאריך אספקה: 15.12.2026 | כתובת: אתר מגדלי העמק, יקנעם"),
        "expected": {
            "status": "פתוחה",
            "why": "מסמך מובנה ומלא. הערה בלבד: 250x300 x4 זהה להזמנה 1048 שבוטלה.",
            "client_id": SG,
            "lines": [("מסגרת פלדה", 200, 300, 8, "מגולוון"), ("מסגרת פלדה", 250, 300, 4, "מגולוון")],
            "date": "2026-12-15",
        },
    },
    {
        "id": 4,
        "title": "בונוס: תמונה של סקיצה (סינתטית)",
        "channel": "וואטסאפ",
        "text": "",
        "image": HERE / "sketch_example4.png",
        "expected": {
            "status": "לבדיקה",
            "why": "אין שם לקוח, חסר אורך, אין כמות. צריך לשאול ולא לנחש.",
            "client_id": None,
            "lines": [("מעקה מדרגות", None, 90, None, "RAL 9005")],
            "date": None,
        },
    },
]
