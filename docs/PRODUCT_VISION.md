# Produktová vízia: jedna pracovná karta pre elektrikára

**Pre koho:** majiteľ a 1–5 členná elektro firma, ktorá prijíma vlastné dopyty, robí obhliadky alebo servis, nacení a odovzdá prácu a sama rieši fakturáciu. Prvým zákazníkom je vlastná prevádzka. Predaj ako SaaS je samostatná hypotéza, nie cieľ prvej verzie.

**Problém:** údaje o klientovi a mieste sú v telefóne, správach, fotkách, poznámkach, ponuke a faktúre. Strácajú sa rozhodnutia, extra práce a náklady. Majiteľ večer prepisuje to, čo už raz videl na stavbe, a nevie s istotou povedať, na ktorej práci zarobil.

**Sľub produktu:** pri každej zákazke zadať identitu, miesto a rozsah raz; potom už len dopĺňať rozhodnutia a skutočnosť. Mobilná karta musí pridať poznámku alebo fotku za 5–10 sekúnd z otvorenej zákazky. Čísla musia mať viditeľný výpočet a pôvod.

## Hlavný pracovný tok

**Väčšia práca:** dopyt → kvalifikácia a ďalší krok → obhliadka → rozsah po miestnostiach → kontrolovateľná kalkulácia → verzia ponuky → potvrdenie zákazníka → zákazka → termíny a nákup → práca/fotky/extra práce → odovzdávacie podklady → koncept faktúry → človekom schválené vystavenie → platba → porovnanie odhadu so skutočnosťou.

**Servis:** dopyt → triáž/termín → zákazka alebo odsúhlasená sadzba → práca/fotka/čas/materiál → potvrdený výsledok → faktúra → platba. Obhliadka a detailná ponuka nie sú povinné formuláre, ak by len zdržiavali.

Stav obchodného prípadu a stav vykonávania sú dve rôzne veci. Dopyt môže byť odmietnutý alebo čakať na zákazníka. Zákazka môže byť pripravená, prebiehať, čakať na materiál alebo byť hotová. Faktúra môže byť vystavená a nezaplatená. Jediný preťažený status by tieto otázky nevyriešil.

## Vstup a práca na mobile

- Pri hovore: rýchly záznam mena/kontaktu, obce alebo adresy, opisu, zdroja a ďalšieho kroku. Po hovore odkaz na doplnenie fotiek a pôdorysu, ak je to potrebné.
- Na stavbe: posledná alebo dnešná karta je na úvodnej obrazovke. Plávajúce **+** ponúkne Foto, Poznámka/hlas, Náklad, Čas, Extra práca. Aplikácia predvyplní zákazku a poslednú miestnosť; používateľ vidí výsledný kontext pred uložením.
- Po obhliadke: nejasnosti sú otázky na klienta, nie vymyslené položky. AI môže pripraviť návrh rozsahu, ale cena vzniká z viditeľných množstiev, sadzieb a materiálu.
- Pri slabom signáli: rozhranie nesmie falošne potvrdiť uloženie. Najprv je prípustné vyžadovať spojenie s jasným upozornením; skutočný offline režim až po terénnom teste, ktorý ukáže jeho potrebu.

## Menu podľa rozhodnutí, nie tabuliek

| Položka | Otázka, ktorú rieši | Obsah |
| --- | --- | --- |
| **Dnes** | Čo musím spraviť? | odpovedať, naceniť, dnešná práca, chýbajúci materiál, možno fakturovať, po splatnosti |
| **Prípady** | Kto odo mňa niečo chce a v akom je to stave? | dopyty a zákazky v jednom zozname; filtre Čaká na mňa, Čaká na zákazníka, Ponuky, Realizácia, Hotové |
| **Plán** | Kde a kedy mám byť? | obhliadky, servisné sloty, etapy stavieb, kolízie |
| **Peniaze** | Čo môžem fakturovať a kto nezaplatil? | koncepty/vystavené faktúry, úhrady, jednoduchá ziskovosť |
| **+** | Čo chcem rýchlo pridať? | kontextové akcie bez ďalšieho menu |

Klient, miesto, doklady, materiál, okruhy a AI sú vo vnútri prípadu alebo pri tvorbe ponuky. AI nie je samostatný povinný modul hlavnej navigácie. Na počítači možno mať rovnaké štyri hlavné položky a viac priestoru pre kalkuláciu.

## Pravidlá, ktoré chránia dôveru

1. Kontakt a miesto majú jedno kanonické ID. Ponuka, zákazka a faktúra naň nadväzujú; odoslaná ponuka a vystavená faktúra navyše držia zmrazený právny snapshot, aby sa neskoršia oprava kontaktu netvárila ako historická dohoda.
2. Každá predajná cena sa dá rozložiť na množstvo, sadzbu, materiál, dopravu, subdodávky, rezervu, zľavu a daňový režim. Rozdiel medzi prirážkou a maržou je zobrazený správne. AI nepridáva cenu bez zobrazenia a potvrdenia.
3. Každá fotka má súkromné oprávnenie a minimálne zákazku, čas a text miesta; pri rozvodoch pred zakrytím aj miestnosť, prvok/trasa a poznámku. Názov súboru ani OCR nikdy nie sú jediný index.
4. Strojový prepis, OCR a vision sú návrhy. Človek potvrdí štruktúrovaný záznam, cenu, súhlas zákazníka, vystavenie faktúry, odoslanie a technické závery.
5. Finančný pohľad prizná chýbajúce hodiny, doklady alebo náklady. Neúplný príspevok sa nesmie označovať ako zisk.

## Čo produkt zámerne teraz nerobí

Nevykonáva projektovanie a revíziu elektrického zariadenia, neurčuje bezpečné istenie z fotografie, nesľubuje univerzálnu legislatívnu správnosť pre SK/CZ/AT/DE, neposiela finančné správy bez kontroly, nebuduje viacprofesijný ERP, úplný sklad ani vlastné účtovníctvo. Export faktúr a dokumentov musí mať miesto pre lokálny účtovný/eFakturačný adapter, keď bude presný právny režim overený.

## Ako rozhodneme, či produkt funguje

Na troch vlastných typoch prác (malý servis, rekonštrukcia, viacdňová práca) zmerať čas administratívy od prijatia dopytu po faktúru, počet opakovaných prepisov adresy/rozsahu, čas vytvorenia ponuky, zabudnuté a sporné položky, čas nájdenia fotografie, pokrytie nákladov a rozdiel odhad/skutočnosť. Po pilotnom mesiaci porovnať s pôvodným postupom. Orientačná pokračovacia brána: aspoň dve z troch práce bez ručného prepisu klienta/miesta a bez nezdokumentovanej extra práce; majiteľ po dokončení vidí, prečo marža vyšla inak. Ak to nevyjde, upraviť workflow, nie pridávať AI.

Pre prípadný SaaS má zmysel test až po tom, čo systém používa vlastná firma a aspoň niekoľko cudzích elektrikárov ho dobrovoľne používa na reálnych prípadoch alebo zaplatí za konkrétny výsledok. Súčasné verejné zdroje nepotvrdzujú ochotu platiť za ďalší softvér.
