#!/usr/bin/env python3
"""Reads the Dear Lottery result page and keeps results.json up to date.

Rule used: last 3 digits of the 5-digit number of the 1st prize ticket
(example: 66J 25818 -> 818).  Only the standard library is used.
"""
import json, re, sys, os
from html.parser import HTMLParser
from urllib.request import Request, urlopen

URL = "https://dearlottery.in/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json")
DRAW_ORDER = {"1PM": 1, "6PM": 2, "8PM": 3}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
     "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"])}
TICKET = re.compile(r"^(\d{2}[A-Z])\s*(\d{5})$")


class Rows(HTMLParser):
    """Collects the text of every table row and a flat text of the page."""
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self.flat = [], None, None, []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "tr":
            self._row = []
        if tag in ("td", "th"):
            self._cell = []
        if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.flat.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._skip:
            return
        self.flat.append(data + " ")
        if self._cell is not None:
            self._cell.append(data)


def fetch(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9"})
    with urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def make(date, draw, ticket):
    m = TICKET.match(ticket.strip().upper())
    if not m:
        return None
    series, num = m.groups()
    return {"id": f"{date}-{draw}", "date": date, "draw": draw,
            "ticket": f"{series} {num}", "n3": num[-3:]}


def parse(html):
    p = Rows()
    p.feed(html)
    flat = re.sub(r"[ \t]+", " ", "".join(p.flat))
    found = {}

    # 1) Month chart: header "CHART NOVEMBER 2026", rows: day | 1 PM | 6 PM | 8 PM
    mm = re.search(r"CHART\s+([A-Za-z]+)\s+(\d{4})", flat, re.I)
    if mm and mm.group(1).upper() in MONTHS:
        month, year = MONTHS[mm.group(1).upper()], int(mm.group(2))
        for row in p.rows:
            if len(row) >= 4 and re.fullmatch(r"\d{1,2}", row[0].strip()):
                day = int(row[0])
                for cell, draw in zip(row[1:4], ("1PM", "6PM", "8PM")):
                    r = make(f"{year:04d}-{month:02d}-{day:02d}", draw, cell)
                    if r:
                        found[r["id"]] = r
        if not found:  # chart exists but not as a table: look at the flat text
            seg = flat[mm.start():]
            for m in re.finditer(r"(?<!\d)(\d{1,2})\s+((?:\d{2}[A-Z]\s?\d{5}\s*){1,3})", seg):
                day = int(m.group(1))
                tickets = re.findall(r"\d{2}[A-Z]\s?\d{5}", m.group(2))
                if len(tickets) == 3:
                    for t, draw in zip(tickets, ("1PM", "6PM", "8PM")):
                        r = make(f"{year:04d}-{month:02d}-{day:02d}", draw, t)
                        if r:
                            found[r["id"]] = r

    # 2) Latest-result blocks: "77H 85744 Draw No. 55 21/11/26 8 PM"
    for m in re.finditer(
            r"(\d{2}[A-Z])\s*(\d{5})\s*Draw\s*No\.?\s*\d+\s*(\d{2})/(\d{2})/(\d{2})\s*(\d{1,2})\s*PM",
            flat, re.I):
        series, num, dd, mo, yy, hr = m.groups()
        draw = f"{int(hr)}PM"
        if draw in DRAW_ORDER:
            r = make(f"20{yy}-{mo}-{dd}", draw, f"{series}{num}")
            if r:
                found.setdefault(r["id"], r)   # the chart wins if both exist
    return list(found.values())


def merge(old, new):
    by = {r["id"]: r for r in old}
    changed = 0
    for r in new:
        if r["id"] not in by or by[r["id"]].get("ticket") != r["ticket"]:
            by[r["id"]] = r
            changed += 1
    out = sorted(by.values(), key=lambda r: (r["date"], DRAW_ORDER[r["draw"]]))
    return out, changed


def main():
    src = sys.argv[sys.argv.index("--file") + 1] if "--file" in sys.argv else None
    html = open(src, encoding="utf-8").read() if src else fetch(URL)
    new = parse(html)
    if not new:
        print("ERROR: no results found on the page (the site layout may have changed)")
        sys.exit(1)
    try:
        old = json.load(open(OUT, encoding="utf-8")).get("results", [])
    except Exception:
        old = []
    merged, changed = merge(old, new)
    if changed:
        json.dump({"source": URL, "rule": "last 3 digits of the 5-digit first-prize ticket number",
                   "results": merged}, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"read {len(new)} results from the page, {changed} new or changed, {len(merged)} saved")


if __name__ == "__main__":
    main()
