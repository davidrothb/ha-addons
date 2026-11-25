# Vlastní fotky setů

Fotky, které nemají být na GitHubu, nahraj přímo do Home Assistantu do složky
`/addon_configs/<slug doplňku>/photos/` (přesná cesta je v logu doplňku po startu, složka i soubor
`NAZVY.txt` se seznamem názvů se vytvoří samy). Nahrát jde přes doplněk Samba (sdílení `addon_configs`),
File editor nebo Studio Code Server. Fotka se ukáže do 10 minut, nebo hned po restartu doplňku,
bez nové verze.

Tahle složka v repozitáři je pro fotky, které na GitHubu být můžou. Po přidání fotky sem je potřeba
zvýšit `version` v `../config.yaml`, commitnout, pushnout a doplněk aktualizovat.

Fotka z Home Assistantu má přednost před fotkou odsud a obě před fotkou z idingu. Soubor pojmenuj podle
setu, podle tabulky níže, s příponou `.jpg`, `.jpeg`, `.png` nebo `.webp`. Stránka ukáže fotku jako
čtvercový náhled (oříznutý na střed) a po ťuknutí celou. Ideálně 1200 × 900 px, JPEG kolem 80 %.

| Set | Soubor | Fotka na idingu |
| --- | --- | --- |
| Dánský toast s vepřovým | `dansky-toast-s-veprovym.jpg` | ano |
| Nudle zhajiang | `nudle-zhajiang.jpg` | – |
| Francouzský toast | `francouzsky-toast.jpg` | – |
| Kuřecí stehno | `kureci-stehno.jpg` | – |
| Velký sytý set | `velky-syty-set.jpg` | – |
| Čínský set | `cinsky-set.jpg` | – |
| Lehký set | `lehky-set.jpg` | – |
| Dětský set | `detsky-set.jpg` | ano |
| Hovězí burger | `hovezi-burger.jpg` | – |
| Bageta s omeletou | `bageta-s-omeletou.jpg` | – |
| Nudle s houbovou omáčkou | `nudle-s-houbovou-omackou.jpg` | – |
| Nudle s černým pepřem | `nudle-s-cernym-peprem.jpg` | – |
| Nudle zhajiang, malé | `nudle-zhajiang-male.jpg` | – |

Název souboru je český název setu bez diakritiky, malými písmeny a s pomlčkami místo mezer.
Nový set, který v tabulce není, se pojmenuje stejně.
