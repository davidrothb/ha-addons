# Changelog

## 0.18.4

- Oznámení s odkazem na platbu otevře LINE i na Androidu: aplikace Home Assistant tam odkaz `line://`
  z oznámení neotevřela, teď dostane Android intent pro aplikaci LINE (`jp.naver.line.android`).
  iOS dostává odkaz `line://` beze změny.

## 0.18.3

- Pozvánky odejdou jen tehdy, když je správce v okně „Zahájit objednávání“ výslovně zvolí. Dřív je
  doplněk poslal i bez okna, když požadavek přišel ze stránky načtené před verzí 0.16.0 (třeba stránka
  dlouho otevřená v aplikaci Home Assistant v telefonu), která o volbě nevěděla.
- Otevřená stránka doplňku se po aktualizaci doplňku sama znovu načte (jakmile je vidět), takže už nikdo
  neklikne na tlačítka staré verze.
- Odebrán testovací režim (přepínač v nastavení, červený pruh a hláška pro strávníky). Uložené
  nastavení se při startu smaže, takže zapnutý režim se sám vypne.

## 0.18.2

- Dashboard Snídaně TV: nahoře aktuální čas a den, dole ovládání přehrávače Spotify. Dashboard se
  při startu přepíše na nové rozvržení (pokud má značku `jinhua47_breakfast_layout`).
- Ukazatel postupu na dashboardu ve stylu idingu: Otevřeno → Vybráno → Objednáno → K vyzvednutí,
  šedě dokud se čeká, zeleně s datem a časem, když je krok hotový; zrušená objednávka jedním řádkem.
  Je to vlastní karta `custom:jinhua47-progress-card`, kterou doplněk sám zaregistruje jako zdroj
  dashboardů (skript přímo v `data:` URL, takže nepotřebuje přístup ke konfiguraci Home Assistantu).
- Objednávka si pamatuje, kdy dosáhla kterého stavu (`stage_times`); v senzoru jako `steps`
  a `cancelled_at`.

## 0.18.1

- Oprava sestavení: `settleup.py` a `tv.py` chyběly v `.dockerignore`, takže se 0.17.0 a 0.18.0
  nesestavily (`"/settleup.py": not found`).

## 0.18.0

- Entita `sensor.jinhua47_breakfast` se stavem dnešní objednávky (`idle`, `choosing`, `approved`,
  `ordered`, `awaiting_payment`, `paid`, `ready`, `closed`, `cancelled`). V atributech je nadpis
  a podrobnosti pro zobrazení, kdo má vybráno a co, kdo ještě ne, souhrn objednávky, čas vyzvednutí,
  číslo objednávky, dřívější kola a tip dne. Mění se hned při každé změně, nejpozději do minuty
  (i po restartu Home Assistantu).
- Dashboard **Snídaně TV** (`/snidane-tv`, pohled `stav`) pro castování na Chromecast. Doplněk ho při
  startu sám založí a při změně rozvržení v nové verzi přepíše. Ručně upravený dashboard (bez klíče
  `jinhua47_breakfast_layout`) nechá být.

## 0.17.0

- Integrace se Settle Up: po zaplacení se objednávka zapíše jako útrata do vybrané skupiny. Platí ten,
  kdo objednal, a každý mu dluží cenu svého výběru (v NT$). V nastavení je sekce Settle Up s přepínačem
  sandbox / live: každé prostředí má vlastní Web API klíč, účet, skupinu a přiřazení strávníků ke členům.
  Výsledek zápisu je u objednávky, při chybě přijde objednavateli oznámení a jde to zkusit znovu.
- Schválení si pamatuje cenu výběru každého strávníka (rozpis pro Settle Up).

## 0.16.0

- Náhledy fotek jen z vlastních fotek; fotky z idingu se už nepoužívají ani nestahují. Set bez vlastní
  fotky je bez náhledu.
- Před zahájením objednávání vidí strávníci menu a můžou si naklikat výběr, jen ho nejde potvrdit
  (tlačítko „Objednávky ještě nejsou otevřené“). Přezdívka, hlášky a lišta zůstávají skryté jako dřív.
  Naklikaný výběr zůstane i po zahájení, kdy se stránka sama obnoví, a stačí ho potvrdit. „Jako včera“ je
  vidět i při naklikávání.
- Oprava diakritiky ve jménu přihlášeného uživatele („Ahoj GabÄa“ místo „Ahoj Gabča“): jméno se bere
  ze seznamu uživatelů Home Assistantu a hlavička od Ingressu se čte jako UTF-8.
