"""
DuraWeather Quick Ship flipbook generator.

Pulls every product in https://duraweather.com/collections/quick-ship (read-only),
downloads one photo per product, and builds a finished flipbook in ./quick-ship/
(index.html + images/). Upload that folder to your GitHub Pages repo.

Run:   python build_quickship_flipbook.py
Needs: Python 3.8+, internet. No extra packages.

Settings below. Rerun any time prices or stock change; it rebuilds from live data.
"""
import json, os, re, sys, html, time, datetime, urllib.request, urllib.parse
from pathlib import Path

# ---------------- settings ----------------
STORE = "https://duraweather.com"
COLLECTION = "quick-ship"
SHOW_PRICES = True          # sale price on each product, dated "Prices as of ..."
SKIP_SOLD_OUT = True        # leave out products with no available variant
IMAGE_WIDTH = 800           # px; Shopify resizes on its CDN
UTM = "utm_source=catalog&utm_medium=flipbook&utm_campaign=quick-ship-2026"
OUT = Path(__file__).resolve().parent / "quick-ship"
# ------------------------------------------

SECTIONS = [  # (name, regex on lowercase title). First match wins, order matters.
    ("Fire pits", r"fire ?pit"),
    ("Counter & bar", r"counter|bar height|bar set|bar stool|stool|tete"),
    ("Dining", r"dining|picnic|octagon table"),
    ("Rockers", r"rocker"),
    ("Gliders, benches & swings", r"glider|bench|swing"),
    ("Lounge & chaise", r"chaise|mayfair|sofa|loveseat|lounge|sectional|chat"),
    ("Accessories", r"side table|end table|umbrella|hammock|ottoman|footrest|cushion|pillow|lantern|planter|table"),
    ("Adirondack chairs", r"adirondack"),
]
ORDER = ["Adirondack chairs", "Dining", "Counter & bar", "Rockers", "Gliders, benches & swings",
         "Lounge & chaise", "Fire pits", "Accessories", "More quick ship pieces"]
INTROS = {
    "Adirondack chairs": "The classic, in king size, folding and stationary styles, singles and sets.",
    "Dining": "Tables and sets for everyday meals and bigger gatherings.",
    "Counter & bar": "Higher seats for decks, patios and outdoor kitchens.",
    "Rockers": "Porch rockers in traditional and Adirondack profiles.",
    "Gliders, benches & swings": "Easy motion and a place to sit along the way.",
    "Lounge & chaise": "Deep seating and chaises for the pool and the patio.",
    "Fire pits": "A warm center for the evening.",
    "Accessories": "Side tables, umbrellas, hammocks and the finishing pieces.",
    "More quick ship pieces": "More from the Quick Ship collection.",
}

UA = {"User-Agent": "Mozilla/5.0 (DuraWeather catalog builder)"}

def get(url, binary=False, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                data = r.read()
                return data if binary else json.loads(data.decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))

def fetch_products():
    out, page = [], 1
    while True:
        url = f"{STORE}/collections/{COLLECTION}/products.json?limit=250&page={page}"
        batch = get(url).get("products", [])
        if not batch:
            break
        out += batch
        print(f"  page {page}: {len(batch)} products")
        page += 1
    return out

def section_of(title):
    t = title.lower()
    for name, rx in SECTIONS:
        if re.search(rx, t):
            return name
    return "More quick ship pieces"

def money(x):
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"

def sized(src, w):
    u = urllib.parse.urlsplit(src if src.startswith("http") else "https:" + src)
    q = urllib.parse.parse_qsl(u.query) + [("width", str(w))]
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), ""))

def prepare(raw):
    items, skipped = [], 0
    for p in raw:
        variants = p.get("variants", [])
        avail = any(v.get("available") for v in variants)
        if SKIP_SOLD_OUT and not avail:
            skipped += 1
            continue
        prices = sorted(float(v["price"]) for v in variants if v.get("price"))
        if SKIP_SOLD_OUT:
            avail_prices = sorted(float(v["price"]) for v in variants if v.get("available") and v.get("price"))
            prices = avail_prices or prices
        imgs = p.get("images") or []
        items.append({
            "handle": p["handle"],
            "title": p["title"].strip(),
            "min": prices[0] if prices else None,
            "max": prices[-1] if prices else None,
            "img": imgs[0]["src"] if imgs else None,
            "section": section_of(p["title"]),
        })
    return items, skipped

