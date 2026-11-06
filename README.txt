3d_workspace – uživatelská příručka
===================================

Tento pracovní prostor slouží k archivaci 3D digitalizátů pořízených
skenerem GOM / ZEISS Scan 1 a zpracovaných v ZEISS Inspect. Pro každý objekt
vytvoří samostatný archivní balíček s pevnou strukturou složek a kontrolními
součty SHA-256. Struktura metadat je můj vlastní návrh pro 3D data
(viz část 5). Verze workflow: 1.0.0 (viz část 10).

Balíček obsahuje mesh TAK, JAK BYL NAMĚŘEN (díry nejsou zalepené), určený pro
podrobné studium povrchu, např. traseologii.

Jde o osobní pracovní nástroj, který mi usnadňuje práci. Nejde o oficiální
nástroj ani metadatový standard žádné instituce.


1. SLOŽKY
---------
  input_staging/   sem vložte data k archivaci
  master/          hotové archivní balíčky (ručně neupravovat)
  log/             dig3d.log – záznam o každém spuštění
  tool/            nástroj:
                     dig3d.py            skript
                     archive.bat         archivuje objekt z input_staging
                     verify.bat          zkontroluje celý archiv
                     config/config.json       šablona metadat objektu
                     config/calibration.json  kalibrace skeneru (viz 3.2)


