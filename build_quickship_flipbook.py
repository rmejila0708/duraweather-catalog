"""
DuraWeather Quick Ship flipbook generator, v2 (editorial catalog).

Pulls every product in https://duraweather.com/collections/quick-ship (read-only),
downloads and optimizes the photos, and builds a finished flipbook in ./quick-ship/
(index.html + images/). Push that folder to your GitHub Pages repo.

Run:    python build_quickship_flipbook.py
Needs:  Python 3.8+, internet, Pillow (pip install pillow) for image optimizing.
        Without Pillow it still builds, but with bigger files and no hero crops.

Settings below. Rerun any time prices or stock change; it rebuilds from live data.
"""
import json, os, re, sys, html, time, hashlib, datetime, io, shutil, urllib.request, urllib.parse
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

# ---------------- settings ----------------
STORE = "https://duraweather.com"
COLLECTION = "quick-ship"
SHOW_PRICES = False         # prices are left out; each photo links to the product page
SKIP_SOLD_OUT = True        # leave out products with no available variant
PUBLIC_URL = "https://rmejila0708.github.io/duraweather-catalog/quick-ship/"   # for link previews
UTM = "utm_source=catalog&utm_medium=flipbook&utm_campaign=quick-ship-2026"
HERE = Path(__file__).resolve().parent
OUT = HERE / "quick-ship"
CACHE = HERE / ".cache"     # raw downloads, safe to delete, not published
CLEAN_W, PHOTO_W, HERO_W = 900, 1300, 2200   # image widths in px (studio shots / photos / hero spreads)
TILE = (239, 239, 235)      # background tile behind studio shots, as RGB
# ------------------------------------------

# Product -> section. First match wins, order matters.
SECTIONS = [
    ("Fire pits", r"fire ?pit"),
    ("Balcony & surfboard", r"balcony|surfboard|easy rider"),
    ("Counter & bar", r"counter|bar height|bar set|bar stool|stool|tete"),
    ("Dining", r"dining|picnic|octagon table"),
    ("Rockers", r"rock(er|ing)"),
    ("Gliders, benches & swings", r"glider|bench|swing"),
    ("Lounge & chaise", r"chaise|mayfair|sofa|loveseat|lounge|sectional|chat"),
    ("Accessories", r"side table|end table|umbrella|hammock|ottoman|footrest|cushion|pillow|lantern|planter|table"),
    ("Adirondack chairs", r"adirondack"),
]
ORDER = ["Adirondack chairs", "Dining", "Counter & bar", "Rockers", "Gliders, benches & swings",
         "Lounge & chaise", "Balcony & surfboard", "Fire pits", "Accessories", "More quick ship pieces"]
INTROS = {
    "Adirondack chairs": "The classic, in king size, folding and stationary styles. Singles and sets.",
    "Dining": "Tables and sets for everyday meals and bigger gatherings.",
    "Counter & bar": "Higher seats for decks, patios and outdoor kitchens.",
    "Rockers": "Porch rockers in traditional and Adirondack profiles.",
    "Gliders, benches & swings": "Easy motion, and a place to sit along the way.",
    "Lounge & chaise": "Deep seating and chaises for the pool and the patio.",
    "Balcony & surfboard": "Balcony chairs and sets, plus the surfboard tables and benches.",
    "Fire pits": "A warm center for the evening.",
    "Accessories": "Side tables, umbrellas, hammocks and the finishing pieces.",
    "More quick ship pieces": "More from the Quick Ship collection.",
}
# Hero photos: section -> file name (without query) of a lifestyle photo in the store's product images.
# If a name is not found, that section falls back to a plain color opener.
HEROES = {
    "COVER": "IMG_8092_44f63a28-e78e-46a0-8ee4-ba6ebe741cad.jpg",
    "INTRO": "Classic3PieceAdriondackBistroSet-4FMBLK.jpg",
    "Adirondack chairs": "Folding_Adirondacks_WW.jpg",
    "Dining": "DuraWeather_Poly_4pc_Dset4.jpg",
    "Counter & bar": "Lifestyle2_c6a2aa93-5520-4b1d-bf75-ba68fba4b98f.jpg",
    "Rockers": "Singlerocker4.jpg",
    "Gliders, benches & swings": "DuraWeatherFAGlider3pcset10.jpg",
    "Lounge & chaise": "DuraWeatherPolyChaiseLounge6.jpg",
    "Balcony & surfboard": "ClassicAdirondackSwivelGliderChairsandLoveseatWatermarks.jpg",
    "Fire pits": "IMG_7533_bd649537-da41-4d62-8cdd-adff0aed2fae.jpg",
    "Accessories": "OriginalAll-WeatherSunbrellaHammocks-50ShoreRegatta3.jpg",
}
CLEAN_PER_PAGE = 4    # studio shots (white backdrop) per page
PHOTO_PER_PAGE = 2    # photos with a real background per page, shown large

UA = {"User-Agent": "Mozilla/5.0 (DuraWeather catalog builder)"}

# ---------------- fetching ----------------
def get(url, binary=False, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
                return data if binary else json.loads(data.decode("utf-8"))
        except Exception:
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

def sized(src, w):
    u = urllib.parse.urlsplit(src if src.startswith("http") else "https:" + src)
    q = urllib.parse.parse_qsl(u.query) + [("width", str(w))]
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), ""))

def cached(url):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
    if not f.exists():
        f.write_bytes(get(url, binary=True))
    return f.read_bytes()

# ---------------- data prep ----------------
def section_of(title):
    t = title.lower()
    for name, rx in SECTIONS:
        if re.search(rx, t):
            return name
    return "More quick ship pieces"

TITLE_FIXES = {"duraweather-poly": "Dining Side Chair"}   # products whose store title is just the brand name