def download_images(items, folder):
    folder.mkdir(parents=True, exist_ok=True)
    fails = 0
    for i, it in enumerate(items, 1):
        if not it["img"]:
            it["local"] = None; fails += 1; continue
        ext = os.path.splitext(urllib.parse.urlsplit(it["img"]).path)[1].lower()
        ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
        name = re.sub(r"[^a-z0-9-]+", "-", it["handle"].lower()).strip("-")[:80] + ext
        dest = folder / name
        if not dest.exists():
            try:
                dest.write_bytes(get(sized(it["img"], IMAGE_WIDTH), binary=True))
            except Exception as e:
                print(f"  image failed: {it['title']} ({e})"); it["local"] = None; fails += 1; continue
        it["local"] = f"images/{name}"
        if i % 20 == 0:
            print(f"  images: {i}/{len(items)}")
    return fails

# ---------------- page builders ----------------
E = lambda s: html.escape(str(s), quote=True)

def link(handle):
    return f"{STORE}/products/{urllib.parse.quote(handle, safe='-_.~%')}?{UTM}"

def price_html(it):
    if not SHOW_PRICES or it["min"] is None:
        return ""
    if it["max"] and it["max"] > it["min"]:
        return f'<div class="price">From {money(it["min"])}</div>'
    return f'<div class="price">{money(it["min"])}</div>'

def card(it, big=False):
    img = f'<img src="{E(it["local"])}" alt="{E(it["title"])}" loading="lazy" decoding="async">' if it.get("local") else '<div class="noimg">Photo online</div>'
    return (f'<a class="card{" big" if big else ""}" href="{E(link(it["handle"]))}" target="_blank" rel="noopener">'
            f'<div class="stage">{img}</div><h3>{E(it["title"])}</h3>{price_html(it)}'
            f'<span class="go">View &amp; order</span></a>')

def foot(n, label):
    return f'<div class="foot"><span>{E(label)}</span><span>{n:02d}</span></div>'