- Doplněk už nespadne při startu, když Home Assistant zrovna startuje a jeho websocket vrací 502
  (dřív se několikrát restartoval s chybou WebSocketBadStatusException); zapíše to a pokračuje.
- Řádky v logu z různých vláken se už neslévají do jednoho („07:24:562026-11-27 07:24:56 Událost…“).
- Denní oznámení se přeskočí, když už ten den správce zahájil objednávání a pozvánky odešly (dřív
  přišlo „co si dáš k snídani“ i po vyzvednutí). Přeskočení je v logu.
- „Zahájit objednávání“ otevře okno s volbou: zahájit a poslat pozvánky, zahájit bez pozvánek, nebo
  zrušit. Pozvánky jdou poslat i při dalším otevření téhož dne; okno řekne, kdy už dnes odešly, a pak
  doporučí zahájit bez nich.
- Víc objednávek za den: po zaplacení se výběr každého, kdo byl v objednávce, uloží jako „naposledy“.
  Tlačítko „Další kolo“ (po zaplacení) výběry vyčistí a hned nabídne nové zahájení; vybírat můžou znovu
  všichni. Zaplacená objednávka se dál hlídá do vyzvednutí (oznámení „připraveno“ i události).
- „Jako včera“ ukazuje poslední objednaný výběr, ze stejného dne jako „Jako naposledy (dnes v 07:25)“.
  O půlnoci se ukládá jen výběr ze dne bez zaplacené objednávky (např. dokončené ručně na iding.tw).
- Log už nezahlcuje chyba „Broken pipe“, když stránka odejde během čekání na živé změny.
- „Tip pro dnešek“: volný text v nastavení (Hlavní stránka), který strávníci uvidí nad výběrem jídla,
  hned po uložení. Prázdný tip se neukáže.

## 0.15.1

- Oprava časů vyzvednutí u větších objednávek: doplněk se na časy ptá s cenou schválené objednávky jako
  web idingu. Na větší objednávku obchod potřebuje víc času a první čas je pozdější; dřív doplněk nabízel
  časy pro nejmenší objednávku a iding je odmítal (訂單準備時間不足, kód 2128).
- Nabídka časů se obnovuje každou minutu a po neúspěšné objednávce; vybraný čas zůstane, pokud ho obchod
  pořád nabízí. Chyba 2128 i prošlý čas mají srozumitelnou hlášku.
- U každého strávníka v nastavení volba „Oznámení“: Normální, Důrazné (přijde hned i v úsporném režimu
  telefonu: `priority: high`, `ttl: 0`, na iPhonu time-sensitive) a Budík (navíc kanál `alarm_stream`, na
  Androidu zvoní i v tichém režimu). Platí pro všechna oznámení na jeho telefon; tlačítko Test použije
  vybranou úroveň i bez uložení. Úroveň je vidět i v logu („důraz alarm“).
- Ikona a logo doplňku (logo 金華47) v seznamu doplňků a na stránce doplňku v Home Assistantu.

## 0.15.0

- Události v Home Assistantu pro automatizace při každé změně stavu objednávky:
  `jinhua47_breakfast_ordered`, `_paid`, `_ready`, `_closed` a `_cancelled`, s číslem objednávky, cenou,
  počtem setů, časem vyzvednutí a tím, kdo objednal. Popis a příklad jsou v README. Každá událost se
  zapíše do logu i s tím, jestli ji Home Assistant přijal, případně s chybou a jeho odpovědí.
- Vlastní fotky setů jde nahrát přímo do Home Assistantu do `/addon_configs/<slug doplňku>/photos/`
  (Samba, File editor, Studio Code Server), bez GitHubu a bez nové verze; ukážou se do 10 minut. Složka
  a soubor `NAZVY.txt` s názvy souborů se vytvoří samy, přesná cesta je v logu doplňku.

## 0.14.0

- Náhledy fotek u setů (i u „Jako včera“). Ťuknutí na náhled ukáže fotku přes celou obrazovku a set
  nevybere. Zatím mají fotku na idingu jen dva sety: dánský toast s vepřovým a dětský set. Doplněk je stáhne
  jednou a pak je podává sám z `/data`.
- Složka `photos/` pro vlastní fotky setů, pojmenované podle setu (seznam názvů je v `photos/README.md`).
  Vlastní fotka má přednost před fotkou z idingu.

## 0.13.3

