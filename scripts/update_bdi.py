#!/usr/bin/env python3

import datetime
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "latest.json"


def load_previous():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("Saved data.")


def build_index(current, previous):
    change = current - previous
    pct = round((change / previous) * 100, 2) if previous else 0
    return {
        "value": current,
        "prev": previous,
        "change": change,
        "pct": pct,
    }


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
            print(f"[API] BDI={result['bdi']['value']}")
            return result

        return None

    except Exception as e:
        print("[API ERROR]", e)
        return None


def fetch_all_data():
    previous = load_previous()

    if not previous:
        print("No previous data.")
        return None

    today = datetime.date.today()

    # skip weekends
    if today.weekday() >= 5:
        print("Weekend — checking API anyway...")

    api = fetch_balticexchange_api()

    if not api:
        print("API failed.")
        return None

print(f"[DEBUG] API DATE={api['bdi']['date']} PREVIOUS DATE={previous.get('date')}")

    new_date = api["bdi"]["date"]
    prev_date = previous.get("date")

    if new_date == prev_date:
        print("Same date — but forcing update to sync")

    def safe(key):
        if key in api:
            return build_index(api[key]["value"], previous[key]["value"])
        return previous[key]

    data = {
        "date": new_date,
        "updated": datetime.datetime.utcnow().strftime("%H:%M UTC"),
        "source": "Baltic Exchange",

        "bdi": safe("bdi"),
        "bci": safe("bci"),
        "bpi": safe("bpi"),
        "bsi": safe("bsi"),
        "bhsi": safe("bhsi"),

        "stats": previous.get("stats", {}),
    }

    return data


if __name__ == "__main__":
    data = fetch_all_data()

    if not data:
        print("No update performed.")
        sys.exit(0)

    save_data(data)
    print("Update complete.")