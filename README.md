# Aquariumplanten

Eenvoudige database voor aquariumplanten, vissen, inspecties, taken en foto's.
Eén bestand, alleen de Python-standaardbibliotheek, data in SQLite. Geen account,
geen cloud: alles blijft op je eigen machine. Interface in het Nederlands en Engels.

## Snel starten

### Docker (kant-en-klaar image)

```bash
mkdir -p data
docker compose pull
docker compose up -d --no-build
```

Daarna: <http://ip-van-de-server:8377>

Je data staat in `data/` (`plants.db` + `photos/`) — die map is meteen je backup.
Bijwerken: `docker compose pull && docker compose up -d --no-build`.

### Docker (zelf bouwen)

```bash
mkdir -p data
docker compose up -d --build
```

### Windows

`Aquarium.exe` dubbelklikken (zit in de exe-zip). Zie `instructies.txt`.
Zelf een exe maken op Windows: `build_exe.bat`.

### Linux / Raspberry Pi / NAS

```bash
python3 plants.py
```

Er is niets te installeren; alleen Python 3.12 of lager (het gebruikt de
`cgi`-module, die in Python 3.13 verdwenen is).

## Configuratie

| Wat | Hoe |
|---|---|
| Poort | 8377 (aanpassen: publish-regel in `docker-compose.yml`) |
| Taal | rechtsboven in de app, of `?lang=en`; keuze wordt een jaar onthouden |
| Tijdzone | `TZ` in `docker-compose.yml` (bepaalt o.a. de ochtendmelding) |
| Meldingen | `notify.json` in de datamap (naast `plants.db`), zie hieronder |

### Meldingen (optioneel)

Zonder configuratie werkt alles behalve pushberichten. Zet een `notify.json`
in de datamap met een Home Assistant- of ntfy-kanaal:

```json
{
  "ntfy": { "server": "https://ntfy.sh", "topic": "kies-een-eigen-onderwerp" }
}
```

of met Home Assistant:

```json
{
  "ha": {
    "url": "http://192.168.1.10:8123",
    "token": "LONG-LIVED-TOKEN",
    "services": ["mobile_app_jouw_toestel"]
  }
}
```

`homeassistant.local` werkt niet in een Docker-container (geen mDNS): gebruik
het IP-adres of `extra_hosts` in `docker-compose.yml`. Zet `chmod 600` op het
bestand: er staat een token in.

## Data en backup

- `plants.db` — alle planten, vissen, aquaria, taken en inspecties
- `photos/` — geüploade foto's
- Backup = die twee kopiëren (Docker: de hele `data/`-map)

## Ontwikkelen

- Geen dependencies, geen build-stap: `python3 plants.py`
- `AGENTS.md` bevat interne notities (architectuur, valkuilen, netwerkdetails) —
  niet publiceren als de repo ooit openbaar wordt
- De container-image wordt door GitHub Actions gebouwd en naar
  `ghcr.io/juant07/aquarium` gepusht (`.github/workflows/docker.yml`)
