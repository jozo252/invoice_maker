# InvoiceMakerAI: CRM pilot pre remeselníkov

Prvý použiteľný postup je **zákazník → zákazka → fotografia bločka → kontrola údajov → potvrdený náklad**. CRM sa rozvíja v existujúcej aplikácii InvoiceMakerAI vo Flasku. Pilot sa dá skúšať lokálne aj cez mobil na VPS; tieto dve verzie majú oddelené dáta.

## Mobil a VPS

Mobilný pilot beží na adrese **https://invoicemakerai.com/remeselnici/**. Výsledok overenia nasadenej verzie zaznamenáva `DEVELOPMENT_LOG.md`. Prístup vyžaduje osobitný kód; bežný účet pôvodného InvoiceMakeru sa nepoužíva. Počítač pri prevádzke na VPS nemusí zostať zapnutý.

`crm_pilot.py` používa vlastnú databázu a súkromné fotografie v `/srv/crm-pilot/shared/`. Nepripája sa k produkčnej fakturácii ani k lokálnemu `instance/crm_local/`. Relácia má vlastný názov a cestu cookie, HTTPS, CSRF a limit pokusov o prihlásenie. OCR súbory sa načítajú aj pod URL prefixom `/remeselnici/`. Pilot ukladá najviac 500 MB fotografií a odmietne ďalší upload pri nedostatku voľného miesta.

VPS pilot používa **serverové AI čítanie cez OpenAI API**. Skutočné čítanie syntetického bločka navrhlo predajcu TEST Elektro, dátum 16. 9. 2026 a sumu 18,40 €. Výsledky nasadenia zaznamenáva `DEVELOPMENT_LOG.md`. Lokálna verzia na porte 5180 naďalej používa čítanie v prehliadači bez externého AI API.

Pripravovaná oprava `receipt-total-v2` odlišuje novo prečítanú sumu od predchádzajúcej uloženej hodnoty a dopĺňa kontrolu meny a typu dokladu. Jej nasadenie a nové overenie treba osobitne potvrdiť v `DEVELOPMENT_LOG.md`; skorší syntetický test túto opravu neoveruje.

Aktualizácie sa pripravujú lokálne, overia testami a zabalia cez `scripts/package_crm_pilot.py`. Na VPS sa zmení samostatné vydanie kódu; databáza a originály zostávajú mimo vydania. Postup nasadenia, zálohy a návratu k predošlej verzii je v `deploy/README.md`. Pôvodná fakturácia na hlavnej doméne pokračuje vo svojej službe.

## Spustenie

1. V tomto priečinku otvorte **`Spustit CRM.cmd`**.
2. Pracovný priestor sa otvorí na **http://127.0.0.1:5180/**.
3. Okno so serverom nechajte počas používania otvorené. Server ukončíte klávesmi **Ctrl+C**.

V PowerShelli možno použiť:

```powershell
& '.\Spustit CRM.cmd'
```

Spúšťač používa existujúce prostredie `.venv`. Ak chýbajú OCR súbory, pripraví ich z lokálne nainštalovaných balíkov. Pri prvom spustení vytvorí oddelenú databázu pilotu; pri ďalšom použije uložené dáta. Ak už tento pilot beží, spúšťač otvorí jeho pracovný priestor. Pri chybe ponechá správu v okne.

Ak po prenesení projektu chýba `.venv`, vytvorte ho pomocou Pythonu 3.12 a existujúceho súboru `requirements`:

```powershell
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements
```

Lokálny vstup na `/` prihlási testovacieho používateľa automaticky. Server počúva iba na `127.0.0.1:5180` a kontroluje lokálny prístup. **Tento spôsob prihlasovania je iba pre lokálny pilot**, nie pre internet alebo firemnú sieť. Telefón sa naň priamo nepripojí.

## Prvá zákazka a bloček

Prehľad **Zákazky** zobrazuje každú zákazku ako samostatnú kartu. Celá karta otvorí detail s kontaktom, termínom, dohodnutou cenou, stavom, poznámkami a bločkami. Na karte sa ukazujú iba potvrdené náklady; rozpracované bločky sú viditeľné v detaile.

V detaile možno pridávať samostatné **priebežné poznámky**. Každá má čas zápisu a zostáva pri danej zákazke. Text možno napísať alebo skúšobne nadiktovať tlačidlom **Diktovať po slovensky**, ak prehliadač podporuje rozpoznávanie reči. Prepis sa vloží iba do upraviteľného poľa; ukladá sa až po kontrole a stlačení **Uložiť poznámku**. Aplikácia neukladá zvukový súbor. Prehliadač však môže hlas spracovať online cez vlastnú službu, preto pri citlivých údajoch zvážte ručné písanie. Dostupnosť a presnosť slovenčiny treba overiť na konkrétnom telefóne.

