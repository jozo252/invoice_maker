# Denný vývojový súhrn — InvoiceMakerAI CRM

## 2026-09-22 — Karty zákaziek a detail (lokálne)

- Na výslovnú žiadosť používateľa sa prehľad `/crm/` zmenil z riadkov na responzívne karty. Celá karta otvára existujúci detail vlastnej zákazky; ukazuje stav, zákazníka, termín, dohodnutú cenu a potvrdené náklady.
- Detail má prehľadnejšie usporiadané dostupné údaje vrátane telefónu aj e-mailu, poznámok, bločkov a zmeny stavu. Nezadanej cene sa hovorí „Nezadaná“, aby sa nemýlila s nulovou cenou.
- Overenie: 26 testov `test_crm.py` a 20 testov `test_crm_pilot.py` prešlo. Jednorazový test s dočasnou databázou potvrdil dve vlastné karty, odkazy do detailu, skrytie cudzej zákazky a dostupné údaje v detaile. Syntetický desktopový náhľad pri 1440 px bol vizuálne skontrolovaný. Úzky mobilný viewport nebol spoľahlivo vizuálne potvrdený; responzívne pravidlá boli upravené podľa zisteného orezávania v headless snímke.
- Zmena je iba v lokálnych súboroch. Nebola nasadená na VPS ani prepojená s produkčnými faktúrami. Ponuky a pracovné fotky ešte nie sú v tomto detaile; pôvodný tok príloh ukladá súbory do verejného `static` a vyžaduje bezpečné prerobenie.
- Najbližší krok: overiť karty a detail v skutočnom mobilnom prehliadači, potom riešiť ponuku priradenú k zákazke a súkromné pracovné fotky. Reálne bločky a pravidelné zálohy zostávajú otvoreným overením pilotu.

### Pokračovanie: priebežné poznámky a hlasový prepis

- Detail zákazky teraz prijíma samostatné priebežné poznámky do existujúcej tabuľky `job_notes`. Zápis aj čítanie kontrolujú vlastníka zákazky a poznámky; text má limit 3 000 znakov a pri neplatnom zápise zostáva rozpracovaný text vo formulári. Úvodný popis zákazky zostáva oddelený.
- V podporovanom bezpečnom prehliadači je skúšobné tlačidlo na diktovanie po slovensky (`sk-SK`). Finálny prepis sa vloží do upraviteľného textu; audio sa v aplikácii neukladá a poznámka sa uloží až po ručnej kontrole a stlačení tlačidla. Ručné písanie funguje aj bez podpory hlasu. UI upozorňuje, že prehliadač môže zvuk spracovať online.
- Overenie: 29 lokálnych CRM testov a 20 testov VPS pilotnej factory prešlo. Nové testy potvrdili zápis, odmietnutie prázdnej a dlhej poznámky so zachovaním textu, izoláciu cudzej zákazky a blokovanie novej routy bez prihlásenia. Štyri Node testy pre hlasový prepis prešli: fallback, finálny výsledok presne raz bez automatického uloženia, chyba siete a zastavenie. `node --check` prešiel.
- Hlas na reálnom mikrofóne a presnosť slovenčiny na telefóne zatiaľ neboli overené. Funkcia je iba v lokálnom kóde, bez nasadenia na VPS. Najbližší test: päť krátkych slovenských pracovných poznámok na vlastnom telefóne, kontrola textu pred uložením a posúdenie, či šetrí čas oproti písaniu.

## 2026-09-16

**Aktuálny míľnik:** zákazník → zákazka → bloček → automatický návrh ceny → kontrola človekom → potvrdený náklad. Účelom je overiť praktické používanie v lokálnom pilote.

### Zmeny

