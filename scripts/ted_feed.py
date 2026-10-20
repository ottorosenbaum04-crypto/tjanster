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
    frist = f'<span class="deadline">Sista anbudsdag {x["frist"]}</span>' if x["frist"] else "Sista anbudsdag: se annonsen"
    return (f'<div class="list-item"><div><a class="t" href="{ted}" rel="noopener">{e(x["titel"])}</a>'
            f'<div class="m">{meta}</div><div class="m">{frist} · publicerad {x["publicerad"]} · {e(x["bransch"])}</div></div>'
            f'<a class="btn btn-secondary btn-sm" href="{mail}">Gratis anbudsanalys</a></div>')


def page(title, desc, inner, depth=1):
    up = "../" * depth
    e = html.escape
    return f"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} – Kravkartan</title><meta name="description" content="{e(desc)}">
<link rel="stylesheet" href="{up}style.css?v=3"></head>
<body>
<nav class="nav"><div class="wrap">
  <a class="logo" href="{up}"><span class="logo-mark">K</span>Kravkartan</a>
  <div class="nav-links"><a href="{up}upphandling/">Anbudsanalys</a><a href="{up}bevakning/" aria-current="page">Öppna upphandlingar</a>
    <a href="{up}rekrytering/">Rekrytering</a><a href="{up}bidrag/">Bidrag</a></div>
  <a class="btn btn-primary btn-sm nav-cta" href="{up}upphandling/">Testa gratis</a>
</div></nav>
<header class="hero" style="padding:52px 0 40px"><div class="wrap" style="display:block">
  <span class="pill"><span class="dot"></span>Uppdateras automatiskt varje morgon</span>
  <h1 style="font-size:clamp(32px,4.4vw,48px)">{e(title)}</h1><p class="lead" style="margin:0">{e(desc)}</p>
</div></header>
<main><div class="wrap" style="padding-top:36px;padding-bottom:64px">{inner}
<div class="ai-note" style="margin-top:32px">ℹ️ <span>Listan hämtas varje morgon från EU:s öppna databas TED och omfattar annonser
över EU:s tröskelvärden. Mindre upphandlingar publiceras i andra databaser. Kontrollera alltid annonsen hos beställaren.
Anbudsanalyserna tas fram med AI och granskas av en människa innan leverans.</span></div>
<div class="cta-band" style="margin-top:48px"><h2>Hittade du en intressant upphandling?</h2>
<p>Klicka på "Gratis anbudsanalys" så får du alla krav, utvärderingsmodellen och riskerna inom 2 arbetsdagar.</p>
<div class="cta-row" style="justify-content:center"><a class="btn btn-primary" href="{up}upphandling/">Så fungerar analysen</a></div></div>
</div></main>
<footer class="footer"><div class="wrap">
  <div class="cols">
    <div><a class="logo" href="{up}"><span class="logo-mark">K</span>Kravkartan</a>
      <p style="margin:12px 0 0;max-width:30em">Analyser och bevakning för svenska småföretag, byggt på öppna data.</p></div>
    <div><h4>Tjänster</h4><a href="{up}upphandling/">Anbudsanalys</a><a href="{up}bevakning/">Öppna upphandlingar</a><a href="{up}rekrytering/">Rekryteringsradarn</a><a href="{up}bidrag/">Bidragsbevakaren</a></div>
    <div><h4>Information</h4><a href="{up}integritet.html">Integritetspolicy</a></div>
  </div>
  <div class="legal"><span data-seller></span><span>Inga cookies, ingen spårning.</span></div>
</div></footer>
<script src="{up}config.js?v=3"></script><script src="{up}site.js?v=3"></script></body></html>"""


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

    cards = "".join(
        f'<a class="card" href="{s}.html" style="color:inherit;text-decoration:none">'
        f'<div class="fact"><b>{len(v)}</b><span>{html.escape(n)}</span></div></a>'
        for (s, n), v in sorted(by_b.items(), key=lambda kv: -len(kv[1])))
    lans = "".join(f'<span class="chip">{html.escape(l)} · {c}</span>' for l, c in lan_count.most_common(10))
    newest = sorted(items, key=lambda x: x["publicerad"], reverse=True)[:40]
    inner = (f'<div class="facts" style="margin-bottom:28px"><div class="fact"><b>{len(items)}</b><span>öppna upphandlingar just nu</span></div>'
             f'<div class="fact"><b>{len(by_b)}</b><span>branscher</span></div>'
             f'<div class="fact"><b>{stamp}</b><span>senast uppdaterad</span></div></div>'
             f'<h2 style="font-size:24px">Per bransch</h2>'
             f'<div class="grid-3" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-bottom:28px">{cards}</div>'
             f'<h2 style="font-size:24px">Flest i</h2><div class="chips" style="margin-bottom:28px">{lans}</div>'
             f'<h2 style="font-size:24px">Senast publicerade</h2>{"".join(item_html(x, email) for x in newest)}')
    (OUT / "index.html").write_text(page("Öppna offentliga upphandlingar i Sverige",
        "Nya upphandlingar varje morgon, sorterade per bransch, med sista anbudsdag. Gratis.", inner), encoding="utf-8")

    for (slug, name), v in by_b.items():
        groups = defaultdict(list)
        for x in v:
            groups[x["lan"]].append(x)
        sec = "".join(f'<h2 style="font-size:22px;margin-top:36px">{html.escape(l)} ({len(g)})</h2>{"".join(item_html(x, email) for x in g)}'
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
