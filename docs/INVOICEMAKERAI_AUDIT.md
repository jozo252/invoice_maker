# InvoiceMakerAI: technický a produktový audit

**Stav:** lokálny zdrojový strom 3. 10. 2026. Audit nadväzuje na [výskum pracovného postupu](ELECTRICIAN_WORKFLOW_RESEARCH.md). Nepotvrdzuje aktuálne nasadené vydanie ani obsah produkčnej databázy.

## 1. Rozsah a ochrana rozpracovanej práce

Repozitár je na vetve main, päť commitov za origin/main. Pred auditom už boli zmenené .gitignore, app.py, jobs/routes.py, models.py a tri šablóny; neversionované boli celý CRM pilot, migrácia d72c913f1b08, testy, dokumentácia pilotu a ďalšie súbory. Tieto zmeny nepochádzajú z tohto auditu. Nevykonal sa checkout, reset, presun, deploy ani zásah do databázy. Pri ďalšej práci sa musí porovnať aktuálny pracovný strom s pôvodným stavom a commitovať iba vlastné súbory. Existujúci [DEVELOPMENT_LOG.md](../DEVELOPMENT_LOG.md) opisuje historické nasadenia pilotu, nie živé overenie k dnešnému dňu.

## 2. Štruktúra, runtime a dátový model

| Vrstva | Skutočný stav | Dôsledok |
| --- | --- | --- |
| Web | Flask factory v [app.py](../app.py), SQLAlchemy, Flask-Migrate/Alembic, Flask-Login, CSRF, Flask-Mail; hlavné routes v [routes.py](../routes.py), [offers.py](../offers.py), [jobs/routes.py](../jobs/routes.py) | Základ je použiteľný, ale obchodný postup je rozdelený medzi viac route súborov. |
| UI | Jinja šablóny, Tabler/Bootstrap a samostatné mobilné CRM šablóny; [templates/base.html](../templates/base.html) ponúka paralelné menu pre fakturáciu, zákazky, CRM a tri AI nástroje | Používateľ vidí technické moduly namiesto jedného pracovného prípadu. |
| Hlavná DB | app.py riadky 34–36 používajú pevnú SQLite cestu invoices.db; modely sú v [models.py](../models.py) | Pre lokálnu fázu stačí, ale konfigurácia je pevná a izolácia pilotu sa nesmie potichu zlúčiť. |
| Migrácie | Postupnosť 253001ad2759 → f5ae5439d4b6 → 631e160e6364 → neversionovaná d72c913f1b08 pre JobPlan/JobReceipt | Test d72 migrácie existuje; nenasadzovať podľa predpokladu, že už beží na hlavnej DB. |
| AI | [ai.py](../ai.py), [aibot_routes.py](../aibot_routes.py), [assistant/agent.py](../assistant/agent.py), [assistant/tools.py](../assistant/tools.py), [crm/ai_receipts.py](../crm/ai_receipts.py) | Štyri čiastočne odlišné AI cesty; zjednocovať iba po meraní hodnoty a hraníc akcií. |
| CRM pilot | [crm_local.py](../crm_local.py) a [crm_pilot.py](../crm_pilot.py) používajú oddelené databázy a súkromné originály bločkov | Je to cenný inkrementálny základ, ale lokálne/online dáta a fakturačná DB sa nesynchronizujú. |

Existujúce entity: User, Company, Client, Invoice, InvoiceItem, InvoiceCounter, Lead, Offer, Job, JobNote, JobAttachment, EmailLog a v rozpracovanom CRM JobPlan, JobReceipt. Lead a Offer majú user_id bez cudzieho kľúča; Offer má company_id bez cudzieho kľúča. Client drží fakturačné údaje, ale chýba osobitné miesto realizácie. Invoice nemá job_id ani offer_id; Job nemá lead_id ani site_id. Ponuka má položky ako JSON, faktúra má relačné InvoiceItem. Cena v Offer je Numeric, avšak položky sa v častiach [offers.py](../offers.py) prevádzajú na float; Invoice a InvoiceItem používajú Float pre peniaze. Nový JobPlan/JobReceipt správne používajú celé centy. Ide o rozdielne peňažné reprezentácie, ktoré treba zjednotiť pri novom výpočte bez spätnej straty údajov.