- Vývoj CRM pre remeselníkov pokračuje v existujúcom Flask projekte `invoice_maker`. Zákazníci a zákazky používajú modely `Client` a `Job`.
- Pridaný blueprint `crm` s prehľadom zákaziek, zákazníkmi, založením zákazky, zmenou stavu, nahrávaním bločkov, potvrdením/opravením údajov a stránkou ďalšieho kroku.
- Pridaný `JobPlan`: voliteľná dohodnutá cena v centoch a termín. Pridaný `JobReceipt`: stav `draft` alebo `confirmed`, údaje bločka, privátny originál a revízia.
- Pripravená prídavná migrácia `d72c913f1b08` nadväzujúca na `631e160e6364`. Nové modely nepridávajú vzťahy do existujúceho `Job`, ktoré by staré fakturačné obrazovky nútili pristupovať k novým tabuľkám.
- Oddelený lokálny vstup `crm_local.py` a spúšťač `Spustit CRM.cmd` používajú `instance/crm_local/crm.sqlite3`, `private_receipts/` a `session.key`. Server beží na `127.0.0.1:5180`; spúšťač otvára prehliadač až po pripravenosti a vie použiť už bežiaci pilot.
- Lokálne OCR používa Tesseract.js 7 so slovenskými a anglickými dátami. Skript `scripts/prepare_receipt_ocr.py` pripraví statické súbory z existujúcich balíkov pôvodného prototypu.
- Vznikol `README_CRM.md` s praktickým spustením, prvým testom a hranicami lokálneho pilotu.

### Chyby a riziká ošetrené v implementácii

- OCR samo nezapisuje potvrdený náklad. Potvrdenie musí prejsť kontrolou servera; do súčtov vstupujú iba `confirmed` záznamy.
- Peniaze sa ukladajú ako celé centy. Neplatné dátumy a sumy sa odmietajú; parser odlišuje celkovú sumu od DPH, hotovosti, výdavku a medzisúčtu a pri nejasnosti vyžaduje ručné zadanie.
- Originály sú mimo `static` a sprístupňujú sa cez kontrolu vlastníka. Názov nahratého súboru sa nepoužíva ako cesta uloženia.
- Opakovaný rovnaký súbor u toho istého používateľa nevytvorí ďalší náklad; deduplikáciu podporuje hash aj unikátne pravidlo databázy.
- Revízia bločka bráni prepísaniu novšej opravy starým formulárom. Pri konflikte sa vyžaduje porovnanie údajov.
- Overujú sa skutočné obrázkové dáta, nie iba prípona: jednotlivé JPEG/PNG/WebP do 8 MB a 30 MP. HEIC, PDF a animované obrázky sa neprijímajú.
- Lokálny pilot kontroluje adresu a hostiteľa, chráni formuláre CSRF a kontrolou pôvodu požiadavky. Automatické lokálne prihlásenie nie je určené na online prevádzku.

### Overenie

- **26 Python testov: úspešných.** Potvrdený beh lokálnych regresných testov CRM s dočasnými dátami.
- **8 Node testov: úspešných.** Potvrdený beh parsera súm, dátumov a textu bločkov.
- **Celý postup v prehliadači so syntetickým bločkom: úspešný.** Vytvorený zákazník a zákazka s cenou 1 250,00 €. OCR načítalo predajcu TEST Elektro, dátum 16. 9. 2026 a sumu 18,40 €. Po kontrole a potvrdení sa náklad započítal presne raz; opakovaný upload otvoril ten istý záznam. Údaje aj prihlásenie zostali zachované po reštarte servera. Formulár overený pri šírke 390 px.
- Syntetické QA záznamy boli po overení odstránené iba z oddeleného pilotu. Obnoviteľná kópia skúšobných dát je vo `work/qa-before-cleanup/`, databáza prešla `PRAGMA quick_check`. Pilot je pripravený bez skúšobných zákaziek.
- **Skutočné používateľove bločky:** zatiaľ neoverené. Testy parsera ani syntetický obrázok nedokazujú presnosť OCR na fotografiách z praxe.
- Vyššie lokálne overenie nepotvrdzuje nasadenie, migráciu produkčnej databázy, odoslanie správ ani cloudovú synchronizáciu. Neskoršie nasadenie samostatného VPS pilotu je zaznamenané nižšie.

### Rozhodnutia

- Hlavný produktový smer je **InvoiceMakerAI → CRM pre remeselníkov**. Samostatný prototyp **Dielňa** sa zachováva; jeho nainštalované OCR balíky sa používajú ako lokálny zdroj. Synchronizácia ani migrácia jeho dát sa teraz nerobí.
- Prvý pilot je iba lokálny, bez externého OCR/AI API a bez nákladov za jednotlivé čítania cez API. Pôvodná produkčná factory sa pri lokálnom spustení nepoužíva.
- Prvá verzia číta celkovú sumu, dátum a predajcu. Rozpis položiek, účtovná evidencia DPH, cudzie meny a dobropisy sú mimo tohto míľnika.
- Rozdiel medzi dohodnutou cenou a bločkami sa označuje ako zostatok pred ďalšími nákladmi, nie ako čistý zisk.
- Progres má vychádzať z konkrétnych uložených výsledkov. Nové AI funkcie majú počkať na zistenia z reálneho používania.

