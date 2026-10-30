#!/usr/bin/env python3
"""Aquariumplanten DB (hive-pal-stijl). Run: python3 plants.py -> http://localhost:8377"""
# ponytail: cgi.FieldStorage bestaat tot Python 3.12 (3.13 verwijdert cgi) — upgrade: multipart handmatig parsen of naar een framework als je ooit verhuist
import cgi, html, json, os, re, socket, sqlite3, sys, threading, time, urllib.request
from datetime import date, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode, quote

HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
# ponytail: AQUARIUM_DATA laat data (db/foto's/notify.json/.digest_sent) los van de code — Docker volume
DATA = os.environ.get("AQUARIUM_DATA") or HERE
DB = os.path.join(DATA, "plants.db")
PHOTOS = os.path.join(DATA, "photos")
NOTIFY_CFG = os.path.join(DATA, "notify.json")
DIGEST = os.path.join(DATA, ".digest_sent")
PORT = 8377

try:
    os.makedirs(PHOTOS, exist_ok=True)
except OSError as e:
    sys.exit(f"Kan niet schrijven in {DATA} ({e}). Zet AQUARIUM_DATA of de rechten goed.")


def _digest_vandaag(dag):
    try:
        with open(DIGEST) as f:
            return f.read().strip() == dag
    except OSError:
        return False


# ponytail: notify.json stuurt naar HA (long-lived token) en/of ntfy (topic) — bestand weg = stil uit
NOTIFY_EN = [
    ("Te laat onderhoud:", "Overdue maintenance:"), (" (nog nooit)", " (never done)"),
    (" (elke ", " (every "), (" afgevinkt", " checked off"),
    ("Taak toegevoegd", "Task added"), ("Taak gedaan", "Task done"),
    ("Aquarium-onderhoud", "Aquarium maintenance"),
]


def _notify_text(s, lang):
    if lang != "en":
        return s
    for nl, en in NOTIFY_EN:
        s = s.replace(nl, en)
    return s


