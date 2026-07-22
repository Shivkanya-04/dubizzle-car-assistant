import os
import re
import sqlite3
import csv
import json
from datetime import datetime

import pandas as pd
from google import genai

VALID_HOURS = range(8, 20)  # 8am - 8pm (slot must START within this range)
VALID_WEEKDAYS = range(0, 6)  # Monday(0) - Saturday(5); Sunday(6) is excluded


class CarBotEngine:
    def __init__(self, csv_path="cars.csv", db_path="app.db", leads_path="leads.csv"):
        self.c_path = csv_path
        self.db_path = db_path
        self.leads_path = leads_path

        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        self.df = pd.read_csv(self.c_path)
        # Normalize column names so header casing in the provided dataset never breaks filtering
        self.df.columns = [c.strip().lower() for c in self.df.columns]

        # Guarantee a stable unique id column the model can reference for booking
        if "id" not in self.df.columns:
            self.df.insert(0, "id", range(1, len(self.df) + 1))

        for col in ("make", "model", "trim", "description"):
            if col not in self.df.columns:
                self.df[col] = ""

        self._init_db()
        self._init_leads_file()

    # ---------------- persistence setup ----------------

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    name TEXT,
                    prefs TEXT,
                    history TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT,
                    lid INTEGER,
                    slot TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT,
                    name TEXT,
                    budget TEXT,
                    needs TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _init_leads_file(self):
        if not os.path.exists(self.leads_path):
            with open(self.leads_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["uid", "name", "budget", "needs", "created_at"])

    # ---------------- user profile (long-term memory) ----------------

    def get_user(self, uid):
        with sqlite3.connect(self.db_path) as c:
            r = c.execute(
                "SELECT uid, name, prefs, history FROM users WHERE uid = ?", (uid,)
            ).fetchone()
            if r:
                return {
                    "uid": r[0],
                    "name": r[1] or "",
                    "prefs": json.loads(r[2] or "{}"),
                    "history": json.loads(r[3] or "[]"),
                }
            return {"uid": uid, "name": "", "prefs": {}, "history": []}

    def save_user(self, udata):
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                "INSERT OR REPLACE INTO users (uid, name, prefs, history) VALUES (?, ?, ?, ?)",
                (
                    udata["uid"],
                    udata.get("name", ""),
                    json.dumps(udata.get("prefs", {})),
                    json.dumps(udata.get("history", [])),
                ),
            )

    # ---------------- inventory search ----------------

    def search_inventory(self, make=None, model=None, year_min=None, year_max=None,
                          price_max=None, price_min=None, q=None):
        res = self.df.copy()
        if make:
            res = res[res["make"].astype(str).str.contains(make, case=False, na=False)]
        if model:
            res = res[res["model"].astype(str).str.contains(model, case=False, na=False)]
        if year_min:
            res = res[res["year"] >= year_min]
        if year_max:
            res = res[res["year"] <= year_max]
        if price_min:
            res = res[res["price"] >= price_min]
        if price_max:
            res = res[res["price"] <= price_max]
        if q:
            m1 = res["description"].astype(str).str.contains(q, case=False, na=False)
            m2 = res["trim"].astype(str).str.contains(q, case=False, na=False)
            res = res[m1 | m2]
        return res.head(5).to_dict(orient="records")

    def get_listing(self, lid):
        row = self.df[self.df["id"] == lid]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    # ---------------- booking ----------------

    def validate_slot(self, slot: str):
        """
        Returns (is_valid: bool, message: str, parsed: datetime|None)
        Expected slot format: 'YYYY-MM-DD HH:MM' (24h).
        """
        try:
            dt = datetime.strptime(slot.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            return False, "Slot must be in 'YYYY-MM-DD HH:MM' format.", None

        if dt.weekday() not in VALID_WEEKDAYS:
            return False, "Viewings are only available Monday to Saturday.", None
        if dt.hour not in VALID_HOURS:
            return False, "Viewings are only available between 8am and 8pm.", None
        return True, "ok", dt

    def book_slot(self, uid, lid, slot):
        listing = self.get_listing(lid)
        if listing is None:
            return f"Sorry, no listing found with ID {lid}."

        is_valid, msg, _ = self.validate_slot(str(slot))
        if not is_valid:
            return f"Could not book: {msg} Please propose a valid Mon-Sat, 8am-8pm slot."

        with sqlite3.connect(self.db_path) as c:
            c.execute(
                "INSERT INTO bookings (uid, lid, slot) VALUES (?, ?, ?)", (uid, lid, slot)
            )
        return (
            f"Successfully booked a viewing for {listing.get('make')} {listing.get('model')} "
            f"(Listing ID {lid}) on {slot}."
        )

    # ---------------- lead qualification ----------------

    def record_lead(self, uid, name, budget, needs):
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                "INSERT INTO leads (uid, name, budget, needs) VALUES (?, ?, ?, ?)",
                (uid, name, budget, needs),
            )
        with open(self.leads_path, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([uid, name, budget, needs, datetime.utcnow().isoformat()])
        return "Lead details qualified and recorded successfully."