- Tlačítko „Resetovat objednávku v doplňku“ (pro správce, kdykoliv je nějaká objednávka): zapomene dnešní
  objednávku jen v doplňku, bez ohledu na stav na idingu (na iding nic nepošle). Zruší i schválení, výběry
  zůstanou. Pro zaseknuté případy, např. platbu, kterou iding už nedokončí, a objednávku, kterou obchod
  nechce zrušit („您的餐點店家可能已準備…“).
- Log po zahájení objednávání shrne pozvánky: komu odešly, komu selhaly a kdo ji nedostal a proč
  (zahájil, nemá telefon, testovací režim). Při dalším otevření téhož dne zapíše, že se znovu neposílají.
- Hlídání objednávky na idingu nevrátí zpátky objednávku, kterou správce mezitím resetoval.
- Oznámení „Zaplaceno ✓.“ má správnou interpunkci i bez čísla objednávky.
- Nad tlačítkem „Zahájit objednávání“ už není vysvětlující text.
- Karta „Dnešní objednávka“ nemá pod „Celkem“ prázdné místo, když tam zrovna není žádná hláška.
- Pod výběrem už není text „Do košíku na idingu to pošle správce, až objednávku schválí.“

## 0.13.2

- Každé odeslané oznámení (pozvánka, denní, správci, průběh objednávky, testovací) se zapíše do logu:
  komu a na který `notify.*`, nadpis, text, odkaz a jestli ho Home Assistant přijal, případně s chybou
  a odpovědí HA.

## 0.13.1

- Oprava platby: „Zaplatil jsem – dokončit“ se nejdřív podívá na objednávku na idingu. Když je už zaplacená
  jinde (např. na iding.tw v prohlížeči po neúspěšném prvním pokusu v LINE), označí ji jako zaplacenou
  místo neúspěšného dokončení staré platby LINE Pay (iding hlásil 付款確認已超出等待時間).
- Doplněk sám každou minutu hlídá i nezaplacenou objednávku: zaplacení jinde pozná a pošle „Zaplaceno ✓“;
  zrušení na idingu taky.
- Když dokončení LINE Pay selže, stránka řekne, co dál (nový odkaz na platbu, nebo počkat na zaplacení jinde).
  Chyby idingu ukazují i jeho kód (např. „kód 5013“).
- Oznámení a stránka nepíšou „číslo None“, když iding číslo objednávky nevrátí.

## 0.13.0

- Tlačítko „Smazat všechny výběry“ v kartě objednávky: správce smaže dnešní výběry všech strávníků
  (jen před schválením; po schválení nejdřív „Znovu otevřít výběr“).
- Stránka se obnovuje živě: jakmile si někdo vybere, správce schválí, objedná nebo uloží nastavení, ostatní
  otevřené stránky (karta objednávky u správce i lišta) to ukážou hned, ne až za půl minuty.
- Po „Zahájit objednávání“ dostane každý strávník s telefonem oznámení „Ahoj <přezdívka>, <hláška>“
  (hláška ze seznamu denních oznámení, každý den jiná) s textem „Klikni zde a objednej.“; ťuknutí otevře
  stránku doplňku. Jen při prvním zahájení
  za den (po uzavření a novém zahájení už ne) a ne tomu, kdo objednávání zahájil. V testovacím režimu
  jen správcům.

## 0.12.0

- Objednávání každý den zahajuje správce tlačítkem „Zahájit objednávání“ v kartě „Dnešní objednávka“;
  o půlnoci se zase zavře. Do té doby ostatní vidí jen „Objednávky zatím nejsou otevřené“: žádnou přezdívku,
  hlášku, lištu ani výběr (nic z toho stránka ani API neposílá) a výběr nejde uložit. Po zahájení se jim
  stránka do půl minuty sama přenačte. Správci vidí všechno pořád.
- Tlačítko „Uzavřít objednávání“: správce může objednávání kdykoliv zase zavřít (výběry, schválení
  i objednávka zůstanou) a znovu zahájit.
- Testovací režim v nastavení na webu: ostatní uvidí jen „Testovací režim“ (nic jiného, ani lištu),
  nemůžou vybírat a denní oznámení dostanou jen správci. Správci vidí všechno a nahoře červený pruh
  „Testovací režim“. Zapnutí i vypnutí se zapíše do logu.
- Kdo není mezi strávníky (a není správce), vidí jen „Zatím nejsi mezi strávníky“: žádnou lištu ani hlášky,
  ať je objednávání otevřené, nebo ne. Když ho správce přidá, stránka se mu sama přenačte.
