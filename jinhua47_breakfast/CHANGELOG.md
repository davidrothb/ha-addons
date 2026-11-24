# Changelog

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
