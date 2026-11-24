# Jinhua47 Snídaně

Společná ranní objednávka snídaně z [金華47](https://iding.tw/store/af0f1c4c).
Každý den objednávání zahajuje správce tlačítkem **Zahájit objednávání** (o půlnoci se zase zavře).
Strávníci s telefonem pak dostanou oznámení „Ahoj <přezdívka>, <hláška z denních oznámení>“ a „Klikni zde a objednej.“
Do té doby ostatní vidí jen hlášku, že objednávky nejsou otevřené. Tlačítkem **Uzavřít objednávání**
jde objednávání kdykoliv zase zavřít.
Zatím testovací základ: stránka pozdraví přihlášeného uživatele Home Assistantu a strávník si
vybere snídani: set, pití, teplotu (studené 冰 / teplé 溫) a velikost (malé 中 / velké 大) s cenou.
Menu se načítá z idingu. Nad sety je „Jako včera“ (poslední výběr z dřívějšího dne na jedno klepnutí) a sekce Oblíbené. Výběr se tlačítkem **Vybrat** uloží v doplňku (jen na dnešek) a lišta nahoře
ukazuje všem, kdo už má vybráno a kdo ne. Dokud správce objednávku neuzavře, jde výběr změnit
nebo tlačítkem **Začít znovu** smazat.

Správce vidí kartu **Dnešní objednávka** se všemi výběry a cenou. Tlačítkem **Schválit a poslat do košíku**
výběry zamkne a doplněk je nahraje do košíku na účtu iding (košík tím **přepíše**). Kdo nevybral, vynechá se.
Cenu pak spočítá i iding a doplněk ji porovná se svou. Tlačítkem **Znovu otevřít výběr** jde zámek zrušit.

Po schválení správce vybere čas vyzvednutí a dá **Objednat a zaplatit**. Doplněk objednávku odešle
jen tehdy, když košík na idingu sedí se schválenou objednávkou (počet kusů a cena). Správci, který
objednal, přijde oznámení s odkazem do LINE Pay. Po schválení platby v LINE dá na stránce
**Zaplatil jsem – dokončit** a doplněk platbu na idingu dokončí. Pak každou minutu hlídá stav objednávky
a když ji obchod označí jako připravenou, pošle správci oznámení. Oznámení o průběhu dostává jen
správce, který objednal; ostatní vidí stav v liště nahoře. Nezaplacenou objednávku jde zrušit.

## Nastavení

V konfiguraci doplňku je jediná volba:

| Volba | Popis |
| --- | --- |
| `admins` | Uživatelská jména správců doplňku (přihlašovací jméno v HA, funguje i zobrazované jméno). Prázdné = všichni administrátoři HA. Jméno, které neodpovídá žádnému uživateli, doplněk vypíše do logu. |

Do postranního panelu se doplněk přidá přepínačem **Zobrazit v postranním panelu** na kartě Informace.
Panel vidí všichni uživatelé Home Assistantu, i ti, kteří nejsou administrátoři.

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
- **Testovací režim:** ostatní uvidí jen hlášku „Testovací režim“ a nemůžou vybírat; denní oznámení
  dostanou jen správci. Správci vidí všechno a nahoře červený pruh.
- **Oznámení správci:** když je zapnuté, správce dostane oznámení, jakmile mají vybráno všichni ostatní
  a chybí jen on, a pak když mají vybráno všichni a čeká se na schválení. Správce musí být mezi
  strávníky a mít přiřazený telefon.
- **Hlavní stránka:** hlášky pod pozdravem, každý den jiná pro každého.
- **Lišta nahoře:** hlášky pro strávníky, kteří už mají vybráno, a pro ty, kteří ještě ne.
  V liště je u každého emoji (👍 / 😠 a podobně), jméno a jedna z hlášek. Žádní dva nemají stejnou
  a nikdo nemá stejnou jako včera (pokud je hlášek aspoň tolik jako strávníků).
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
Výběr snídaně vidí jen strávníci, takže si v nastavení nejdřív přidej sám sebe. Menu se načítá
ze skutečného idingu. Pozor: i v dev režimu pracuje doplněk se skutečným účtem iding z nastavení:
schválení plní skutečný košík a **Objednat a zaplatit** odešle skutečnou objednávku.

Které sety a nápoje stránka nabízí, oblíbené sety, české názvy a překlady popisů jsou v `menu.py`.

## Test v Home Assistantu bez pushe

Zkopíruj složku `jinhua47_breakfast` do `/addons/` na HA (doplněk Samba nebo SSH),
v obchodě s doplňky dej **⋮ → Zkontrolovat aktualizace** a doplněk se objeví v sekci
**Local add-ons**. Po změně kódu stačí **Znovu sestavit**.