- Sety a nápoje se ukazují bez čínských názvů: set má český název a pod ním český popis, co v něm je
  (z popisu položky na idingu, část po části; neznámá část zůstane čínsky). Pod nápojem je český popis,
  u teploty a velikosti už není čínský znak.
- Sekce „⭐ Oblíbené“ nahoře ve výběru setu: dánský toast, nudle zhajiang a francouzský toast
  (seznam je v `menu.py`, `FAVORITES`); ostatní sety jsou pod ní.
- Nad oblíbenými je pro každého „↩️ Jako včera“: jeho poslední výběr (set, pití, teplota, velikost) na jedno
  klepnutí, pak stačí „Vybrat“. Když včera nevybíral, nabídne se poslední dřívější („Jako minule (pá 20. 11.)“).
  Když dnes set nebo pití nejde, karta je zašedlá s důvodem. Poslední výběry se ukládají při přechodu
  na nový den do `/data/choices.json`; poprvé se tedy karta objeví den po aktualizaci.
- Po kliknutí na set, pití, teplotu nebo velikost stránka vždy sjede na další krok, i když se jen mění dřívější volba.
- Přezdívky, hlášky a emoji se dál vybírají každý den náhodně, ale nikdy stejné jako předchozí den
  (když je v seznamu aspoň dvojice). Dnešní výběry se proto změní oproti dřívější verzi.
- Lepší log pro ladění: každý řádek má čas; každá chyba, kterou stránka ukáže, je i v logu (s uživatelem);
  objednávka loguje přepočet košíku, odeslání, přípravu a dokončení platby, změny stavu na idingu
  a odeslaná oznámení. Neočekávaná chyba ve smyčce na pozadí se vypíše a smyčka běží dál.
- Lišta nahoře: hlášky i emoji se rozdělují mezi strávníky tak, aby žádní dva neměli stejnou a nikdo neměl
  stejnou jako včera. Když je hlášek méně než strávníků, některé se musí opakovat, ale pořád ne tomu samému dva dny po sobě.
- Panel v postranním panelu vidí i uživatelé Home Assistantu, kteří nejsou administrátoři (`panel_admin: false`).
  Nastavení doplňku dál vidí jen správci doplňku.
- Lišta nahoře se při najetí myší už nezastaví.
- Oprava: stránka byla na telefonu širší než displej (ceny vpravo byly uříznuté).

## 0.11.0

- Po schválení může správce objednat: vybere čas vyzvednutí (nabídka obchodu po 5 minutách,
  „co nejdřív“ první) a dá „Objednat a zaplatit“. Doplněk nejdřív nechá iding spočítat košík; když nesedí
  počet kusů nebo cena se schválenou objednávkou, nic neobjedná. Pak objednávku odešle a požádá
  LINE Pay o platbu.
- Správci, který objednal, přijde na telefon oznámení s odkazem do LINE Pay; na stránce jsou tlačítka
  „Zaplatit v LINE“, „Platba v prohlížeči“, „Zaplatil jsem – dokončit“, „Nový odkaz na platbu“
  a „Zrušit objednávku“ (jen nezaplacená).
- Po zaplacení doplněk každou minutu kontroluje stav objednávky na idingu. Když ji obchod označí
  jako připravenou, přijde správci oznámení. Oznámení o průběhu dostává jen správce, který objednal.
- V liště nahoře je vidět, jak daleko objednávka je (platí se / zaplaceno s časem vyzvednutí /
  připraveno). Karta „Dnešní objednávka“ je pro správce nahoře pod pozdravem.

## 0.10.0

- Nové nastavení „Oznámení správci“ (výchozí zapnuto): správce dostane na telefon oznámení, když už mají
  všichni ostatní vybráno a chybí jen on („chybíš jen ty“), a když mají vybráno všichni a objednávka čeká
  na schválení. Každé jen jednou; znovu přijde, až se stav změní (někdo začne znovu). Když výběr dokončí
  sám správce, oznámení mu nepřijde. Správce musí být strávník s přiřazeným telefonem.
- Nahrání košíku na iding posílá celý košík jako web (otisk menu, počty setů, celkovou cenu);
  bez toho iding odpovídal 傳入參數錯誤.
- Chyby idingu říkají, které volání selhalo, a celá odpověď idingu se vypíše do logu.

## 0.9.0

- Správce vidí na hlavní stránce kartu „Dnešní objednávka“: co si kdo vybral, stejné výběry sečtené
  dohromady a celkovou cenu. Kdo nevybral, do objednávky nejde.
