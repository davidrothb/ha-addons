# WSJJSC Tracker

Každých 10 minut během otevírací doby (6:00–22:00, čas Asia/Taipei) stáhne z
<https://wsjjsc.com.tw/> počet lidí v posilovně, připíše ho do CSV a pošle do
Home Assistantu jako senzory. Každý den po 22:00 překreslí týdenní graf.

## Senzory

| Entita | Stav | Atributy |
| --- | --- | --- |
| `binary_sensor.wsjjsc_gym_open` | otevřeno / zavřeno | `opens`, `closes` |
| `sensor.wsjjsc_gym_occupancy` | počet lidí (mimo otevírací dobu 0) | `capacity`, `last_sample` |
| `sensor.wsjjsc_gym_occupancy_percent` | obsazenost v % kapacity | `last_sample` |
| `sensor.wsjjsc_gym_typical` | průměr pro dnešní den v týdnu a aktuální čas, z předchozích týdnů | `difference`: teď minus obvykle |
| `sensor.wsjjsc_gym_quietest_time` | kdy je podle historie nejvolněji, třeba `14:20` | `day` (`dnes` / po zavírací době `zítra`), `expected` |

Nejvolnější čas se hledá jen mezi 6:10 a 21:00, aby zbyla aspoň hodina na
trénink. Obsazenost a procenta mají `state_class: measurement`, takže je HA
ukládá i do dlouhodobých statistik (karta *Statistics graph*).

Senzory se posílají přes REST API, takže nemají `unique_id` a nedají se
upravovat v UI. Po restartu Home Assistantu se do 5 minut znovu objeví.

## Graf na dashboardu

Graf se ukládá do `/config/www/wsjjsc_tracker/gym_occupancy.png` a po prvním
spuštění add-onu se vytvoří hned. Pokud složka `www` předtím neexistovala,
restartuj jednou Home Assistant, jinak adresa `/local/` nebude fungovat.

**Jako kamera (obnovuje se sama):** Nastavení → Zařízení a služby → Přidat
integraci → *Local File*, cesta `/config/www/wsjjsc_tracker/gym_occupancy.png`.
Na dashboard pak dej kartu *Picture entity* s entitou `camera.…`.

**Jako obrázek:**

```yaml
type: picture
image: /local/wsjjsc_tracker/gym_occupancy.png
```

Prohlížeč si ho ale může nechat v cache, takže kamera je spolehlivější.

Příklad karty se senzory:

```yaml
type: entities
title: Posilovna
entities:
  - binary_sensor.wsjjsc_gym_open
  - sensor.wsjjsc_gym_occupancy
  - sensor.wsjjsc_gym_occupancy_percent
  - sensor.wsjjsc_gym_typical
  - sensor.wsjjsc_gym_quietest_time
```

## Data

CSV je v `/share/wsjjsc_tracker/gym_occupancy.csv` (ve Sambě složka `share`):

```csv
timestamp,count,capacity
2026-11-09T09:40:07+08:00,77,160
```

Když se počítadlo na stránce nenajde, uloží se stránka do
`/share/wsjjsc_tracker/last_failed_page.html`.

## Lokálně

```sh
./run.sh                 # průběžný sběr do data/gym_occupancy.csv
python3 poll.py --once   # jeden vzorek hned

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python plot.py # graf do data/gym_occupancy.png
```

Pro graf z dat z Home Assistantu: `plot.py --csv cesta/k/gym_occupancy.csv`.

## Soubory

- `poll.py` – sběr dat, hlavní smyčka add-onu
- `ha.py` – výpočet a odeslání senzorů do Home Assistantu
- `history.py` – otevírací doba a čtení CSV (sdílí ho graf i senzory)
- `plot.py` – graf obsazenosti podle dnů v týdnu
- `data/` – lokálně nasbíraná data a vygenerovaný graf
