# Stav implementácie pracovného toku elektrikára

**3. 10. 2026.** Tento súbor opisuje aktuálny lokálny kód. Výskumné a auditné dokumenty zostávajú historickým východiskom; terénne overenie ešte neprebehlo.

## Čo už prechádza jedným tokom

1. **Dopyt:** meno, telefón alebo email, pôvod, typ práce, miesto realizácie a ďalší krok. Adresa miesta je samostatná od fakturačnej adresy klienta.
2. **Obhliadka:** čas a poznámka pri dopyte. Následne možno vytvoriť klienta alebo zvoliť existujúceho a založiť ponuku s preneseným miestom a kontaktom.
3. **Ponuka:** ručné položky, množstvá, jednotkové ceny a zľava; pred odoslaním sa znovu vypočíta a skontroluje suma. Množstvo má najviac tri a jednotková cena najviac dve desatinné miesta, aby položky faktúry súhlasili s prijatou sumou. AI vytiahne len návrh rozsahu a množstva, jej odhadnuté ceny a zľava sa zahodia. Odoslaná verzia má nemenný JSON snapshot a zaznamenaný kanál/dátum.
4. **Schválenie:** potvrdenie zákazníka s poznámkou vytvorí najviac jednu zákazku z prijatej verzie. Klient, miesto a cena sa prenesú bez opätovného zadania. Opakované kliknutie nevytvorí ďalšiu zákazku.
5. **Realizácia a fotky:** nové prílohy sa ukladajú mimo `static`, podávajú sa len prihlásenému vlastníkovi zákazky. Fotka môže niesť miestnosť, prvok, typ kábla a trasu; záznamy sa dajú textovo hľadať.
6. **Faktúra:** z dokončenej zákazky s prijatou ponukou vzniká po kontrole dátumov, DPH, fakturačnej adresy a platby faktúra. Má väzbu na zákazku a presnú prijatú revíziu. Nová faktúra si uloží snapshot odberateľa a dodávateľa; neskoršia zmena klienta nemení zobrazenie vystavenej faktúry. Dvojklik nevytvorí druhú faktúru.
7. **Dnes:** akčný prehľad otvorených dopytov, ponúk bez odpovede aspoň 7 dní, termínov, materiálu na nákup, hotových nefakturovaných zákaziek a faktúr po splatnosti. Starý fakturačný dashboard zostáva dostupný.
8. **Materiál a priame náklady:** jednoduchý nákupný zoznam na zákazke má stavy treba kúpiť → objednané → pripravené → použité/vrátené. Práca sa zapisuje v minútach s interným hodinovým nákladom, doprava/subdodávka/iné v eurách. Potvrdené bločky z existujúceho CRM sa sčítajú samostatne.
9. **Dodatok rozsahu:** nový výkon má množstvo, jednotkovú cenu a vypočítanú sumu. Na faktúru sa dostane iba po zapísaní spôsobu a dátumu súhlasu zákazníka. Prijatá pôvodná ponuka zostáva nezmenená; dodatok je samostatný záznam na zákazke.
10. **Vlastný malý cenník:** práca alebo materiál má predajnú cenu, voliteľný nákupný/interný náklad a poznámku o pôvode ceny. Výber v novej ponuke prenesie názov, jednotku a cenu; ponuka si uloží ich vtedajšie hodnoty. Neskoršia úprava cenníka nemení odoslanú ponuku.

## Čo je ešte otvorené

