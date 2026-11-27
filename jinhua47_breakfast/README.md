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
- **Settle Up:** viz níže.

## Settle Up

Po zaplacení doplněk zapíše objednávku do skupiny v [Settle Up](https://settleup.io) jako útratu
„Snídaně 金華47 č. …“ v NT$ (TWD): platil správce, který objednal, a každý strávník mu dluží cenu svého
výběru (když iding účtuje jinak, rozpočítá se poměrně). Výsledek je vidět u objednávky v kartě
**Dnešní objednávka**; když zápis selže (třeba strávník bez přiřazeného člena), přijde objednavateli
oznámení a po opravě nastavení jde dát **Zapsat do Settle Up znovu**.

Settle Up pouští aplikace nejdřív jen na testovací server (sandbox), live klíč vydá až po otestování:

1. Zaregistruj aplikaci na [developers.settleup.io](https://developers.settleup.io/) a opiš si sandbox
   Web API klíč.
2. Na [sandboxu](https://settle-up-sandbox-app.web.app/) si založ účet **e-mailem a heslem** (doplněk
   se přihlašuje jen tak; Google přihlášení nejde), skupinu a členy, jako jsou strávníci.
3. V nastavení doplňku → Settle Up: prostředí **Sandbox**, klíč, e-mail, heslo,
   **Přihlásit a načíst skupiny**, vyber skupinu, přiřaď strávníky ke členům, zapni zápis a ulož.
4. Udělej objednávku (nebo víc) a zkontroluj na sandboxu útratu, dluhy a měnu.
5. Na developers.settleup.io požádej o live klíč. Po schválení vyplň prostředí **Live** (skutečný účet,
   pokud se přihlašuješ přes Google, požádej Settle Up o převod na e-mail a heslo), vyber skupinu,
   přiřaď členy a přepni prostředí na Live. Sandbox nastavení zůstane uložené.

Klíče a hesla jsou v `/data/settings.json` (i v zálohách HA), stránka je nikdy nezobrazí.
V dev režimu pracuje doplněk se skutečným Settle Up podle nastavení.

## Události pro automatizace

Při každé změně stavu dnešní objednávky doplněk vyšle v Home Assistantu událost, na kterou jde
navázat automatizace (spouštěč **Ruční událost** / `platform: event`):

| Událost | Kdy |
| --- | --- |
| `jinhua47_breakfast_ordered` | objednávka odeslaná na iding (ještě nezaplacená) |
| `jinhua47_breakfast_paid` | zaplaceno |
| `jinhua47_breakfast_ready` | obchod ji označil jako připravenou k vyzvednutí |
| `jinhua47_breakfast_closed` | vyřízená (vyzvednutá) |
| `jinhua47_breakfast_cancelled` | zrušená |

Data události: `stage`, `order_id`, `order_number`, `total` (NT$), `items` (počet setů),
`pickup_time` (`HH:MM`), `pickup` (`YYYY-MM-DD HH:MM`), `by` a `by_user_id` (kdo objednal).
Každá odeslaná událost je i v logu doplňku („Událost …“).

```yaml
automation:
  - alias: Snídaně zaplacená
    triggers:
      - trigger: event
        event_type: jinhua47_breakfast_paid
    actions:
      - action: notify.notify
        data:
          message: "Snídaně objednaná ({{ trigger.event.data.total }} NT$), vyzvednutí v {{ trigger.event.data.pickup_time }}."
```

Vyzkoušet jde i bez objednávky: Vývojářské nástroje → Události → odeslat např.
`jinhua47_breakfast_paid` s daty `{"total": 190, "pickup_time": "08:30"}`.

## Dashboard na TV

Doplněk udržuje entitu `sensor.jinhua47_breakfast` a při startu sám založí dashboard **Snídaně TV**
(`/snidane-tv`, v postranním panelu), určený k castování na Chromecast:

```yaml
action: cast.show_lovelace_view
data:
  entity_id: media_player.obyvak
  dashboard_path: snidane-tv
  view_path: stav
```

Stav entity: `idle` (objednávání nezačalo), `choosing` (vybírá se), `approved` (výběr uzavřený),
dál stav objednávky `ordered`, `awaiting_payment`, `paid`, `ready`, `closed`, `cancelled`. Atributy:
`emoji`, `headline`, `detail` (hotové texty k zobrazení), `picks` (`name`, `text`), `pending` (jména),
`chosen_count`, `member_count`, `groups` (`quantity`, `text`), `items`, `total`, `pickup_time`,
`order_number`, `ordered_by`, `earlier` (dřívější kola dne), `tip`, `steps`, `cancelled_at`. Entitu jde použít
i v automatizacích (např. `trigger: state` na `ready`).

Ukazatel postupu (Otevřeno → Vybráno → Objednáno → K vyzvednutí) je vlastní karta
`custom:jinhua47-progress-card` ([`progress-card.js`](progress-card.js)). Doplněk ji při startu
zaregistruje jako zdroj dashboardů (Nastavení → Dashboardy → ⋮ → Zdroje) se skriptem přímo v `data:`
URL a při změně v nové verzi ji aktualizuje. Data bere z atributů `steps` (`label`, `done`, `date`,
`time`) a `cancelled_at`.

Rozvržení dashboardu je v [`tv.py`](tv.py). Když se v nové verzi změní, doplněk dashboard přepíše.
Chceš-li ho upravit po svém, smaž v editoru kódu dashboardu řádek `jinhua47_breakfast_layout: …`:
pak už na něj doplněk nesáhne. Smazaný dashboard doplněk při dalším startu založí znovu.

## Fotky setů

U setů s vlastní fotkou se ukazuje náhled. Vlastní fotky nahraj v Home Assistantu do
`/addon_configs/<slug doplňku>/photos/` (přes Samba, File editor nebo Studio Code Server; přesná cesta
je v logu doplňku a seznam názvů souborů v `NAZVY.txt` tamtéž). Ukážou se do 10 minut bez nové verze
a na GitHub se nedostanou. Fotky v repozitáři patří do [`photos/`](photos/) (víc v
[`photos/README.md`](photos/README.md)). Set bez vlastní fotky je bez náhledu.

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

## TODO

- [ ] Hodnocení jídel hvězdičkami: každý strávník ohodnotí svou dnešní snídani.
- [ ] Celkové statistiky útraty (celkem i po lidech) s ekvivalentem útraty.
- [x] Dashboard v Home Assistantu.
- [x] Část dashboardu na Google Cast (zobrazení na Chromecastu nebo Nest Hubu).
- [ ] Volba přehrávače (entita Spotify) pro dashboard Snídaně TV v nastavení doplňku; teď je natvrdo v `tv.py`.
- [x] Integrace se Settle Up: po zaplacení zapsat útratu, kdo platil a kolik dluží ostatní.