2. INSTALACE (jednorázově)
--------------------------
  1. Nainstalujte Python 3.9 nebo novější (https://www.python.org).
     Ve Windows při instalaci zaškrtněte „Add Python to PATH“.
  2. Otevřete příkazový řádek a spusťte:
       py -m pip install numpy
     numpy je povinné: počítá technickou část metadat (rozměry, rozlišení,
     plocha, díry). Bez něj nástroj archivaci odmítne.


3. ARCHIVACE OBJEKTU
--------------------
  1. V ZEISS Inspect:
       - PŘED polygonizací nastavte sérii měření na „Více detailů“,
         NE na „Uživatelsky definováno“, a nechte model přepočítat,
       - teprve potom polygonizujte sken, také v režimu „Více detailů“;
         díry NEZALEPUJTE,
       - vyexportujte mesh jako .ply,
       - vyexportujte stejný prvek meshe jako .zixml (paradata).
     Exportujte prvek MESHE. Export měřicí série obsahuje jen referenční
     body a nástroj ho odmítne.

  2. Zkopírujte tool/config/config.json do input_staging/ a vyplňte jej:

       {
         "id": "",                          <- ID objektu: A-Z, 0-9, „-“, „_“
         "cultural_heritage_object": {
           "title": "",
           "inventory_number": "",
           "institution_owner": "MZM"
         },
         "digitization": {
           "date": "YYYY-MM-DD",             <- datum skenování
           "operator_name": "",
           "equipment": "GOM Scan 1",
           "software": "ZEISS Inspect"
         }
       }

     Povinné: id, title, inventory_number, institution_owner, date,
     operator_name.

     Kalibrace se u objektu NEVYPLŇUJE. Nástroj ji bere z
     tool/config/calibration.json: nejnovější kalibraci s datem
     nejpozději v den skenování.
     Po rekalibraci do calibration.json PŘIDEJTE nový záznam (zkopírujte
     poslední a přepište hodnoty z „Informace o aktuální kalibraci“
     v ZEISS Inspect). Staré záznamy nikdy nepřepisujte – starší skeny
     archivované později je stále potřebují.

  3. V input_staging/ musí být přesně tři soubory:
       jeden .ply, jeden .zixml a jeden .json.
     Na názvech nezáleží, nástroj soubory přejmenuje.

  4. Spusťte tool/archive.bat (dvojklikem).

  5. Hotovo. Balíček je v master/<id>_<ROK>/ (ROK = rok skenování)
     a input_staging/ se vyprázdní.


4. STRUKTURA BALÍČKU
--------------------
  master/<id>_<ROK>/
  |-- 01_MESH/<id>_mesh.ply            naměřený mesh (díry nezalepené)
  |-- 02_PARADATA/<id>_paradata.zixml  parametry polygonizace ze ZEISS Inspect
  `-- 03_METADATA/<id>_metadata.json   metadata vč. kontrolních součtů dat


5. METADATA.JSON (struktura metadat)
------------------------------------
  id                              ID objektu
  workflow_version                verze tohoto nástroje (část 10)
  cultural_heritage_object        z config.json
  digitization                    z config.json
  calibration                     z tool/config/calibration.json,
                                  platná v den skenování
  files                           cesta, SHA-256 a velikost každého souboru
  technical
    mesh                          formát, jednotka, vrcholy, plošky,
                                  rozměry, délka hran (rozlišení), plocha,
                                  otevřené hrany, díry, watertight
    paradata                      verze ZEISS Inspect, jednotka, parametry
                                  polygonizace a kroky post-processingu
                                  (čísla s jednotkami; české texty ze
                                  ZEISS přeložené do angličtiny)

  Vše kromě config.json doplní nástroj automaticky.


6. NAHRAZENÍ OBJEKTU
--------------------
  Balíčky se neverzují. Pokud je potřeba objekt archivovat znovu (nový
  sken, opravená metadata), přesuňte starý balíček z master/ jinam (nebo
  ho smažte) a archivujte objekt znovu podle části 3. Objekt, který už
  v master/ je, nástroj odmítne.


7. KONTROLA ARCHIVU
-------------------
  Spusťte tool/verify.bat. Nástroj znovu spočítá SHA-256 každého souboru ve
  všech balíčcích (mesh a paradata) a nahlásí chybějící nebo poškozený
  soubor.
  Doporučeno jednou měsíčně a po každé záloze.


8. ČASTÉ HLÁŠKY (nástroj píše anglicky)
---------------------------------------
  „input_staging must contain exactly one .ply file (found 0)“
      Chybí soubor, nebo jsou ve složce soubory dvou objektů.

  „Missing in config.json: ...“
      Vyplňte uvedená pole.

  „digitization.date must be YYYY-MM-DD“
      Datum pište jako 2026-10-21.

  „id may contain only letters A-Z, digits, '-' and '_'“
      V ID nesmí být mezery, lomítka ani diakritika.

  „The .zixml contains no polygonization parameters“
      Byla vyexportována měřicí série místo prvku meshe.

  „Polygonization mode is '...' - only 'More details' is allowed“
      Nastavte sérii měření na „Více detailů“, nechte model přepočítat
      a polygonizujte znovu v režimu „Více detailů“.

  „master/... already exists“
      Objekt už je archivovaný. Nejdřív přesuňte nebo smažte starý balíček
      (část 6).

  „Inventory number '...' is already archived under id '...'“
      Objekt už je archivovaný pod jiným id. Zkontrolujte inventární číslo,
      nebo nejdřív odstraňte starý balíček.

  „No calibration ... is dated on or before the date of scanning“
      Sken je starší než všechny kalibrace v calibration.json. Zkontrolujte
      datum, nebo doplňte kalibraci platnou v té době.

  „numpy is not installed“
      Nainstalujte numpy (část 2).

  „... package(s) checked: N error(s)“
      Některý soubor v master/ je poškozený nebo chybí. Obnovte jej ze zálohy.


9. DOPORUČENÍ
-------------
  - Nástroj přijme jen režim polygonizace „Více detailů“, takže jsou všechny
    objekty zpracované stejně.
  - Také série měření musí být před polygonizací nastavená na „Více
    detailů“. Nástroj to zkontrolovat neumí (v .zixml to není uložené),
    odpovídá za to operátor.
  - Ve složce master/ nic ručně neupravujte (odstranění celého balíčku
    před novou archivací je v pořádku).
  - Uchovávejte zálohu master/ na jiném disku a po každé záloze spusťte
    kontrolu (verify).


10. VERZE WORKFLOW
------------------
  Verze workflow se zapisuje do každého souboru metadat (workflow_version),
  takže je vždy jasné, kterou verzí nástroje balíček vznikl. Při změně
  nástroje zvyšte verzi v dig3d.py (WORKFLOW_VERSION) a přidejte sem
  záznam, nejnovější nahoru.
  MAJOR.MINOR.PATCH: MAJOR = změna struktury metadat, MINOR = nové
  kontroly nebo hodnoty, PATCH = opravy bez vlivu na výstup.

  1.0.0  2026-10-27
    - První verze. Vyžaduje Python 3.9+ a numpy.
    - Vstup: mesh .ply, paradata .zixml (jen režim „Více detailů“),
      config.json; kalibrace z tool/config/calibration.json podle data
      skenování.
    - Balíček <id>_<ROK> se složkami 01_MESH, 02_PARADATA, 03_METADATA;
      id objektu v názvech všech souborů.
    - Metadata podle vlastní struktury pro 3D data; rozbor meshe
      (rozměry, rozlišení, plocha, díry) a parametry polygonizace se
      načítají automaticky.
    - SHA-256 meshe a paradat v metadatech; příkaz verify.
    - Kontroly: povinná pole, formát data a id, duplicitní id a inventární
      číslo, nainstalované numpy.