Karty, priebežné poznámky a hlasové diktovanie z 22. 9. 2026 sú súčasťou tohto zdrojového vydania. Online pilot používa samostatné vydania; aktuálne nasadený stav a jeho overenie zaznamenáva `DEVELOPMENT_LOG.md`.

1. V časti **Zákazníci** uložte meno a prípadne telefón alebo e-mail.
2. Vytvorte zákazku pre tohto zákazníka. Doplňte názov, prípadne dohodnutú cenu, termín a poznámky.
3. V detaile zákazky nahrajte fotografiu bločka.
4. Počkajte na návrh predajcu, dátumu a celkovej sumy. Na VPS sa nový rozpracovaný bloček najprv číta cez OpenAI; pri nedostupnosti sa skúsi OCR v prehliadači. Lokálne sa používa iba OCR v prehliadači. Ak čítanie nefunguje, zastavte ho a vyplňte údaje ručne.
5. Porovnajte všetky údaje s originálom, skontrolujte priradenú zákazku a pôvod zobrazenej sumy. Ak na doklade chýba mena, použite ponuku **Použiť … ako EUR** iba po vlastnom overení meny. Doplňte chýbajúci dátum dokladu; dátum splatnosti ho nenahrádza. Potom zaškrtnite potvrdenie kontroly.
6. Kliknite na **Potvrdiť a uložiť náklad**. Až potom sa suma započíta do nákladov zákazky.

Podporované sú jednotlivé fotografie **JPEG/JPG, PNG a WebP**, najviac **8 MB a 30 megapixelov**. **HEIC, PDF a animované obrázky nie sú podporované.** Pre tento pilot používajte bločky v eurách; cudzie meny a vrátenie peňazí zatiaľ nemajú samostatný postup.

Systém ukladá celú potvrdenú sumu bločka. Nerozpisuje položky ani nevedie účtovnú evidenciu DPH. Ukazovateľ „Zostatok pred ďalšími nákladmi“ je dohodnutá cena mínus potvrdené bločky; nezohľadňuje vašu prácu, dopravu, odvody ani ostatné náklady. **Nie je to čistý zisk.**

## Kde zostávajú dáta

| Cesta v projekte | Obsah |
|---|---|
| `instance/crm_local/crm.sqlite3` | Zákazníci, zákazky, plánovanie a záznamy bločkov lokálneho pilotu |
| `instance/crm_local/private_receipts/` | Pôvodné fotografie bločkov, mimo verejného priečinka `static` |
| `instance/crm_local/session.key` | Lokálny podpisovací kľúč relácie; nezverejňovať ani neposielať do repozitára |
| `static/crm/vendor/ocr/` | Knižnica OCR, jej worker a jazykové modely; neobsahuje bločky |

V **lokálnom pilote na porte 5180** smeruje upload fotografie do lokálneho Flask servera. OCR potom číta súkromný originál v prehliadači bez externého OCR/AI API a bez API kľúča. Lokálne dáta sa nesynchronizujú do VPS ani iného počítača a automatická záloha zatiaľ nie je implementovaná.

V **VPS AI postupe** sa originál ukladá súkromne na VPS a jeho upravená kópia sa posiela do OpenAI na externé spracovanie. Nie je to čisto lokálne čítanie fotografie. Neodosielajú sa databáza zákazníkov, ostatné zákazky ani API kľúč do prehliadača. Odoslaná fotografia však obsahuje všetky údaje, ktoré sú na nej viditeľné. Pilot neposiela e-maily ani nevolá platobné služby.

`crm_local.py` spúšťa oddelenú lokálnu aplikáciu, neimportuje produkčnú factory `app.create_app()` a nepoužíva jej `invoices.db`. Opakované `--init` existujúcu databázu pilotu neprepisuje ani neaktualizuje jej schému. Budúce zmeny schémy treba riešiť migráciou.

Pred prvými reálnymi údajmi a po pracovnom dni ukončite server cez Ctrl+C a skopírujte **celý priečinok `instance/crm_local/`** do samostatného priečinka záloh. Nestačí zálohovať iba databázu: fotografie sú uložené osobitne. Záloha obsahuje súkromné bločky a lokálny kľúč relácie. Obnovenie robte pri vypnutom serveri z jednej spoločnej zálohy databázy a fotografií.

## Ako fungujú bločky

