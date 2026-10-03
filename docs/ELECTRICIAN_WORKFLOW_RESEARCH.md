# Pracovný systém elektrikára: výskum pred auditom InvoiceMakerAI

**Stav:** fáza 1, výskum verejných zdrojov uzavretý 3. 10. 2026. Toto je návrh pracovného postupu a súbor hypotéz; nie audit aplikácie ani potvrdenie dopytu po SaaS.

## 1. Ako boli vyhodnotené zdroje

Primárny dôraz je na Slovensko, Česko, Rakúsko a Nemecko. Právne a technické hranice opieram o národné úrady, predpisy a normotvorné organizácie. Funkcie konkurentov opisujem podľa ich vlastnej dokumentácie, takže sú to **tvrdenia dodávateľov**, nie overená kvalita. Diskusie a recenzie používam ako príklady problémov a alternatívnych postupov, nie ako reprezentatívne dáta. UK, Austrália a USA slúžia len na porovnanie softvérových pracovných postupov. Pri tejto fáze neprebehli rozhovory s elektrikármi ani pozorovanie zákazky; úspory času v tomto dokumente sú explicitné odhady na otestovanie.

**Predbežný záver:** Najvyššiu šancu znížiť administratívu má jedna karta dopytu/zákazky, z ktorej vznikne presný rozsah a kontrolovateľná kalkulácia, následne plán, záznam práce, odovzdanie a faktúra. Existujúce produkty už zvládajú všeobecný tok od dopytu po platbu; priestor na vlastný nástroj sa musí dokázať na konkrétnych elektro úlohách a lokálnom postupe, nie počtom funkcií. [ServiceM8: priebeh zákazky](https://support.servicem8.com/help-center/desktop/basics/new-to-servicem8-start-with-a-job-walkthrough), [Fergus: kalkulácia a faktúra](https://fergus.com/features/estimating-software/), [Timoty: práca v teréne](https://www.timoty.sk/remeslo/).

### Čo zatiaľ nevieme

- Koľko hodín administratívy týždenne má konkrétna cieľová firma. Údaj **10 h/týždeň** z zadania je pracovný predpoklad, nie nameraný základ.
- Podiel servisných zásahov, rekonštrukcií, novostavieb a subdodávok. Tieto prípady majú odlišné cenotvorby aj dokumenty.
- Ktorý kanál nosí platené zákazky, či sú od jednorazových domácností alebo opakovaných B2B klientov, a ktoré informácie dnes skutočne prepisuje.
- Či vlastný InvoiceMakerAI odstráni viac práce než jednoduché spojenie existujúcich nástrojov. Bez porovnania na reálnej zákazke je budovanie širokej platformy ekonomická hypotéza.

## 2. Reálny životný cyklus: dva vstupy, jedna karta práce

Kompletná rekonštrukcia obvykle potrebuje obhliadku, rozsah po miestnostiach a odsúhlasenú ponuku. Malý servis často začína popisom poruchy, termínom a vyúčtovaním skutočného času a materiálu. Nútiť obidva prípady cez povinnú obhliadku a rozpočet by pridalo administratívu. Toto rozdelenie vyplýva z opísaných „reactive callouts“ a „multi-stage projects“ v [Simpro](https://www.simprogroup.com/industries/electrical-software) a z prehľadu [ServiceM8](https://support.servicem8.com/help-center/desktop/basics/new-to-servicem8-start-with-a-job-walkthrough); konkrétne nastavenie je produktový návrh.

| Krok | Rekonštrukcia / väčšia zákazka | Malý servis | Údaj, ktorý sa prenáša ďalej |
| --- | --- | --- | --- |
| Dopyt | telefonát, odporúčanie, web, e-mail, správa alebo stavebný partner | telefonát, správa, opakovaný klient | klient, kontakt, miesto, požiadavka, zdroj, ďalší krok |
| Kvalifikácia | rozsah, termín, dostupné podklady, vhodnosť | bezpečnostná naliehavosť, prístup, základná diagnostika | typ práce, riziko, termín, fotky |
| Obhliadka | miestnosti, body, trasy, rozvádzač, podmienky realizácie | len ak je potrebná | poznámky, merania, fotky, nejasnosti |
| Návrh rozsahu a kalkulácia | množstvá, práca, materiál, výluky, rezervy | sadzba, minimálny výjazd alebo odhad po diagnostike | interný rozpočet s pôvodom cien |
| Ponuka a súhlas | verzia ponuky a preukázateľný súhlas | podľa prípadu objednávka alebo odsúhlasená sadzba | odsúhlasený rozsah a cena |
| Plánovanie a nákup | etapy, ľudia, materiál, dodávky | časový slot, dostupnosť dielu | termíny, zoznam nákupu |
| Realizácia | denný záznam, čas, spotreba, fotky pred zakrytím, zmeny | zásah, čas, diely, výsledok | skutočná práca a náklady |
| Odovzdanie | kontrola, podklady pre odbornú skúšku/revíziu, zápis | záznam vykonanej práce a prípadné odporúčanie | dôkaz o rozsahu a dokončení |
| Faktúra a platba | záloha/etapy/konečná podľa dohody | konečná podľa skutočnosti | schválené položky, platby |
| Vyhodnotenie | odhad vs. skutočnosť | skutočná marža zásahu | poučenie pre budúce ceny |

Výsledný stav nie je 14 povinných formulárov. Každý krok sa má ukázať len vtedy, keď je pre daný typ zákazky relevantný. Potrebu jasného rozsahu, dohody o výlukách a verziách podporujú konkrétne spory pri neurčitých ponukách v [nemeckej diskusii](https://www.reddit.com/r/Elektroinstallation/comments/1joq6kv) a pri rozdiele medzi plánom a naceneným počtom zásuviek v [diskusii stavebníkov](https://www.reddit.com/r/Hausbau/comments/1tstf5h/streit_mit_elektriker/). Sú to anekdoty, ale poukazujú na priamo testovateľný failure mode.

**Lokálna kontrola postupu:** slovenské firmy [SunBrothers](https://www.sunbrothers.sk/elektroinstalacie/) a [AH Projects](https://ahprojects.sk/) na svojich weboch opisujú zbieranie fotiek/projektu, prípadnú obhliadku a následnú písomnú ponuku podľa skutočného rozsahu. [VOLTAMP](https://www.voltamp.sk/cennik/) uvádza orientačný rozhovor, obhliadku a položkové nacenenie; pri väčších stavbách používa stavebný cenníkový program. [OHMA](https://www.ohma.sk/) ukazuje digitálnu zložku s revíznymi správami a fotkami. Ide o verejný opis predajného postupu konkrétnych firiem, nie meranie ich každodennej práce. Potvrdzuje však, že problém má lokálny kontext: rozsah a podklady sa líšia podľa stavby a dodávateľa, preto jedna univerzálna povinná sada polí nie je dobrý návrh.

## 3. Dopyt a príjem zákazky

### Minimum pri prvom kontakte

1. **Kto a ako sa mu ozvať:** meno/názov, jeden spoľahlivý kontakt, preferovaný kanál.
2. **Kde:** presná adresa realizácie alebo aspoň obec na prvé posúdenie dojazdu; fakturačná adresa je samostatná len v prípade rozdielu.
3. **Čo chce alebo čo nefunguje:** výsledok vlastnými slovami, typ objektu a či je to servis, úprava, rekonštrukcia alebo novostavba.
4. **Kedy a ako nalieha:** požadovaný termín, prístup na miesto a či je prítomné akútne nebezpečenstvo. Pri dyme, zápachu horenia, prehrievaní alebo vode pri elektrickom zariadení systém nemá dávať okamžitú cenu ani technické rady laikovi; má zvýrazniť potrebu bezpečného postupu a odbornej triáže. Toto je produktový návrh, nie vzdialená diagnostika.
5. **Podklady:** 1–3 široké fotografie problému a miesta, prípadne projekt/pôdorys. Podrobnejšie polia sa pýtajú až podľa typu práce.

Obhliadkový formulár nesmie nútiť zákazníka poznať hlavný istič, distribútora, druh siete či kabeláž pri výmene jedného svietidla. Pri EV nabíjačke majú zmysel model nabíjačky, umiestnenie, približná vzdialenosť od rozvádzača, priechod trasy a **bezpečne odfotený vonkajší pohľad** na rozvádzač/štítok. Britská elektro firma v [návode na podklady pre EV ponuku](https://www.hitches-glitches.co.uk/ev-charger-installation-photos-guide/) žiada viac konkrétnych fotografií; technická kapacita sa aj tak musí posúdiť odborne na mieste. Pri RD/byte sú relevantné pôdorys, požadované zásuvkové, svetelné, dátové a technologické body po miestnostiach, rozsah búrania a hranica murárskych prác. Príklad slovenskej firmy výslovne oddeľuje revíziu, projekt a murárske vysprávky od montážnej ceny, čo podporuje potrebu evidovať výluky už pri dopyte. [Omni-Elektro](https://omni-elektro.sk/).

**Navrhnutý intake:** 60-sekundový formulár s povinným kontaktom, miestom, opisom, termínom a prílohou iba ak ju zákazník má. Potom jedna z 3–4 krátkych vetiev: porucha/servis, byt alebo dom, rozvádzač/prípojka, špeciálna technológia (EV/FV). Neznáme údaje ostávajú „nezistené“ a vytvoria otázku na obhliadku; AI ich nesmie domyslieť. Operátor má vedieť dopyt po telefonáte založiť ručne za menej než minútu.

**Kanály:** telefón, SMS, WhatsApp, Messenger/Instagram, e-mail, web, Google Business a odporúčania treba vedieť aspoň *označiť ako zdroj*. Úplné prepojenie všetkých schránok v prvej verzii nie je podmienkou na zníženie prepisovania a prináša prevádzkový dlh. Systém môže ponúknuť kontaktný odkaz na zber podkladov aj po telefonáte. Príklad elektrikárskej firmy v [prípadovej štúdii ServiceM8](https://www.servicem8.com/au/customer-stories/westcork-electrical) opisuje rozptýlené poznámky a fotky v mobile; ide o marketingový príbeh jedného zákazníka, nie meranie trhu.

## 4. Obhliadka a mobilné zachytenie

**Praktické poradie na mieste:** otvoriť kartu podľa dnešného termínu alebo poslednej zákazky → jedným klepnutím pridať fotku, hlas alebo text → podľa potreby priradiť miestnosť a prvok → na konci vidieť chýbajúce rozhodnutia. Každý záznam má čas, autora a zdroj. Pri slabom signáli musí byť jasné, či je záznam uložený lokálne a či sa synchronizoval; „tvári sa uložené“ je neakceptovateľný failure mode. [CompanyCam: offline fotodokumentácia](https://companycam.com/resources/blog/offline-photo-documentation-for-field-crews).

Pre väčšiu obhliadku má zmysel krátky checklist: stav existujúcej inštalácie a dostupnej dokumentácie, miesto rozvádzača, hranice dodávky, miestnosti/body, možné trasy, rozmer/dĺžka s uvedením metódy odhadu, prístup a koordinácia s ďalšími profesiami, otvorené otázky pre zákazníka. Pri servise stačí foto, popis, príčina zistená/nezistená a ďalší krok. [Diskusia elektrikárov o kalkulácii podľa bodov, dĺžok a času](https://www.reddit.com/r/Elektroinstallation/comments/1s277cl/wie_kalkuliert_ihr_angebote/).

**Hlas:** „Novák, obývačka, dve zásuvky za TV, CAT6, presun vypínača o 40 cm“ sa najprv prepíše do **editovateľného textu**. Štruktúrované návrhy (miestnosť, práca, množstvo) sa zobrazia vedľa originálu a uložia až po potvrdení človekom. Nejasné čísla, jednotky, názvy káblov a mená sa majú označiť. Web Speech API má podľa [MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/start) obmedzenú podporu naprieč prehliadačmi; pre produkciu treba otestovať konkrétne telefóny a mať textový vstup alebo nahrávku s prepisom na serveri ako alternatívu. Hlas môže skrátiť písanie, ale závisí od hluku, signálu a ochoty hovoriť pred zákazníkom.

**Pôdorys a video:** výkres s pripnutými bodmi je vhodný pre veľké rekonštrukcie, no prvý test má skúsiť jednoduché názvy miestností a fotky. Plnohodnotný editor pôdorysu, automatické rozpoznávanie zásuviek či odhad metrov kábla z fotografie sú až experiment; chybné množstvo sa priamo premietne do marže. Video len ako príloha s ručným názvom miesta, nie ako základ vyhľadávania.

## 5. Cenová ponuka a databáza cien

Elektrikári nekalkulujú jednotne. V [diskusii o cenotvorbe](https://www.reddit.com/r/Elektroinstallation/comments/1s277cl/wie_kalkuliert_ihr_angebote/) sú príklady ceny za zásuvkový či svetelný bod, času po činnostiach, paušálu na opakované byty a kalkulácie podľa skutočných hodín a materiálu. Príspevky zároveň spomínajú podcenenie káblov, rozvádzača, skúšok a času. Z toho vyplýva potreba **viacerých šablón výpočtu**, nie jednej univerzálnej ceny za „zásuvku“. Verejná ponuka môže zoskupiť prácu do zrozumiteľných položiek; interná kalkulácia má zachovať materiál, čas, nákupnú cenu a réžiu. Neurčitá verejná ponuka je riziko sporu. [Diskusia o neurčitom rozsahu](https://www.reddit.com/r/Elektroinstallation/comments/1joq6kv). Rakúska [WKO](https://www.wko.at/vertragsrecht/kostenvoranschlag-ueberblick) pri odhade nákladov rozlišuje prácu, materiál a ostatné náklady a upozorňuje na rozdiely medzi spotrebiteľom a podnikateľom; preto označenie a právny účinok výstupného dokumentu treba riešiť podľa krajiny.

### Kontrolovateľný výpočet

Pre každú internú položku treba držať: množstvo × jednotka; zdroj materiálovej nákupnej ceny a dátum; odhad hodín × interný náklad na hodinu; externé náklady (doprava, nájom, subdodávka, revízia podľa dohody); prípadnú rezervu; predajnú cenu, zľavu a DPH podľa krajiny, statusu firmy a typu plnenia. **Marža** sa počíta `(predaj bez dane − priame náklady) / predaj bez dane`; **prirážka** je `(predaj − priame náklady) / priame náklady`. Zámena týchto dvoch veličín vedie k inej cene. Príklad: náklad 80 € pri cieli 20 % hrubej marže dá cenu 100 €, nie 96 €.

Údaje z obhliadky → *návrh* rozsahu → človekom upravené množstvá a šablóny → výpočet v deterministickom kóde → verzia ponuky. AI môže predložiť zoznam možných chýbajúcich položiek a otázok, nikdy skryto meniť cenu. Každá odoslaná verzia ponuky musí mať zmrazené položky, sadzby, daňový režim, výluky, termín a súhlas. Zmeny po schválení patria do dodatku/extra práce, nie do tichého prepísania pôvodnej ponuky. [Fergus: materiál, práca, marža a prechod do faktúry](https://fergus.com/features/estimating-software/), [Housecall Pro: schválený rozsah a náklady](https://www.housecallpro.com/resources/commercial-electrical-pricing/).

### Najmenší užitočný katalóg

- **Práca / montážna šablóna:** napr. nový zásuvkový bod pod omietkou, presun existujúceho bodu, svietidlo so známym typom, dátový bod, okruh, práca na rozvádzači, diagnostika. Nie iba objekt „zásuvka“: rovnaký viditeľný prvok má inú náročnosť v SDK, betóne, novej stavbe a hotovej izbe.
- **Komponent šablóny:** očakávaný materiál v jednotkách, normovaný *interný* čas ako východisko, predpoklady, výluky. Položka sa dá pri konkrétnej ponuke upraviť a originál sa zachová.
- **Materiál:** vlastný kód, názov, výrobca, model/GTIN alebo dodávateľské číslo, jednotka, posledná nákupná cena s dátumom, prípadne priemerná nákupná cena z nákupov, predvolená predajná cena alebo pravidlo marže. Uchovávať aj historickú cenu použitú v odoslanej ponuke.
- **Cenové pravidlo:** sadzba práce a réžia podľa typu práce, minimum výjazdu, doprava, subdodávka, rezervy. Zľava je viditeľné rozhodnutie človeka.

Na začiatok stačí 20–40 najčastejších montážnych šablón a import CSV/XLSX od vlastných dodávateľov. Kompletný európsky katalóg by spôsobil drahú údržbu a slabé vyhľadávanie. [ETIM](https://www.etim-international.com/classification/) je použiteľný neutrálny klasifikačný základ do budúcna, nie zdroj konkrétnych nákupných cien. V Nemecku [Rexel](https://www.rexel.de/rexeleasy/oci-und-ids) a [Sonepar](https://www.sonepar.de/resource/blob/146194/c43f97c7706a50f878738570e47a841b/sdebro-servicebroschuere-hj1-0525-iz-25832512780-data.pdf) publikujú IDS/OCI/DATANORM/UGL cesty pre ceny, dostupnosť a objednávky. Prístup a obchodné podmienky sú závislé od zákazníckeho účtu a treba ich osobitne overiť v SK/CZ/AT. Pre prvú verziu preto nedáva zmysel sľubovať live API od veľkoobchodu. Rakúsky [Sonepar web shop](https://events.sonepar.at/faq/webshop) podporuje CSV import košíka; to nie je potvrdenie API na čítanie osobných cien.

## 6. Po schválení: jedna zákazka, jednoduchá realizácia

Lead → klient a miesto → obhliadka → ponuka → **odsúhlasená verzia** → zákazka. Prijatý dopyt sa nesmie kopírovať do nového záznamu s voľne upraviteľnou adresou. Zákazka zdedí referencie na klienta/miesto a snapshot dohody. Oddeliť treba *plán* (cena, odhad množstva a času) od *skutočnosti* (odpracované hodiny, nákup, spotreba, doprava, subdodávka). Inak zmeny cien spätne prepíšu históriu. Schopnosť porovnať odhad a skutočnosť je jasná hodnota aj v [produkte Fergus](https://fergus.com/us/industries/electrical/).

**Na pracovnej karte v mobile:** dnes/ďalší termín, telefonovať, navigovať, pridať fotku, poznámku, čas, nákup alebo extra prácu; posledné tri činnosti nesmú vyžadovať hlboké menu. Materiálová evidencia nech je iba „potrebné → objednané → na mieste → použité/vrátené“, prípadne potvrdený nákupný náklad. Skladové karty, rezervácie na dodávku, inventúry a FIFO pre 1–5 ľudí nie sú odôvodnené bez dôkazu o častých stratách materiálu. [Timoty: spotreba materiálu priamo na zákazke](https://www.timoty.sk/remeslo/), [Fergus: nákupné doklady a job costing](https://fergus.com/us/industries/electrical/).

Zmenu rozsahu treba zaznamenať v momente zadania: kto ju požiadal, opis, foto, vplyv na cenu a termín, stav schválenia. Schválený dodatok sa môže dostať do faktúry; neschválený nemá byť fakturovaný ako dohodnutá položka. Pri rekonštrukciách sú požiadavky zákazníka počas práce bežnou témou v [diskusii elektrikárov](https://www.reddit.com/r/Elektroinstallation/comments/1s277cl/wie_kalkuliert_ihr_angebote/), no ich frekvenciu v cieľovej firme treba zmerať.

### Fotodokumentácia, ktorú možno nájsť o dva roky

Navrhnuté indexovanie: **miesto → zákazka/etapa → miestnosť alebo zóna → prvok či okruh → fotka**. Minimálne tagy: fáza (pred zásahom, pred zakrytím, po dokončení), miestnosť, opis, dátum a autor; podľa prípadu typ kábla, trasa, rozmer, číslo okruhu. Foto pri skrytom vedení musí mať orientačný široký záber s oknom/dverami/rohom a detail; pri mierke treba skutočné referenčné rozmery alebo meter v zábere, nie len automaticky vypočítanú „polohu“. Obrys či šípku ukladať ako anotáciu nad originálom; originál nemeniteľne archivovať. [CompanyCam: fázy, tagy a anotácie](https://companycam.com/resources/blog/how-to-take-job-documentation-photos-that-actually-help-your-business), [PlanRadar: poloha na pláne](https://www.planradar.com/sa-en/product/siteview/). Potrebu fotiť trasy pred zakrytím opakovane opisujú aj [stavitelia v diskusii](https://www.reddit.com/r/Hausbau/comments/1w8a5b5/fotografiert_jede_offene_wand_bevor_sie_wieder/); to je skúsenosť používateľov, nie norma.

Prvé MVP nepotrebuje samostatnú tabuľku pre každý prvok stavby. Môže ukladať miestnosť a voľný názov prvku k fotke; presné prepojenie na elektrický okruh sa pridá, ak ho ľudia skutočne vyplňujú. Kritérium kvality: počas 30 sekúnd nájsť fotku „obývačka, TV stena, vedenie pred omietkou“ na staršej zákazke.

## 7. Odovzdanie, revízia a rozvádzač: odborná hranica

Neexistuje jeden jednotný „EÚ elektro odovzdávací formulár“. Produkt potrebuje podľa krajiny a typu diela nastaviteľný zoznam podkladov; presnú povinnosť pri konkrétnej zákazke stanoví kvalifikovaná osoba podľa platného miestneho režimu. Program nesmie vydávať nahranú fotku či AI text za revíznu správu.

| Jurisdikcia | Overený zdroj a dôsledok pre systém |
| --- | --- |
| **Slovensko** | [Národný inšpektorát práce](https://www.ip.gov.sk/files/publikacie/nova-prirucka-bezpecnost-technickych-zariadeni/bezpecnost-technickych-zariadeni.pdf) uvádza východiskovú odbornú prehliadku a odbornú skúšku a správu od revízneho technika VTZ elektrických. [Stanovisko NIP k STN 33 2000-6](https://www.ip.gov.sk/bozp/vyhradene-technicke-zariadenia-vtz/elektricke/stanovisko-k-plneniu-poziadaviek-vyplyvajucich-z-clanku-6-4-4-4-stn-33-2000-62018.html) odlišuje zodpovednosť projektanta, zhotoviteľa a revízneho technika a žiada identifikáciu skúšaných okruhov, ochranných prvkov a výsledkov. Systém môže pripraviť podklady a sledovať stav, podpis revíznej správy patrí oprávnenej osobe. |
| **Česko** | [NV 190/2022 Sb. v e-Sbírke](https://e-sbirka.gov.cz/sb/2022/190) definuje revízneho technika, dokumentáciu zodpovedajúcu skutočnému vyhotoveniu a náležitosti revíznej správy (§ 6, 9, 10). Elektronická revízna správa má vlastný podpisový režim; obyčajné PDF vytvorené aplikáciou ho nenahrádza. |
| **Rakúsko** | [Elektrotechnikverordnung 2020 § 6](https://ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Anlage=&Artikel=&FassungVom=2026-01-24&Gesetzesnummer=20011222&Paragraf=6&Uebergangsrecht=) opisuje prvú skúšku nízkonapäťovej inštalácie pred prvým uvedením do prevádzky. [Elektroschutzverordnung 2012 § 11](https://ris.bka.gv.at/NormDokument.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20007682&Paragraf=11) stanovuje obsah skúšobného záznamu a uchovávanie podkladov v pracovnom prostredí. Rakúska [WKO](https://www.wko.at/gewerbe-handwerk/elektro-gebaeude-alarm-kommunikation/pruefung-elektrischer-anlagen-und-dokumentation) rozoberá aj odovzdanie Anlagenbuchu a skúšobných podkladov. Konkrétne pravidlá sú závislé od druhu stavby/pracoviska. |
| **Nemecko** | [DKE k DIN VDE 0100-600](https://www.dke.de/de/normen-standards/dokument?id=7089969&type=dke%7Cdokument) uvádza prvú skúšku po novej inštalácii alebo zmene a správu o nej; [spresnenie DKE](https://www.dke.de/de/arbeitsfelder/core-safety/normenhinweise/dke-uk-221-1-zu-mindestinhalte-eines-pruefberichts) opisuje obsah. [DGUV Vorschrift 3](https://publikationen.dguv.de/widgets/pdf/download/article/1052) sa týka skúšok elektrických zariadení v pracovnom kontexte. Systém má uchovať správu a jej autora, nie vyhodnocovať bezpečnosť namiesto odborne spôsobilej osoby. |

**Kto čo do systému vloží:** montér môže priebežne zaznamenať svoje práce, fotky, skutočné trasy, použité výrobky a návrh popisov okruhov; to sú pracovné podklady a interná dokumentácia, nie automaticky schválený projekt alebo revízia. Projektovú dokumentáciu a jej zmeny musí potvrdiť osoba, ktorej to príslušný miestny režim zveruje. Merania a odbornú správu systém ukladá s menom/autorstvom a kvalifikáciou osoby, ktorá ich vyhotovila; neodvodzuje ich z fotiek ani ich nepodpisuje za ňu. Odovzdávací zápis zachytí dohodnutý rozsah a prebrané dokumenty, ale nenahrádza správu o odbornej skúške. Konkrétne rozdelenie zodpovednosti treba pri zákazke preveriť podľa [slovenského NIP](https://www.ip.gov.sk/bozp/vyhradene-technicke-zariadenia-vtz/elektricke/stanovisko-k-plneniu-poziadaviek-vyplyvajucich-z-clanku-6-4-4-4-stn-33-2000-62018.html), [českého NV 190/2022](https://e-sbirka.gov.cz/sb/2022/190), [rakúskej WKO](https://www.wko.at/gewerbe-handwerk/elektro-gebaeude-alarm-kommunikation/pruefung-elektrischer-anlagen-und-dokumentation) a [nemeckej DKE](https://www.dke.de/de/arbeitsfelder/core-safety/normenhinweise/dke-uk-221-1-zu-mindestinhalte-eines-pruefberichts).

**Podklady na pracovnej karte:** pôvodný a skutočný plán (ak existuje), zoznam okruhov a popisy, použité komponenty a návody, fotky pred zakrytím, montážne záznamy, merania a protokoly od oprávnenej osoby, odovzdávací zápis a podpísaná revízna správa tam, kde sa vyžaduje. Pri malej výmene nebude vždy celý balík potrebný. Zoznam okruhov sa môže priebežne vypĺňať počas montáže a poskytnúť projektantovi či revíznemu technikovi ako podklad, ale aplikácia nemá sama schvaľovať technické riešenie. [Stanovisko NIP](https://www.ip.gov.sk/bozp/vyhradene-technicke-zariadenia-vtz/elektricke/stanovisko-k-plneniu-poziadaviek-vyplyvajucich-z-clanku-6-4-4-4-stn-33-2000-62018.html), [NV 190/2022 Sb.](https://e-sbirka.gov.cz/sb/2022/190).

**Rozvádzač:** ako budúci modul dáva zmysel *pracovný zoznam* spotrebičov, okruhov, prvkov, štítkov, rezerv a predbežného BOM, s evidenciou návrh → odborná kontrola → schválené podklady → skutočné vyhotovenie. Automatické priradenie istenia, dimenzovanie vodičov, selektivita, tepelná záťaž, skratové pomery a vyhlásenie zhody patria do odborného návrhu a overovania. [IEC 61439-1](https://webstore.iec.ch/en/publication/32338) stanovuje konštrukčné a overovacie požiadavky na nízkonapäťové rozvádzače; [IEC TR 61439-0](https://webstore.iec.ch/en/publication/66003) rozlišuje špecifikáciu požiadaviek a výrobu/overenie. AI teda smie pripraviť zoznam otázok, nie „hotový bezpečný rozvádzač“.

## 8. Plán, komunikácia, faktúry a ziskovosť

**Plánovanie:** v malej firme sú potrebné obhliadka, pevný servisný slot a viacdňová etapa stavby. Stačí jednoduchý zoznam/týždeň s filtrom pracovníka a kontrolou kolízie; drag & drop je pohodlie, nie jadro. Interný termín musí byť zdrojom pravdy, externý kalendár môže byť synchronizovaný až po vyriešení konfliktov a duplicitných udalostí. [Google Calendar API](https://developers.google.com/workspace/calendar/api/guides/create-events) podporuje udalosti a vlastné ID; OAuth prístup vyžaduje vhodný rozsah oprávnení podľa [dokumentácie](https://developers.google.com/workspace/calendar/api/auth).

**Komunikácia:** najprv prehľad posledného kontaktu, kanála, stručný výsledok rozhovoru, ďalší krok a návrhy textov. Ukladanie všetkých správ zo všetkých kanálov má vysokú integračnú cenu. WhatsApp Business Platform má pravidlá pre servisné okno a schválené šablóny mimo neho; [oficiálna politika WhatsApp](https://business.whatsapp.com/policy/preview?lang=es_LA) a [Meta Postman dokumentácia](https://www.postman.com/meta/whatsapp-business-platform/folder/fuaee8l/statuses-object). Messenger Send API vyžaduje oprávnenie a má časové obmedzenia, podľa [oficiálnej kolekcie Meta](https://www.postman.com/meta/messenger-platform-api/folder/vilwbh4/send-api). Integrácie preto netreba sľubovať pred overením účtu, povolení a používaného čísla/stránky. Finančné a citlivé správy ostávajú ako návrh na kontrolu.

**CRM:** prevádzkovo stačí „nový dopyt → čaká na podklady → obhliadka/diagnostika → ponuka pripraviť → ponuka odoslaná → čaká na rozhodnutie → vyhrané/odmietnuté“. Schválenie otvorí zákazku. Nevyžadovať zvláštny adresár kontaktov a ďalšiu pipeline, ak jedna osoba rieši 10–30 otvorených prípadov; počet je hypotetický. Kľúčové je, aby každý otvorený prípad mal *vlastníka a ďalší konkrétny krok s dátumom*.

**Fakturácia:** položky zo schválenej ponuky sa prevezmú do konceptu faktúry, upravia sa o schválené zmeny a reálne množstvá podľa dohody. Záloha a etapy sú voliteľné pre väčšiu zákazku; pri servise nech zostane jedna faktúra. Platby musia byť oddelené od vystavenia: faktúra ≠ zaplatené. Nezaplatené záväzky sú na pracovnom prehľade. Na Slovensku je [eFaktúra od 1. 1. 2027](https://www.financnasprava.sk/sk/podnikatelia/dane/dan-z-pridanej-hodnoty/e-faktura/_1) významná plánovaná zmena pre vymedzené B2B situácie; pred fakturačným refaktorom treba overiť aktuálne znenie a účtovný postup. [EK uvádza EN 16931](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108950/EN%2B16931%2Bcompliance) a národné obmedzenia; systém by mal mať oddeliteľný export/adapter, nie vlastnú improvizovanú právnu implementáciu. EK tiež upozorňuje na [vydanie normy EN 16931-1:2026](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108971/Obtaining%2Ba%2Bcopy%2Bof%2Bthe%2BEuropean%2Bstandard%2Bon%2BeInvoicing).

**Ziskovosť zákazky:** zobraziť predaj bez dane, rozpočtované priame náklady, skutočný nákup materiálu, skutočný náklad práce (hodiny × interná nákladová sadzba), cestu, subdodávky a ostatné potvrdené náklady. Hrubý príspevok = predaj bez dane − priame náklady; v prehľade pomenovať, či je alebo nie je zahrnutá réžia majiteľa, reklamácie a dane. Keď chýbajú hodiny či doklady, ukázať **neúplný odhad**, nie falošne presný zisk. Porovnať odhad a skutočnosť po dokončení. [Fergus: job costing](https://fergus.com/us/industries/electrical/), [Jobber recenzia spomína časovač pri vyhodnotení zákazky](https://www.capterra.com/p/127994/Jobber/reviews/).

**Denný prehľad majiteľa:** najviac päť pracovných blokov: treba odpovedať/naplánovať, treba naceniť, dnes na stavbe a chýbajúci materiál, možno fakturovať, faktúry po splatnosti. V mesačnom pohľade stačia počet a hodnota odoslaných ponúk, miera prijatia (len pri uzavretých rozhodnutiach) a marža dokončených zákaziek s indikátorom chýbajúcich nákladov. Prvé tri bloky slúžia na akciu, posledné dva na cashflow a učenie sa. Toto je produktový návrh podľa opakujúcich sa základných kategórií v [Jobber](https://www.capterra.com/p/127994/Jobber/) a [Fergus](https://fergus.com/us/industries/electrical/), nie dôkaz, že každá metrika zlepší výsledok.

## 9. OCR, vision a asistent: kde je hranica automatizácie

| Vstup | Užitočný návrh | Kontrola človekom / typický problém |
| --- | --- | --- |
| Hlasová poznámka | prepis a návrh miestnosti, činnosti, množstva, úlohy | redigovateľný originál; nesprávne číslo, jednotka, hluk, názov výrobku |
| Dodací list, faktúra dodávateľa, bloček | číslo, dátum, dodávateľ, položky, množstvo, cena; návrh priradenia k zákazke | potvrdiť účtovné údaje a priradenie; doklad môže zahŕňať viac zákaziek |
| Projekt/pôdorys | vyhľadať stranu, navrhnúť zoznam otázok a bodov | výkres nie je skutočné vyhotovenie; nesprávne rozpoznanie mierky a značiek |
| Foto rozvádzača/štítku | čitateľný model, označenia, možný zoznam komponentov | neodvodzovať bezpečnosť, správne istenie ani revízny výsledok len z fotografie |
| Správy zákazníka | zhrnutie, chýbajúce údaje, návrh odpovede a follow-up | meno, rozsah, cena, sľub termínu a odoslanie vyžadujú kontrolu |

Konkurent [Tradify uvádza SmartRead pre import fakturačných položiek z fotky](https://www.tradifyhq.com/uk/trades/electrician-av-software-app), čo potvrdzuje technickú dostupnosť kategórie, nie presnosť na slovenských dokladoch. Asistent v cieľovom systéme má volať úzko definované aplikačné operácie: `find_job`, `get_job_financials`, `list_missing_material`, `draft_invoice`, `draft_followup`, `attach_photo`, `convert_approved_quote`. Čítanie a príprava konceptu môžu byť rýchle; odoslanie, fakturácia, zmena dohodnutej ceny a technický záver potrebujú používateľské potvrdenie. Pri dokumentoch a fotkách je nutné riadiť prístup a uchovávanie podľa účelu; [EDPB pre malé firmy](https://www.edpb.europa.eu/sme/learn-the-basics/data-protection-basics_en) vysvetľuje minimalizáciu a lehoty uchovania, [EK](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/obligations_en) princíp ochrany pri návrhu systému.

## 10. Konkurencia: čo prevziať a čomu sa vyhnúť

| Produkt/kategória | Overené z dokumentácie dodávateľa | Signál z recenzií alebo produktové riziko pre malé elektro |
| --- | --- | --- |
| [Timoty](https://www.timoty.sk/remeslo/) (SK/CZ) | zákazky, rozdelenie práce, mobilné výkazy a materiál | lokálna alternatíva; vlastný produkt musí ukázať merateľnú výhodu pri kalkulácii a elektro dokumentácii |
| [KROS pre profesistov](https://www.kros.sk/profesisti/) (SK) | rozpočtovanie, cenníková databáza, napojenie na fakturáciu | silný cenový základ; netreba budovať obrovský stavebný cenník bez potreby |
| [ToolTime](https://www.tooltime.app/handwerkersoftware-elektro) / [Craftnote](https://craftnote.de/gewerke/elektriker/) (DE) | ponuky, plán, dokumentácia a mobilná stavebná zložka | konkurencia v DACH; lokalizáciu nepovažovať za jednoduché prepnutie meny |
| [Tradify](https://www.tradifyhq.com/uk/features/timesheet-software-app) | dopyt → ponuka → plán → zákazka → faktúra, mobilné výkazy | [Capterra recenzie](https://www.capterra.com/p/152413/Tradify/reviews/) oceňujú jednoduché ponuky/plán; jednotlivé hlásenia o doručení či stave správ overiť pri vlastnom UX |
| [Fergus](https://fergus.com/us/industries/electrical/) | mobilná karta, kalkulácia, veľkoobchodné cenníky a nákupné faktúry, job costing | silný vzor pre prepojenie nákupu a marže; dodávateľské integrácie nemusia platiť v SK |
| [ServiceM8](https://www.servicem8.com/za/industries/electrician-software) | rýchla terénna zákazka, fotky, pripomienky, faktúra | vhodný referenčný test 5–10 sekundového zadania, najmä servis |
| [Jobber](https://www.capterra.com/p/127994/Jobber/) | jednoduchý tok dopyt/ponuka/plán/faktúra, klientsky portál | recenzie uvádzajú slabšie reporty, občasný sync a drahší rast podľa používateľov; americké platby/daňové toky nie sú vzor pre SK |
| [Housecall Pro](https://www.housecallpro.com/industries/electrical-contractor-software/) | servis, mobil, alternatívne ponuky, platby a pripomienky | jeho predajné a financujúce prvky by v prvom SK produkte odvádzali pozornosť |
| [simPRO](https://www.simprogroup.com/industries/electrical-software) | viacstupňové projekty, servis, plán, materiál, fakturácia | [Capterra](https://www.capterra.com/p/10529/Simpro-Enterprise/reviews/) ukazuje nižšiu jednoduchosť používania a sťažnosti na cenu/podporu; neopakovať zložitý setup |
| [ServiceTitan](https://www.servicetitan.com/industries/electrical-software), [Commusoft](https://www.commusoft.com/en-gb/industries/electrical-contractor-software/?language-picker-select=us), [FieldPulse](https://www.fieldpulse.com/solutions/electrical) | široké operácie, dispatch, assety, servisné kontrakty, reporting | porovnávací strop, nie MVP benchmark; menšia firma pravdepodobne nevyužije fleet tracking, marketing automation a zložitú dispečerskú logiku |

Z Capterra/Reddit sa dá vyvodiť smer UX, nie presné rozšírenie funkcií. Používateľské sťažnosti sú selektované a niektoré recenzie vznikli na podnet dodávateľa. [Capterra: Jobber metodika a recenzie](https://www.capterra.com/p/127994/Jobber/reviews/), [diskusia elektrikárov o softvéri](https://www.reddit.com/r/electricians/comments/1kr9qif/software_for_contractors/).

## 11. Kandidátne automatizácie a odhad prínosu

**Odhadové predpoklady:** 8 nových dopytov, 4 obhliadky, 4 ponuky, 10 aktívnych dní stavby, 3 dokončenia/faktúry mesačne. Všetky minúty nižšie sú *hypotéza na meranie*, nie údaj zo zdroja. Úspory sa prekrývajú; sčítanie riadkov by nadhodnotilo prínos.

| Dnes ručne | Návrh automatizácie | Možná úspora pri jednom výskyte | Riziko chyby a brána |
| --- | --- | --- | --- |
| dopyt v telefóne/správe sa spätne zapisuje | rýchla karta + krátky odkaz na doplnenie fotiek a adresy | 3–8 min/dopyt | nesprávna adresa; používateľ potvrdí identitu a miesto |
| poznámky z obhliadky sa večer prepisujú | mobilná fotka/hlas/text priamo na zákazke | 10–25 min/obhliadka | zlá miestnosť alebo prepis; úprava pred uložením štruktúry |
| opakuje sa výpočet štandardných bodov | šablóny práce, materiálu a cenník so zmrazenou cenou v ponuke | 15–45 min/ponuka | zlý rozsah/množstvo; finálny výpočet a odoslanie schváli človek |
| pripomína sa ponuka z pamäti | ďalší krok a dátum, návrh follow-up textu | 3–7 min/follow-up | nevhodná komunikácia; človek odosiela |
| na stavbe sa opakovane zisťuje, čo chýba | potrebný/objednaný/pripravený materiál na karte | 5–15 min/nákup | duplicitný nákup; človek potvrdí objednávku |
| fotky sa triedia večer | automatická zákazka, čas, posledná miestnosť + rýchly tag | 5–15 min/deň s fotením | nesprávny kontext; zobraziť tag pri zábere |
| extra práca sa dopisuje do faktúry z pamäti | zmena rozsahu s cenou a súhlasom | 5–15 min/zmena; potenciálne väčší vplyv na príjem | sporná dohoda; súhlas zákazníka pred fakturáciou |
| faktúra sa prepisuje z ponuky | koncept zo schváleného rozsahu a potvrdenej skutočnosti | 10–25 min/faktúra | daňový režim, množstvo; človek schvaľuje vystavenie |
| marža sa odhaduje pocitovo | automatický prepočet z potvrdených nákladov | 10–30 min/uzavretie | chýbajúce doklady; ukázať neúplnosť a neuzavrieť hodnotenie |

**Najlepší prvý test:** na troch reálnych zákazkách merať čas od dopytu po odoslanie ponuky, počet ručných prepisov, počet zabudnutých položiek, čas na vyhotovenie faktúry, náklady proti odhadu a čas nájdenia fotky. Ak systém len pridá nové polia, úspech nenastal. Benchmark 10 h administratívy týždenne je potrebné najprv odmerať. Praktická brána pre ďalší vývoj: aspoň 2 z 3 zákaziek prejdú bez dodatočného prepisovania adresy/rozsahu a majiteľ po nich vie doložiť, kde stratil čas alebo maržu; až potom má zmysel rozširovať integrácie.

## 12. Odporúčanie pre nasledujúce fázy

1. **Fáza 2 – terénne overenie:** prejsť tri reálne typy zákaziek (malý servis, rekonštrukcia, väčšia etapová práca) s majiteľom od prvého kontaktu po platbu. Urobiť 5–8 krátkych rozhovorov s elektrikármi z 1–5 členných firiem v SK/CZ a aspoň 1–2 v AT/DE, ak cieľom ostáva DACH. Získať anonymizované reálne ponuky, obhliadkové poznámky, nákupné doklady, odovzdávacie podklady a kalendárny postup. Bez toho sa nemá tvrdiť, že problém je validovaný.
2. **Fáza 3 – konkurenčný test:** vykonať rovnakú jednu zákazku v existujúcom jednoduchom nástroji a zapísať počet krokov, čas, cenu a chýbajúce elektro podklady. Vlastný produkt potrebuje konkrétny dôvod, prečo sa ho oplatí udržiavať.
3. **Až potom audit InvoiceMakerAI:** zistiť skutočné entity, migrácie, prístupové práva, tok ponuka → zákazka → faktúra, prácu s prílohami, asistentom a cenami. Tento dokument zámerne netvrdí, čo aktuálna aplikácia robí.
4. **Predbežné poradie hodnoty:** (a) karta prípadu a ďalší krok, (b) obhliadkové podklady a foto, (c) transparentná kalkulácia a verzia ponuky, (d) potvrdené zmeny a náklady, (e) faktúra bez prepisu. Automatické všetky kanály, plný sklad, inteligentný rozvádzač a vision analýza zostávajú mimo prvého overenia.
