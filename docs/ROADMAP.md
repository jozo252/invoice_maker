# Roadmapa InvoiceMakerAI pre elektrikára

**Stav 3. 10. 2026:** výskum a audit sú zdokumentované; prvý lokálny P0 tok je implementovaný a otestovaný na dočasnej DB. Presné hranice sú v [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). Terénne rozhovory a test na vlastných zákazkách ešte neprebehli. Tento plán nie je tvrdenie, že trh alebo úspora sú validované.

## Brána pred vývojom pracovného systému

Do 14 dní získať tri anonymizované alebo vlastné prípady: malý servis, rekonštrukciu a viacdňovú prácu. Pre každý: pôvodný dopyt, podklady, obhliadku, kalkuláciu/ponuku, zmeny, nákup, odovzdanie, faktúru a čas administratívy. Urobiť 5–8 krátkych rozhovorov s elektrikármi 1–5 členných firiem v SK/CZ; ak má DACH byť prvý trh, pridať aspoň 1–2 AT/DE. Jednu rovnakú zákazku skúsiť v jednoduchom existujúcom nástroji a porovnať kroky a čas. Nemusí ísť o predajný výskum, ale o rozhodnutie, či systém šetrí skutočnú prácu.

**Stop/pivot:** ak tri prípady neukážu opakovaný prepis alebo stratu pri kalkulácii/zmene/faktúre, ďalej nestavať všeobecný pracovný systém. Zachovať užitočný CRM pilot a doplniť len konkrétny chýbajúci krok, prípadne použiť existujúci nástroj. Ak sa problém potvrdí, pokračovať postupne.

## P0 — základ, bez ktorého nemožno veriť toku

| Inkrement | Prečo teraz | Hotové, keď | Test/vrátenie |
| --- | --- | --- | --- |
| P0.0 Bezpečné hranice | staré verejné prílohy, otvorený test email, nechránené ReplyBot POST, falošný výsledok send_invoice_email | neprihlásený nedostane cudzie dáta ani AI náklad; e-mail úspech má potvrdenie alebo chybu; nové elektro fotky nejdú do static | route/owner testy; žiadne mazanie historických súborov |
| P0.1 Kanonický prípad a miesto | údaje sa dnes prepisujú a miesto práce sa zamieňa s fakturačnou adresou | nový Lead nesie kontakt, miesto, typ, zdroj, stav a dátum ďalšieho kroku; klient/miesto sa vyberie alebo vytvorí raz | create lead, link client, vlastník, duplicitný kontakt, migrácia na kópii starej DB |
| P0.2 Ponuka a transparentný výpočet | cena je najväčšie riziko marže | výpočet z množstiev/sadzieb/nákladov je deterministický; všetky medzisúčty viditeľné; odoslaná verzia sa nemení | peniaze/zaokrúhľovanie/DPH podľa nastaveného režimu, neplatné hodnoty, snapshot |
| P0.3 Prijatie a vznik Job | dnes prijatie Offer Job nevytvorí | jedna prijatá verzia → jedna Job s Client/Site/rozsahom a cenou, aj pri dvojkliku | idempotencia, FK ownership, rollback, legacy accepted bez doloženého súhlasu |
| P0.4 Koncept faktúry zo Job | teraz sa ponuka/faktúra prepája len náhľadom | položky a adresy sa predvyplnia zo schváleného rozsahu a viditeľných dodatkov, človek skontroluje a vystaví | vytvorenie faktúry, väzba na Job, nezmenený originál, migračný test |

Každý P0 inkrement je samostatný commit alebo malá séria po teste, na pracovnej vetve s návratom na predchádzajúci stav. Žiadna migrácia nesmie dropnúť tabuľku alebo resetovať údaje. Pred každou schémovou zmenou urobiť zálohu DB aj príloh a otestovať upgrade na kópii. Nasadenie, prípadné odoslanie e-mailov a zmena živých dát sú osobitné kroky s overením konkrétnej verzie a readbackom.

## P1 — vysoká návratnosť až po priechodnom P0

