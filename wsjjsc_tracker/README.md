# WSJJSC Tracker

Každých 10 minut během otevírací doby (6:00–22:00, čas Asia/Taipei) stáhne z
<https://wsjjsc.com.tw/> počet lidí v posilovně a připíše řádek do CSV.

## Add-on v Home Assistantu

Data se ukládají do `/share/wsjjsc_tracker/gym_occupancy.csv`
(ve Sambě/File editoru složka `share`). Formát:

```csv
timestamp,count,capacity
2026-11-09T09:40:07+08:00,77,160
```

Add-on nemá žádné nastavení. Log je v záložce **Protokol**.

## Lokálně

```sh
./run.sh                 # průběžný sběr do data/gym_occupancy.csv
python3 poll.py --once   # jeden vzorek hned

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python plot.py # graf do data/gym_occupancy.png
```

Pro graf z dat z Home Assistantu: `plot.py --csv cesta/k/gym_occupancy.csv`.

## Soubory

- `poll.py` – sběr dat (jediný soubor, který jde do Docker image)
- `plot.py` – graf obsazenosti podle dnů v týdnu
- `data/` – lokálně nasbíraná data a vygenerovaný graf
