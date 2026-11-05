#!/usr/bin/env python3
"""Zelftest voor backup, grafieken, versie-check en soft-delete — run: python3 test_features.py"""
import json, os, re, sqlite3, tempfile, zipfile
from html.parser import HTMLParser

import plants

tmp = tempfile.mkdtemp()
plants.DATA = tmp
plants.DB = os.path.join(tmp, "plants.db")
plants.PHOTOS = os.path.join(tmp, "photos")
plants.SITES_CFG = os.path.join(tmp, "sites.json")
plants.NOTIFY_CFG = os.path.join(tmp, "notify.json")
plants.BACKUPS = os.path.join(tmp, "backups")
plants.UPDATE_CFG = os.path.join(tmp, ".latest_version")
os.makedirs(plants.PHOTOS)

# ---------- grafiek ----------
assert plants.svg_grafiek([None, 3.0, None]) == ""
assert plants.svg_grafiek([1.0, 2.0]).count('points="') == 1
assert len(plants.svg_grafiek([1.0, 2.0]).split('points="')[1].split('"')[0].split()) == 2
assert "nan" not in plants.svg_grafiek([5, 5, 5, 5]).lower()      # vlakke reeks
assert "nan" not in plants.svg_grafiek([1, None, 4, None, 2]).lower()

# ---------- versie-check (alleen cache) ----------
def zet_versie(tag):
    with open(plants.UPDATE_CFG, "w") as f:
        json.dump(["2026-11-05", tag], f)

zet_versie("v9.9.9")
assert plants.nieuwere_versie() == "9.9.9"
zet_versie("v" + plants.VERSION)
assert plants.nieuwere_versie() is None
zet_versie("v0.0.1")
assert plants.nieuwere_versie() is None
zet_versie(None)
assert plants.nieuwere_versie() is None
with open(plants.UPDATE_CFG, "w") as f:
    f.write("geen json")
assert plants.nieuwere_versie() is None

# ---------- backup-rotatie ----------
os.makedirs(plants.BACKUPS)
for i in range(1, 10):
    open(os.path.join(plants.BACKUPS, f"aquarium-2026110{i}.zip"), "w").close()
plants.ruim_backups_op(7)
namen = sorted(os.listdir(plants.BACKUPS))
assert len(namen) == 7 and namen[-1] == "aquarium-20261109.zip", namen

# ---------- backup-inhoud ----------
c = plants.db()
c.execute("INSERT INTO plants(naam,soort,foto) VALUES('Testplant','plant','x.jpg')")
c.commit()
c.close()
open(os.path.join(plants.PHOTOS, "x.jpg"), "wb").write(b"foto")
open(plants.SITES_CFG, "w").write('{"plant":["flowgrow"]}')
open(plants.NOTIFY_CFG, "w").write('{"ha":{"token":"GEHEIM"}}')
dest = os.path.join(tmp, "backup.zip")
plants.maak_backup(dest)
with zipfile.ZipFile(dest) as z:
    namen = z.namelist()
    assert "plants.db" in namen and "photos/x.jpg" in namen and "sites.json" in namen, namen
    assert not any("notify" in n for n in namen), namen
    z.extract("plants.db", os.path.join(tmp, "chk"))
c = sqlite3.connect(os.path.join(tmp, "chk", "plants.db"))
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert c.execute("SELECT count(*) FROM plants").fetchone()[0] == 1
c.close()
assert not any(n.startswith(".vacuum-") for n in os.listdir(tmp)), os.listdir(tmp)

# ---------- soft-delete purge ----------
c = plants.db()
c.execute("INSERT INTO plants(naam,soort,foto,verwijderd) VALUES('Oud','plant','oud.jpg','2026-01-01T10:00:00')")
c.execute("INSERT INTO plants(naam,soort,foto,verwijderd) VALUES('Nieuw','plant','nieuw.jpg',?)",
          (plants.datetime.now().isoformat(timespec="seconds"),))
c.commit()
c.close()
for n in ("oud.jpg", "nieuw.jpg"):
    open(os.path.join(plants.PHOTOS, n), "wb").write(b"x")
assert plants.ruim_verwijderd_op(30) == 1
c = plants.db()
namen = [r[0] for r in c.execute("SELECT naam FROM plants")]
c.close()
assert namen == ["Testplant", "Nieuw"], namen
assert not os.path.exists(os.path.join(plants.PHOTOS, "oud.jpg"))
assert os.path.exists(os.path.join(plants.PHOTOS, "nieuw.jpg"))

# ---------- pagina-HTML: geen kapotte attributen/tags (bug v1.1.0) ----------
c = plants.db()
c.execute("INSERT INTO aquaria(naam,liters,wissel_pct) VALUES('Testbak',150,25)")
tid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
c.execute("INSERT INTO plants(naam,soort) VALUES('Waterplant','plant')")
c.commit()
html_ = plants.page(c, tid, "plant")
c.close()
assert 'value="150"' in html_ and 'value="25"' in html_, "tankvelden niet gequote"
assert not re.search(r'value="[^"]*[<>]', html_), "value-attribuut loopt door in de tag"
assert 'name=liters_' in html_ and 'name=pct_' in html_


class Checker(HTMLParser):
    leeg = {"input", "br", "img", "meta", "link", "hr", "source"}

    def __init__(self):
        super().__init__()
        self.stack, self.fout = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.leeg:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag not in self.leeg:
            self.fout.append(f"</{tag}> sluit {self.stack[-2:]}")


chk = Checker()
chk.feed(html_)
assert not chk.fout, chk.fout[:5]
assert not chk.stack, chk.stack
assert '<details class=inst>' in html_ and html_.count("</details>") == 1

print("OK")