def build_pages(items, build_date):
    groups = {name: [] for name in ORDER}
    for it in items:
        groups[it["section"]].append(it)
    groups = {k: v for k, v in groups.items() if v}

    pages = []
    # cover
    picks = [it for it in items if it.get("local")][:3]
    pages.append(("Cover", f'''<div class="pg cover">
      <div class="cv-top"><div class="brand">DuraWeather<sup>&reg;</sup></div><div class="yr">2026</div></div>
      <h1>The Quick Ship<br>Collection</h1>
      <p class="lede">Every piece from our Quick Ship collection, in one place. {len(items)} pieces in DuraWeather Poly&reg;.</p>
      <div class="cv-row">{"".join(f'<div class="cv-c"><img src="{E(p["local"])}" alt=""></div>' for p in picks)}</div>
      <div class="cv-foot"><span>Made in USA</span><span>duraweather.com</span></div></div>'''))
    # why
    why = [
        ("Made in the USA", "Built in our plants in Iowa, Ohio and Wisconsin."),
        ("Limited 20-year warranty", "Warranty backed against fading, rotting and rusting."),
        ("316 marine-grade stainless", "Powder-coated stainless hardware on every piece, for pools, coasts and winter salt."),
        ("Stays outside year round", "95% high-density polyethylene with 5% UV inhibitors. No painting or sealing."),
    ]
    pages.append(("Why DuraWeather", f'''<div class="pg pad">
      <h2>Why DuraWeather</h2><p class="intro">Outdoor furniture made to be left outside, season after season.</p>
      <div class="why">{"".join(f'<div class="w"><h4>{t}</h4><p>{d}</p></div>' for t, d in why)}</div>
      <div class="call"><div><div class="k">Questions or bulk orders?</div><div class="v">Call 252-512-4191</div></div>
      <div class="small">Monday to Saturday, 10 AM to 6 PM EST<br>Sunday, 1 PM to 6 PM</div></div></div>'''))
    # contents placeholder (filled after numbering)
    pages.append(("Contents", None))
    toc = []
    for name, its in groups.items():
        start = len(pages) + 1
        toc.append((name, start, len(its)))
        hero, rest = its[:2], its[2:]
        pages.append((name, f'''<div class="pg pad" id="p{start}">
          <div class="sec-head"><h1 class="sec">{E(name)}</h1><p class="intro">{E(INTROS.get(name, ""))}<span class="cnt">{len(its)} piece{"s" if len(its) != 1 else ""}</span></p></div>
          <div class="hero g{len(hero)}">{"".join(card(h, True) for h in hero)}</div></div>'''))
        for i in range(0, len(rest), 6):
            chunk = rest[i:i + 6]
            pages.append((name, f'<div class="pg pad"><div class="grid">{"".join(card(c) for c in chunk)}</div></div>'))
    # contents
    rows = "".join(f'<a class="toc-row" data-go="{p}" href="#p{p}"><span class="tn">{E(n)}</span><span class="tc">{c}</span><span class="tp">{p:02d}</span></a>' for n, p, c in toc)
    pages[2] = ("Contents", f'''<div class="pg pad"><h2>Inside</h2>
      <p class="intro">Tap any product to see colors and options and to order on duraweather.com.</p>
      <div class="toc">{rows}</div></div>''')
    # back
    note = f"Prices as of {build_date}. " if SHOW_PRICES else ""
    pages.append(("Back", f'''<div class="pg back">
      <div class="brand w">DuraWeather<sup>&reg;</sup></div>
      <h1>See every color online.</h1>
      <p class="lede">Each product links to its page on duraweather.com, with current colors, options and pricing.</p>
      <a class="big" href="{STORE}/collections/{COLLECTION}?{UTM}" target="_blank" rel="noopener">duraweather.com</a>
      <div class="ph">Questions? Call 252-512-4191</div>
      <p class="fine">{note}Colors, availability and prices may change. Visit duraweather.com for current details. &copy; {datetime.date.today().year} DuraWeather.</p></div>'''))
    # footers
    final = []
    for i, (label, body) in enumerate(pages, 1):
        if label not in ("Cover", "Back"):
            body = body[:-6] + foot(i, label) + "</div>"
        final.append(body)
    return final

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>DuraWeather Quick Ship Collection</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🪑</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,400;0,6..96,500;1,6..96,400&family=Jost:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#E7E8E3;--chrome:#1E2B26;--muted:#6D7671;--btn:#fff;--btn-ink:#1E2B26;--shadow:rgba(20,30,25,.28);--line:rgba(30,43,38,.12);
 --ink:#1D2824;--body:#3E4844;--pm:#77807B;--pl:#D9DCD6;--stage:#F1F1ED;--spruce:#1F332B;--brass:#94713A;color-scheme:light;
 box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121815;--chrome:#E3E8E4;--muted:#93A099;--btn:#1F2925;--btn-ink:#E3E8E4;--shadow:rgba(0,0,0,.6);--line:rgba(227,232,228,.14);color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121815;--chrome:#E3E8E4;--muted:#93A099;--btn:#1F2925;--btn-ink:#E3E8E4;--shadow:rgba(0,0,0,.6);--line:rgba(227,232,228,.14);color-scheme:dark}
