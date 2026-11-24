# ha-addons

Vlastní add-ony pro Home Assistant.

## Instalace

1. V Home Assistantu otevři **Nastavení → Doplňky → Obchod s doplňky**.
2. Vpravo nahoře **⋮ → Repozitáře** a přidej `https://github.com/davidrothb/ha-addons`.
3. Add-ony z tohoto repozitáře se objeví dole v seznamu.

## Add-ony

| Add-on | Popis |
| --- | --- |
| [Jinhua47 Snídaně](jinhua47_breakfast/) | Společná ranní objednávka snídaně z 金華47 (výběr setu s pitím, schválení správcem, objednávka na idingu a platba přes LINE Pay). |
| [WSJJSC Tracker](wsjjsc_tracker/) | Obsazenost posilovny Taipei Zhongzheng Sports Center jako senzory v HA, CSV historie a denní graf. |

## Nový add-on

Každý add-on má vlastní složku s `config.yaml`, `Dockerfile` a `README.md`.
Po každé změně zvyš `version` v `config.yaml`, jinak Home Assistant aktualizaci nenabídne.
