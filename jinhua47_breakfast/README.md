# Jinhua47 Snídaně

Společná ranní objednávka snídaně z [金華47](https://iding.tw/store/af0f1c4c).
Zatím jen testovací základ: stránka pozdraví přihlášeného uživatele Home Assistantu
a tlačítkem pošle testovací oznámení na telefon.

## Nastavení

V konfiguraci doplňku je jediná volba:

| Volba | Popis |
| --- | --- |
| `admins` | Uživatelská jména správců doplňku (přihlašovací jméno v HA, funguje i zobrazované jméno). Prázdné = všichni administrátoři HA. Jméno, které neodpovídá žádnému uživateli, doplněk vypíše do logu. |

Do postranního panelu se doplněk přidá přepínačem **Zobrazit v postranním panelu** na kartě Informace.

### Nastavení na stránce doplňku

Uživatele doplněk pozná sám: Home Assistant mu přes Ingress předává ID a jméno přihlášeného uživatele.
Správci vidí v horní liště ozubené kolečko a pod ním nastavují:

- **Strávníci:** kdo se objednávek účastní. Přidávají se výběrem z uživatelů HA a ukládají se podle
  ID uživatele HA, ne podle jména, takže přejmenování propojení nerozbije. U každého telefon z aplikace
  Companion, seznam přezdívek (jedna na řádek, každý den se vybere jedna; bez přezdívky se použije
  jméno z HA) a tlačítko pro testovací oznámení. Odebráním se smaže i jeho telefon a přezdívky.
  Smazaný uživatel HA zůstane v seznamu označený, dokud ho správce neodebere.
- **Denní oznámení:** čas (prázdné = vypnuto) a hlášky. Každý s přiřazeným telefonem dostane každý den
  `Ahoj <přezdívka>, <hláška>`. Po restartu se oznámení pošle, jen pokud od nastaveného času
  neuběhla víc než hodina.
- **Hlavní stránka:** hlášky pod pozdravem, každý den jiná pro každého.
- **Účet iding:** telefon a heslo, tlačítko **Ověřit přihlášení**. Kdo se přihlašuje jen přes LINE,
  musí si v účtu nastavit heslo. Heslo se uloží do `/data/settings.json` doplňku (je i v zálohách HA)
  a stránka ho už nikdy nezobrazí.

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
