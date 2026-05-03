#!/usr/bin/env python3

import datetime
import json
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "latest.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


# ----------------------------
# LOAD PREVIOUS DATA
# ----------------------------
def load_previous():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return None


# ----------------------------
# BUILD INDEX STRUCTURE
# ----------------------------
def build_index(current, previous):
    change = current - previous
    pct = round((change / previous) * 100, 2) if previous else 0
    return {
        "value": current,
        "prev": previous,
        "change": change,
        "pct": pct,
    }


# ----------------------------
# PRIMARY: BALTIC EXCHANGE API
# ----------------------------
def fetch_balticexchange_api():
    try:
        url = "https://blacksun-api.balticexchange.com/api/ticker"
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            return None

        data = r.json()
        result = {}

        for item in data:
            code = item.get("indexDataSetName", "").lower()
            current = item.get("current")

            if current and current.get("value") is not None:
                result[code] = {
                    "value": int(current["value"]),
                    "date": current["indexDate"][:10],
                }

        if "bdi" in result:
            print(f"[API SUCCESS] BDI={result['bdi']['value']} DATE={result['bdi']['date']}")
            return result

        return None

    except Exception as e:
        print("[API ERROR]", e)
        return None


# ----------------------------
# FALLBACK: HANDYBULK
# ----------------------------
def fetch_handybulk():
    try:
        url = "https://www.handybulk.com/baltic-dry-index/"
        r = requests.get(url, headers=HEADERS, timeout=15)

        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "lxml")
        text = " ".join(soup.get_text(" ").split())

        import re

        match = re.search(r"BDI[^0-9]{0,40}([\d,]{3,6})", text)

        if match:
            value = int(match.group(1).replace(",", ""))
            print(f"[Fallback] HandyBulk BDI={value}")
            return {"bdi": value}

        return None

    except Exception as e:
        print("[HANDYBULK ERROR]", e)
        return None


# ----------------------------
# MAIN LOGIC
# ----------------------------
def fetch_all_data():
    previous = load_previous()

    if not previous:
        print("No previous data found. Exiting.")
        return None

    today = datetime.date.today()

    # Skip weekends
    if today.weekday() >= 5:
        print("Weekend — no update.")
        return None

    print(f"=== RUN {today} ===")

    # ----------------------------
    # PRIMARY API
    # ----------------------------
    api = fetch_balticexchange_api()

    if api:
        new_date = api["bdi"]["date"]
        prev_date = previous.get("date")

        # Prevent duplicate updates
        if new_date == prev_date:
            print("No new data yet.")
            return None

        print("Using Baltic Exchange API data.")

        data = {
            "date": new_date,
            "updated": datetime.datetime.utcnow().strftime("%H:%M UTC"),
            "source": "Baltic Exchange",

            "bdi": build_index(api["bdi"]["value"], previous["bdi"]["value"]),
            "bci": build_index(api["bci"]["value"], previous["bci"]["value"]),
            "bpi": build_index(api["bpi"]["value"], previous["bpi"]["value"]),
            "bsi": build_index(api["bsi"]["value"], previous["bsi"]["value"]),
            "bhsi": build_index(api["bhsi"]["value"], previous["bhsi"]["value"]),

            "stats": previous.get("stats", {}),
        }

        # Update stats
        stats = data["stats"]
        stats["week52High"] = max(stats.get("week52High", data["bdi"]["value"]), data["bdi"]["value"])
        stats["week52Low"] = min(stats.get("week52Low", data["bdi"]["value"]), data["bdi"]["value"])
        data["stats"] = stats

        return data

    # ----------------------------
    # FALLBACK LOGIC
    # ----------------------------
    print("API failed — using fallback.")

    fb = fetch_handybulk()

    if fb and fb.get("bdi"):
        new_bdi = fb["bdi"]
        prev_bdi = previous["bdi"]["value"]

        data = previous.copy()
        data["updated"] = datetime.datetime.utcnow().strftime("%H:%M UTC")
        data["source"] = "Fallback (HandyBulk)"
        data["bdi"] = build_index(new_bdi, prev_bdi)

        return data

    print("All sources failed.")
    return None


# ----------------------------
# SAVE DATA
# ----------------------------
def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("Saved data.")


# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    data = fetch_all_data()

    if not data:
    print("No update from primary logic — forcing fallback update")

    previous = load_previous()

    if previous:
        previous["updated"] = datetime.datetime.utcnow().strftime("%H:%M UTC")
        previous["source"] = "No update — kept previous"

        save_data(previous)
        sys.exit(0)

    else:
        print("No previous data — exiting")
        sys.exit(1)