### Otvorené body a hranice

- Overiť rýchlosť a presnosť OCR na piatich vlastných bločkoch; aktuálne nepoznáme jeho praktickú úspešnosť.
- Deduplikácia je podľa rovnakých bajtov súboru. Dve rôzne fotografie toho istého papierového bločka môžu vytvoriť dva záznamy.
- Automatické zálohovanie nie je implementované. Lokálne dáta zatiaľ zostávajú na tomto počítači.
- Migrácia nových tabuliek do pôvodnej/produkčnej databázy zostáva na neskorší samostatný krok. Existujúca lokálna databáza sa cez `--init` automaticky nemigruje.
- Starý tok `JobAttachment` stále používa verejný `static/uploads/jobs/`. Pred online vydaním treba riešiť jeho súkromie aj existujúce súbory; nové CRM to neopravuje automaticky.

### Najbližšie konkrétne kroky

1. Spustiť `Spustit CRM.cmd`, založiť jednu vlastnú zákazku a nahrať päť skutočných bločkov.
2. Pri každom zaznamenať správnosť navrhnutej sumy pred opravou, čas do potvrdenia a nutné opravy. Ručné prepisovanie rovnakých údajov použiť ako porovnanie.
3. Používať pilot tri pracovné dni a zapísať jednu najväčšiu prekážku. Opraviť túto prekážku pred rozširovaním funkcií.
4. Ukázať overený postup jednému remeselníkovi a zistiť, či mu šetrí čas a či by ho používal pri ďalšej zákazke.

Pri ďalšom pokračovaní pridať nový denný záznam: čo sa zmenilo, čo sa skutočne overilo, otvorený problém, rozhodnutie a jeden najbližší konkrétny krok. Plán sa neoznačuje za hotový výsledok.

### Pokračovanie: mobil a VPS

- Používateľ chce prístup aj cez mobilné dáta a uprednostnil existujúci VPS pred dočasným tunelom. Cloudflare tunel sa nespustil a nevytvoril sa žiadny nový hostingový účet.
- Live kontrola potvrdila VPS `vps-gallax`, bežiacu `invoice.service` a HTTPS doménu `invoicemakerai.com`. CRM je nasadené ako samostatná služba na loopback porte 8098 pod URL `/remeselnici/`, bez zmeny produkčnej databázy fakturácie.
- Pridaná factory `crm_pilot.py`: explicitné HTTPS/prefix/proxy pravidlá, prístupový kód, CSRF, ochrana originálov, secure cookie s vlastnou cestou, odhlásenie a limit 20 pokusov za minútu. Automatické lokálne prihlásenie sa v online pilote nepoužíva.
- OCR cesty sa generujú podľa prefixu. Pridaný limit 500 MB fotografií pilotu a kontrola rezervy voľného miesta 256 MB. Existujúce rovnaké bločky sa otvoria aj pri dosiahnutom limite úložiska.
- Pripravený balík s výslovným zoznamom povolených súborov a SHA-256 manifestom, samostatné runtime závislosti, systemd služba a úzka nginx cesta. Balík neobsahuje `.env`, lokálne databázy, privátne bločky ani pôvodné prílohy zákaziek.
- **Overenie: 46 Python + 8 Node testov úspešne** v oddelenom runtime s Flask 3.1.3. `pip check` úspešný. Z toho 20 testov preveruje online autentifikáciu, proxy, CSRF/Origin, cookies, limity a úložisko.
- **VPS nasadenie úspešné:** `https://invoicemakerai.com/remeselnici/`, vydanie `20260916T174607305609Z`, služba `crm-pilot.service` aktívna a zapnutá po štarte VPS. Pôvodná `invoice.service` zostala aktívna s rovnakým MainPID `3927642`; hlavná fakturačná stránka vrátila HTTP 200. Produkčná factory, databáza a nastavenia fakturácie sa nemenili.
- Prvý pokus sa bezpečne vrátil späť po verejnej HTTP kontrole pred dokončením nginx reloadu. Installer teraz počká na presný verejný health marker najviac 20 sekúnd. Vypnutý nepotrebný Gunicorn control socket, ktorý skúšal písať do systémového účtu `/nonexistent`. Druhé nasadenie prešlo vrátane 20 online testov na Linuxe.
- **Prehliadač na verejnom HTTPS:** prístupový kód, založenie zákazníka a zákazky za 1 250 €, nahratie syntetického bločka, OCR TEST Elektro / 16. 9. 2026 / 18,40 €, explicitné potvrdenie a správny zostatok 1 231,60 €. Formulár overený pri šírke 390 px bez vodorovného presahu; bez chýb OCR/CSP v konzole. Odhlásenie prešlo; neprihlásený prístup k originálu otvoril prihlasovaciu stránku.
- Kód zostáva vo verziovaných `releases/`, runtime vo `runtimes/` a údaje mimo nich v `/srv/crm-pilot/shared/`. Záloha pred úspešným nasadením: `/srv/crm-pilot/backups/20260916T174607305609Z-d8c75356`. Prístupový kód sa nezapisuje do dokumentácie ani archívu kódu. Lokálny pilot a VPS sa nesynchronizujú.
- Syntetický VPS zákazník, zákazka, plán a bloček boli po presných kontrolách ID/názvu/vlastníka/hasha odstránené v jednej transakcii. Záloha: `/srv/crm-pilot/backups/qa-20260916T174932Z-0g_cxfs6`; pôvodný skúšobný obrázok zostal iba v privátnom úložisku bez dostupného záznamu. Databáza prešla `quick_check` aj `foreign_key_check`. Po reštarte iba CRM služby prešlo prihlásenie, prehľad ukázal 0 zákaziek a 0 € nákladov, verejný health vrátil 200 a pôvodný InvoiceMaker si zachoval MainPID.
- Najbližší produktový test zostáva jedna vlastná zákazka a päť reálnych bločkov; ich presnosť OCR zatiaľ nie je overená.

