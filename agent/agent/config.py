"""Board/column ids in the "מתכת הגליל" workspace, model choice and price table."""
import os

BOARDS = {
    "clients": os.environ.get("MONDAY_CLIENTS_BOARD_ID", "5108619489"),
    "orders": os.environ.get("MONDAY_ORDERS_BOARD_ID", "5108619492"),
}

COLS = {
    "clients": {
        "contact": "text_mm9fw32x",
        "phone": "phone_mm9fexqh",
        "contacts": "long_text_mm9fdwtw",
        "aliases": "long_text_mm9fkfxt",
        "orders": "board_relation_mm9fva76",
    },
    "orders": {
        "client": "board_relation_mm9f8ktk",
        "contact": "text_mm9f65sx",
        "phone": "phone_mm9f7f2q",
        "received": "date_mm9fn9v5",
        "due": "date_mm9fypm1",
        "status": "color_mm9fthcm",
        "urgent": "boolean_mm9f3eq4",
        "project": "text_mm9f717x",
        "channel": "color_mm9f8wbp",
        "number": "text_mm9fczvm",
        "notes": "long_text_mm9f691a",
        "review": "long_text_mm9fhm4n",   # "מה לבדוק"
        "files": "file_mm9fm1jr",
        "po": "text_mm9fsg5c",
        "source": "text_mm9fjgc7",       # "נקלט ע"י"
    },
    "lines": {
        "type": "dropdown_mm9fc007",
        "width": "numeric_mm9f4zht",
        "height": "numeric_mm9fg0vs",
        "dims_raw": "text_mm9fj8dd",
        "qty": "numeric_mm9ffjg8",
        "delivered": "numeric_mm9fxwb7",
        "color": "dropdown_mm9fatep",
        "stage": "color_mm9f11w5",
    },
}

ITEM_TYPES = ["מעקה מרפסת", "מעקה מדרגות", "שער חניה", "שער כניסה", "מסגרת פלדה", "אחר"]
CHANNELS = ["מייל", "וואטסאפ", "טלפון", "הזמנת רכש", "פורטל", "אתר", "לא ידוע"]

STATUS_OK = "פתוחה"
STATUS_REVIEW = "לבדיקה"

# Sonnet 5.5 is the default: reliable Hebrew, reads PDFs and photos. Haiku 5.5 is the cheap option (--model).
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")

# USD per million tokens (Claude API list prices, Nov 2026). Used only for the cost estimate in eval.
PRICES = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
}

TIMEZONE = "Asia/Jerusalem"
MAX_AGENT_TURNS = 4
DUPLICATE_WINDOW_DAYS = 30
