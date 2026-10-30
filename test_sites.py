#!/usr/bin/env python3
"""Zelftest voor de instelbare zoekbronnen (sites.json) — run: python3 test_sites.py"""
import json, os, tempfile, urllib.error

import plants

tmp = tempfile.mkdtemp()
plants.SITES_CFG = os.path.join(tmp, "sites.json")


def write(cfg):
    with open(plants.SITES_CFG, "w") as f:
        json.dump(cfg, f)


# geen bestand -> default
urls, order = plants.sites()
assert urls["flowgrow"] == "https://www.flowgrow.de", urls
assert order == {"plant": ["flowgrow", "aquainfo"], "vis": ["aquainfo", "flowgrow"]}, order

# eigen volgorde + URL (en trailing slash weg)
write({"plant": ["aquainfo"], "vis": ["flowgrow", "vis"], "urls": {"aquainfo": "https://example.org/"}})
urls, order = plants.sites()
assert order["plant"] == ["aquainfo"], order
assert order["vis"] == ["flowgrow"], order          # onbekende naam 'vis' eruit
assert urls["aquainfo"] == "https://example.org", urls
assert urls["flowgrow"] == "https://www.flowgrow.de", urls   # niet opgegeven -> default

# ongeldige URL in bestand wordt genegeerd
write({"urls": {"aquainfo": "ftp://nope", "flowgrow": None}})
urls, _ = plants.sites()
assert urls["aquainfo"] == "https://aquainfo.nl", urls

# lege lijsten -> default, kommagescheiden string ook ok
write({"plant": [], "vis": "flowgrow,aquainfo"})
_, order = plants.sites()
assert order["plant"] == ["flowgrow", "aquainfo"], order
assert order["vis"] == ["flowgrow", "aquainfo"], order

# foutmeldingen
assert plants._fout(urllib.error.HTTPError("u", 403, "Forbidden", {}, None)) == "HTTP 403"
assert plants._fout(urllib.error.URLError("Connection refused")) == "Connection refused"
assert plants._fout(TimeoutError()) == "TimeoutError"

# bron die faalt -> volgende bron + melding (zonder netwerk)
os.remove(plants.SITES_CFG)
called = []


def kapot(naam, url):
    called.append("flowgrow")
    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)


def goed(naam, url):
    called.append("aquainfo")
    return "https://x/y", "https://x/y.jpg", "midden", None


oud = dict(plants.BRONNEN)
plants.BRONNEN.update({"flowgrow": kapot, "aquainfo": goed})
plants.gbif_land = lambda naam: "Brazilië"
info, fouten = plants.lookup_bron("Testplant", "plant")
assert info[0] == "https://x/y" and info[3] == "Brazilië", info
assert fouten == [("Flowgrow", "HTTP 403")], fouten
assert called == ["flowgrow", "aquainfo"], called

# beide bronnen stuk -> geen info, twee meldingen
plants.BRONNEN["aquainfo"] = kapot
info, fouten = plants.lookup_bron("Testplant", "plant")
assert info is None and len(fouten) == 2, (info, fouten)
plants.BRONNEN.clear()
plants.BRONNEN.update(oud)

print("OK")