### Pokračovanie: automatické AI čítanie bločkov a faktúr

- Používateľ potvrdil úspešný upload faktúry a požiadal o API čítanie sumy. Pridané serverové OpenAI Responses API s modelom `gpt-4.1-mini-2025-04-14` a striktne štruktúrovaným návrhom predajcu, dátumu a celkovej sumy vrátane DPH. Faktúra používa dátum vystavenia a sumu na úhradu; samotná DPH, základ, hotovosť či výdavok sa nemajú považovať za celkovú sumu.
- API kľúč už existoval v tomto projekte. Bez výpisu bol prenesený cez SSH stdin do `/srv/crm-pilot/shared/openai-api.key`, oprávnenia 0400 a vlastník `crm-pilot`. GET overenie modelu prešlo bez plateného volania. Produkčná `.env`, fakturačná databáza ani služba sa nemenili. Kľúč nie je vo fronte, archíve ani dokumentácii.
- AI sa spúšťa po otvorení rozpracovaného bločka. Endpoint vyžaduje vlastníka, vlastnú zákazku, CSRF, Origin a aktuálnu revíziu. Posiela overený originál pripravený ako JPEG do 2048 px; bez EXIF, verejného URL, redirectov, nástrojov a automatických sieťových retry. API používa `store:false`.
- AI návrh nikdy nemení `JobReceipt` ani potvrdené náklady. Kontrola človeka a potvrdenie zostávajú povinné. Zmena revízie počas API blokuje výsledok; UI zachová ručné úpravy a potvrdený bloček automaticky nečíta.
- Oddelené privátne `ai-state.sqlite3`: cache podľa vlastníka/hasha/modelu/verzie promptu, atómová rezervácia volania, maximálne 30 pokusov za deň UTC a 6 za minútu. Aj neisté alebo zlyhané volanie sa počíta. Retry po zlyhaní má odstup 60 sekúnd, pending rezervácia 90 sekúnd. Rovnaký úspešne načítaný súbor nemá ďalšie platené volanie.
- Pri nečitateľnej sume alebo nepotvrdenej EUR mene sa suma nenavrhuje. Dobropisy majú ručnú kontrolu. Pri nedostupnej AI nasleduje pôvodné čítanie v prehliadači a možnosť ručného zadania; fotografia a formulár zostanú zachované.
- **Testy: 67 Python + 8 Node úspešne.** Nových 21 AI testov používa iba mockované API a dočasné dáta. Navyše prešlo 11 UI mock scenárov a 4 renderovania šablóny, vrátane ručných editácií, zrušenia čítania, sekvenčného fallbacku a URL prefixu. Dva ďalšie UI scenáre overili, že potvrdený doklad sa automaticky nečíta, ale explicitné tlačidlo posiela `manual:true` a iba navrhuje opravu.
- Po nasadení bolo zistené, že používateľ už svoj doklad ručne potvrdil. Preto je doplnené výslovné AI opätovné čítanie aj potvrdeného dokladu cez tlačidlo; vyžaduje `manual:true`, aktuálnu revíziu a opätovné potvrdenie opravy. Samotné čítanie nezmení existujúci náklad.
- **VPS aktualizácia úspešná:** finálne vydanie `20260916T180855975999Z`, záloha `/srv/crm-pilot/backups/20260916T180855975999Z-33138d4c`. Pred prepnutím prešlo 41 online/AI testov v Linux runtime. CRM aktívne/enabled, verejný HTTPS health 200; pôvodná `invoice.service` zostala aktívna s MainPID `3927642`. Existujúca zákazka a používateľom potvrdené údaje zostali zachované.
- **Skutočné API čítanie na verejnom HTTPS prešlo:** syntetická fotografia automaticky navrhla TEST Elektro, dátum 2026-09-16 a sumu 18,40 €. Po kontrole sa náklad potvrdil obvyklým formulárom. Následné explicitné AI načítanie už potvrdeného skúšobného dokladu prešlo z cache bez zmeny revízie či nákladu; stav stále `confirmed`, revízia 1, suma 1840 centov. Privátny AI report potvrdil presne jedno API volanie, jeden úspech a jeden výsledok cache aj po aktualizácii a reštarte. Mobilná šírka 390 px bez vodorovného presahu, bez konzolových chýb.
- Skúšobný klient/zákazka/plán/bloček boli odstránené úzkym overeným postupom pri zastavenej CRM službe. Obnoviteľná záloha `/srv/crm-pilot/backups/qa-20260916T181038Z-e1gl2sbc`, privátny skúšobný originál a cache zostali zachované. `quick_check` a `foreign_key_check` prešli. Po reštarte prehľad obsahoval iba používateľovu existujúcu zákazku a náklady. Kľúč má overené oprávnenia 0400 a AI state 0600, vlastník `crm-pilot`.
- Existujúcu používateľovu faktúru sme pri testoch neposielali do API. Na jej opätovné čítanie stačí obnoviť mobilnú stránku a v detaile stlačiť **Načítať údaje znovu**. Presnosť na tomto doklade a ďalších reálnych fotografiách musí overiť používateľ porovnaním s originálom.

