# Jinhua47 Snídaně

Společná ranní objednávka snídaně z [金華47](https://iding.tw/store/af0f1c4c).
Zatím jen testovací základ: stránka pozdraví přihlášeného uživatele Home Assistantu
a tlačítkem pošle testovací oznámení na telefon.

## Nastavení

| Volba | Popis |
| --- | --- |
| `notify_service` | Notify služba telefonu, např. `notify.mobile_app_davids_iphone`. Seznam je v **Nástroje pro vývojáře → Akce** (hledej `notify.mobile_app`). Když je volba prázdná nebo špatná, stránka po stisku tlačítka vypíše dostupné telefony. |
| `show_in_sidebar` | Zobrazí doplněk v postranním panelu jako „Snídaně“. Projeví se po restartu doplňku a přepíše ruční přepínač na kartě Informace. |

Uživatele doplněk pozná sám: Home Assistant mu přes Ingress předává, kdo je přihlášený.

## Lokální vývoj

```sh
./run.sh                    # http://localhost:8099, uživatel David
open "http://localhost:8099/?as=Jana"   # jiný uživatel
./run.sh --host 0.0.0.0     # přístup z telefonu na stejné wifi
```

V dev režimu se oznámení jen vypíše do terminálu.

## Test v Home Assistantu bez pushe

Zkopíruj složku `jinhua47_breakfast` do `/addons/` na HA (doplněk Samba nebo SSH),
v obchodě s doplňky dej **⋮ → Zkontrolovat aktualizace** a doplněk se objeví v sekci
**Local add-ons**. Po změně kódu stačí **Znovu sestavit**.
