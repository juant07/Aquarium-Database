# Aquariumplanten

[Nederlands](#nederlands) · [English](#english)

---

## Nederlands

Eenvoudige database voor aquariumplanten, vissen, inspecties, taken en foto's.
Eén bestand, alleen de Python-standaardbibliotheek, data in SQLite. Geen account,
geen cloud: alles blijft op je eigen machine. Interface in het Nederlands en Engels.

Broncode: <https://github.com/juant07/Aquarium-Database>

> **Gemaakt met [Opencode](https://opencode.ai) (model Big Pickle)**, een
> AI-codingassistent. De code is in samenspraak met de eigenaar geschreven en
> getest op Linux, Windows (via Wine) en in Docker.

### Snel starten

#### Docker (kant-en-klaar image)

```bash
mkdir -p data
docker compose pull
docker compose up -d --no-build
```

Daarna: <http://ip-van-de-server:8377>

Je data staat in `data/` (`plants.db` + `photos/`) — die map is meteen je backup.
Bijwerken: `docker compose pull && docker compose up -d --no-build`.

#### Docker (zelf bouwen)

```bash
mkdir -p data
docker compose up -d --build
```

#### Windows

`Aquarium.exe` dubbelklikken (zit in de exe-zip). Zie `instructies.txt`.
Zelf een exe maken op Windows: `build_exe.bat`.

#### Linux / Raspberry Pi / NAS

```bash
python3 plants.py
```

Er is niets te installeren; alleen Python 3.12 of lager (het gebruikt de
`cgi`-module, die in Python 3.13 verdwenen is).

### Configuratie

| Wat | Hoe |
|---|---|
| Poort | 8377 (aanpassen: publish-regel in `docker-compose.yml`) |
| Taal | rechtsboven in de app, of `?lang=en`; keuze wordt een jaar onthouden |
| Tijdzone | `TZ` in `docker-compose.yml` (bepaalt o.a. de ochtendmelding) |
| Meldingen | `notify.json` in de datamap (naast `plants.db`), zie hieronder |

#### Meldingen (optioneel)

Zonder configuratie werkt alles behalve pushberichten. Zet een `notify.json`
in de datamap met een ntfy-kanaal:

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

### Data en backup

- `plants.db` — alle planten, vissen, aquaria, taken en inspecties
- `photos/` — geüploade foto's
- Backup = die twee kopiëren (Docker: de hele `data/`-map)

### Ontwikkelen

- Geen dependencies, geen build-stap: `python3 plants.py`
- `AGENTS.md` bevat interne notities en staat bewust niet in deze repo
- De container-image wordt door GitHub Actions gebouwd en naar
  `ghcr.io/juant07/aquarium` gepusht (`.github/workflows/docker.yml`)

---

## English

A small database for aquarium plants, fish, inspections, tasks and photos.
One file, Python standard library only, data in SQLite. No account, no cloud:
everything stays on your own machine. Interface available in Dutch and English.

Source: <https://github.com/juant07/Aquarium-Database>

> **Built with [Opencode](https://opencode.ai) (Big Pickle model)**, an
> AI coding assistant. The code was written in dialogue with the owner and
> tested on Linux, Windows (via Wine) and in Docker.

### Quick start

#### Docker (prebuilt image)

```bash
mkdir -p data
docker compose pull
docker compose up -d --no-build
```

Then open <http://server-ip:8377>

Your data lives in `data/` (`plants.db` + `photos/`) — that folder is your backup.
Updating: `docker compose pull && docker compose up -d --no-build`.

#### Docker (build it yourself)

```bash
mkdir -p data
docker compose up -d --build
```

#### Windows

Double-click `Aquarium.exe` (in the exe zip). See `instructies.txt` (Dutch).
To build the exe yourself on Windows, use `build_exe.bat`.

#### Linux / Raspberry Pi / NAS

```bash
python3 plants.py
```

Nothing to install, but use Python 3.12 or older (the app uses the `cgi`
module, which was removed in Python 3.13).

### Configuration

| Setting | How |
|---|---|
| Port | 8377 (change the publish line in `docker-compose.yml`) |
| Language | top right in the app, or `?lang=en`; remembered for a year |
| Time zone | `TZ` in `docker-compose.yml` (drives the morning digest) |
| Notifications | `notify.json` in the data folder (next to `plants.db`), see below |

#### Notifications (optional)

Everything works without configuration except push notifications. Drop a
`notify.json` in the data folder with an ntfy topic:

```json
{
  "ntfy": { "server": "https://ntfy.sh", "topic": "pick-your-own-topic" }
}
```

or with Home Assistant:

```json
{
  "ha": {
    "url": "http://192.168.1.10:8123",
    "token": "LONG-LIVED-TOKEN",
    "services": ["mobile_app_your_device"]
  }
}
```

`homeassistant.local` does not resolve inside a Docker container (no mDNS):
use the IP address or `extra_hosts` in `docker-compose.yml`. Run
`chmod 600` on the file — it contains a token.

### Data and backup

- `plants.db` — all plants, fish, tanks, tasks and inspections
- `photos/` — uploaded photos
- Backup = copy those two (Docker: the whole `data/` folder)

### Development

- No dependencies, no build step: `python3 plants.py`
- `AGENTS.md` holds internal notes and is intentionally not part of this repo
- The container image is built by GitHub Actions and pushed to
  `ghcr.io/juant07/aquarium` (`.github/workflows/docker.yml`)