### Pokračovanie: pôvodná suma zostala po čiastočnom AI výsledku

- Používateľ nahlásil, že po opätovnom čítaní zostala suma 1 000 €. Priamy priechod jeho záznamom a úzka read-only kontrola potvrdili `amount:null` a `receipt_date:null` v AI cache; zobrazených 1 000 € pochádzalo z predchádzajúceho potvrdeného nákladu. Predajca sa doplnil, ale chýbajúci návrh sumy formulár preskočil bez jasného označenia pôvodu starej hodnoty.
- Originál je pokyn k platbe s jednou čiastkou, bez viditeľnej meny a bez dátumu vystavenia; má iba dátum splatnosti. Preto nesmie byť automaticky označený za faktúru, doklad o zaplatení ani EUR náklad s dátumom vystavenia odvodeným zo splatnosti.
- Backend `receipt-total-v2` rozlišuje `payment_instruction` a vracia samostatný overený kladný `detected_amount`, menu a typ dokladu. `amount` zostáva prázdny, keď EUR nie je výslovne uvedené. Pokyn k platbe označuje sumu na platbu, nie celkovú sumu faktúry. Cudzia mena sa nekonvertuje. Prompt obsahuje iba všeobecné pravidlá, bez konkrétneho správneho výsledku používateľovho dokumentu.
- Cache v2 je oddelená od starého výsledku; existujúce pokusy, limit, potvrdený náklad a fotografia zostávajú zachované. AI endpoint nemení nijaký stĺpec pôvodného nákladu.
- UI pri sume zobrazí prečítaný návrh a odlíši ho od pôvodnej alebo ručne zadanej hodnoty. Neznámu menu možno výslovne potvrdiť ako EUR tlačidlom; prevzatie návrhu neukladá náklad. Platná známa EUR suma sa vloží automaticky, ak používateľ medzitým pole neupravil. Nové opätovné ručné čítanie chráni úpravy od začiatku aktuálneho čítania a neponechá starý príznak editácie navždy.
- Čítanie v prehliadači neoznačuje sumu bez viditeľného EUR pri celkovej sume za potvrdené EUR. Parser ignoruje dátum splatnosti/dodania pri hľadaní dátumu bločka alebo vystavenia.
- **Lokálne overené: 74 Python testov a 10 testov parsera úspešne.** Z toho 28 AI testov používa iba mockované API; overujú pokyn k platbe, neznámu/cudziu menu, cache v2 aj nezmenený potvrdený náklad so všetkými stĺpcami. UI regresie a živé nasadenie sa dokončujú; tento záznam ich zatiaľ neoznačuje za úspešné.
- **15 trvalých UI regresných testov úspešne** (`tests/receipt-ui.test.cjs`), spolu 25 Node testov. Pokrývajú starú sumu pri `amount:null`, výslovné EUR prevzatie návrhu bez uloženia, neznámy dátum, cudziu menu a dobropisy, predošlú a súbežnú ručnú editáciu, POST zachovanie, revíziu, zrušenie, automatický draft, ručné čítanie potvrdeného dokladu aj fallback do OCR. `git diff --check` prešiel. Živé nasadenie a čítanie pôvodného obrázka nasledujú po týchto kontrolách.
- **VPS oprava úspešne nasadená:** vydanie `20260916T182351789985Z`, záloha `/srv/crm-pilot/backups/20260916T182351789985Z-fdf21ed1`. Preflight potvrdil 43 povolených súborov a žiadnu potrebnú zmenu nginx. Pred prepnutím prešli online/AI testy z aktuálneho kompozitného súboru (20 + 28); verejný health a pôvodná domovská stránka prešli, MainPID pôvodnej `invoice.service` zostal rovnaký.
- **Skutočný nahlásený obrázok prešiel AI čítaním:** prečítaná čiastka `108.00`, `document_type:payment_instruction`, `currency:null`, `receipt_date:null`, bezpečný EUR `amount:null`. UI zobrazuje 108,00 pri pôvodných 1 000 € a výslovné tlačidlo EUR. Read-only kontrola po prvom aj opakovanom kliknutí potvrdila presne jeden v2 API pokus/úspech a návrh v cache; druhé čítanie nepridalo platené volanie. Pôvodný náklad zostal `confirmed`, revízia 1, 100000 centov a nezmenený dátum. Automatické uloženie ani potvrdenie meny nevykonal agent.
- **Mobilná kontrola pri 390 px úspešná:** dokument aj viewport mali šírku 375 px, bez vodorovného presahu; čitateľný návrh a výslovné tlačidlo EUR pri sume, informácia o nepotvrdenom dátume vystavenia a vypnuté uloženie bez kontroly. Konzola bez chýb. Overenie presnosti na ďalších reálnych bločkoch zostáva otvorené.

