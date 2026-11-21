# Changelog

## 1.1.0

- Senzory v Home Assistantu: obsazenost (počet a %), obvyklá obsazenost touto dobou, nejvolnější čas a otevřeno/zavřeno.
- Týdenní graf se každý den po zavírací době vygeneruje do `/config/www/wsjjsc_tracker/gym_occupancy.png`.
- Image je teď založený na Debianu (kvůli matplotlibu); armv7 už není podporované.

## 1.0.1

- Když se počítadlo nenajde, log ukáže HTTP status, URL a titulek stránky a stránka se uloží do `last_failed_page.html` vedle CSV.

## 1.0.0

- První verze: zápis obsazenosti posilovny každých 10 minut (6:00–22:00, čas Taipei).