def clean_title(p):
    if p["handle"] in TITLE_FIXES:
        return TITLE_FIXES[p["handle"]]
    t = html.unescape(p["title"]).replace("®", "").strip()
    t = re.sub(r"(?i)^quick\s*ship\s*[-:]\s*", "", t)
    t = re.sub(r"(?i)^duraweather\s*(poly)?\s*", "", t).strip(" -")
    if not t:   # some titles are only the brand name; fall back to the URL handle
        t = re.sub(r"(?i)^duraweather[- ]?(poly[- ]?)?", "", p["handle"]).replace("-", " ").strip()
    letters = [c for c in t if c.isalpha()]
    if letters and (sum(c.isupper() for c in letters) / len(letters) > 0.6 or t.islower()):
        t = re.sub(r"\b[Xx]\b", "x", t.title())
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\b(With|And|Of|For|In|On|Or)\b", lambda m: m.group(1).lower(), t)
    return t[:1].upper() + t[1:] if t else p["handle"]

def money(x):
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"

def color_count(p):
    for o in p.get("options", []):
        if o.get("name", "").lower() in ("color", "colour"):
            return len(o.get("values", []))
    return 0

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
            prices = sorted(float(v["price"]) for v in variants if v.get("available") and v.get("price")) or prices
        imgs = p.get("images") or []
        items.append({
            "handle": p["handle"], "title": clean_title(p), "raw_title": p["title"],
            "min": prices[0] if prices else None, "max": prices[-1] if prices else None,
            "img": imgs[0]["src"] if imgs else None, "nimg": len(imgs),
            "colors": color_count(p), "section": section_of(clean_title(p) + " " + p["title"]),
        })
    return items, skipped

def find_image(raw, name):
    for p in raw:
        for im in p.get("images", []):
            if im["src"].split("?")[0].endswith("/" + name):
                return im["src"]
    return None

# ---------------- image processing ----------------
def slug(s):
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")[:70]

