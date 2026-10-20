"""Daglig upphandlingsbevakning: hämtar öppna svenska upphandlingar från TED och bygger statiska sidor.

Körs automatiskt varje morgon av .github/workflows/daily.yml (inga API-nycklar, ingen LLM).
Lokalt: python3 scripts/ted_feed.py
"""
import html
import json
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bevakning"
API = "https://api.ted.europa.eu/v3/notices/search"
SITE = "https://ottorosenbaum04-crypto.github.io/tjanster"
DAYS_BACK = 21

BRANSCH = {  # CPV-division -> (slug, namn)
    "45": ("bygg", "Bygg och anläggning"), "71": ("bygg", "Bygg och anläggning"),
    "44": ("bygg", "Bygg och anläggning"),
    "72": ("it-konsult", "IT och konsult"), "48": ("it-konsult", "IT och konsult"),
    "79": ("it-konsult", "IT och konsult"), "73": ("it-konsult", "IT och konsult"),
    "90": ("fastighet-stad", "Fastighetsservice och städ"), "50": ("fastighet-stad", "Fastighetsservice och städ"),
    "77": ("fastighet-stad", "Fastighetsservice och städ"),
    "60": ("transport", "Transport"), "34": ("transport", "Transport"),
    "85": ("vard-omsorg", "Vård och omsorg"), "33": ("vard-omsorg", "Vård och omsorg"),
    "15": ("livsmedel", "Livsmedel och måltider"), "55": ("livsmedel", "Livsmedel och måltider"),
}
OVRIGT = ("ovrigt", "Övrigt")
LAN = {
    "SE110": "Stockholms län", "SE121": "Uppsala län", "SE122": "Södermanlands län", "SE123": "Östergötlands län",
    "SE124": "Örebro län", "SE125": "Västmanlands län", "SE211": "Jönköpings län", "SE212": "Kronobergs län",
    "SE213": "Kalmar län", "SE214": "Gotlands län", "SE221": "Blekinge län", "SE224": "Skåne län",
    "SE231": "Hallands län", "SE232": "Västra Götalands län", "SE311": "Värmlands län", "SE312": "Dalarnas län",
    "SE313": "Gävleborgs län", "SE321": "Västernorrlands län", "SE322": "Jämtlands län",
    "SE331": "Västerbottens län", "SE332": "Norrbottens län",
}


def seller_email():
    m = re.search(r'email:\s*"([^"]+)"', (ROOT / "config.js").read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def fetch(since):
    q = f"buyer-country=SWE AND notice-type=cn-standard AND publication-date>={since}"
    fields = ["publication-number", "title-proc", "buyer-name", "classification-cpv", "publication-date",
              "deadline-receipt-tender-date-lot", "place-of-performance", "buyer-city", "estimated-value-proc"]
    out, page = [], 1
    while True:
        body = json.dumps({"query": q, "fields": fields, "limit": 250, "page": page}).encode()
        req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            notices = json.load(r).get("notices", [])
        out += notices
        if len(notices) < 250 or page >= 20:
            return out
        page += 1


def first(v):
    if isinstance(v, dict):
        v = v.get("swe") or next(iter(v.values()), "")
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v or "").strip()


def parse(n, today):
    deadlines = sorted(d[:10] for d in (n.get("deadline-receipt-tender-date-lot") or []) if d)
    deadline = next((d for d in deadlines if d >= today), None)
    if deadlines and not deadline:
        return None  # alla frister har passerat
    cpv = n.get("classification-cpv") or []
    br = next((BRANSCH[c[:2]] for c in cpv if c[:2] in BRANSCH), OVRIGT)
    lan = next((LAN[p] for p in (n.get("place-of-performance") or []) if p in LAN), "")
    if not lan:  # NUTS2-nivå eller saknas: försök med prefix
        lan = next((LAN[k] for p in (n.get("place-of-performance") or []) for k in LAN if p and k.startswith(p) and len(p) >= 4), "")
    value = n.get("estimated-value-proc")
    try:
        value = float(value) if value else None
    except (TypeError, ValueError):
        value = None
    return {
        "nr": n["publication-number"], "titel": first(n.get("title-proc")) or "(utan titel)",
        "kopare": first(n.get("buyer-name")), "ort": first(n.get("buyer-city")).title(),
        "lan": lan or "Hela Sverige / ej angivet", "publicerad": (n.get("publication-date") or "")[:10],
        "frist": deadline, "varde": value, "bslug": br[0], "bransch": br[1],
    }


def kr(v):
    if not v:
        return ""
    if v >= 1e6:
        return f"ca {v / 1e6:.1f} Mkr".replace(".", ",")
    return f"ca {round(v / 1e3):.0f} tkr"