- Tlačítko „Schválit a poslat do košíku“ zamkne dnešní výběry, přihlásí se uloženým účtem do idingu
  a košík na idingu nahradí dnešními výběry. iding pak cenu spočítá sám a doplněk ji porovná se svou.
  Nic se neobjedná ani nezaplatí; objednávku jde zatím dokončit ručně na iding.tw.
- Správce může objednávku znovu otevřít („Znovu otevřít výběr“).
- Strávník, který má uloženo a objednávka ještě není uzavřená, může tlačítkem „Začít znovu“
  výběr smazat a vybírat od začátku.
- Po uzavření jsou volby zamčené a v liště nahoře běží „🔒 Objednávka je uzavřená.“

## 0.8.0

- Nahoře pod hlavičkou běží lišta, kterou vidí všichni: u každého strávníka emoji, jméno a hláška
  podle toho, jestli už má vybráno (👍 David má jasno. / 😠 Jana pořád neví, co chce.).
  Emoji i hláška se každý den vybírají náhodně; hlášky nastavuje správce v sekci „Lišta nahoře“.
- Výběr snídaně se ukládá tlačítkem „Vybrat“ do doplňku (`/data/choices.json`, platí jen pro dnešek)
  a po otevření stránky se obnoví. Do idingu se zatím nic neposílá.
- Lišta se obnovuje každých 30 sekund a po návratu do aplikace.

## 0.7.0

- Strávníci si na hlavní stránce vyberou set (všechny sety z menu 金華47), k němu pití
  (black tea, lemon black tea, milk tea, sugar free green tea, winter melon tea, winter melon green tea,
  winter melon lemon, coke, fresh milk), teplotu (studené = 冰, teplé = 溫) a velikost (malé = 中, velké = 大).
  Cena se počítá podle menu včetně příplatků; vyprodané položky nejdou vybrat.
- Menu se načítá z idingu (bez přihlášení) a drží se 10 minut; když iding neodpovídá, použije se poslední načtené.
- Výběr se zatím nikam neukládá ani neobjednává.

## 0.6.0

- Správce přidává a odebírá strávníky (výběr z uživatelů Home Assistantu). Ukládají se podle ID uživatele,
  takže přejmenování v Home Assistantu propojení nerozbije. Denní oznámení chodí jen strávníkům.
- Kdo mezi strávníky není, uvidí na stránce, ať ho správce přidá.
- Při aktualizaci se strávníky stanou ti, kdo už měli přiřazený telefon nebo přezdívku.

## 0.5.0

- V konfiguraci doplňku zůstali jen správci (`admins`). Účet iding, čas denního oznámení a hlášky
  se nastavují na stránce doplňku pod ozubeným kolečkem; hodnoty z dřívější konfigurace se přesunou samy.
- Tlačítko „Ověřit přihlášení“ zkusí přihlášení do idingu zadaným telefonem a heslem.
- Změna času oznámení platí hned, bez restartu doplňku.

## 0.4.0

- Nastavení pro správce je schované pod ozubeným kolečkem v horní liště; hlavní stránka je jen pozdrav.
- Volba `admins`: seznam uživatelských jmen správců. Prázdná = všichni administrátoři Home Assistantu.
- Testovací oznámení posílá správce každému uživateli zvlášť (tlačítko u uživatele, funguje i před uložením).

## 0.3.0

- Denní oznámení v nastaveném čase (`daily_notification_time`) všem uživatelům s přiřazeným telefonem:
  „Ahoj <přezdívka>, <hláška>“.
- Seznamy hlášek pro oznámení a pro stránku v nastavení doplňku. Každý uživatel dostane každý den jinou náhodnou.
- Administrátor nastavuje na stránce doplňku každému uživateli seznam přezdívek; každý den se vybere jedna.

## 0.2.0

- Administrátoři Home Assistantu přiřazují na stránce doplňku každému uživateli jeho telefon
  (rozbalovací seznam telefonů z aplikace Companion). Testovací oznámení jde na telefon přihlášeného uživatele.
- V nastavení doplňku jsou přihlašovací údaje k iding.tw (telefon a heslo).
- Volby `notify_service` a `show_in_sidebar` jsou odstraněné; panel se zapíná přepínačem na kartě Informace.

## 0.1.0

- Testovací základ: stránka v postranním panelu (Ingress) s pozdravem přihlášeného uživatele
  a tlačítkem, které pošle testovací oznámení na telefon z nastavení.