def notify(bericht, titel="Aquarium"):
    try:
        with open(NOTIFY_CFG) as f:
            cfg = json.load(f)
    except Exception:
        return False
    lang = str(cfg.get("lang") or "nl").lower()
    bericht, titel = _notify_text(bericht, lang), _notify_text(titel, lang)
    verzonden = False
    ha = cfg.get("ha") or {}
    if ha.get("token") and ha.get("services"):
        try:
            data = json.dumps({"title": titel, "message": bericht}).encode()
            for svc in ha["services"]:
                req = urllib.request.Request(
                    ha["url"].rstrip("/") + "/api/services/notify/" + svc, data=data,
                    headers={"Authorization": "Bearer " + ha["token"],
                             "Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=8).read()
            verzonden = True
        except Exception as e:
            print("HA-notify mislukt:", e)
    nt = cfg.get("ntfy") or {}
    if nt.get("topic"):
        try:
            srv = nt.get("server", "https://ntfy.sh").rstrip("/")
            body = json.dumps({"topic": nt["topic"], "title": titel,
                               "message": bericht}).encode()
            hdrs = {"Content-Type": "application/json"}
            if nt.get("token"):
                hdrs["Authorization"] = "Bearer " + nt["token"]
            urllib.request.urlopen(urllib.request.Request(
                srv + "/", data=body, headers=hdrs), timeout=8).read()
            verzonden = True
        except Exception as e:
            print("ntfy-notify mislukt:", e)
    return verzonden


def meld_late_taken():
    c = db()
    # JOIN (niet LEFT JOIN): taken van verwijderde aquaria zijn onzichtbaar in de UI
    # en zouden anders elke dag opnieuw gemeld worden zonder afgevinkt te kunnen worden.
    rows = c.execute("SELECT t.titel,t.interval_dagen,t.laatst_gedaan,a.naam "
                     "FROM taken t JOIN aquaria a ON a.id=t.tank_id").fetchall()
    c.close()
    late = [(t, an, ll) for t, iv, ll, an in rows if overdue(ll, iv) is True]
    if not late:
        return False
    tekst = "\n".join(f"- {t}" + ("" if ll else " (nog nooit)") + (f" [{an}]" if an else "")
                      for t, an, ll in late)
    return notify("Te laat onderhoud:\n" + tekst, "Aquarium-onderhoud")


def taken_watch():
    while True:
        nu = datetime.now()
        dag = nu.date().isoformat()
        if nu.hour >= 9 and not _digest_vandaag(dag) and meld_late_taken():
            with open(DIGEST, "w") as f:
                f.write(dag)
        time.sleep(300)


def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS plants(
        id INTEGER PRIMARY KEY, naam TEXT, link TEXT, plaats TEXT,
        land TEXT, van_wie TEXT, foto TEXT)""")
    if "tank_id" not in {r[1] for r in c.execute("PRAGMA table_info(plants)")}:
        c.execute("ALTER TABLE plants ADD COLUMN tank_id INTEGER")
        c.execute("UPDATE plants SET tank_id=1 WHERE tank_id IS NULL")
    if "soort" not in {r[1] for r in c.execute("PRAGMA table_info(plants)")}:
        c.execute("ALTER TABLE plants ADD COLUMN soort TEXT DEFAULT 'plant'")
        c.execute("UPDATE plants SET soort='plant' WHERE soort IS NULL")
    c.execute("CREATE TABLE IF NOT EXISTS plant_tanks(plant_id INTEGER, tank_id INTEGER)")
    if not c.execute("SELECT 1 FROM plant_tanks LIMIT 1").fetchone():
        c.execute("INSERT INTO plant_tanks(plant_id,tank_id) "
                  "SELECT id,tank_id FROM plants WHERE tank_id IS NOT NULL")
    c.execute("CREATE TABLE IF NOT EXISTS aquaria(id INTEGER PRIMARY KEY, naam TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS inspecties(
        id INTEGER PRIMARY KEY, tank_id INTEGER, datum TEXT,
        temp REAL, ph REAL, no2 REAL, no3 REAL, po4 REAL,
        gh REAL, kh REAL, co2 TEXT,
        opmerking TEXT, foto TEXT)""")
    icols = {r[1] for r in c.execute("PRAGMA table_info(inspecties)")}
    for col, typ in (("gh", "REAL"), ("kh", "REAL"), ("co2", "TEXT")):
        if col not in icols:
            c.execute(f"ALTER TABLE inspecties ADD COLUMN {col} {typ}")
    c.execute("""CREATE TABLE IF NOT EXISTS taken(
        id INTEGER PRIMARY KEY, tank_id INTEGER, titel TEXT,
        interval_dagen INTEGER, laatst_gedaan TEXT)""")
    if not c.execute("SELECT 1 FROM aquaria LIMIT 1").fetchone():
        c.execute("INSERT INTO aquaria(naam) VALUES('Aquarium')")
    c.commit()
    return c


def num(v):
    v = (v or "").strip().replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>@@NAAM@@</title>
<link rel=manifest href=/manifest.json>
<link rel=apple-touch-icon href=/icon.png>
<meta name=theme-color content="#123">
<style>
body{font-family:system-ui;margin:1rem 0;padding:0 1rem;background:#123;color:#eee}
h1{font-size:1.4rem} a{color:#8cf} h1 small{color:#9ab;font-weight:400;font-size:.9rem}
h2{font-size:1.05rem;margin:1.8rem 0 .6rem;border-bottom:1px solid #345;padding-bottom:.3rem}
form{background:#1d3a52;padding:1rem;border-radius:8px;margin-bottom:1.5rem}
label{display:block;margin:.4rem 0 .1rem;font-size:.85rem;color:#bcd}
input[type=text],input[type=url],input[type=number],input[type=date],input[type=password],select{
width:100%;padding:.4rem;border-radius:4px;border:1px solid #456;background:#0b2030;color:#eee;box-sizing:border-box}
input[type=file]{color:#bcd}
button{margin-top:.8rem;padding:.5rem 1.2rem;border:0;border-radius:4px;background:#2a8f4a;color:#fff;font-size:1rem;cursor:pointer}
.tabs{margin:.6rem 0 1rem}
.tabs a{display:inline-block;padding:.35rem .8rem;background:#1d3a52;color:#9ab;text-decoration:none;border-radius:6px 6px 0 0;margin-right:2px;font-size:.9rem}
.tabs a.on{background:#2a6f9e;color:#fff;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.8rem}
.card{background:#1d3a52;border-radius:8px;padding:.6rem;font-size:.8rem;overflow:hidden}
.card img{width:100%;height:120px;object-fit:cover;border-radius:4px;background:#0b2030}
.card b{display:block;margin:.35rem 0 .15rem;font-size:.9rem}
.card span{color:#9ab;display:block;word-break:break-all}
form.edit{background:#243;margin:.4rem 0 0;padding:.5rem}
form.edit label{margin:.25rem 0 .05rem}
.danger{color:#e77}
form.mini{padding:.6rem;margin-bottom:1rem}
form.mini button{margin-top:0}
.row{display:flex;gap:.6rem;align-items:flex-end;flex-wrap:wrap}
.row label{margin:0}
.row .grow{flex:1;min-width:8rem}
.checks{display:flex;gap:.7rem;flex-wrap:wrap;margin:.2rem 0 .4rem}
.checks label{display:flex;gap:.3rem;align-items:center;margin:0;color:#bcd;font-size:.9rem}
.lookprev{display:none;margin-top:.5rem;max-height:100px;border-radius:4px}
.netopt{display:none}
.netopt.on{display:flex;gap:.3rem;align-items:center;color:#bcd;font-size:.9rem;margin:.3rem 0}
.zoekbtn{background:#2a6f9e;margin:0}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{text-align:left;padding:.35rem .4rem;border-bottom:1px solid #2a4a66;vertical-align:middle}
th{color:#9ab;font-weight:600}
img.thumb{width:48px;height:34px;object-fit:cover;border-radius:3px;display:block}
.pill{padding:.15rem .55rem;border-radius:99px;font-size:.75rem;white-space:nowrap}
.pill.late{background:#a33;color:#fff} .pill.ok{background:#2a8f4a;color:#fff}
.taak{display:flex;gap:.7rem;align-items:center;background:#1d3a52;padding:.5rem .7rem;border-radius:6px;margin-bottom:.4rem;flex-wrap:wrap}
.taak .t{flex:1;min-width:10rem}
.taak small{color:#9ab}
.taak form{margin:0;background:none;padding:0;display:inline}
.taak button{margin:0;padding:.3rem .7rem;font-size:.85rem}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:100;cursor:zoom-out}
#lightbox img{max-width:92vw;max-height:92vh;border-radius:6px;box-shadow:0 0 30px #000}
.card img{cursor:zoom-in}
.filter{width:100%;padding:.45rem;border-radius:4px;border:1px solid #456;background:#0b2030;color:#eee;box-sizing:border-box;margin-bottom:.8rem}
.banner{background:#2a8f4a;color:#fff;padding:.5rem .8rem;border-radius:6px;margin:.4rem 0 .8rem;font-size:.9rem}
.empty{color:#9ab;font-size:.9rem;margin:.4rem 0}
.pager{display:flex;align-items:center;gap:.8rem;justify-content:center;margin:.9rem 0}
.pager a,.pager span{padding:.35rem .9rem;border-radius:6px;font-size:.9rem;background:#1d3a52;color:#9ab;text-decoration:none}
.pager a:hover{background:#2a6f9e;color:#fff}
.pager .off{opacity:.45}
.pager .pgcur{background:transparent;color:#eee}
.per{display:flex;align-items:center;gap:.4rem;font-size:.85rem;color:#9ab;margin:0 0 .8rem}
.per a{padding:.2rem .6rem;border-radius:6px;background:#1d3a52;color:#9ab;text-decoration:none}
.per a.on{background:#2a6f9e;color:#fff;font-weight:600}
.lang{float:right;font-weight:400;font-size:.85rem;margin-top:.2rem}
.lang a{color:#9ab;text-decoration:none;padding:0 .15rem}
.lang a.on{color:#fff;font-weight:600}
</style>
<h1>@@NAAM@@ <small>@@COUNT@@</small> <span class=lang>@@LANGSW@@</span></h1>
@@MSG@@
<div class=tabs>@@TABS@@</div>
<form class=mini method=post action=/add_tank>
<input type=hidden name=soort value=@@SOORT@@>
<div class=row><label class=grow>Nieuw aquarium<input type=text name=naam required></label><button>+</button></div>
</form>

<div class=tabs>@@SECTABS@@</div>
<h2>@@SECTNAAM@@</h2>
<form method=post action=/add enctype=multipart/form-data id=add>
<input type=hidden name=soort value=@@SOORT@@>
<div class=row>
<label>Aquarium(en)</label><div class=checks>@@TANKCHECKS@@</div>
<label class=grow>Naam *<input type=text name=naam required autofocus></label>
<button type=button class=zoekbtn onclick="zoekInfo(this,this.form)">Zoek info</button>
<label class=grow>Link<input type=text name=link placeholder=https://...></label>
<label class=grow>Plaats in bak<input type=text name=plaats placeholder="@@PLAATS@@"></label>
<label class=grow>Land / herkomst<input type=text name=land></label>
<label class=grow>Bij wie gehaald<input type=text name=van_wie></label>
<label>Foto<input type=file name=foto accept=image/* onchange="this.form.use_lookup.checked=false"></label>
<button>Toevoegen</button>
</div>
<input type=hidden name=lookup_foto>
<img class=lookprev alt="">
<label class=netopt><input type=checkbox name=use_lookup value=1> Internetfoto gebruiken</label>
</form>
<input class=filter type=search placeholder="Zoek in deze lijst op naam..." oninput="filterCards(this.value)">
@@PERSEL@@
<div class=grid>@@CARDS@@</div>
@@PAGER@@

<h2>Water-inspecties</h2>
<form class=mini method=post action=/add_inspectie enctype=multipart/form-data>
<input type=hidden name=tank_id value=@@TID@@>
<input type=hidden name=soort value=@@SOORT@@>
<div class=row>
<label>Datum<input type=date name=datum value=@@DATUM@@ required></label>
<label>GH<input type=number step=0.5 name=gh placeholder="8"></label>
<label>KH<input type=number step=0.5 name=kh placeholder="4"></label>
<label>Temp °C<input type=number step=0.1 name=temp placeholder="24"></label>
<label>pH<input type=number step=0.01 name=ph placeholder="7,0"></label>
<label>NO₂<input type=number step=0.01 name=no2 placeholder="0"></label>
<label>NO₃<input type=number step=0.1 name=no3 placeholder="10"></label>
<label>PO₄<input type=number step=0.01 name=po4 placeholder="0,5"></label>
<label>CO₂<select name=co2><option value="">-</option><option value=ja>ja</option><option value=nee>nee</option></select></label>
<label class=grow>Opmerking<input type=text name=opmerking></label>
<label>Foto<input type=file name=foto accept=image/*></label>
<button>Log</button>
</div>
</form>
@@INSP@@

<h2>Onderhoudstaken</h2>
<form class=mini method=post action=/add_taak>
<input type=hidden name=tank_id value=@@TID@@>
<input type=hidden name=soort value=@@SOORT@@>
<div class=row>
<label class=grow>Taak<input type=text name=titel placeholder="waterverversing" required></label>
<label>Elke<input type=number name=interval_dagen min=1 value=7 style="width:5rem"> dagen</label>
<button>+</button>
</div>
</form>
@@TAKEN@@
<div id=lightbox><img alt=""></div>
<script>
function filterCards(q){
  q=q.toLowerCase();
  document.querySelectorAll('.card').forEach(c=>{
    c.style.display=c.textContent.toLowerCase().indexOf(q)<0?'none':'';
  });
}
function cardPreview(form, d){
  const card=form.closest('.card');
  if(!card) return;
  const sp=card.querySelector('.p-plaats'); if(sp&&d.plaats) sp.textContent=d.plaats;
  const sl=card.querySelector('.p-land'); if(sl&&d.land) sl.textContent=d.land;
  const im=card.querySelector('img'); if(im&&d.foto) im.setAttribute('src','/photos/'+d.foto);
  const lk=card.querySelector('.p-link');
  if(lk&&d.link){lk.innerHTML='';const a=document.createElement('a');a.href=d.link;a.target='_blank';a.rel='noopener';a.textContent=d.link;lk.appendChild(a);}
}
async function zoekInfo(btn, form){
  const n=form.naam.value.trim();
  const l=form.link?form.link.value.trim():'';
  if(!n&&!l){btn.textContent='vul een naam of link in';return;}
  btn.textContent='zoeken...';
  try{
    const q=n?('naam='+encodeURIComponent(n)+(form.soort?'&soort='+form.soort.value:''))
             :('url='+encodeURIComponent(l));
    const d=await (await fetch('/lookup?'+q)).json();
    if(d.naam&&!n&&form.naam) form.naam.value=d.naam;
    ['link','plaats','land'].forEach(k=>{ if(d[k]) form[k].value=d[k]; });
    if(d.foto){
      form.lookup_foto.value=d.foto;
      const p=form.querySelector('.lookprev');
      if(p){ p.src='/photos/'+d.foto; p.style.display='block'; }
      const cb=form.querySelector('input[name=use_lookup]');
      const lab=form.querySelector('.netopt');
      if(cb) cb.checked=true;
      if(lab) lab.classList.add('on');
    }
    cardPreview(form, d);
    const ok = n ? (d.link||d.land||d.foto||d.plaats) : (d.naam||d.land||d.foto||d.plaats);
    btn.textContent = ok ? 'Info gevonden'
      : (n ? 'niets gevonden' : 'link niet leesbaar – probeer een andere site of typ de naam');
  }catch(e){btn.textContent='zoeken mislukt';}
}
document.addEventListener('click', e=>{
  if(e.target.tagName==='IMG'&&e.target.closest('.card')){
    const lb=document.getElementById('lightbox');
    lb.querySelector('img').src=e.target.src;
    lb.style.display='flex';
  } else if(e.target.id==='lightbox'){
    e.target.style.display='none';
  }
});
(()=>{const b=document.getElementById('banner'); if(b) setTimeout(()=>{b.style.display='none';},3000);})();
function autoPer(){
  const sp=new URLSearchParams(location.search);
  if(sp.has('perSet')||!document.querySelector('.card')) return;
  const cols=(getComputedStyle(document.querySelector('.grid')).gridTemplateColumns||'')
    .split(' ').filter(Boolean).length||1;
  const per=Math.max(6,cols*3);
  if(sp.get('per')===String(per)) return;
  sp.set('per',String(per));
  location.replace('?'+sp.toString());
}
window.addEventListener('load',autoPer);
</script>
"""

CARD = """<div class=card>
{img}
<b>{naam}</b>
 <span class=p-plaats>{plaats}</span><span class=p-land>{land}</span><span>{van_wie}</span>
<span class=p-link>{link}</span>
<form class=edit method=post action=/edit enctype=multipart/form-data>
<input type=hidden name=id value={id}>
<input type=hidden name=soort value="{soort}">
<label>Naam</label><input type=text name=naam value="{naam_e}">
<button type=button class=zoekbtn onclick="zoekInfo(this,this.form)">Zoek info</button>
<label>Link</label><input type=text name=link value="{link_e}">
<label>Plaats</label><input type=text name=plaats value="{plaats_e}">
<label>Land</label><input type=text name=land value="{land_e}">
<label>Bij wie</label><input type=text name=van_wie value="{van_wie_e}">
<label>Aquarium(en)</label><div class=checks>{tankchecks}</div>
<label>Nieuwe foto</label><input type=file name=foto accept=image/* onchange="this.form.use_lookup.checked=false">
<input type=hidden name=lookup_foto>
<img class=lookprev alt="">
<label class=netopt><input type=checkbox name=use_lookup value=1> Internetfoto gebruiken</label>
<button>Opslaan</button>
</form>
<form method=post action=/del onsubmit="return confirm('Verwijderen?')">
<input type=hidden name=id value={id}><input type=hidden name=soort value="{soort}"><button class=danger>Verwijder</button>
</form>
</div>"""

INSP_ROW = """<tr><td>{datum}</td><td>{gh}</td><td>{kh}</td><td>{temp}</td><td>{ph}</td><td>{no2}</td>
<td>{no3}</td><td>{po4}</td><td>{co2}</td><td>{opm}</td><td>{foto}</td>
<td><form method=post action=/del_insp onsubmit="return confirm('Verwijderen?')">
<input type=hidden name=id value={id}><input type=hidden name=tank_id value={tid}>
<input type=hidden name=soort value={soort}>
<button class=danger style="margin:0;padding:.2rem .5rem;font-size:.8rem">&times;</button></form></td></tr>"""


# --- taal (nl/en): vaste template-teksten worden hieronder 1x vertaald ---
EN_REPL = [
    ("Plaats in bak", "Position in tank"),
    ("Land / herkomst", "Country / origin"),
    ("Bij wie gehaald", "Bought from"),
    ("Internetfoto gebruiken", "Use internet photo"),
    ("Zoek in deze lijst op naam...", "Search this list by name..."),
    ("Zoek info", "Find info"),
    ("Nieuw aquarium", "New aquarium"),
    ("Water-inspecties", "Water inspections"),
    ("Onderhoudstaken", "Maintenance tasks"),
    ("Aquarium(en)", "Aquarium(s)"),
    ("Nieuwe foto", "New photo"),
    ("Naam *", "Name *"),
    ("Opmerking", "Remark"),
    ("Toevoegen", "Add"),
    ("Opslaan", "Save"),
    ("Verwijderen?", "Delete?"),
    (">Verwijder<", ">Delete<"),
    (">Naam<", ">Name<"),
    (">Plaats<", ">Position<"),
    (">Land<", ">Country<"),
    (">Bij wie<", ">Bought from<"),
    (">Datum<", ">Date<"),
    (">Taak<", ">Task<"),
    (">Elke<", ">Every<"),
    (">Foto<", ">Photo<"),
    ("> dagen<", "> days<"),
    ("<button>Log</button>", "<button>Save</button>"),
    ('placeholder="waterverversing"', 'placeholder="water change"'),
    ("<option value=ja>ja</option>", "<option value=ja>yes</option>"),
    ("<option value=nee>nee</option>", "<option value=nee>no</option>"),
    ("'vul een naam of link in'", "'enter a name or link'"),
    ("'zoeken...'", "'searching...'"),
    ("'Info gevonden'", "'info found'"),
    ("'niets gevonden'", "'nothing found'"),
    ("'link niet leesbaar – probeer een andere site of typ de naam'",
     "'link unreadable - try another site or type the name'"),
    ("'zoeken mislukt'", "'search failed'"),
]

T = {
    "nl": {
        "plants": "Planten", "fish": "Vissen",
        "plant_lc": "planten", "fish_lc": "vissen", "measurements": "metingen",
        "empty_plant": "Nog geen planten in dit aquarium — gebruik het formulier "
                       "hierboven om er een toe te voegen.",
        "empty_fish": "Nog geen vissen in dit aquarium — gebruik het formulier "
                      "hierboven om er een toe te voegen.",
        "places_plant": "achtergrond, middenzone",
        "places_fish": "boven, midden, bodem",
        "prev": "&lsaquo; vorige", "next": "volgende &rsaquo;", "page": "pagina",
        "per_page": "Per pagina:", "auto": "auto",
        "date": "Datum", "remark": "Opmerking", "photo": "Foto",
        "last30": "toont laatste 30",
        "late": "te laat", "never": "nog nooit", "left": "nog {n}d",
        "never_done": "nooit",
        "every_last": "elke {n} dagen &middot; laatst: {last}",
        "done": "Klaar", "no_tasks": "geen taken — voeg erboven een toe",
        "confirm_del": "Verwijderen?",
    },
    "en": {
        "plants": "Plants", "fish": "Fish",
        "plant_lc": "plants", "fish_lc": "fish", "measurements": "measurements",
        "empty_plant": "No plants in this aquarium yet — use the form above to add one.",
        "empty_fish": "No fish in this aquarium yet — use the form above to add one.",
        "places_plant": "background, midground",
        "places_fish": "upper, middle, bottom",
        "prev": "&lsaquo; previous", "next": "next &rsaquo;", "page": "page",
        "per_page": "Per page:", "auto": "auto",
        "date": "Date", "remark": "Remark", "photo": "Photo",
        "last30": "showing last 30",
        "late": "overdue", "never": "never done", "left": "{n}d left",
        "never_done": "never",
        "every_last": "every {n} days &middot; last: {last}",
        "done": "Done", "no_tasks": "no tasks — add one above",
        "confirm_del": "Delete?",
    },
}

MSG_EN = {
    "Toegevoegd": "Added", "Opgeslagen": "Saved", "Verwijderd": "Deleted",
    "Aquarium toegevoegd": "Aquarium added", "Inspectie gelogd": "Inspection logged",
    "Meting verwijderd": "Measurement deleted", "Taak toegevoegd": "Task added",
    "Taak afgevinkt": "Task checked off", "Taak verwijderd": "Task deleted",
}


def _en_tmpl(tmpl):
    for nl, en in EN_REPL:
        tmpl = tmpl.replace(nl, en)
    return tmpl


TPL = {"nl": (PAGE, CARD, INSP_ROW),
       "en": tuple(_en_tmpl(x) for x in (PAGE, CARD, INSP_ROW))}


def overdue(laatst, interval):
    if not interval:
        return None
    if not laatst:
        return True
    return (date.today() - date.fromisoformat(laatst)).days >= interval


PER_PAGE = 12


def page(c, tank, soort="plant", msg=None, pageno=1, per=PER_PAGE, per_set=False, lang="nl"):
    lang = lang if lang in T else "nl"
    t = lambda k: T[lang][k]
    tpl_page, tpl_card, tpl_insp = TPL[lang]
    soort = "vis" if soort == "vis" else "plant"
    per = per if isinstance(per, int) and 1 <= per <= 200 else PER_PAGE
    tid, tnaam = c.execute(
        "SELECT id,naam FROM aquaria WHERE id=?", (tank,)).fetchone() or (1, "Aquarium")
    tanks = c.execute("SELECT id,naam FROM aquaria ORDER BY id").fetchall()
    qs = "&soort=vis" if soort == "vis" else ""
    tabs = " ".join(
        f'<a href="/?tank={i}{qs}"{" class=on" if i == tid else ""}>{html.escape(n)}</a>'
        for i, n in tanks)
    sectabs = " ".join(
        f'<a href="/?tank={tid}{"&soort=vis" if k == "vis" else ""}"'
        f'{" class=on" if k == soort else ""}>{t("fish" if k == "vis" else "plants")}</a>'
        for k in ("plant", "vis"))
    links = {}
    for p, tk in c.execute("SELECT plant_id,tank_id FROM plant_tanks"):
        links.setdefault(p, set()).add(tk)
    checks = lambda sel: "".join(
        f'<label><input type=checkbox name=tank_id value={i}'
        f'{" checked" if i in sel else ""}>{html.escape(n)}</label>'
        for i, n in tanks)

    rows = c.execute(
        "SELECT DISTINCT p.id,p.naam,p.link,p.plaats,p.land,p.van_wie,p.foto "
        "FROM plants p JOIN plant_tanks pt ON pt.plant_id=p.id "
        "WHERE pt.tank_id=? AND p.soort=? ORDER BY p.naam", (tid, soort)).fetchall()
    totaal = len(rows)
    npages = max(1, (totaal + per - 1) // per)
    pageno = min(max(1, pageno), npages)
    rows = rows[(pageno - 1) * per:pageno * per]
    cards = []
    for pid, naam, link, plaats, land, van_wie, foto in rows:
        naam = naam or ""
        img = f'<img src="/photos/{html.escape(foto)}" alt="">' if foto else "<img alt=''>"
        linkhtml = ""
        if link:
            m = re.search(r"https?://\S+", link)
            if m:
                url = m.group(0)
                label = link[:m.start()].strip().strip("-\u2013 ") or url
                linkhtml = (f'<span><a href="{html.escape(url, quote=True)}" '
                            f'target=_blank rel=noopener>{html.escape(label[:80])}</a></span>')
            else:
                linkhtml = f"<span>{html.escape(link[:100])}</span>"
        e = lambda s: html.escape(s or "", quote=True)
        cards.append(tpl_card.format(
            id=pid, soort=soort, img=img, naam=html.escape(naam), plaats=html.escape(plaats or ""),
            land=html.escape(land or ""), van_wie=html.escape(van_wie or ""),
            link=linkhtml, naam_e=e(naam), link_e=e(link), plaats_e=e(plaats),
            land_e=e(land), van_wie_e=e(van_wie), tankchecks=checks(links.get(pid, set()))))
    cards_html = "\n".join(cards) or (
        f'<p class=empty>{t("empty_fish" if soort == "vis" else "empty_plant")}</p>')
    ps = "&perSet=1" if per_set else ""
    if npages > 1:
        pg = lambda n, lab, off: (f'<span class=off>{lab}</span>' if off
                                  else f'<a href="/?tank={tid}{qs}&per={per}{ps}&p={n}">{lab}</a>')
        pager = (f'<div class=pager>{pg(pageno - 1, t("prev"), pageno <= 1)}'
                 f'<span class=pgcur>{t("page")} {pageno} / {npages}</span>'
                 f'{pg(pageno + 1, t("next"), pageno >= npages)}</div>')
    else:
        pager = ""
    persel = (f'<div class=per>{t("per_page")} ' + "".join(
        f'<a href="/?tank={tid}{qs}&per={n}&perSet=1"{" class=on" if n == per else ""}>{n}</a>'
        for n in (6, 12, 24))
        + ("" if per in (6, 12, 24) else f'<span class=pgcur>{t("auto")}: {per}</span>') + '</div>')
    langsw = " ".join(
        f'<a href="/?tank={tid}{qs}&per={per}{ps}&p={pageno}&lang={code}"'
        f'{" class=on" if code == lang else ""}>{code.upper()}</a>'
        for code in ("nl", "en"))
    if msg and lang == "en":
        msg = MSG_EN.get(msg, msg)
    msg_html = f'<div id=banner class=banner>{html.escape(msg)}</div>' if msg else ""

    fmt = lambda v, d=2: ("%%.%df" % d) % v if v is not None else "-"
    insp = c.execute(
        "SELECT id,datum,gh,kh,temp,ph,no2,no3,po4,co2,opmerking,foto FROM inspecties "
        "WHERE tank_id=? ORDER BY datum DESC,id DESC LIMIT 30", (tid,)).fetchall()
    insp_html = [f"<table><tr><th>{t('date')}</th><th>GH</th><th>KH</th><th>Temp</th><th>pH</th>"
                 f"<th>NO₂</th><th>NO₃</th><th>PO₄</th><th>CO₂</th>"
                 f"<th>{t('remark')}</th><th>{t('photo')}</th><th></th></tr>"]
    for iid, datum, gh, kh, temp, ph, no2, no3, po4, co2, opm, foto in insp:
        f = (f'<a href="/photos/{html.escape(foto)}" target=_blank>'
             f'<img class=thumb src="/photos/{html.escape(foto)}" alt=""></a>') if foto else ""
        insp_html.append(tpl_insp.format(
            id=iid, tid=tid, soort=soort, datum=html.escape(datum or "-"),
            gh=fmt(gh, 1), kh=fmt(kh, 1), temp=fmt(temp, 1),
            ph=fmt(ph), no2=fmt(no2), no3=fmt(no3), po4=fmt(po4),
            co2=html.escape(co2 or "-"),
            opm=html.escape(opm or ""), foto=f))
    insp_html.append("</table>")
    if len(insp) == 30:
        insp_html.append(f"<small style=color:#9ab>{t('last30')}</small>")

    taken = c.execute(
        "SELECT id,titel,interval_dagen,laatst_gedaan FROM taken WHERE tank_id=? ORDER BY id",
        (tid,)).fetchall()
    taken_html = []
    for kid, titel, interval, laatst in taken:
        od = overdue(laatst, interval)
        if od is True:
            pill = (f'<span class="pill late">{t("late")}</span>' if laatst
                    else f'<span class="pill late">{t("never")}</span>')
        else:
            rest = interval - (date.today() - date.fromisoformat(laatst)).days if laatst else interval
            pill = f'<span class="pill ok">{t("left").format(n=rest)}</span>'
        taken_html.append(
            f'<div class=taak><span class=t>{html.escape(titel)}</span>'
            f'<small>{t("every_last").format(n=interval, last=html.escape(laatst or t("never_done")))}</small>'
            f'{pill}'
            f'<form method=post action=/taak_done><input type=hidden name=id value={kid}>'
            f'<input type=hidden name=soort value={soort}><button>{t("done")}</button></form>'
            f'<form method=post action=/del_taak onsubmit="return confirm(\'{t("confirm_del")}\')">'
            f'<input type=hidden name=id value={kid}><input type=hidden name=tank_id value={tid}>'
            f'<input type=hidden name=soort value={soort}>'
            f'<button class=danger>&times;</button></form></div>')
    if not taken_html:
        taken_html.append(f"<small style=color:#9ab>{t('no_tasks')}</small>")

    # ponytail: geen str.format (CSS-braces) — vervang vaste placeholders; content kan geen @@..@@ zijn
    out = tpl_page
    for k, v in (("@@NAAM@@", html.escape(tnaam)),
                 ("@@COUNT@@", f"{totaal} {t('fish_lc' if soort == 'vis' else 'plant_lc')}, "
                               f"{len(insp)} {t('measurements')}"),
                 ("@@LANGSW@@", langsw),
                 ("@@TABS@@", tabs),
                 ("@@SECTABS@@", sectabs),
                 ("@@SECTNAAM@@", t("fish" if soort == "vis" else "plants")),
                 ("@@SOORT@@", soort),
                 ("@@PLAATS@@", t("places_fish" if soort == "vis" else "places_plant")),
                 ("@@TID@@", str(tid)),
                 ("@@TANKCHECKS@@", checks({tid})),
                 ("@@DATUM@@", date.today().isoformat()),
                 ("@@CARDS@@", cards_html),
                 ("@@PERSEL@@", persel),
                 ("@@PAGER@@", pager),
                 ("@@MSG@@", msg_html),
                 ("@@INSP@@", "\n".join(insp_html)),
                 ("@@TAKEN@@", "\n".join(taken_html))):
        out = out.replace(k, v)
    return out


def save_photo(field):
    if not field.file or not field.filename:
        return None
    ext = os.path.splitext(field.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"):
        ext = ".jpg"
    name = f"{int(time.time()*1000)}{ext}"
    with open(os.path.join(PHOTOS, name), "wb") as f:
        f.write(field.file.read())
    return name


def drop_photo(name):
    if name:
        try:
            os.remove(os.path.join(PHOTOS, name))
        except OSError:
            pass


# ponytail: plantinfo van flowgrow.de (aquariumplanten-database) + GBIF (verspreiding) — gratis, geen key, faalt stil (None)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}
FG = "https://www.flowgrow.de"


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)


def _get_text(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read().decode("utf-8", "replace")


def _best_slug(slugs, naam):
    qt = [t for t in re.split(r"[^a-z0-9]+", naam.lower()) if t]
    best = best_score = None
    for s in slugs:
        st = s.split("-")
        hit = sum(1 for t in qt if t in st)
        if hit and (best_score is None or (hit, hit - len(st)) > best_score):
            best, best_score = s, (hit, hit - len(st))
    return best


def _fg_slugs(naam):
    html_ = _get_text(f"{FG}/db/aquaticplants?{urlencode({'filter[fulltext]': naam})}")
    return re.findall(r'href="' + FG + r'/db/aquaticplants/([^"#?]+)"', html_)


def flowgrow_info(naam):
    try:
        slugs = _fg_slugs(naam) or _fg_slugs(re.split(r"[^A-Za-z0-9]+", naam.strip())[0])
        slug = _best_slug(sorted(set(slugs)), naam)
        if not slug:
            return None, None, None
        link = f"{FG}/db/aquaticplants/{slug}"
        page = _get_text(link)
        m = re.search(r'<meta property="og:image" content="([^"]+)"', page)
        return link, (m.group(1) if m else None), _plaats(page)
    except Exception:
        return None, None, None


AI = "https://aquainfo.nl"
AI_ZONE = {"upper": "boven", "middle": "midden", "bottom": "bodem",
           "all": "boven, midden, bodem"}
AI_ZONE_ORDER = ["boven", "midden", "bodem"]


def _ai_zone(page):
    tokens = [t for z in re.findall(r'/zone/([a-z\-]+)/?"', page)
              for t in re.split(r"[^a-z]+", z.lower())]
    got = set()
    for t in tokens:
        got.update(AI_ZONE.get(t, "").split(", "))
    return ", ".join(p for p in AI_ZONE_ORDER if p in got) or None


def _ai_search(naam, base, pref):
    return re.findall(r'href="' + AI + r'/' + pref + r'/([a-z0-9\-]+)/?"',
                      _get_text(base + "?" + urlencode({"s": naam})))


def _page_info(page):
    """(naam, foto, plaats, land) uit een pagina — JSON-LD (schema.org) + og:image + zone."""
    naam = foto = land = None
    graph = []
    for m in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            o = json.loads(m)
        except ValueError:
            continue
        graph += o.get("@graph", []) if isinstance(o, dict) else o
    landen, places = [], []
    for it in graph:
        t = it.get("@type")
        if t == "ImageObject" and not foto:
            foto = it.get("url") or it.get("contentUrl")
        elif t == "Country":
            landen.append(it.get("name"))
        elif t == "Place":
            places.append(it.get("name"))
        elif t == "Taxon" and not naam and " " in (it.get("name") or ""):
            naam = it.get("name")
    land = ", ".join(dict.fromkeys(x for x in (landen or places) if x)) or None
    if not foto:
        mm = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', page)
        foto = mm.group(1) if mm else None
    if not naam:
        mm = (re.search(r'<h1[^>]*>([^<]+)</h1>', page)
              or re.search(r"<title>([^<]+)</title>", page))
        naam = html.unescape(mm.group(1)).strip() if mm else None
    if naam:
        naam = re.split(r"\s*[|–—]\s*|- ", naam, 1)[0].strip() or naam
    return naam, foto, _ai_zone(page), land


def fish_info(naam):
    try:
        slug = pref = None
        kort = re.split(r"[^A-Za-z0-9]+", naam.strip())[0]
        for base, p in ((f"{AI}/en/", "en/article"), (f"{AI}/", "artikel")):
            slugs = _ai_search(naam, base, p) or _ai_search(kort, base, p)
            found = _best_slug(sorted(set(slugs)), naam)
            if found:
                slug, pref = found, p
                break
        if not slug:
            return None, None, None, None
        link = f"{AI}/{pref}/{slug}/"
        _, foto, plaats, land = _page_info(_get_text(link))
        return link, foto, plaats, land
    except Exception:
        return None, None, None, None


def url_info(url):
    """Info uit een geplakte link (bv. aquainfo-artikel): (naam, foto, plaats, land)."""
    try:
        if not re.match(r"^https?://", url):
            return None, None, None, None
        return _page_info(_get_text(url))
    except Exception:
        return None, None, None, None


def _plaats(page):
    nl = {"Background": "achtergrond", "Midground": "midden", "Foreground": "voorgrond"}
    usages = re.findall(r'title="Usage: (Background|Midground|Foreground)[^"]*"', page)
    if usages:
        return ", ".join(dict.fromkeys(nl[u] for u in usages))
    m = re.search(r"<strong>Height:</strong>[^0-9]*([0-9]+)(?:\s*-\s*([0-9]+))?", page)
    if m:
        h = int(m.group(2) or m.group(1))
        return "voorgrond" if h <= 15 else ("midden" if h <= 40 else "achtergrond")
    return None


def gbif_land(naam):
    try:
        m = _get_json("https://api.gbif.org/v1/species/match?name=" + quote(naam))
        key = m.get("acceptedUsageKey") or m.get("usageKey")
        if not key:
            return None
        d = _get_json(f"https://api.gbif.org/v1/species/{key}/distributions?limit=40")
        landen = []
        for r in d.get("results", []):
            c = r.get("locality") or r.get("country")
            if c and 3 < len(c) <= 40 and c != "Global" and c not in landen:
                landen.append(c)
        return ", ".join(landen[:6]) or None
    except Exception:
        return None


def fetch_photo(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"):
            ext = ".jpg"
        name = f"auto_{int(time.time()*1000)}{ext}"
        with open(os.path.join(PHOTOS, name), "wb") as f:
            f.write(data)
        return name
    except Exception:
        return None


def lookup_photo(g):
    lf = os.path.basename(g("lookup_foto"))
    return lf if lf and os.path.isfile(os.path.join(PHOTOS, lf)) else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _lang(self):
        v = (parse_qs(urlparse(self.path).query).get("lang") or [""])[0]
        if v in T:
            return v, True
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, val = part.strip().partition("=")
            if k == "lang" and val in T:
                return val, False
        return "nl", False

    def _redirect(self, tank=None, soort=None, msg=None):
        q = []
        if tank:
            q.append(f"tank={tank}")
        if soort == "vis":
            q.append("soort=vis")
        if msg:
            q.append("msg=" + quote(msg))
        self.send_response(303)
        self.send_header("Location", "/?" + "&".join(q) if q else "/")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path in ("/manifest.json", "/icon.png"):
            fp = os.path.join(HERE, path.lstrip("/"))
            if os.path.isfile(fp):
                self.send_response(200)
                self.send_header("Content-Type",
                                 "application/manifest+json" if path.endswith("json") else "image/png")
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
                return
        if path.startswith("/photos/"):
            fp = os.path.join(PHOTOS, os.path.basename(path))
            if os.path.isfile(fp):
                self.send_response(200)
                self.send_header("Content-Type", "image/*")
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
                return
        q = parse_qs(u.query)
        if path == "/lookup":
            naam = (q.get("naam", [""])[0]).strip()
            url = (q.get("url", [""])[0]).strip()
            link = land = foto = plaats = nm = None
            img = None
            if url:
                link = url
                nm, img, plaats, land = url_info(url)
                foto = fetch_photo(img) if img else None
            elif naam:
                if (q.get("soort", [""])[0]).strip() == "vis":
                    link, img, plaats, land = fish_info(naam)
                    if not link:
                        link, img, plaats = flowgrow_info(naam)
                        land = land or gbif_land(naam)
                else:
                    link, img, plaats = flowgrow_info(naam)
                    land = gbif_land(naam)
                    if not link:
                        link, img, plaats, land = fish_info(naam)
                foto = fetch_photo(img) if img else None
            body = json.dumps({"link": link, "land": land, "foto": foto,
                               "plaats": plaats, "naam": nm}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        c = db()
        try:
            tank = int(q.get("tank", ["0"])[0])
            if not c.execute("SELECT 1 FROM aquaria WHERE id=?", (tank,)).fetchone():
                tank = c.execute("SELECT id FROM aquaria ORDER BY id LIMIT 1").fetchone()[0]
        except (ValueError, TypeError):
            tank = c.execute("SELECT id FROM aquaria ORDER BY id LIMIT 1").fetchone()[0]
        try:
            pageno = int(q.get("p", ["1"])[0])
        except (ValueError, TypeError):
            pageno = 1
        try:
            per = int(q.get("per", [str(PER_PAGE)])[0])
        except (ValueError, TypeError):
            per = PER_PAGE
        lang, lang_nieuw = self._lang()
        body = page(c, tank, q.get("soort", ["plant"])[0], q.get("msg", [""])[0],
                    pageno, per, "perSet" in q, lang).encode()
        c.close()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if lang_nieuw:
            self.send_header("Set-Cookie",
                             f"lang={lang}; Path=/; Max-Age=31536000; SameSite=Lax")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        ctype = self.headers.get("Content-Type", "")
        if not ctype:
            return self._redirect()
        env = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype,
               "CONTENT_LENGTH": self.headers.get("Content-Length", "0")}
        form = cgi.FieldStorage(fp=self.rfile, environ=env, keep_blank_values=True)
        c = db()
        path = urlparse(self.path).path
        g = lambda k: (form.getvalue(k) or "").strip()

        if path == "/add":
            naam = g("naam")
            tids = [t for t in form.getlist("tank_id") if t] or ["1"]
            if naam:
                own = save_photo(form["foto"]) if "foto" in form else None
                net = lookup_photo(g) if g("use_lookup") == "1" else None
                foto = net or own
                if net and own:
                    drop_photo(own)
                c.execute("INSERT INTO plants(naam,link,plaats,land,van_wie,foto,soort) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (naam, g("link"), g("plaats"), g("land"), g("van_wie"), foto,
                           g("soort") or "plant"))
                pid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                c.executemany("INSERT INTO plant_tanks(plant_id,tank_id) VALUES(?,?)",
                              [(pid, t) for t in tids])
                c.commit()
            return c.close() or self._redirect(tids[0], g("soort"),
                                               "Toegevoegd" if naam else None)
        if path == "/edit":
            pid = g("id")
            own = save_photo(form["foto"]) if "foto" in form else None
            net = lookup_photo(g) if g("use_lookup") == "1" else None
            old = c.execute("SELECT foto FROM plants WHERE id=?", (pid,)).fetchone()
            old_foto = old and old[0]
            foto = net or own or old_foto
            c.execute("UPDATE plants SET naam=?,link=?,plaats=?,land=?,van_wie=?,foto=? WHERE id=?",
                      (g("naam"), g("link"), g("plaats"), g("land"), g("van_wie"), foto, pid))
            tids = [t for t in form.getlist("tank_id") if t]
            if tids:
                c.execute("DELETE FROM plant_tanks WHERE plant_id=?", (pid,))
                c.executemany("INSERT INTO plant_tanks(plant_id,tank_id) VALUES(?,?)",
                              [(pid, t) for t in tids])
            c.commit()
            if own and own != foto:
                drop_photo(own)
            if old_foto != foto:
                drop_photo(old_foto)
            if not tids:
                tids = [r[0] for r in c.execute(
                    "SELECT tank_id FROM plant_tanks WHERE plant_id=? ORDER BY tank_id", (pid,))]
            return c.close() or self._redirect(tids[0] if tids else None, g("soort"),
                                               "Opgeslagen")
        if path == "/del":
            pid = g("id")
            old = c.execute("SELECT foto,soort FROM plants WHERE id=?", (pid,)).fetchone()
            tank = c.execute("SELECT tank_id FROM plant_tanks WHERE plant_id=? "
                             "ORDER BY tank_id LIMIT 1", (pid,)).fetchone()
            c.execute("DELETE FROM plants WHERE id=?", (pid,))
            c.execute("DELETE FROM plant_tanks WHERE plant_id=?", (pid,))
            c.commit()
            if old and old[0]:
                drop_photo(old[0])
            return c.close() or self._redirect(tank and tank[0], old and old[1], "Verwijderd")
        if path == "/add_tank":
            if g("naam"):
                c.execute("INSERT INTO aquaria(naam) VALUES(?)", (g("naam"),))
                c.commit()
                new = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                return c.close() or self._redirect(new, g("soort"), "Aquarium toegevoegd")
            return c.close() or self._redirect(None, g("soort"))
        if path == "/add_inspectie":
            tid = g("tank_id") or "1"
            co2 = g("co2") if g("co2") in ("ja", "nee") else None
            c.execute("INSERT INTO inspecties(tank_id,datum,gh,kh,temp,ph,no2,no3,po4,co2,opmerking,foto) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (tid, g("datum") or date.today().isoformat(),
                       num(g("gh")), num(g("kh")),
                       num(g("temp")), num(g("ph")), num(g("no2")), num(g("no3")), num(g("po4")),
                       co2, g("opmerking"),
                       save_photo(form["foto"]) if "foto" in form else None))
            c.commit()
            return c.close() or self._redirect(tid, g("soort"), "Inspectie gelogd")
        if path == "/del_insp":
            iid = g("id")
            f = c.execute("SELECT foto FROM inspecties WHERE id=?", (iid,)).fetchone()
            c.execute("DELETE FROM inspecties WHERE id=?", (iid,))
            c.commit()
            if f and f[0]:
                drop_photo(f[0])
            return c.close() or self._redirect(g("tank_id") or None, g("soort"), "Meting verwijderd")
        if path == "/add_taak":
            tid = g("tank_id") or "1"
            interval = num(g("interval_dagen"))
            if g("titel") and interval and interval > 0:
                c.execute("INSERT INTO taken(tank_id,titel,interval_dagen,laatst_gedaan) "
                          "VALUES(?,?,?,NULL)", (tid, g("titel"), int(interval)))
                c.commit()
                tnaam = (c.execute("SELECT naam FROM aquaria WHERE id=?", (tid,)).fetchone() or ["?"])[0]
                notify(f"{g('titel')} (elke {int(interval)}d) — {tnaam}", "Taak toegevoegd")
            return c.close() or self._redirect(tid, g("soort"), "Taak toegevoegd")
        if path == "/taak_done":
            kid = g("id")
            row = c.execute("SELECT tank_id,titel FROM taken WHERE id=?", (kid,)).fetchone()
            c.execute("UPDATE taken SET laatst_gedaan=? WHERE id=?",
                      (date.today().isoformat(), kid))
            c.commit()
            if row:
                notify(f"{row[1]} afgevinkt", "Taak gedaan")
            return c.close() or self._redirect(row and row[0], g("soort"), "Taak afgevinkt")
        if path == "/del_taak":
            kid = g("id")
            c.execute("DELETE FROM taken WHERE id=?", (kid,))
            c.commit()
            return c.close() or self._redirect(g("tank_id") or None, g("soort"), "Taak verwijderd")
        c.close()
        self._redirect(None, g("soort"))


if __name__ == "__main__":
    db().close()
    threading.Thread(target=taken_watch, daemon=True).start()
    url = f"http://localhost:{PORT}"
    print(f"Planten op {url}", flush=True)
    print(f"Data in {DATA}", flush=True)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            url = f"http://{ip}:{PORT}"
            print(f"Vanaf je gsm of laptop: {url}", flush=True)
    except OSError:
        pass
    if getattr(sys, "frozen", False) or os.name == "nt":
        import webbrowser
        webbrowser.open(url)
    try:
        HTTPServer(("0.0.0.0", PORT), H).serve_forever()
    except OSError as e:
        print(f"Poort {PORT} niet beschikbaar ({e.strerror}) — draait de app al?", flush=True)