## 2026-09-17 — plán na zajtra

**Stav: plán, zatiaľ nevykonané.** Cieľ dňa: spoľahlivo používať mobilný tok bloček → návrh → kontrola → uložený náklad na jednej zákazke. Nasledujúce úlohy nie sú naplánovaným automatickým spustením ani pripomienkou.

1. **Overiť päť vlastných EUR dokladov na mobile (používateľ + spoločná kontrola, približne 20–30 minút).** Začať kontrolou dnešnej opravy na existujúcom pokyne k platbe: návrh čiastky a označenie neznámej meny sa musia odlíšiť od pôvodného nákladu. Pokyn sám nepotvrdzuje zaplatenie. Potom skúsiť päť bežných EUR bločkov/faktúr, z toho aspoň jednu dodávateľskú faktúru. Originál porovnať s predajcom, dátumom a celkovou sumou; pri každom zapísať správnosť prvého návrhu, čas do uloženia a nutné opravy. Porovnať čas s ručným zápisom. Po uložení a obnovení stránky musí sedieť detail aj súčet zákazky. Opakovaný rovnaký upload musí otvoriť existujúci záznam a náklad sa započíta iba raz; rozpracovaný návrh súčet nezmení.
2. **Opraviť jednu najväčšiu zistenú prekážku (vývoj, približne 60 minút).** Prioritu určí skutočný výsledok testu, nie ďalšia nová funkcia. Ak stále mätie stará suma oproti návrhu, zjednodušiť zobrazenie pôvodu a prevzatie návrhu. Ak čítanie vyberá nesprávnu sumu alebo dátum, opraviť konkrétny prípad a overiť ochranu ručných opráv. Pracovný cieľ pilotu: aspoň štyri z piatich jednoznačných EUR dokladov so správnou sumou bez ručného prepisovania; ak sa cieľ nesplní, ďalšie rozšírenia odložiť. Päť dokladov nepreukazuje všeobecnú presnosť AI.
3. **Krátke praktické demo jednému remeselníkovi (používateľ, približne 10–15 minút).** Na oddelených skúšobných dátach a anonymizovanom doklade nechať remeselníka počas osobného dema založiť zákazku a potvrdiť bloček. Zistiť, či by ho použil pri ďalšej zákazke a ktorá časť mu šetrí čas; zaznamenať aj miesto, kde potrebuje vysvetlenie. Kontaktovanie ani odosielanie ukážok nie je týmto plánom vykonané.
4. **Pripraviť pravidelnú zálohu, nacvičiť obnovu a uzavrieť denný log (vývoj, približne 30–60 minút).** Existujúce zálohy pred nasadením sú východiskom; denná záloha zatiaľ nie je zavedená. Riešenie má pokryť konzistentnú databázu pilotu aj privátne originály a potrebnú konfiguráciu, uchovať časť kópií mimo toho istého VPS a nevystaviť tajné údaje. Obnovu overiť v oddelenom úložisku, bez prepísania živých dát. Spôsob, cieľ uloženia a rozsah prístupu konkretizovať pred zavedením; žiadnu novú platenú službu automaticky neobjednávať. Zapísať namerané výsledky, vykonanú opravu, stav záloh a jedinú ďalšiu prioritu.