def item_html(x, email):
    e = html.escape
    ted = f"https://ted.europa.eu/sv/notice/-/detail/{x['nr']}"
    subj = f"Gratis anbudsanalys: {x['titel']} ({x['nr']})"
    body = (f"Hej!\n\nVi funderar på att lämna anbud i:\n{x['titel']}\n{x['kopare']}\nTED: {ted}\n\n"
            "Vi vill gärna ha en gratis pilotanalys (kravmatris, skall-krav, utvärderingsmodell, risker).\n"
            "Företag:\nKontaktperson:\n\n(källa: bevakning)")
    mail = f"mailto:{email}?subject={urllib.request.quote(subj)}&body={urllib.request.quote(body)}"
    meta = " · ".join(filter(None, [e(x["kopare"]), e(x["lan"]), kr(x["varde"])]))
    frist = f'<strong>Sista anbudsdag {x["frist"]}</strong>' if x["frist"] else "Sista anbudsdag: se annonsen"
    return (f'<li class="up"><a class="t" href="{ted}" rel="noopener">{e(x["titel"])}</a>'
            f'<div class="m">{meta}</div><div class="m">{frist} · publicerad {x["publicerad"]} · {e(x["bransch"])}</div>'
            f'<a class="btn ghost small" href="{mail}">Få en gratis anbudsanalys</a></li>')


def page(title, desc, inner, depth=1):
    up = "../" * depth
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="stylesheet" href="{up}style.css">
<style>.up{{list-style:none;border-bottom:1px solid var(--line);padding:14px 0}} .up .t{{font-weight:600}}
.m{{color:var(--muted);font-size:14px}} .small{{padding:6px 10px;font-size:14px;margin-top:6px}}
ul.list{{padding:0}} .chips a{{display:inline-block;margin:4px 6px 4px 0;font-size:14px}}</style></head>
<body><header><div class="eyebrow"><a href="{up}upphandling/">Anbudsklar</a> · Upphandlingsbevakning</div>
<h1>{html.escape(title)}</h1><p class="lead">{html.escape(desc)}</p></header><main>{inner}
<div class="ai">Listan uppdateras automatiskt varje morgon från EU:s öppna databas TED. Den omfattar annonser över EU:s
tröskelvärden. Mindre upphandlingar publiceras i andra databaser. Kontrollera alltid annonsen hos beställaren.
Anbudsanalyserna tas fram med AI och granskas innan leverans.</div></main>
<footer><div data-seller></div><div><a href="{up}integritet.html">Integritetspolicy</a> · Inga cookies.</div></footer>
<script src="{up}config.js"></script><script src="{up}site.js"></script></body></html>"""


def main():
    today = date.today().isoformat()
    since = (date.today() - timedelta(days=DAYS_BACK)).strftime("%Y%m%d")
    items = [x for x in (parse(n, today) for n in fetch(since)) if x]
    items.sort(key=lambda x: (x["frist"] or "9999", x["titel"]))
    email = seller_email()
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    by_b = defaultdict(list)
    for x in items:
        by_b[(x["bslug"], x["bransch"])].append(x)
    lan_count = Counter(x["lan"] for x in items)

    chips = "".join(f'<a href="{s}.html">{html.escape(n)} ({len(v)})</a>'
                    for (s, n), v in sorted(by_b.items(), key=lambda kv: -len(kv[1])))
    lans = " · ".join(f"{html.escape(l)} {c}" for l, c in lan_count.most_common(8))
    newest = sorted(items, key=lambda x: x["publicerad"], reverse=True)[:40]
    inner = (f'<p><strong>{len(items)} öppna upphandlingar</strong> just nu (uppdaterad {stamp}).</p>'
             f'<h2>Per bransch</h2><div class="chips">{chips}</div>'
             f'<h2>Flest i</h2><p class="m">{lans}</p>'
             f'<h2>Senast publicerade</h2><ul class="list">{"".join(item_html(x, email) for x in newest)}</ul>')
    (OUT / "index.html").write_text(page("Öppna offentliga upphandlingar i Sverige",
        "Nya upphandlingar varje morgon, sorterade per bransch, med sista anbudsdag. Gratis.", inner), encoding="utf-8")

    for (slug, name), v in by_b.items():
        groups = defaultdict(list)
        for x in v:
            groups[x["lan"]].append(x)
        sec = "".join(f'<h2>{html.escape(l)} ({len(g)})</h2><ul class="list">{"".join(item_html(x, email) for x in g)}</ul>'
                      for l, g in sorted(groups.items(), key=lambda kv: -len(kv[1])))
        inner = f'<p><a href="index.html">← Alla branscher</a> · {len(v)} öppna upphandlingar · uppdaterad {stamp}</p>{sec}'
        (OUT / f"{slug}.html").write_text(page(f"Öppna upphandlingar: {name}",
            f"{len(v)} öppna offentliga upphandlingar inom {name.lower()} i Sverige, per län, med sista anbudsdag.", inner),
            encoding="utf-8")

    urls = [f"{SITE}/", f"{SITE}/upphandling/", f"{SITE}/rekrytering/", f"{SITE}/bidrag/", f"{SITE}/bevakning/"]
    urls += [f"{SITE}/bevakning/{s}.html" for (s, _) in by_b]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{stamp}</lastmod></url>\n" for u in urls) + "</urlset>\n",
        encoding="utf-8")
    print(f"{len(items)} öppna upphandlingar, {len(by_b)} branscher → {OUT}")


if __name__ == "__main__":
    main()