*{box-sizing:border-box;margin:0;padding:0}html,body{height:100%}
body{background:var(--bg);color:var(--chrome);font-family:Jost,"Helvetica Neue",Arial,sans-serif;overflow:hidden;display:flex;flex-direction:column}
header{display:flex;justify-content:space-between;align-items:center;padding:14px 22px;font-size:14px;flex:none}
header .t{font-weight:500}header .t span{color:var(--muted);font-weight:400;margin-left:8px}
header a{color:var(--chrome);text-decoration:none;border-bottom:1px solid currentColor;font-size:13px}
#stage{flex:1;position:relative;display:flex;align-items:center;justify-content:center;min-height:0}
#book{position:relative;perspective:2600px}
.half{position:absolute;top:0;height:100%;overflow:hidden;background:#fff}.half.L{left:0}.half.R{right:0}.half.empty{background:transparent}
#book.spread .half{width:50%}#book.single .half{width:100%}#book.single .half.L{display:none}
.shadow{position:absolute;inset:0;box-shadow:0 18px 50px var(--shadow);pointer-events:none}
#book.spread.first .shadow{left:50%}#book.spread.last .shadow{right:50%}
.gutter{position:absolute;top:0;bottom:0;left:50%;width:60px;margin-left:-30px;pointer-events:none;z-index:4;background:linear-gradient(90deg,transparent 0,rgba(0,0,0,.06) 40%,rgba(0,0,0,.15) 50%,rgba(0,0,0,.06) 60%,transparent 100%)}
#book.single .gutter,#book.first .gutter,#book.last .gutter{display:none}
.leaf{position:absolute;top:0;height:100%;width:50%;transform-style:preserve-3d;z-index:5;pointer-events:none}
.leaf .face{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden;overflow:hidden;background:#fff}
.leaf .back{transform:rotateY(180deg)}.leaf.fwd{left:50%;transform-origin:left center}.leaf.bwd{left:0;transform-origin:right center}
.nav{position:absolute;top:50%;transform:translateY(-50%);width:46px;height:46px;border-radius:50%;border:1px solid var(--line);background:var(--btn);color:var(--btn-ink);cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:10;box-shadow:0 4px 14px var(--shadow)}
.nav:disabled{opacity:.3;cursor:default}.nav svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
#prev{left:18px}#next{right:18px}
footer{flex:none;display:flex;justify-content:center;align-items:center;gap:14px;padding:12px 16px 16px}
footer button{font:inherit;font-size:13px;color:var(--chrome);background:transparent;border:1px solid var(--line);border-radius:20px;padding:7px 14px;cursor:pointer}
#count{font-size:13px;color:var(--muted);min-width:90px;text-align:center;font-variant-numeric:tabular-nums}
#thumbs{position:fixed;inset:0;background:var(--bg);z-index:50;display:none;overflow:auto;padding:calc(env(safe-area-inset-top,0px) + 70px) 22px calc(env(safe-area-inset-bottom,0px) + 30px)}
#thumbs.open{display:block}#thumbs .grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:22px 16px;max-width:1100px;margin:0 auto}
#thumbs .tb{background:none;border:0;cursor:pointer;color:var(--muted);font:inherit;font-size:12px}
#thumbs .tbox{width:100%;aspect-ratio:816/1056;overflow:hidden;position:relative;background:#fff;box-shadow:0 6px 18px var(--shadow);margin-bottom:6px;pointer-events:none}
#thumbs .close{position:fixed;top:calc(env(safe-area-inset-top,0px) + 16px);right:22px;font:inherit;font-size:13px;border:1px solid var(--line);border-radius:20px;padding:7px 14px;color:var(--chrome);background:var(--btn);cursor:pointer}
@media (max-width:760px){header{padding:10px 14px}header .t span{display:none}.nav{width:40px;height:40px}#prev{left:8px}#next{right:8px}}

/* ---- catalog page (816 x 1056 px = 8.5 x 11 in) ---- */
.pg{width:816px;height:1056px;position:relative;overflow:hidden;background:#fff;color:var(--body);font-family:Jost,sans-serif;font-size:14px;line-height:1.5;transform-origin:0 0}
.pg a{color:inherit;text-decoration:none}.pg img{display:block}
.pad{padding:64px 68px 0}
.pg h1,.pg h2,.pg h3,.pg h4{font-family:"Bodoni Moda",serif;color:var(--ink);font-weight:400;text-wrap:balance}
.pg h2{font-size:42px;line-height:1.08;margin-bottom:12px}
.intro{font-size:15px;line-height:1.55;max-width:420px}
.foot{position:absolute;left:68px;right:68px;bottom:38px;display:flex;justify-content:space-between;font-size:10px;letter-spacing:.03em;color:var(--pm);border-top:.7px solid var(--pl);padding-top:9px}
.cover{background:var(--spruce);color:#DCE3DE;padding:72px 68px}
.cv-top{display:flex;justify-content:space-between;align-items:baseline}
.brand{font-family:"Bodoni Moda",serif;font-size:26px;color:#fff;font-style:italic}.brand sup{font-size:.45em}
.yr{font-size:13px;letter-spacing:.08em;color:#AFC0B6}
.cover h1{color:#fff;font-size:76px;line-height:1;margin:140px 0 20px;letter-spacing:-.01em}
.cover .lede{font-size:17px;color:#C9D3CD;max-width:520px}
.cv-row{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:70px}
.cv-c{background:#F1F1ED;height:250px;border-radius:2px;overflow:hidden}
.cv-c img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply;padding:10%}
.cv-foot{position:absolute;left:68px;right:68px;bottom:52px;display:flex;justify-content:space-between;font-size:12px;color:#AFC0B6;border-top:.7px solid #3A5045;padding-top:10px}
.why{display:grid;grid-template-columns:1fr 1fr;gap:34px 46px;margin-top:56px;padding-top:40px;border-top:.7px solid var(--pl)}
.w h4{font-size:22px;font-weight:500;margin-bottom:6px}.w p{font-size:14px}
.call{margin-top:70px;background:var(--stage);padding:28px 30px;display:flex;justify-content:space-between;align-items:center;gap:20px}
.call .k{font-size:13px;color:var(--pm)}.call .v{font-family:"Bodoni Moda",serif;font-size:28px;color:var(--ink)}.call .small{font-size:12.5px;color:var(--pm);text-align:right}
.toc{margin-top:46px;border-top:.7px solid var(--pl)}
.toc-row{display:grid;grid-template-columns:1fr 90px 40px;align-items:baseline;padding:17px 0;border-bottom:.7px solid var(--pl);cursor:pointer}
.tn{font-family:"Bodoni Moda",serif;font-size:23px;color:var(--ink)}.tc{font-size:12px;color:var(--pm)}.tp{font-size:13px;color:var(--pm);text-align:right}
.sec-head{display:grid;grid-template-columns:1fr 300px;gap:30px;align-items:end;padding-bottom:26px;margin-bottom:30px;border-bottom:.7px solid var(--pl)}
.sec{font-size:58px;line-height:1.02}.sec-head .intro{font-size:14.5px}.cnt{display:block;margin-top:8px;font-size:12px;color:var(--pm)}
.hero{display:grid;gap:26px}.hero.g2{grid-template-columns:1fr 1fr}.hero.g1{grid-template-columns:1fr}
.card{display:flex;flex-direction:column}
.stage{background:var(--stage);border-radius:2px;overflow:hidden;height:282px;margin-bottom:12px}
.stage img{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply;padding:8%}
.noimg{height:100%;display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--pm)}
.card h3{font-size:16.5px;line-height:1.22;font-weight:500;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.price{font-size:14px;color:var(--ink);margin-top:5px;font-weight:500}
.go{align-self:flex-start;font-size:11.5px;font-weight:500;color:var(--ink);border-bottom:1px solid var(--brass);padding-bottom:2px;margin-top:7px}
.card.big .stage{height:470px}.card.big h3{font-size:21px}.hero.g1 .card.big .stage{height:520px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,auto);gap:30px 24px}
.card:hover .go{color:var(--brass)}
.back{background:var(--spruce);color:#DCE3DE;padding:150px 80px}
.brand.w{margin-bottom:150px}.back h1{color:#fff;font-size:56px;line-height:1.04;max-width:560px;margin-bottom:18px}
.back .lede{font-size:16px;color:#C9D3CD;max-width:480px}
.back .big{display:inline-block;font-family:"Bodoni Moda",serif;font-size:32px;color:#fff;margin-top:70px;border-bottom:1px solid var(--brass)}
.back .ph{margin-top:12px;font-size:15px}
.fine{position:absolute;left:80px;right:80px;bottom:56px;font-size:10.5px;color:#93A39A;border-top:.7px solid #3A5045;padding-top:10px}
@media (prefers-reduced-motion:reduce){.leaf{display:none}}
</style></head><body>
<header><div class="t">DuraWeather<span>Quick Ship Collection</span></div><a href="__SHOP__" target="_blank" rel="noopener">Shop duraweather.com</a></header>
<div id="stage">
 <button class="nav" id="prev" aria-label="Previous page"><svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg></button>
 <div id="book" class="spread"><div class="shadow"></div><div class="half L"></div><div class="half R"></div><div class="gutter"></div></div>
 <button class="nav" id="next" aria-label="Next page"><svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></button>
</div>
<footer><button id="first">Cover</button><span id="count"></span><button id="all">All pages</button></footer>
<div id="thumbs" role="dialog" aria-label="All pages"><button class="close" id="closeT">Close</button><div class="grid2"></div></div>
<template id="src">__PAGES__</template>
<script>
const SRC=[...document.getElementById('src').content.children];const N=SRC.length,AR=816/1056,DUR=700;
const book=document.getElementById('book'),L=book.querySelector('.half.L'),R=book.querySelector('.half.R');
const prevBtn=document.getElementById('prev'),nextBtn=document.getElementById('next');
let mode='spread',pos=1,busy=false,scale=1;const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
function spreadOf(p){if(p<=1)return[0,1];if(p>=N&&N%2===0)return[N,0];const l=p%2===0?p:p-1;return[l,l+1<=N?l+1:0]}
function pageNode(n){if(!n)return null;const c=SRC[n-1].cloneNode(true);c.style.transform=`scale(${scale})`;c.querySelectorAll('img').forEach(i=>i.loading='eager');return c}
function fill(el,n){el.replaceChildren();const c=pageNode(n);if(c)el.appendChild(c);el.classList.toggle('empty',!n)}
function layout(){mode=innerWidth<760||innerWidth<innerHeight*.95?'single':'spread';
 const st=document.getElementById('stage').getBoundingClientRect();const pad=mode==='single'?(innerWidth<760?16:110):150;
 let h=st.height-24,w=h*AR*(mode==='spread'?2:1);const mw=st.width-pad;if(w>mw){w=mw;h=w/(AR*(mode==='spread'?2:1))}
 book.style.width=w+'px';book.style.height=h+'px';book.className=mode;scale=h/1056;render()}
function render(){if(mode==='spread'){const[l,r]=spreadOf(pos);fill(L,l);fill(R,r);book.classList.toggle('first',!l);book.classList.toggle('last',!r);
  document.getElementById('count').textContent=!l?'Cover':!r?'Back cover':`${l}–${r} of ${N}`;prevBtn.disabled=!l;nextBtn.disabled=!r||r>=N}
 else{fill(R,pos);book.classList.remove('first','last');document.getElementById('count').textContent=`${pos} of ${N}`;prevBtn.disabled=pos<=1;nextBtn.disabled=pos>=N}
 try{history.replaceState(null,'',pos>1?'#p'+pos:location.pathname+location.search)}catch(e){}
 [pos-2,pos-1,pos+1,pos+2,pos+3].forEach(n=>{if(n>=1&&n<=N)SRC[n-1].querySelectorAll('img').forEach(i=>{const im=new Image();im.src=i.getAttribute('src')})})}
function turn(dir){if(busy)return;
 if(mode==='single'){const t=pos+dir;if(t<1||t>N)return;if(reduce){pos=t;render();return}busy=true;
  R.animate([{opacity:1,transform:'translateX(0)'},{opacity:0,transform:`translateX(${-dir*30}px)`}],{duration:180,easing:'ease-in'}).onfinish=()=>{pos=t;render();
  R.animate([{opacity:0,transform:`translateX(${dir*30}px)`},{opacity:1,transform:'none'}],{duration:220,easing:'ease-out'}).onfinish=()=>busy=false};return}
 const[l,r]=spreadOf(pos);if(dir>0&&(!r||r>=N))return;if(dir<0&&!l)return;
 const target=dir>0?r+1:(l-1<=1?1:l-1);const[nl,nr]=spreadOf(target);if(reduce){pos=target;render();return}busy=true;
 const leaf=document.createElement('div');leaf.className='leaf '+(dir>0?'fwd':'bwd');
 const f=document.createElement('div');f.className='face front';const b=document.createElement('div');b.className='face back';
 const fn=pageNode(dir>0?r:l),bn=pageNode(dir>0?nl:nr);if(fn)f.appendChild(fn);if(bn)b.appendChild(bn);leaf.append(f,b);book.appendChild(leaf);
 if(dir>0){fill(R,nr);book.classList.toggle('last',!nr)}else{fill(L,nl);book.classList.toggle('first',!nl)}
 requestAnimationFrame(()=>{leaf.animate([{transform:'rotateY(0deg)'},{transform:`rotateY(${dir>0?-180:180}deg)`}],{duration:DUR,easing:'cubic-bezier(.45,.05,.25,1)'}).onfinish=()=>{pos=target;render();leaf.remove();busy=false}})}
prevBtn.onclick=()=>turn(-1);nextBtn.onclick=()=>turn(1);document.getElementById('first').onclick=()=>{pos=1;render()};
addEventListener('keydown',e=>{if(document.getElementById('thumbs').classList.contains('open')){if(e.key==='Escape')closeThumbs();return}
 if(e.key==='ArrowRight'||e.key==='PageDown')turn(1);if(e.key==='ArrowLeft'||e.key==='PageUp')turn(-1)});
book.addEventListener('click',e=>{const a=e.target.closest('[data-go]');if(a){e.preventDefault();pos=+a.dataset.go;render()}});
let sx=null,sy=null;book.addEventListener('touchstart',e=>{sx=e.touches[0].clientX;sy=e.touches[0].clientY},{passive:true});
book.addEventListener('touchend',e=>{if(sx===null)return;const dx=e.changedTouches[0].clientX-sx,dy=e.changedTouches[0].clientY-sy;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy))turn(dx<0?1:-1);sx=null},{passive:true});
const tg=document.querySelector('#thumbs .grid2');let thumbsBuilt=false;
function buildThumbs(){if(thumbsBuilt)return;thumbsBuilt=true;SRC.forEach((s,i)=>{const b=document.createElement('button');b.className='tb';b.dataset.p=i+1;
 const box=document.createElement('div');box.className='tbox';const c=s.cloneNode(true);box.appendChild(c);b.append(box,document.createTextNode(i===0?'Cover':i===N-1?'Back':i+1));tg.appendChild(b);
 requestAnimationFrame(()=>{c.style.transform=`scale(${box.clientWidth/816})`})})}
tg.onclick=e=>{const b=e.target.closest('.tb');if(!b)return;pos=+b.dataset.p;closeThumbs();render()};
function closeThumbs(){document.getElementById('thumbs').classList.remove('open')}
document.getElementById('all').onclick=()=>{document.getElementById('thumbs').classList.add('open');buildThumbs()};
document.getElementById('closeT').onclick=closeThumbs;
function fromHash(){const m=/^#p(\d+)$/.exec(location.hash);if(m){const n=+m[1];if(n>=1&&n<=N)pos=n}}
addEventListener('hashchange',()=>{const o=pos;fromHash();if(pos!==o)render()});
fromHash();addEventListener('resize',layout);layout();
</script></body></html>"""

def main(products=None):
    print("Fetching Quick Ship products ...")
    raw = products if products is not None else fetch_products()
    items, skipped = prepare(raw)
    print(f"  {len(raw)} products found, {skipped} sold out skipped, {len(items)} in catalog")
    OUT.mkdir(parents=True, exist_ok=True)
    print("Downloading photos ...")
    fails = download_images(items, OUT / "images")
    build_date = datetime.date.today().strftime("%B %-d, %Y") if os.name != "nt" else datetime.date.today().strftime("%B %#d, %Y")
    pages = build_pages(items, build_date)
    doc = TEMPLATE.replace("__PAGES__", "\n".join(pages)).replace("__SHOP__", f"{STORE}/collections/{COLLECTION}?{UTM}")
    (OUT / "index.html").write_text(doc, encoding="utf-8")
    (OUT / "products.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
    secs = {}
    for it in items: secs[it["section"]] = secs.get(it["section"], 0) + 1
    print(f"\nDone: {OUT / 'index.html'}")
    print(f"  {len(pages)} pages, {len(items)} products, {fails} photos missing")
    for k in ORDER:
        if k in secs: print(f"  {k}: {secs[k]}")
    print("\nUpload the whole quick-ship folder (index.html + images) to your GitHub repo.")

if __name__ == "__main__":
    main()