def to_rgb(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")

def edge_info(im):
    """Look at the four corners. Flat, matching corners mean a product shot on a plain backdrop;
    busy corners mean a scene. Returns (flat, average corner color)."""
    w, h = im.size
    t = max(4, int(min(w, h) * 0.04))
    boxes = [(0, 0, t, t), (w - t, 0, w, t), (0, h - t, t, h), (w - t, h - t, w, h)]
    means, spreads = [], []
    for bx in boxes:
        patch = im.crop(bx).resize((6, 6))
        px = list(patch.get_flattened_data()) if hasattr(patch, "get_flattened_data") else list(patch.getdata())
        m = tuple(sum(c[i] for c in px) / len(px) for i in range(3))
        means.append(m)
        spreads.append((sum(sum((c[i] - m[i]) ** 2 for i in range(3)) / 3 for c in px) / len(px)) ** 0.5)
    avg = tuple(sum(m[i] for m in means) / 4 for i in range(3))
    apart = max(max(abs(m[i] - avg[i]) for i in range(3)) for m in means)
    return apart < 16 and max(spreads) < 14, avg

def content_box(im, avg, tol=14, n=128):
    """Bounding box of everything that is not backdrop, and how full that box is.
    A studio shot fills well under 80% of its box; a photo inside a white frame fills over 90%."""
    t = im.resize((n, n))
    px = list(t.get_flattened_data()) if hasattr(t, "get_flattened_data") else list(t.getdata())
    pts = [k for k, c in enumerate(px) if any(abs(c[i] - avg[i]) >= tol for i in range(3))]
    if not pts:
        return None
    xs = [k % n for k in pts]; ys = [k // n for k in pts]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    w, h = im.size
    return {"fill": len(pts) / ((x1 - x0) * (y1 - y0)),
            "crop": (int(x0 * w / n), int(y0 * h / n), min(w, int(x1 * w / n) + 1), min(h, int(y1 * h / n) + 1))}

def save_product(src, name, folder):
    """Studio shots on a white backdrop are re-toned onto the tile color so they sit on it seamlessly.
    Anything with a real background (a scene, or a colored backdrop) is kept as a photo.
    Returns (relative path, kind) with kind 'clean' or 'photo'."""
    raw = cached(sized(src, PHOTO_W))
    if Image is None:
        ext = os.path.splitext(urllib.parse.urlsplit(src).path)[1].lower() or ".jpg"
        (folder / (name + ext)).write_bytes(raw)
        return f"images/{name}{ext}", "clean"
    im = to_rgb(Image.open(io.BytesIO(raw)))
    flat, avg = edge_info(im)
    box = None
    if flat and min(avg) >= 232:
        box = content_box(im, avg)
    if box and box["fill"] >= 0.9:
        # a photo sitting inside a white frame: trim the frame and treat it as a photo
        im = im.crop(box["crop"])
        flat = False
    if flat and min(avg) >= 232:
        chans = [c.point([min(255, int(v * t / max(a, 1) + .5)) for v in range(256)]) for c, a, t in zip(im.split(), avg, TILE)]
        im = Image.merge("RGB", chans)
        im.thumbnail((CLEAN_W, CLEAN_W), Image.LANCZOS)
        kind = "clean"
    else:
        if im.width > PHOTO_W:
            im = im.resize((PHOTO_W, round(im.height * PHOTO_W / im.width)), Image.LANCZOS)
        kind = "photo"
    im.save(folder / (name + ".webp"), "WEBP", quality=80, method=4)
    return f"images/{name}.webp", kind

def save_hero(src, width, name, folder, quality=82):
    raw = cached(sized(src, width))
    im = to_rgb(Image.open(io.BytesIO(raw)))
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(folder / (name + ".webp"), "WEBP", quality=quality, method=4)
    return f"images/{name}.webp"

# ---------------- page builders ----------------
E = lambda s: html.escape(str(s), quote=True)

def link(handle):
    return f"{STORE}/products/{urllib.parse.quote(handle, safe='-_.~%')}?{UTM}"

def meta_html(it):
    bits = []
    if SHOW_PRICES and it["min"] is not None:
        if it["max"] and it["max"] > it["min"]:
            bits.append(f'<b>From {money(it["min"])}</b>')
        else:
            bits.append(f'<b>{money(it["min"])}</b>')
    if it["colors"] > 1:
        bits.append(f'<span>{it["colors"]} colors</span>')
    return f'<p class="meta">{"".join(bits)}</p>' if bits else '<p class="meta"></p>'

def img_tag(it):
    if it.get("local"):
        return f'<img src="{E(it["local"])}" alt="{E(it["title"])}" loading="lazy" decoding="async">'
    return '<span class="noimg">Photo online</span>'

def card(it):
    href = f'href="{E(link(it["handle"]))}" target="_blank" rel="noopener"'
    text = f'<h3>{E(it["title"])}</h3><div class="row">{meta_html(it)}<span class="go">View on duraweather.com</span></div>'
    if it.get("kind") == "photo":
        return f'<a class="card shot" {href}>{img_tag(it)}<div class="cap">{text}</div></a>'
    return f'<a class="card" {href}><div class="tile">{img_tag(it)}</div><div class="ct">{text}</div></a>'

def grid_page(chunk, section, kind):
    cls = ("s" if kind == "photo" else "c") + ("1" if len(chunk) == 1 else "4")
    return (f'<div class="pad"><p class="eyebrow">{E(section)}</p>'
            f'<div class="grid {cls}">{"".join(card(c) for c in chunk)}</div></div>')

def split_even(items, k):
    """Split items into k pages as evenly as possible."""
    base, extra = divmod(len(items), k)
    out, i = [], 0
    for j in range(k):
        n = base + (1 if j < extra else 0)
        out.append(items[i:i + n]); i += n
    return out

def split_fill(items, k, cap):
    """Fill pages to the limit so every page looks the same, and keep the last page from holding a single piece."""
    n = len(items)
    if k * cap < n or k == 1:
        sizes = [n]
    else:
        sizes = None
        if -(-n // cap) == k:
            rem = n - cap * (k - 1)
            sizes = [cap] * (k - 1) + [rem]
            if rem == 1 and k >= 2 and cap > 2:
                sizes[-2:] = [cap - 1, 2]
    if sizes is None or len(sizes) != k:
        return split_even(items, k)
    out, i = [], 0
    for z in sizes:
        out.append(items[i:i + z]); i += z
    return out

def paginate(its):
    """Photos with a real background get their own large pages, then the studio shots follow.
    Returns (list of (kind, chunk), needs_closer)."""
    photos = [i for i in its if i.get("kind") == "photo"]
    clean = [i for i in its if i.get("kind") != "photo"]
    kp, kg = -(-len(photos) // PHOTO_PER_PAGE), -(-len(clean) // CLEAN_PER_PAGE)
    closer = False
    pages = []
    if kp:
        pages += [("photo", c) for c in split_fill(photos, kp, PHOTO_PER_PAGE)]
    if kg:
        pages += [("clean", c) for c in split_fill(clean, kg, CLEAN_PER_PAGE)]
    return pages, closer

def hero_pages(section, img, count, lo):
    """A full-bleed two-page opener. The same photo spans both pages."""
    price = f" &middot; from {money(lo)}" if SHOW_PRICES and lo is not None else ""
    pic = lambda pos: f'<img class="bleed {pos}" src="{E(img)}" alt="" loading="lazy" decoding="async">' if img else ""
    base = "hero" if img else "hero plain"
    size = 112 if len(section) <= 14 else 92 if len(section) <= 20 else 76
    left = (f'<div class="{base}">{pic("l")}<div class="scrim"></div><div class="htxt">'
            f'<p class="eyebrow w">{count} piece{"s" if count != 1 else ""}{price}</p>'
            f'<h1 style="font-size:calc(var(--u)*{size})">{E(section)}</h1></div></div>')
    right = (f'<div class="{base}">{pic("r")}<div class="scrim"></div><div class="htxt r">'
             f'<p class="lede w">{E(INTROS.get(section, ""))}</p></div></div>')
    return left, right

def build_pages(items, imgs, build_date):
    groups = {name: [] for name in ORDER}
    for it in items:
        groups[it["section"]].append(it)
    groups = {k: v for k, v in groups.items() if v}

    pages = []   # list of (label, html, kind); kind in cover|back|hero|inner
    A = pages.append

    cover_img = f'<img class="bleed" src="{E(imgs["COVER"])}" alt="">' if imgs.get("COVER") else ""
    A(("Cover", f'''<div class="cover">{cover_img}
      <div class="scrim cv"></div>
      <div class="cvtop"><span class="mark">DURAWEATHER<sup>&reg;</sup></span><span class="yr">2026</span></div>
      <div class="cvmid"><p class="eyebrow w">Quick Ship Collection</p><h1>Outdoor furniture,<br>ready to ship.</h1>
      <p class="lede w">{len(items)} pieces in DuraWeather Poly&reg;. Made in the USA.</p></div>
      <div class="cvfoot"><span>Made in USA</span><span>duraweather.com</span></div></div>''', "cover"))

    why = [("Made in the USA", "Built in our plants in Iowa, Ohio and Wisconsin."),
           ("Limited 20-year warranty", "Backed against fading, rotting and rusting."),
           ("316 marine-grade stainless", "Powder-coated stainless hardware on every piece, for pools, coasts and winter salt."),
           ("Stays outside year round", "95% high-density polyethylene with 5% UV inhibitors. No painting or sealing.")]
    ph = f'<img src="{E(imgs["INTRO"])}" alt="" loading="lazy" decoding="async">' if imgs.get("INTRO") else ""
    A(("Why DuraWeather", f'''<div class="why"><div class="whyimg">{ph}</div><div class="pad">
      <p class="eyebrow">Why DuraWeather</p><h2>Made to be left outside,<br>season after season.</h2>
      <div class="facts">{"".join(f'<div><h4>{t}</h4><p>{d}</p></div>' for t, d in why)}</div>
      <div class="call"><div><p class="k">Questions or bulk orders?</p><p class="v">Call 252-512-4191</p></div>
      <p class="hrs">Monday to Saturday, 10 AM to 6 PM EST<br>Sunday, 1 PM to 6 PM</p></div></div></div>''', "inner"))
    A(("Contents", None, "inner"))

    toc = []
    for name, its in groups.items():
        start = len(pages) + 1
        assert start % 2 == 0, f"section {name} would start on an odd page"
        lo = min((i["min"] for i in its if i["min"] is not None), default=None)
        toc.append((name, start, len(its)))
        l, r = hero_pages(name, imgs.get(name), len(its), lo)
        A((name, l, "hero")); A((name, r, "hero"))
        pgs, closer = paginate(its)
        for kind, chunk in pgs:
            A((name, grid_page(chunk, name, kind), "inner"))
        if closer or (len(pages) + 1) % 2 != 0:   # keep the next opener on a left page
            pic = f'<img class="bleed" src="{E(imgs[name])}" alt="">' if imgs.get(name) else ""
            A((name, f'<div class="closer">{pic}</div>', "hero"))

    rows = "".join(f'<a class="toc" data-go="{p}" href="#p{p}"><span class="tn">{E(n)}</span>'
                   f'<span class="tc">{c} piece{"s" if c != 1 else ""}</span><span class="tp">{p:02d}</span></a>' for n, p, c in toc)
    pages[2] = ("Contents", f'''<div class="pad"><p class="eyebrow">Contents</p><h2>Inside</h2>
      <p class="intro">Tap any photo to see every color and option on duraweather.com.</p>
      <div class="tocs">{rows}</div></div>''', "inner")

    note = f"Prices as of {build_date}. " if SHOW_PRICES else ""
    # keep the back cover on a left page
    while (len(pages) + 1) % 2 != 0:
        A(("Notes", '<div class="pad"><p class="eyebrow">Notes</p></div>', "inner"))
    A(("Back", f'''<div class="back"><p class="mark">DURAWEATHER<sup>&reg;</sup></p>
      <h1>See every color online.</h1>
      <p class="lede w">Each piece links to its page on duraweather.com, with current colors and options.</p>
      <a class="big" href="{STORE}/collections/{COLLECTION}?{UTM}" target="_blank" rel="noopener">duraweather.com</a>
      <p class="ph2">Questions? Call 252-512-4191</p>
      <p class="fine">{note}Colors and availability may change. Visit duraweather.com for current details. &copy; {datetime.date.today().year} DuraWeather.</p></div>''', "back"))

    final = []
    for i, (label, body, kind) in enumerate(pages, 1):
        cls = {"cover": "pg", "back": "pg", "hero": "pg"}.get(kind, "pg inner")
        foot = ""
        if kind == "inner":
            folio = f'<span class="folio">{i:02d}</span>'
            lab = f'<span>DuraWeather Quick Ship &middot; {E(label)}</span>'
            foot = f'<div class="foot">{folio + lab if i % 2 == 0 else lab + folio}</div>'
        final.append(f'<section class="{cls}" data-n="{i}">{body}{foot}</section>')
    return final, len(pages)

CSS = r"""
:root{--bg:#EDEEEA;--chrome:#17241E;--muted:#66706A;--btn:#fff;--shadow:rgba(16,26,21,.30);--line:rgba(23,36,30,.14);
 --ink:#17241E;--body:#3B4741;--soft:#67716B;--rule:#DADDD7;--spruce:#17241E;--brass:#9A7433;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0F1512;--chrome:#E7ECE8;--muted:#98A59E;--btn:#1E2924;--shadow:rgba(0,0,0,.6);--line:rgba(231,236,232,.16);color-scheme:dark}}
*{box-sizing:border-box;margin:0;padding:0}html,body{height:100%}
body{background:var(--bg);color:var(--chrome);font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif;overflow:hidden;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
header{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:14px 22px;font-size:14px;flex:none}
header .t{font-weight:600;letter-spacing:.14em;font-size:12.5px;white-space:nowrap}header .t span{color:var(--muted);font-weight:500;letter-spacing:.04em;margin-left:12px;font-size:13px}
header nav{display:flex;gap:10px;align-items:center}
header a,header button{font:inherit;font-size:13px;color:var(--chrome);background:none;border:0;cursor:pointer;text-decoration:none;padding:6px 4px;border-bottom:1px solid currentColor}
#stage{flex:1;position:relative;display:flex;min-height:0;overflow:auto;scrollbar-width:thin}
#stage.zoomed{cursor:grab}
#book{position:relative;perspective:3200px;margin:auto;flex:none;transition:transform .7s cubic-bezier(.45,.05,.25,1)}
#book.first.spread{transform:translateX(-25%)}#book.last.spread{transform:translateX(25%)}
.half{position:absolute;top:0;height:100%;overflow:hidden;background:#fff;container-type:size}.half.L{left:0}.half.R{right:0}.half.empty{background:transparent}
#book.spread .half{width:50%}#book.single .half{width:100%}#book.single .half.L{display:none}
.shadow{position:absolute;inset:0;box-shadow:0 22px 60px var(--shadow);pointer-events:none;transition:left .7s,right .7s}
#book.spread.first .shadow{left:50%}#book.spread.last .shadow{right:50%}
.gutter{position:absolute;top:0;bottom:0;left:50%;width:7%;margin-left:-3.5%;pointer-events:none;z-index:4;background:linear-gradient(90deg,transparent 0,rgba(0,0,0,.05) 38%,rgba(0,0,0,.16) 50%,rgba(0,0,0,.05) 62%,transparent 100%)}
#book.single .gutter,#book.first .gutter,#book.last .gutter{display:none}
.leaf{position:absolute;top:0;height:100%;width:50%;transform-style:preserve-3d;z-index:5;pointer-events:none}
.leaf .face{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden;overflow:hidden;background:#fff;container-type:size}
.leaf .back{transform:rotateY(180deg)}.leaf.fwd{left:50%;transform-origin:left center}.leaf.bwd{left:0;transform-origin:right center}
.shade{position:absolute;inset:0;z-index:9;opacity:0;pointer-events:none}
.leaf.fwd .front .shade{background:linear-gradient(90deg,rgba(0,0,0,.42),rgba(0,0,0,0))}.leaf.fwd .back .shade{background:linear-gradient(270deg,rgba(0,0,0,.42),rgba(0,0,0,0))}
.leaf.bwd .front .shade{background:linear-gradient(270deg,rgba(0,0,0,.42),rgba(0,0,0,0))}.leaf.bwd .back .shade{background:linear-gradient(90deg,rgba(0,0,0,.42),rgba(0,0,0,0))}
.nav{position:fixed;top:50%;transform:translateY(-50%);width:46px;height:46px;border-radius:50%;border:1px solid var(--line);background:var(--btn);color:var(--chrome);cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:10;box-shadow:0 4px 14px var(--shadow)}
.nav:disabled{opacity:.28;cursor:default}.nav svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
#prev{left:16px}#next{right:16px}
:focus-visible{outline:2px solid var(--brass);outline-offset:3px}
footer{flex:none;display:flex;justify-content:center;align-items:center;gap:12px;padding:10px 16px 16px;flex-wrap:wrap}
footer button{font:inherit;font-size:13px;color:var(--chrome);background:transparent;border:1px solid var(--line);border-radius:20px;padding:7px 15px;cursor:pointer}
#count{font-size:13px;color:var(--muted);min-width:96px;text-align:center;font-variant-numeric:tabular-nums}
#thumbs{position:fixed;inset:0;background:var(--bg);z-index:50;display:none;overflow:auto;padding:76px 22px 30px}
#thumbs.open{display:block}#thumbs .grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:22px 16px;max-width:1100px;margin:0 auto}
#thumbs .tb{background:none;border:0;cursor:pointer;color:var(--muted);font:inherit;font-size:12px}
#thumbs .tbox{width:100%;aspect-ratio:816/1056;overflow:hidden;position:relative;background:#fff;box-shadow:0 6px 18px var(--shadow);margin-bottom:6px;pointer-events:none;container-type:size}
#thumbs .close{position:fixed;top:16px;right:22px;font:inherit;font-size:13px;border:1px solid var(--line);border-radius:20px;padding:7px 15px;color:var(--chrome);background:var(--btn);cursor:pointer}
@media (max-width:760px){header{padding:10px 14px}header .t span,#full,header nav a{display:none}header nav{gap:8px}header button{white-space:nowrap}.nav{width:40px;height:40px}#prev{left:6px}#next{right:6px}}

/* ---------- catalog pages. Every size is in u = 1/816 of the page width, so pages stay crisp at any size ---------- */
.pg{--u:calc(100cqw / 816);position:absolute;inset:0;background:#fff;color:var(--body);overflow:hidden;font-size:calc(var(--u)*16);line-height:1.5;font-family:"Instrument Sans","Helvetica Neue",Arial,sans-serif}
.pg a{color:inherit;text-decoration:none}.pg img{display:block}
.pg h1,.pg h2,.pg h3,.pg h4{font-weight:600;color:var(--ink);text-wrap:balance}
.pg h1,.pg h2{font-family:"Cormorant Garamond",Georgia,serif;letter-spacing:-.01em}
.pad{position:absolute;inset:0;padding:68u 64u 0}
.eyebrow{font-size:12.5u;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--soft);display:flex;align-items:center;gap:12u;height:18u}
.eyebrow i{width:26u;height:1px;background:var(--brass);display:inline-block}
.eyebrow.w{color:rgba(255,255,255,.86)}
.lede{font-size:20u;line-height:1.5;color:var(--body)}.lede.w{color:rgba(255,255,255,.94)}
.foot{position:absolute;left:64u;right:64u;bottom:36u;display:flex;justify-content:space-between;align-items:baseline;font-size:12u;letter-spacing:.04em;color:var(--soft);border-top:1px solid var(--rule);padding-top:12u}
.folio{font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:.08em}
.bleed{position:absolute;top:0;height:100%;width:100%;object-fit:cover;object-position:center}
.scrim{position:absolute;inset:0;background:linear-gradient(0deg,rgba(11,20,15,.82) 0,rgba(11,20,15,.45) 32%,rgba(11,20,15,0) 62%)}
.scrim.cv{background:linear-gradient(180deg,rgba(11,20,15,.55) 0,rgba(11,20,15,0) 24%,rgba(11,20,15,.35) 48%,rgba(11,20,15,.9) 100%)}
/* cover */
.cover{position:absolute;inset:0;background:var(--spruce);color:#fff}
.cvtop{position:absolute;left:64u;right:64u;top:60u;display:flex;justify-content:space-between;align-items:baseline}
.mark{font-size:18u;font-weight:600;letter-spacing:.34em;color:#fff}.mark sup{font-size:.55em;letter-spacing:0}
.yr{font-size:14u;letter-spacing:.2em;color:rgba(255,255,255,.85)}
.cvmid{position:absolute;left:64u;right:64u;bottom:150u}
.cvmid h1{font-size:94u;line-height:.98;color:#fff;margin:18u 0 24u;font-weight:500}.cvmid .lede{font-size:21u;max-width:520u}
.cvfoot{position:absolute;left:64u;right:64u;bottom:54u;display:flex;justify-content:space-between;font-size:13u;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.8);border-top:1px solid rgba(255,255,255,.3);padding-top:14u}
/* why */
.why{position:absolute;inset:0}.whyimg{position:absolute;left:0;right:0;top:0;height:430u;overflow:hidden}.whyimg img{width:100%;height:100%;object-fit:cover}
.why .pad{top:430u;padding-top:48u}
.why h2{font-size:46u;line-height:1.05;margin:14u 0 0;font-weight:500}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:26u 40u;margin-top:34u}.facts h4{font-size:17u;margin-bottom:4u}.facts p{font-size:14.5u;line-height:1.45}
.call{position:absolute;left:64u;right:64u;bottom:90u;background:#F2F3EF;padding:20u 26u;display:flex;justify-content:space-between;align-items:center;gap:20u}
.call .k{font-size:13u;color:var(--soft)}.call .v{font-family:"Cormorant Garamond",Georgia,serif;font-size:30u;font-weight:600;color:var(--ink);line-height:1.2}.hrs{font-size:12.5u;color:var(--soft);text-align:right}
/* contents */
.pad h2{font-size:56u;line-height:1;margin:22u 0 16u;font-weight:500}.intro{font-size:17u;max-width:470u}
.tocs{margin-top:40u;border-top:1px solid var(--rule)}
.toc{display:grid;grid-template-columns:1fr 120u 44u;align-items:baseline;padding:11u 0;border-bottom:1px solid var(--rule);cursor:pointer}
.tn{font-family:"Cormorant Garamond",Georgia,serif;font-size:29u;font-weight:600;color:var(--ink)}.tc{font-size:14u;color:var(--soft)}.tp{font-size:14u;font-weight:600;text-align:right;color:var(--ink);font-variant-numeric:tabular-nums}
.toc:hover .tn{color:var(--brass)}
/* hero openers: one photo spans two pages */
.hero{position:absolute;inset:0;background:var(--spruce);overflow:hidden}
.hero .bleed{width:200%}.hero .bleed.l{left:0}.hero .bleed.r{left:-100%}
.hero .htxt{position:absolute;left:64u;right:64u;bottom:76u}
.hero .htxt h1{font-size:112u;line-height:.92;color:#fff;font-weight:500;margin-top:14u;max-width:690u}
.hero .htxt.r{display:flex;align-items:flex-end;justify-content:flex-start}.hero .htxt.r .lede{font-size:22u;max-width:440u;margin-left:0}
.hero.plain{background:linear-gradient(135deg,#1d3128,#0f1a14)}
.closer{position:absolute;inset:0;background:var(--spruce);overflow:hidden}.closer .bleed{width:200%;left:-100%}.closer .htxt{position:absolute;left:64u;right:64u;bottom:76u}.closer .lede{font-size:20u;max-width:420u}
/* product pages: studio shots sit on a tile, photos with a real background run large with the title over them */
.grid{display:grid;gap:28u 30u;margin-top:26u;height:calc(var(--u)*856)}
.grid.c4{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
.grid.s2{grid-template-columns:1fr;grid-template-rows:1fr 1fr}
.grid.c1{grid-template-columns:1fr;grid-template-rows:1fr;height:calc(var(--u)*700)}.grid.s1{grid-template-columns:1fr;grid-template-rows:1fr}
.card{display:flex;flex-direction:column;min-height:0;position:relative}
.tile{flex:1;min-height:0;position:relative;overflow:hidden;background:#efefeb;border-radius:2u}
.tile img,.shot img{position:absolute;inset:0;width:100%;height:100%;transition:transform .6s cubic-bezier(.2,.6,.2,1)}
.tile img{object-fit:contain;padding:7%}.shot img{object-fit:cover}
.card:hover .tile img,.card.shot:hover img{transform:scale(1.035)}
.noimg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:13u;color:var(--soft)}
.ct{flex:none;height:calc(var(--u)*128);padding-top:14u;display:flex;flex-direction:column}
.card h3{font-family:"Cormorant Garamond",Georgia,serif;font-size:25u;line-height:1.1;font-weight:600;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:14u;margin-top:auto;padding-bottom:2u}
.meta{font-size:15u;color:var(--soft);min-height:1em}
.go{font-size:13.5u;font-weight:600;color:var(--ink);border-bottom:1px solid var(--brass);padding-bottom:1u;white-space:nowrap}
.card:hover h3{color:var(--brass)}
.shot{background:#222;border-radius:2u;overflow:hidden}
.shot::after{content:"";position:absolute;inset:0;background:linear-gradient(0deg,rgba(11,20,15,.78) 0,rgba(11,20,15,.35) 34%,rgba(11,20,15,0) 58%)}
.shot .cap{position:absolute;left:30u;right:30u;bottom:26u;z-index:2}
.shot h3{font-size:36u;color:#fff;-webkit-line-clamp:2}.shot .row{margin-top:8u}
.shot .meta{color:rgba(255,255,255,.86)}.shot .go{color:#fff;border-color:rgba(255,255,255,.7)}
.shot:hover h3{color:#fff}
/* back cover */
.back{position:absolute;inset:0;background:var(--spruce);color:#DDE5E0;padding:150u 80u}
.back .mark{margin-bottom:140u}.back h1{color:#fff;font-size:76u;line-height:1;font-weight:500;max-width:560u;margin-bottom:22u}
.back .lede{max-width:480u}
.back .big{display:inline-block;font-family:"Cormorant Garamond",Georgia,serif;font-size:42u;font-weight:600;color:#fff;margin-top:64u;border-bottom:1px solid var(--brass)}
.ph2{margin-top:16u;font-size:17u;color:#fff}
.fine{position:absolute;left:80u;right:80u;bottom:56u;font-size:12u;color:#9FB0A7;border-top:1px solid rgba(255,255,255,.22);padding-top:12u}
@media (prefers-reduced-motion:reduce){.leaf{display:none}#book{transition:none}}
"""

JS = r"""
const SRC=[...document.getElementById('src').content.children];const N=SRC.length,AR=816/1056,DUR=760;
const P=[null,...SRC.map(s=>{const c=document.importNode(s,true);c.querySelectorAll('img').forEach(i=>i.loading='eager');return c})];
const $=id=>document.getElementById(id),book=$('book'),stage=$('stage'),L=book.querySelector('.half.L'),R=book.querySelector('.half.R');
const prevBtn=$('prev'),nextBtn=$('next');
let mode='spread',pos=1,busy=false,zoom=1;const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
function spreadOf(p){if(p<=1)return[0,1];if(p>=N&&N%2===0)return[N,0];const l=p%2===0?p:p-1;return[l,l+1<=N?l+1:0]}
function setHalf(el,n){const node=n?P[n]:null;if(node){if(el.firstChild!==node||el.childNodes.length>1)el.replaceChildren(node)}else el.replaceChildren();el.classList.toggle('empty',!n)}
const loaded=new Set();
function srcsOf(n){return n>=1&&n<=N?[...SRC[n-1].querySelectorAll('img')].map(i=>i.getAttribute('src')):[]}
function preload(n){return Promise.all(srcsOf(n).map(s=>{if(loaded.has(s))return;loaded.add(s);const im=new Image();im.src=s;return im.decode?im.decode().catch(()=>{}):0}))}
function around(p){[p-2,p-1,p,p+1,p+2,p+3].forEach(preload)}
function layout(){const narrow=innerWidth<760||innerWidth<innerHeight*.95;mode=narrow?'single':'spread';
 const st=stage.getBoundingClientRect();const k=mode==='spread'?2:1;const padx=mode==='single'?(innerWidth<760?20:110):160;
 let h=st.height-28,w=h*AR*k;const mw=st.width-padx;if(w>mw){w=mw;h=w/(AR*k)}
 if(zoom>1){w*=zoom;h*=zoom}
 book.style.width=w+'px';book.style.height=h+'px';book.className=mode;stage.classList.toggle('zoomed',zoom>1);render()}
function render(){if(mode==='spread'){const[l,r]=spreadOf(pos);setHalf(L,l);setHalf(R,r);book.classList.toggle('first',!l);book.classList.toggle('last',!r);
  $('count').textContent=!l?N+' pages':!r?'Back cover':`Pages ${l}–${r} of ${N}`;prevBtn.disabled=!l;nextBtn.disabled=!r||r>=N}
 else{setHalf(R,pos);book.classList.remove('first','last');$('count').textContent=`Page ${pos} of ${N}`;prevBtn.disabled=pos<=1;nextBtn.disabled=pos>=N}
 try{history.replaceState(null,'',pos>1?'#p'+pos:location.pathname+location.search)}catch(e){}around(pos)}
function anim(el,kf,o){return new Promise(res=>{const a=el.animate(kf,o);a.onfinish=res;a.oncancel=res})}
async function turn(dir){if(busy)return;busy=true;try{
 if(mode==='single'){const t=pos+dir;if(t<1||t>N)return;await Promise.race([preload(t),wait(500)]);
  if(!reduce){await anim(R,[{opacity:1,transform:'translateX(0)'},{opacity:0,transform:`translateX(${-dir*28}px)`}],{duration:160,easing:'ease-in'})}
  pos=t;render();if(!reduce)await anim(R,[{opacity:0,transform:`translateX(${dir*28}px)`},{opacity:1,transform:'none'}],{duration:200,easing:'ease-out'});return}
 const[l,r]=spreadOf(pos);if(dir>0&&(!r||r>=N))return;if(dir<0&&!l)return;
 const target=dir>0?r+1:(l-1<=1?1:l-1);const[nl,nr]=spreadOf(target);
 await Promise.race([Promise.all([preload(nl),preload(nr)]),wait(600)]);
 if(reduce){pos=target;render();return}
 const leaf=document.createElement('div');leaf.className='leaf '+(dir>0?'fwd':'bwd');
 const f=document.createElement('div');f.className='face front';const b=document.createElement('div');b.className='face back';
 const fs=document.createElement('div');fs.className='shade';const bs=document.createElement('div');bs.className='shade';
 const fn=P[dir>0?r:l],bn=dir>0?(nl?P[nl]:null):(nr?P[nr]:null);
 /* the same page elements move into the turning leaf, so nothing is re-created or re-loaded */
 if(fn)f.appendChild(fn);f.appendChild(fs);if(bn)b.appendChild(bn);b.appendChild(bs);leaf.append(f,b);book.appendChild(leaf);
 if(dir>0){setHalf(R,nr);book.classList.toggle('last',!nr);book.classList.toggle('first',false)}else{setHalf(L,nl);book.classList.toggle('first',!nl);book.classList.toggle('last',false)}
 const o={duration:DUR,easing:'cubic-bezier(.45,.05,.25,1)'};
 fs.animate([{opacity:0},{opacity:1}],{...o,fill:'forwards'});bs.animate([{opacity:1},{opacity:0}],{...o,fill:'forwards'});
 await anim(leaf,[{transform:'rotateY(0deg)'},{transform:`rotateY(${dir>0?-180:180}deg)`}],o);
 pos=target;if(dir>0){setHalf(L,nl)}else{setHalf(R,nr)}leaf.remove();render()
 }finally{busy=false}}
prevBtn.onclick=()=>turn(-1);nextBtn.onclick=()=>turn(1);$('first').onclick=()=>{pos=1;render()};
$('toc').onclick=()=>{pos=3;render()};
$('zoom').onclick=()=>{zoom=zoom>1?1:(innerWidth<760?2.4:1.7);$('zoom').textContent=zoom>1?'Fit page':'Zoom';layout();stage.scrollTo(0,0)};
$('full').onclick=()=>{document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.()};
addEventListener('keydown',e=>{if($('thumbs').classList.contains('open')){if(e.key==='Escape')closeThumbs();return}
 if(e.key==='ArrowRight'||e.key==='PageDown'||e.key===' ')turn(1);if(e.key==='ArrowLeft'||e.key==='PageUp')turn(-1)});
book.addEventListener('click',e=>{const a=e.target.closest('[data-go]');if(a){e.preventDefault();pos=+a.dataset.go;render()}});
let sx=null,sy=null;book.addEventListener('touchstart',e=>{if(zoom>1)return;sx=e.touches[0].clientX;sy=e.touches[0].clientY},{passive:true});
book.addEventListener('touchend',e=>{if(sx===null)return;const dx=e.changedTouches[0].clientX-sx,dy=e.changedTouches[0].clientY-sy;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy))turn(dx<0?1:-1);sx=null},{passive:true});
const tg=document.querySelector('#thumbs .grid2');let built=false;
function buildThumbs(){if(built)return;built=true;SRC.forEach((s,i)=>{const b=document.createElement('button');b.className='tb';b.dataset.p=i+1;
 const box=document.createElement('div');box.className='tbox';box.appendChild(s.cloneNode(true));b.append(box,document.createTextNode(i===0?'Cover':i===N-1?'Back':i+1));tg.appendChild(b)})}
tg.onclick=e=>{const b=e.target.closest('.tb');if(!b)return;pos=+b.dataset.p;closeThumbs();render()};
function closeThumbs(){$('thumbs').classList.remove('open')}
$('all').onclick=()=>{$('thumbs').classList.add('open');buildThumbs()};$('closeT').onclick=closeThumbs;
function fromHash(){const m=/^#p(\d+)$/.exec(location.hash);if(m){const n=+m[1];if(n>=1&&n<=N)pos=n}}
addEventListener('hashchange',()=>{const o=pos;fromHash();if(pos!==o)render()});
let rt;addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(layout,80)});
fromHash();const go=()=>{layout()};
Promise.race([document.fonts?document.fonts.ready:0,wait(2500)]).then(go);
"""

TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>DuraWeather Quick Ship Collection</title>
<meta name="description" content="__COUNT__ pieces of American-made outdoor furniture, ready to ship. Browse the DuraWeather Quick Ship collection.">
<meta property="og:title" content="DuraWeather Quick Ship Collection"><meta property="og:type" content="website">
<meta property="og:description" content="__COUNT__ pieces of American-made outdoor furniture, ready to ship.">
<meta property="og:url" content="__PUBLIC__">__OG__
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 rx=%2218%22 fill=%22%2317241E%22/><text x=%2250%22 y=%2272%22 font-family=%22Georgia,serif%22 font-size=%2272%22 text-anchor=%22middle%22 fill=%22white%22>D</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Instrument+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>__CSS__</style></head><body>
<header><div class="t">DURAWEATHER<span>Quick Ship Collection</span></div>
<nav><button id="toc">Contents</button><button id="all">All pages</button><button id="zoom">Zoom</button><button id="full">Full screen</button><a href="__SHOP__" target="_blank" rel="noopener">Shop duraweather.com</a></nav></header>
<div id="stage">
 <div id="book" class="spread"><div class="shadow"></div><div class="half L"></div><div class="half R"></div><div class="gutter"></div></div>
</div>
<button class="nav" id="prev" aria-label="Previous page"><svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg></button>
<button class="nav" id="next" aria-label="Next page"><svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></button>
<footer><button id="first">Cover</button><span id="count" aria-live="polite"></span></footer>
<div id="thumbs" role="dialog" aria-label="All pages"><button class="close" id="closeT">Close</button><div class="grid2"></div></div>
<template id="src">__PAGES__</template>
<script>__JS__</script></body></html>"""

def make_css():
    # design sizes are written as Nu (1/816 of the page width) and converted to container units
    return re.sub(r"(?<![\w#.-])(-?\d*\.?\d+)u\b", lambda m: f"calc(var(--u)*{m.group(1)})", CSS)

def main(products=None):
    print("Fetching Quick Ship products ...")
    raw = products if products is not None else fetch_products()
    items, skipped = prepare(raw)
    print(f"  {len(raw)} products found, {skipped} sold out skipped, {len(items)} in catalog")
    if Image is None:
        print("  Pillow not installed: photos will not be optimized and heroes will be skipped (pip install pillow)")
    if OUT.exists():
        shutil.rmtree(OUT)
    folder = OUT / "images"
    folder.mkdir(parents=True)

    print("Photos for each piece ...")
    fails = 0
    for n, it in enumerate(items, 1):
        if not it["img"]:
            it["local"], it["kind"] = None, "clean"; fails += 1; continue
        try:
            it["local"], it["kind"] = save_product(it["img"], slug(it["handle"]), folder)
        except Exception as e:
            print(f"  image failed: {it['title']} ({e})"); it["local"], it["kind"] = None, "clean"; fails += 1
        if n % 25 == 0:
            print(f"  {n}/{len(items)}")
    nphoto = sum(1 for i in items if i["kind"] == "photo")
    print(f"  {nphoto} photos with a background, {len(items) - nphoto} studio shots")

    groups = {}
    for it in items:
        groups.setdefault(it["section"], []).append(it)

    print("Hero photos ...")
    imgs = {}
    if Image is not None:
        for key, name in HEROES.items():
            if key not in ORDER + ["COVER", "INTRO"]:
                continue
            if key in ORDER and key not in groups:
                continue
            src = find_image(raw, name)
            if not src:
                print(f"  not found: {key} ({name})"); continue
            try:
                imgs[key] = save_hero(src, HERO_W if key != "INTRO" else 1400, "hero-" + slug(key), folder)
            except Exception as e:
                print(f"  hero failed: {key} ({e})")

    build_date = datetime.date.today().strftime("%B %-d, %Y") if os.name != "nt" else datetime.date.today().strftime("%B %#d, %Y")
    pages, n = build_pages(items, imgs, build_date)
    og = f'<meta property="og:image" content="{PUBLIC_URL}{imgs["COVER"]}">' if imgs.get("COVER") else ""
    doc = (TEMPLATE.replace("__CSS__", make_css()).replace("__JS__", JS).replace("__PAGES__", "\n".join(pages))
           .replace("__SHOP__", f"{STORE}/collections/{COLLECTION}?{UTM}").replace("__COUNT__", str(len(items)))
           .replace("__PUBLIC__", PUBLIC_URL).replace("__OG__", og))
    (OUT / "index.html").write_text(doc, encoding="utf-8")
    (OUT / "products.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
    secs = {}
    for it in items:
        secs[it["section"]] = secs.get(it["section"], 0) + 1
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"\nDone: {OUT / 'index.html'}")
    print(f"  {n} pages, {len(items)} products, {fails} photos missing, {total:.1f} MB total")
    for k in ORDER:
        if k in secs:
            print(f"  {k}: {secs[k]}")
    print("\nCommit and push the quick-ship folder to your GitHub Pages repo.")

if __name__ == "__main__":
    main()