## 3. Reálny tok dnes

1. Lead sa dá vytvoriť v offers.py riadky 319–350 iba s názvom, voľným opisom, menom a e-mailom. Hneď po uložení smeruje na AI generovanie ponuky. Nemá telefón, miesto, zdroj, termín ďalšieho kroku ani obhliadku.
2. Ponuka môže vzniknúť z leadu, AI textu, ručne alebo zo už existujúcej zákazky. Pri lead → ponuka existuje lead_id; pri job → ponuka existuje job_id. Výber klientskeho mena v ručnom formulári nie je stabilná väzba na Client. Pri uložení ručnej ponuky sa company_id v offers.py riadky 950–1023 iba prevedie na int, bez overenia vlastníctva firmy. Rovnaká kontrola chýba pri ceste generate-from-text. To je riziko priradenia cudzieho firemného záznamu.
3. Odoslanie ponuky nastaví status sent a tlačidlo mark_accepted nastaví accepted. [offers.py](../offers.py) riadky 743–771 potom stále povoľujú prepis tých istých položiek. Nie je verzia, čas/zdroj súhlasu ani zmrazený odsúhlasený rozsah. Označenie accepted nevytvorí Job.
4. Job sa tvorí samostatne v [jobs/routes.py](../jobs/routes.py) riadky 37–94, prípadne v CRM. Nová kontrola vlastníctva Client/Company v jobs/routes.py má dobrý smer. Job obsahuje stav, poznámky a všeobecné prílohy, nie rozpočet, miesto, úlohy či zmeny rozsahu. JobPlan v CRM pridáva dohodnutú cenu a termín.
5. Z Offer vedú dve cesty k náhľadu faktúry (offers.py riadky 475–579), nie jedna transakčná služba. Jedna cesta dohľadáva Client podľa e-mailu/mena a prevádza položky cez float. Invoice z [routes.py](../routes.py) riadky 783–925 sa vytvára osobitne s vlastnou validáciou. Chýba trvalá väzba faktúra → schválená ponuka/zákazka, takže sa nedá spoľahlivo ukázať, čo je vyfakturované a čo ostáva.
6. Nové CRM vie vytvoriť Client/Job, pridať časované poznámky, vyfotiť bloček a po ručnom potvrdení započítať náklad. Text sa dá nadiktovať do upraviteľného poľa, ale hlas sa neukladá automaticky. Prehľad zobrazuje dohodnutú cenu mínus potvrdené bločky; nie zisk, lebo chýbajú hodiny, doprava a subdodávky. [README_CRM.md](../README_CRM.md) tento limit správne pomenúva.

Text pri offers.py riadku 1096 obsahuje ďalšiu definíciu convert_offer_to_invoice iba v trojitom komentári; nejde o aktívnu duplicitnú route. Aktívna duplicita je viac paralelných postupov na vytvorenie a prepočet ponuky/faktúry.

## 4. Čo zachovať a kde je dlh

| Zachovať | Prečo | Čo upraviť |
| --- | --- | --- |
| Client, Company, Invoice, PDF, čísla faktúr a kontroly vlastníka | Už riešia fakturačné jadro a používateľské dáta | Pridať stabilnú väzbu na zákazku a auditovať sumy, DPH, stav platby a opravy vydaných dokladov. |
| Job, JobNote a jednoduchú pracovnú kartu | Nízka cena vstupu v teréne | Doplniť miesto, ďalší krok, termíny a schválený rozsah bez ďalšej paralelnej karty. |
| CRM originál bločka, SHA-256, potvrdenie, revíziu a celé centy | Dobré riešenie rizika OCR a súbežnej opravy | Rozšíriť náklady o typ, prípadne rozdelenie medzi zákazky až keď to vyžadujú reálne doklady. |
| Asistentove owner-filtered čítacie tools | Hľadanie zákaziek a faktúr už má rozumnú hranicu | Každý nový zápis viesť cez aplikačnú službu, nie priamy ORM zápis z LLM; odoslanie ponechať človeku. |
| Alembic a existujúce testy pilotu | Umožňujú inkrementálne zmeny | Doplniť testy celého toku lead → ponuka → zákazka → faktúra a migračný test nových tabuliek. |