- Nahratie vytvorí stav **`draft`**. Rozpracovaný bloček má uložený originál, ale ešte nevytvára potvrdený náklad.
- OCR poskytuje iba návrh. Server vyžaduje vlastnú zákazku, platný dátum, predajcu, kladnú sumu a výslovné potvrdenie kontroly.
- Suma sa ukladá a sčítava ako celé **centy**, nie ako desatinné číslo s pohyblivou čiarkou.
- Úplne rovnaký súbor u rovnakého používateľa identifikuje SHA-256. Opakované nahratie otvorí existujúci bloček, aj keď ho skúsite nahrať k inej zákazke. Priradenie možno upraviť v jeho formulári. **Nová fotografia toho istého papierového bločka môže mať iný hash**; to zatiaľ nie je automaticky odhalená duplicita.
- Pri oprave sa používa číslo revízie. Starší formulár nesmie prepísať novšiu opravu; pri konflikte zostanú odoslané hodnoty vo formulári na porovnanie.
- Pôvodný súbor sa pri oprave sumy, dátumu alebo zákazky nemení. Prístup k záznamom a originálom je viazaný na vlastníka.

## AI čítanie na VPS

Implementácia `crm/ai_receipts.py` používa OpenAI Responses API s modelom **`gpt-4.1-mini-2025-04-14`**. Pred odoslaním overí hash originálu, upraví orientáciu a pripraví JPEG s dlhšou stranou najviac 2048 pixelov. Originál zostáva uložený bezo zmien. API vracia návrh predajcu, dátumu a celkovej sumy vrátane DPH. Pripravovaná verzia `receipt-total-v2` osobitne vracia prečítanú kladnú sumu (`detected_amount`), menu a typ dokumentu; bezpečný návrh sumy v EUR od týchto metadát odlišuje. Model podporuje obrázkové vstupy a štruktúrovaný výstup podľa [oficiálnej OpenAI dokumentácie](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

Pri sume formulár odlišuje **prečítanú sumu, uloženú sumu a ručne upravenú hodnotu**. Ak AI sumu neurčí, predchádzajúca uložená suma sa nesmie prezentovať ako nový výsledok čítania. Ručne upravená hodnota sa oneskoreným návrhom neprepisuje. Samotné opätovné načítanie nemení uložený náklad.

Keď AI prečíta kladnú sumu, ale mena na doklade nie je viditeľná, suma sa automaticky nepovažuje za EUR. Používateľ môže po overení meny výslovne použiť ponuku **Použiť … ako EUR**; stále musí skontrolovať celý formulár a potvrdiť jeho uloženie. Pri rozpoznanej cudzej mene sa táto ponuka nezobrazí a suma sa automaticky nekonvertuje ani neoznačí ako EUR. Nečitateľná či nejednoznačná suma vyžaduje ručnú kontrolu originálu.

Verzia `receipt-total-v2` rozlišuje aj **pokyn k platbe** (`payment_instruction`) od faktúry či účtenky. Výzva na úhradu sama nepotvrdzuje, že bola suma zaplatená. Dátum splatnosti sa nepoužíva ako dátum vystavenia alebo dátum bločka; ak doklad obsahuje iba splatnosť, návrh dátumu zostane prázdny a treba ho doplniť podľa overeného podkladu.

AI sa spúšťa automaticky po otvorení nového bločka v stave `draft`, ak má VPS nastavený kľúč. Ručne zmenené polia počas čítania zostanú zachované. Otvorenie už potvrdeného nákladu automatický AI pokus nespúšťa. Aj potvrdený doklad možno načítať cez AI výslovným stlačením **Načítať údaje znovu**; uložené údaje zostanú nezmenené, kým nepotvrdíte opravu. Pri chybe alebo vyčerpaní limitu zostáva dostupné OCR v prehliadači a ručné zadanie. **Ani úspešná AI odpoveď nezapisuje potvrdený náklad:** vždy treba porovnať údaje s originálom a potvrdiť ich vo formulári.

Výsledky a rezervované pokusy sa ukladajú do súkromného `shared/ai-state.sqlite3` mimo vydania kódu. Cache je oddelená podľa vlastníka, hash fotografie, modelu a verzie pokynov. Nová verzia `receipt-total-v2` preto znovu nepoužíva návrh z cache `receipt-total-v1`; potvrdené náklady tým nemení. Opakované čítanie rovnakého uloženého výsledku v tej istej verzii nevolá API znova. Na celý pilot platí najviac **30 rezervovaných AI pokusov za deň podľa UTC a 6 za minútu**; počítajú sa aj neúspešné pokusy. Po chybe rovnakého bločka je ďalší pokus blokovaný 60 sekúnd, rozpracovaný pokus 90 sekúnd. Tieto záznamy a cache pretrvajú reštart služby.

OpenAI API sa účtuje samostatne podľa použitia; predplatné ChatGPT nenahrádza API kredit. Limit pokusov nie je peňažný strop účtu. Spotrebu kontrolujte v OpenAI API účte a podľa [aktuálneho cenníka API](https://developers.openai.com/api/docs/pricing). Požiadavka používa `store: false`; to neznamená nulové spracovanie alebo nulovú retenciu u poskytovateľa. Podmienky opisuje [OpenAI dokumentácia spracovania dát](https://developers.openai.com/api/docs/guides/your-data).

API kľúč je iba na serveri v `/srv/crm-pilot/shared/openai-api.key`, s oprávnením `0400` a vlastníkom `crm-pilot`. Nepatrí do frontend kódu, aplikačných logov ani archívu vydania. Bezpečná samostatná konfigurácia je opísaná v `deploy/README.md`.

## Lokálne OCR súbory

Použité verzie: `tesseract.js@7.0.0`, `tesseract.js-core@7.0.0`, `@tesseract.js-data/slk@1.0.0` a `@tesseract.js-data/eng@1.0.0`.

Prípravu zabezpečuje:

```powershell
& '.\.venv\Scripts\python.exe' '.\scripts\prepare_receipt_ocr.py'
```

Predvolený zdroj balíkov je `C:\Users\pc\Documents\ChatGPT\crm-remeselnici\node_modules`. Skript overuje verzie a kopíruje JavaScript, worker, core varianty, jazykové dáta a priložené oznámenia licencií do `static/crm/vendor/ocr/`. Sám balíky nesťahuje.

Pre iný lokálny zdroj:

```powershell
& '.\.venv\Scripts\python.exe' '.\scripts\prepare_receipt_ocr.py' --node-modules 'C:\cesta\k\node_modules'
```

Pôvodný prototyp **Dielňa** v `crm-remeselnici` zostáva zachovaný ako zdroj už nainštalovaných OCR balíkov. Hlavná implementácia pokračuje tu vo Flasku; dáta prototypu sa sem automaticky nemigrujú ani nesynchronizujú.

## Overenie a najbližší test

Oprava `receipt-total-v2` prešla **74 Python testami a 25 Node testami** (10 parser + 15 UI) v oddelenom testovacom runtime. Nasadenie a živé čítanie nahláseného pokynu k platbe potvrdzuje `DEVELOPMENT_LOG.md`: návrh sa zobrazuje oddelene od starej sumy, opakované čítanie použije cache a potvrdený náklad zostáva bez uloženia nezmenený. Predchádzajúci VPS pilot prešiel aj postupom so syntetickým bločkom vrátane OCR v prehliadači, potvrdenia 18,40 € a formulára pri šírke 390 px. **Presnosť čítania treba ďalej overovať na skutočných bločkoch a ďalších typoch dokladov.**

Testy možno spustiť bez produkčnej databázy:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p test_crm.py
node --test tests/receipt-parser.test.mjs tests/receipt-ui.test.cjs
```

Najbližší lacný test: **jedna vlastná zákazka, päť reálnych bločkov a tri pracovné dni používania**. Pri každom bločku zaznamenajte:

| Bloček | Navrhnutá suma správna pred opravou? | Čas od nahratia po potvrdenie | Nutná oprava / problém |
|---|---|---|---|
| 1–5 | áno / nie / nenačítaná | sekundy | stručne |

Porovnajte čas s ručným prepísaním rovnakých údajov. Po troch dňoch opravte najväčšiu prekážku a ukážte postup jednému remeselníkovi. Ďalšiu AI funkciu pridávajte až vtedy, keď z tohto testu vyplynie konkrétny prínos. Časť **Ďalší krok** zobrazuje progres podľa uložených záznamov; počet potvrdených bločkov sám nepreukazuje správnosť OCR. Pripomienky ani automatické správy nie sú zapnuté.

## Integrácia do pôvodnej aplikácie a hranica pilotu

Blueprint `crm` je registrovaný aj v bežnej factory `app.create_app()`. Opakovane sa používajú existujúce modely `Client` a `Job`; nové tabuľky sú:

- `JobPlan` / `job_plans`: dohodnutá cena v centoch a termín zákazky.
- `JobReceipt` / `job_receipts`: súkromný originál, návrh, potvrdené údaje a revízia bločka.

Pripravená prídavná migrácia je `migrations/versions/d72c913f1b08_add_local_crm_receipts.py`, nadväzujúca na `631e160e6364`. **Jej aplikovanie na pôvodnú/produkčnú databázu nie je súčasťou lokálneho testu a zostáva na neskorší samostatný krok.** Nestačí iba zapnúť pôvodnú aplikáciu a otvoriť `/crm/` bez pripravených tabuliek.

Pred spojením pilotu s pôvodnou online aplikáciou treba vyriešiť existujúci starší tok `JobAttachment` v `jobs/routes.py`, ktorý ukladá prílohy do verejného `static/uploads/jobs/`. Samostatný VPS pilot tento starší tok nespúšťa a staré prílohy neobsahuje. Produkčné dáta sa nemigrovali. Nasadenie vytvára zálohu pred aktualizáciou; pravidelné automatické zálohovanie zatiaľ nie je implementované.