**Na tento deň odložené:** ďalší veľký modul CRM, automatické e-maily, platené nástroje a redizajn. Priame PDF/HEIC riešiť až keď mobilný test potvrdí, že sú hlavným zdrojom zbytočného prepisovania alebo screenshotov.

## 2026-09-22 — karty, poznámky a hlasový prepis na VPS

- Na výslovnú žiadosť používateľa bolo vydanie `20260922T055602851251Z` nasadené na `https://invoicemakerai.com/remeselnici/`. Obsahuje karty zákaziek s otvorením celého detailu, samostatné priebežné poznámky a tlačidlo na prepis slovenčiny do upraviteľného poľa. Uloženie prepisu zostáva ručným krokom.
- Balík má 44 súborov z výslovného zoznamu a súhlasné SHA-256 lokálne aj na VPS. Pred prepnutím prešiel read-only preflight, následne installer spustil vlastné testy a vytvoril zálohu `/srv/crm-pilot/backups/20260922T055602851251Z-7e104c33`. Pred vydaním prešlo lokálne 77 Python a 29 Node testov.
- Po nasadení je `crm-pilot.service` aktívna. Verejné `/remeselnici/health` a login vracajú HTTP 200, neprihlásené CRM HTTP 302 na login a pôvodná fakturačná stránka HTTP 200. `invoice.service` ostala aktívna s nezmeneným MainPID `3614610`.
- Autentifikovaná in-process skúška iba na čítanie proti nasadenému kódu a živej databáze vrátila HTTP 200 pre zoznam kariet, detail existujúcej vlastnej zákazky a `job-notes.js`; v HTML bol odkaz na kartu, sekcia poznámok, hlasové tlačidlo aj skript. Použila izolované syntetické prihlásenie, nemenila živé údaje. Živá aj záložná SQLite databáza majú `PRAGMA quick_check=ok`, správnu schému `job_notes` a rovnaké počty 1 zákazka, 0 priebežných poznámok, 1 doklad.
- Skutočné uloženie poznámky používateľom a mikrofón na mobile zatiaľ nie sú overené; presnosť a dostupnosť prepisu závisia od prehliadača. Ďalší krok: používateľ otvorí vlastnú zákazku na mobile, uloží jednu poznámku a vyskúša päť krátkych diktátov s kontrolou textu.