- **Cenotvorba je ešte základná.** Výpočet predajnej ceny je deterministický a malé ručné ceny sa dajú opakovať. Zatiaľ chýba kontrolovaný import cenníkov, rozdiel prirážka/marža, rezerva, doprava v kalkulácii a spoľahlivé rozlíšenie nákupnej ceny s DPH/bez DPH. Predajnú cenu musí potvrdiť človek.
- **Ekonomika je orientačná.** Karta ukazuje dohodnutú cenu mínus potvrdené bločky a zadané priame náklady. Ak chýba práca alebo doklad, upozorní. Pri platiteľovi DPH sú potvrdené bločky v hrubej sume bez rozdelenia odpočítateľnej dane. Režijné náklady a dane zatiaľ nie sú zahrnuté; suma sa preto nevolá čistý zisk.
- **Zálohy a čiastkové faktúry** ešte nie sú v novom fakturačnom toku. Ten vystavuje jednu konečnú faktúru z prijatej ponuky a odsúhlasených dodatkov. Po vystavení už nepripúšťa nový dodatok na tú istú faktúru. Existujúce samostatné fakturačné cesty zostali funkčné, ale nemajú všetky nové záruky ani snapshot strán.
- **Staré prílohy** ostávajú v `static/uploads/jobs`. Flask statickú cestu blokuje a sprístupňuje ich cez overenie vlastníka; kontrolovaný Nginx nemá priamy `/static` alias. Pred nasadením treba znova skontrolovať konfiguráciu a zálohovať staré fotky. Presun súborov nie je nutný pre toto vydanie a má byť samostatnou kontrolovanou zmenou. Nové prílohy do verejného priečinka nejdú.
- **Hlavná a CRM pilotná databáza** sú stále oddelené. Nový tok je súčasťou hlavnej aplikácie a neznamená automatickú synchronizáciu pilota. Migrácie `d72c913f1b08`, `ea42d6a90b17`, `f36b7c0912da`, `c42f980d7b25` a `b47a19de0c62` tvoria jeden verziovaný reťazec. Na súkromnej kópii konkrétnej produkčnej DB prešiel a zachoval 99 pôvodných riadkov; finálny commit treba pred servisným oknom preveriť znova.
- **Existujúca lokálna `instance/invoices.db` nemá tabuľku `alembic_version` a chýbajú jej aj tabuľky zákaziek.** Čisto automatický `flask db upgrade` na jej kópii narazil na už existujúcu tabuľku `lead`; zdroj bol otvorený iba na čítanie. Túto databázu nemožno naslepo označiť (`stamp`) ako aktuálnu migráciu. Najprv treba určiť jej skutočnú schému a pri dátach, ktoré chceme zachovať, nacvičiť osobitnú bezpečnú migráciu na kópii. Tento Git commit nespúšťa žiadnu databázovú migráciu.
- **Mobilný čas 5–10 sekúnd, úspora administratívy a ochota platiť** nie sú overené. Na test treba vlastnú servisnú zákazku a rekonštrukciu, kde zmeriame kroky, opravy údajov a čas.

## Overenie a bezpečné nasadenie

- `python -B -m pytest -q`: regresie hlavnej aplikácie, Veduci integrácie a CRM pilota.
- `node --test tests/job-notes-ui.test.cjs tests/receipt-parser.test.mjs tests/receipt-ui.test.cjs`: existujúce JS UI testy (PowerShell nerozbaľuje globy pre Node).
- Nové testy overujú dopyt → obhliadka → ponuka → odoslaná verzia → prijatie → zákazka → odsúhlasený dodatok → faktúra, vlastníctvo, idempotenciu, presnosť ceny a množstva, súkromné fotky, nákupný zoznam, interný náklad práce, odmietnutie chybných súborov, nulovanie AI cien a migráciu vrátane celého Alembic reťazca na dočasnej SQLite DB. Aktuálny lokálny beh: 94 Python a 29 JS testov úspešných.
- **Pred živou migráciou:** príprava na kópii skutočnej DB už prešla; ešte treba urobiť konzistentnú zálohu SQLite a príloh počas zastavenia služby, overiť ju a postupovať podľa [nasadzovacieho návodu](DEPLOYMENT_INVOICE.md). Nie je hotové živé nasadenie ani test na živom mobile.

## Ďalší najvyšší ROI inkrement

Na jednej skutočnej zákazke odmerať prácu s dopytom, cenou, fotkami, nákupným zoznamom a internou nákladovou sadzbou. Potom upraviť cenník podľa skutočne opakovaných položiek a rozlíšiť nákupné náklady bez/vrátane DPH, aby porovnanie plán/skutočnosť bolo rozhodovacie. Bez toho nesmie dashboard tvrdiť čistý zisk.