| Funkcia | Predpoklad použitia v malej firme | Hodnota / najmenší variant | Podmienka pokračovania |
| --- | --- | --- | --- |
| Mobilná obhliadka a rýchle poznámky | 3–6× mesačne | jedna karta, posledná miestnosť, foto/text/hlas; 10–25 min/obhliadka je len hypotéza | zmerať kroky a presnosť na reálnom telefóne |
| Foto pred zakrytím + vyhľadanie | dni s montážou, opakované spätné hľadanie | súkromný súbor s miestnosťou, prvkom a trasou; prehľad podľa miesta | nájsť konkrétnu trasu do 30 s po pilotnom odovzdaní |
| Malý vlastný cenník/šablóny | 3–6 ponúk mesačne | 20–40 najčastejších výkonov, CSV import materiálu, dátum ceny | aspoň polovica položiek ponúk vzniká zo šablóny bez ďalšej opravy |
| Termíny a ďalšie kroky | denne | týždenný zoznam obhliadka/servis/etapa a kolízie | kalendár nepridá viac údržby než papier/Google Calendar |
| Materiál pre zákazku | pri každej práci | potrebné → objednané → na mieste → použité/vrátené; bez skladových pohybov | menej zabudnutých jázd/nákupov |
| Zmeny rozsahu a extra práce | menej často, vysoký dopad na príjem | rozsah, cena, dátum a doložený súhlas pred fakturáciou | žiadna fakturovaná extra práca bez rozhodnutia |
| Čas, doprava a subdodávky; marža | denne/týždenne | celé minúty a centy, odhad vs. skutočnosť, varovanie pri chýbajúcom náklade | po uzavretí zákazky majiteľ rozumie odchýlke |
| Akčný dashboard a draft follow-up | denne/týždenne | päť blokov na konanie, nie 30 grafov; človek odosiela text | 7-dňové ponuky nezostávajú bez ďalšieho kroku |

P1 sa nezapína naraz. Prvé poradie podľa očakávanej hodnoty je mobilný záznam/fotky, šablóny kalkulácie, zmena rozsahu a skutočné náklady. Plán a dashboard sa opierajú o dáta z týchto tokov. Úspory času z [výskumu](ELECTRICIAN_WORKFLOW_RESEARCH.md) sa prekrývajú a po každom pilote sa majú nahradiť meraním.

## P2 — silné vylepšenia po dátach z P1

- Čiastočné platby a zálohy, keď sa vyskytnú v skutočných zákazkách; bankový import len pri dostatočnom objeme.
- Odovzdávací balík s fotkami, okruhmi a dokumentmi. Revíznu správu pripája autor s oprávnením; aplikácia ju nevydáva.
- Google Calendar ako doplnkové zobrazenie/synchronizácia po vyriešení konfliktov. Úplné WhatsApp/Messenger/SMS integrácie len pri preukázanom objeme správ a povoleniach.
- Lokálny účtovný/eFakturačný export podľa aktuálneho režimu; pred implementáciou overiť SK 2027 požiadavky, dátové formáty a účtovný postup.
- Asistent číta zákazky, náklady a nezaplatené ponuky cez aplikačné služby a pripravuje koncepty; všetky externé a finančné akcie majú náhľad a potvrdenie.

## P3 — experimenty, nie záväzok

AI Vision na štítky, prílohy a návrh tagu fotografie; návrh štruktúrovaných položiek z hlasu; body do pôdorysu; predbežný zoznam okruhov/BOM rozvádzača; napojenia na živé ceny veľkoobchodov; pokročilý offline režim. Každý experiment má malú sadu reálnych vzoriek, cenu na prípad, meranie chýb a jasné STOP pravidlo. Žiadna AI funkcia nepredstiera technický návrh, skúšku alebo revíziu.

## Sekvencia fáz z pôvodného zadania

| Fáza | Stav | Výsledok / nasledujúci krok |
| --- | --- | --- |
| 1 Deep Research | dokumentovaný desk research | [ELECTRICIAN_WORKFLOW_RESEARCH.md](ELECTRICIAN_WORKFLOW_RESEARCH.md); doplniť živé rozhovory |
| 2 Reálny workflow | hypotéza, terén čaká | tri prípady, rozhovory a časový denník |
| 3 Konkurencia | verejný desk benchmark | porovnanie jednej reálnej zákazky v existujúcom nástroji |
| 4 Audit | lokálny kód preskúmaný | [INVOICEMAKERAI_AUDIT.md](INVOICEMAKERAI_AUDIT.md); živé nasadenie osobitne |
| 5 Gap | zdokumentované | [GAP_ANALYSIS.md](GAP_ANALYSIS.md) |
| 6 Vízia | zdokumentované | [PRODUCT_VISION.md](PRODUCT_VISION.md) |
| 7 Doménový návrh | návrh pred kódom | [DOMAIN_ARCHITECTURE.md](DOMAIN_ARCHITECTURE.md) |
| 8 Priority | tento plán | upraviť po troch prípadoch |
| 9 P0 | lokálny tok čiastočne hotový | dopyt/miesto/obhliadka/ponuka/verzia/zákazka/faktúra otestované; nákladová kalkulácia, legacy súbory a reálne dáta otvorené |
| 10 P1 | foto štítky, materiál, interný čas/náklady, dodatky, malý ručný cenník a akčný prehľad lokálne hotové | DPH nákladov a terénne overenie zostávajú |

**Najbližší konkrétny krok:** získať prvý anonymizovaný úplný prípad a prejsť ho lokálnym tokom. Zmerať čas a kroky, potom doplniť len chýbajúci nákladový/cenový krok. Pred prácou so skutočnými dátami vykonať zálohu a migračnú skúšku na kópii.
