# Jinhua47 Snídaně

Společná ranní objednávka snídaně z [金華47](https://iding.tw/store/af0f1c4c).
Zatím jen testovací základ: stránka pozdraví přihlášeného uživatele Home Assistantu
a tlačítkem pošle testovací oznámení na telefon.

## Nastavení

| Volba | Popis |
| --- | --- |
| `iding_phone` | Telefonní číslo účtu na iding.tw. |
| `iding_password` | Heslo k účtu na iding.tw. Kdo se přihlašuje jen přes LINE, musí si v účtu nastavit heslo. |

Do postranního panelu se doplněk přidá přepínačem **Zobrazit v postranním panelu** na kartě Informace.

### Uživatelé a telefony

Uživatele doplněk pozná sám: Home Assistant mu přes Ingress předává, kdo je přihlášený.
Administrátoři Home Assistantu vidí na stránce doplňku sekci **Telefony uživatelů**, kde každému
uživateli vyberou jeho telefon z aplikace Companion. Na ten telefon pak chodí jeho oznámení.

## Lokální vývoj

```sh
./run.sh                    # http://localhost:8099, uživatel David (admin)
open "http://localhost:8099/?as=Jana"   # jiný uživatel
./run.sh --host 0.0.0.0     # přístup z telefonu na stejné wifi
```

V dev režimu jsou uživatelé (David – admin, Jana, Petr) i telefony vymyšlené, oznámení se jen
vypíše do terminálu a přiřazení telefonů se ukládá do `dev_data/settings.json`.

## Test v Home Assistantu bez pushe

Zkopíruj složku `jinhua47_breakfast` do `/addons/` na HA (doplněk Samba nebo SSH),
v obchodě s doplňky dej **⋮ → Zkontrolovat aktualizace** a doplněk se objeví v sekci
**Local add-ons**. Po změně kódu stačí **Znovu sestavit**.