## 5. Riziká zoradené podľa naliehavosti

**Bezpečnosť a dáta:** Staré JobAttachment ukladá súbory do [static/uploads/jobs](../jobs/routes.py) a aplikácia ich podáva staticky; kontrola vlastníka pri nahraní nechráni URL originálu. Nová elektrická fotodokumentácia tam nemá ísť. Pôvodné súbory by pri migrácii potrebovali inventúru a súkromné úložisko. V [routes.py](../routes.py) je GET /test_email bez prihlásenia a spúšťa odoslanie testovacieho e-mailu. Dve POST cesty ReplyBotu v [aibot_routes.py](../aibot_routes.py) nemajú login_required (CSRF ochranu factory majú); neprihlásený návštevník môže potenciálne čerpať AI službu. app.py načítava poštové hodnoty bez bezpečných predvolených hodnôt, takže štart/test factory môže zlyhať, ak chýbajú premenné. Opravu týchto bodov treba izolovať a regresne otestovať pred širším vystavením aplikácie.

**Spoľahlivosť a účtovníctvo:** send_invoice_email v routes.py riadky 425–515 vracia text o zlyhaní namiesto výnimky, zatiaľ čo route riadky 410–422 po každom návrate ukazuje úspech. Pri prevádzke tak môže vzniknúť falošné potvrdenie odoslania. Faktúry majú len stav paid/unpaid/canceled/accepted, nie samostatné Payment a čiastočné úhrady. DPH a suma sa skladajú na viacerých miestach. Po vystavení faktúry je k dispozícii edit a delete; pred zmenou pravidiel potrebujeme presne určiť stavy návrh/vydané/storno a účtovnú politiku pre danú krajinu.

**Architektúra/UX:** Kód mieša HTTP, validáciu, ceny, DB commit, PDF a odoslanie. Offer a Invoice používajú odlišné schémy položiek, čo komplikuje jeden zdroj pravdy. Pri Job stave je ľubovoľné prepnutie bez kontroly prechodu alebo existencie schválenej ponuky. Sidebar ukazuje CRM, prehľad, zákazky, ponuky, faktúry, klientov a samostatné AI nástroje; v mobile to znamená viac vetiev, než je potrebné na rýchly záznam. Rozdiel medzi lokálnou, pilotnou a hlavnou DB je prevádzkové riziko pri neskoršom zlúčení; bez exportu a mapovania identít sa nesmú dáta kopírovať podľa ID.

## 6. Testy a úroveň overenia

Na lokálnom pracovnom strome prešlo 77 Python unittest testov (tests.test_crm, tests.test_crm_ai, tests.test_crm_pilot) a 29 Node testov poznámok/OCR/UI. V Python výstupe sú deprecation/resource warningy a očakávaný log pri negatívnom upload teste. Testy overujú CRM pilota vrátane izolácie používateľov, potvrdenia bločka, súbežných zmien a roundtrip migrácie d72; **neoverujú celý pôvodný fakturačný/ponukový postup ani nasadený VPS**. V tejto fáze neboli vykonané produkčné čítania ani zápisy.

## 7. Rozhodnutie auditu

Nezačínať rewrite. Existujúce jadro je dostatočné na inkrementálny pilot, ale ďalšia AI funkcia by teraz neznížila hlavný počet prepisov. Prvý produktový problém je stabilný prípad s klientom a miestom, prechod z prijatej ponuky do zákazky a faktúra naviazaná na odsúhlasený rozsah. Pred používaním reálnych fotiek treba vyriešiť súkromie JobAttachment. Presný návrh je v [gap analýze](GAP_ANALYSIS.md), [architektúre](DOMAIN_ARCHITECTURE.md) a [roadmape](ROADMAP.md).
