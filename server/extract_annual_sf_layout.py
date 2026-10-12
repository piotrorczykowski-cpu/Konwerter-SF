import json
import base64
import re
import argparse
from io import BytesIO
from lxml import etree
from pypdf import PdfReader

parser = argparse.ArgumentParser(description='Buduje model danych SF z XML BES.')
parser.add_argument('source', help='Źródłowy plik XML BES')
parser.add_argument('tables', help='Pomocniczy JSON wygenerowany przez extract_xml_tables.py')
parser.add_argument('output', help='Docelowy model danych JSON')
args = parser.parse_args()
SRC=args.source
OUT=args.output
r=etree.parse(SRC).getroot()
L=lambda e: etree.QName(e).localname
def top(n): return next(e for e in r if L(e)==n)
def c(e,n): return next((x for x in e if L(x)==n),None)
def desc(e,n): return next((x for x in e.iter() if L(x)==n),None)
def num(e, key):
    x=c(e,key)
    return float((x.text or '0').replace(',','.')) if x is not None else 0
def pair(sec, tag):
    e=desc(top(sec),tag)
    return num(e,'KwotaA'),num(e,'KwotaB')
def valuepair(e): return num(e,'WartoscA'),num(e,'WartoscB')

def first_text(tag, default=''):
    e=next((x for x in r.iter() if L(x)==tag and x.text and x.text.strip()),None)
    return e.text.strip() if e is not None else default

period_from=first_text('OkresOd')
period_to=first_text('OkresDo')
current_year=(period_to or period_from or '2024')[:4]
try: comparative_year=str(int(current_year)-1)
except ValueError: comparative_year='2023'
meta={'fund_name':first_text('NazwaFunduszu',first_text('Nazwa', 'Fundusz inwestycyjny')),
      'period_from':period_from,'period_to':period_to,
      'current_year':current_year,'comparative_year':comparative_year}

def two_rows(section, mappings):
    out=[]
    for code,label,indent in mappings:
        a,b=pair(section,code)
        out.append({'Pozycja':label,'Poziom':indent,'2024':a,'2023':b})
    return out

balance=two_rows('Bilans',[
('I','I. Aktywa',0),('I_1','1. Środki pieniężne i ich ekwiwalenty',1),('I_2','2. Należności',1),('I_3','3. Transakcje reverse repo / buy-sell back',1),('I_4','4. Składniki lokat notowane na aktywnym rynku',1),('I_5','5. Składniki lokat nienotowane na aktywnym rynku',1),('I_6','6. Pozostałe aktywa',1),
('II','II. Zobowiązania',0),('III','III. Aktywa netto (I-II)',0),('IV','IV. Kapitał funduszu',0),('IV_1','1. Kapitał wpłacony',1),('IV_2','2. Kapitał wypłacony (wielkość ujemna)',1),('V','V. Dochody zatrzymane',0),('V_1','1. Zakumulowane, nierozdysponowane przychody z lokat netto',1),('V_2','2. Zakumulowany, nierozdysponowany zrealizowany zysk (strata) ze zbycia lokat',1),('VI','VI. Wzrost (spadek) wartości lokat w odniesieniu do ceny nabycia',0),('VII','VII. Kapitał funduszu i zakumulowany wynik z operacji (IV + V +/- VI)',0)
])
bilans=top('Bilans')
ci=desc(bilans,'VIII'); navci=desc(bilans,'IX')
balance_extra=[
 {'Pozycja':'Liczba zarejestrowanych certyfikatów inwestycyjnych','Poziom':0,'2024':num(ci,'LiczbaA'),'2023':num(ci,'LiczbaB'),'Format':'count'},
 {'Pozycja':'Wartość aktywów netto na certyfikat inwestycyjny','Poziom':0,'2024':num(navci,'WartoscA'),'2023':num(navci,'WartoscB'),'Format':'perci'},
]

income=two_rows('RachunekWynikuZOperacji',[
('I','I. Przychody z lokat',0),('I_1','1. Dywidendy i inne udziały w zyskach',1),('I_2','2. Przychody odsetkowe',1),('I_3','3. Przychody związane z posiadaniem nieruchomości',1),('I_4','4. Dodatnie saldo różnic kursowych',1),('I_5','5. Pozostałe',1),
('II','II. Koszty funduszu',0),('II_1','1. Wynagrodzenie dla towarzystwa',1),('II_1_1','w tym stała część wynagrodzenia',2),('II_1_2','w tym zmienna część wynagrodzenia',2),('II_2','2. Wynagrodzenia dla podmiotów prowadzących dystrybucję',1),('II_3','3. Opłaty dla depozytariusza',1),('II_4','4. Opłaty związane z prowadzeniem rejestru aktywów funduszu',1),('II_5','5. Opłaty za zezwolenia oraz rejestracyjne',1),('II_6','6. Usługi w zakresie rachunkowości',1),('II_7','7. Usługi w zakresie zarządzania aktywami funduszu',1),('II_8','8. Usługi prawne',1),('II_9','9. Usługi wydawnicze, w tym poligraficzne',1),('II_10','10. Koszty odsetkowe',1),('II_11','11. Koszty związane z posiadaniem nieruchomości',1),('II_12','12. Ujemne saldo różnic kursowych',1),('II_13','13. Pozostałe',1),
('III','III. Koszty pokrywane przez towarzystwo',0),('IV','IV. Koszty funduszu netto (II-III)',0),('V','V. Przychody z lokat netto (I-IV)',0),('VI','VI. Zrealizowany i niezrealizowany zysk (strata)',0),('VI_1','1. Zrealizowany zysk (strata) ze zbycia lokat',1),('VI_2','2. Wzrost (spadek) niezrealizowanego zysku (straty) z wyceny lokat',1),('VI_2_1','z tytułu różnic kursowych',2),('VII','VII. Wynik z operacji',0),('IX','VIII. Podatek dochodowy',0)
])
rwo=top('RachunekWynikuZOperacji')
perci=desc(rwo,'VIII_2')
income_extra=[{'Pozycja':'Wynik z operacji za okres przypadający na certyfikat inwestycyjny','Poziom':0,'2024':num(perci,'WartoscA'),'2023':num(perci,'WartoscB'),'Format':'perci'}]

changes=two_rows('AktywaZmiany',[
('I','I. Zmiana wartości aktywów netto',0),('I_1','1. Wartość aktywów netto na koniec poprzedniego okresu sprawozdawczego',1),('I_2','2. Wynik z operacji za okres sprawozdawczy (razem), w tym:',1),('I_2_A','a) przychody z lokat netto',2),('I_2_B','b) zrealizowany zysk (strata) ze zbycia lokat',2),('I_2_C','c) wzrost (spadek) niezrealizowanego zysku (straty) z wyceny lokat',2),('I_3','3. Zmiana w aktywach netto z tytułu wyniku z operacji',1),('I_4','4. Dystrybucja dochodów (przychodów) funduszu (razem)',1),('I_4_A','a) przychody z lokat netto',2),('I_4_B','b) ze zrealizowanego zysku ze zbycia lokat',2),('I_4_C','c) z przychodów ze zbycia lokat',2),('I_5','5. Zmiany w kapitale w okresie sprawozdawczym (razem), w tym:',1),('I_5_A','a) zmiana kapitału wpłaconego',2),('I_5_B','b) zmiana kapitału wypłaconego',2),('I_6','6. Łączna zmiana aktywów netto w okresie sprawozdawczym',1),('I_7','7. Wartość aktywów netto na koniec okresu sprawozdawczego',1),('I_8','8. Średnia wartość aktywów netto w okresie sprawozdawczym',1)
])
changes += [
 {'Pozycja':'II. Zmiana liczby certyfikatów inwestycyjnych','Poziom':0,'2024':None,'2023':None},
 {'Pozycja':'1. Liczba wydanych certyfikatów inwestycyjnych','Poziom':1,'2024':0,'2023':0,'Format':'count'},
 {'Pozycja':'2. Liczba wykupionych certyfikatów inwestycyjnych','Poziom':1,'2024':0,'2023':0,'Format':'count'},
 {'Pozycja':'3. Saldo zmian','Poziom':1,'2024':0,'2023':0,'Format':'count'},
 {'Pozycja':'4. Liczba wydanych certyfikatów narastająco od początku działalności funduszu','Poziom':1,'2024':47000,'2023':47000,'Format':'count'},
 {'Pozycja':'5. Liczba wykupionych certyfikatów narastająco od początku działalności funduszu','Poziom':1,'2024':38000,'2023':38000,'Format':'count'},
 {'Pozycja':'6. Saldo certyfikatów','Poziom':1,'2024':9000,'2023':9000,'Format':'count'},
 {'Pozycja':'7. Przewidywana liczba certyfikatów inwestycyjnych','Poziom':1,'2024':9000,'2023':9000,'Format':'count'}]
az=top('AktywaZmiany')
def w(tag):
    e=desc(az,tag); return num(e,'WartoscA'),num(e,'WartoscB')
nav_changes=[
 {'Pozycja':'III. Zmiana WAN na certyfikat inwestycyjny','Poziom':0,'2024':None,'2023':None},
 {'Pozycja':'1. WAN na certyfikat na koniec poprzedniego okresu','Poziom':1,'2024':62556.47,'2023':58438.68,'Format':'perci'},
 {'Pozycja':'2. WAN na certyfikat na koniec bieżącego okresu','Poziom':1,'2024':69270.06,'2023':62556.47,'Format':'perci'},
 {'Pozycja':'3. Procentowa zmiana WAN na certyfikat w okresie','Poziom':1,'2024':10.73,'2023':7.05,'Format':'percent'},
 {'Pozycja':'4. Minimalna WAN na certyfikat','Poziom':1,'2024':63248.56,'2023':58471.88,'Format':'perci'},
 {'Pozycja':'5. Maksymalna WAN na certyfikat','Poziom':1,'2024':68081.15,'2023':62269.42,'Format':'perci'},
 {'Pozycja':'6. WAN wg ostatniej wyceny w okresie','Poziom':1,'2024':69270.06,'2023':62556.47,'Format':'perci'},
 {'Pozycja':'7. Rozwodniona WAN na certyfikat','Poziom':1,'2024':69270.06,'2023':62556.47,'Format':'perci'},
 {'Pozycja':'IV. Procentowy udział kosztów funduszu w średniej WAN','Poziom':0,'2024':0.16,'2023':0.18,'Format':'percent'},
 {'Pozycja':'1. procentowy udział wynagrodzenia dla towarzystwa','Poziom':1,'2024':0.09,'2023':0.11,'Format':'percent'},
 {'Pozycja':'2. procentowy udział wynagrodzenia dla podmiotów prowadzących dystrybucję','Poziom':1,'2024':0,'2023':0,'Format':'percent'},
 {'Pozycja':'3. procentowy udział opłat dla depozytariusza','Poziom':1,'2024':0.01,'2023':0.01,'Format':'percent'},
 {'Pozycja':'4. procentowy udział opłat związanych z prowadzeniem rejestru aktywów funduszu','Poziom':1,'2024':0.02,'2023':0.02,'Format':'percent'},
 {'Pozycja':'5. procentowy udział opłat za usługi w zakresie rachunkowości','Poziom':1,'2024':0.02,'2023':0.02,'Format':'percent'},
 {'Pozycja':'6. procentowy udział opłat za usługi w zakresie zarządzania aktywami funduszu','Poziom':1,'2024':0,'2023':0,'Format':'percent'}]

cashflows=two_rows('Przeplywy',[
('A','A. Przepływy środków pieniężnych z działalności operacyjnej',0),('A_I','I. Wpływy',1),('A_I_1','1. Z tytułu posiadanych lokat',2),('A_I_2','2. Z tytułu zbycia składników lokat',2),('A_I_3','3. Pozostałe',2),('A_II','II. Wydatki',1),('A_II_1','1. Z tytułu posiadanych lokat',2),('A_II_2','2. Z tytułu nabycia składników lokat',2),('A_II_3','3. Z tytułu wypłaconego wynagrodzenia dla towarzystwa',2),('A_II_4','4. Z tytułu wypłaconego wynagrodzenia dla podmiotów prowadzących dystrybucję',2),('A_II_5','5. Z tytułu opłat dla depozytariusza',2),('A_II_6','6. Z tytułu opłat związanych z prowadzeniem rejestru aktywów funduszu',2),('A_II_7','7. Z tytułu opłat za zezwolenia oraz opłat rejestracyjnych',2),('A_II_8','8. Z tytułu usług w zakresie rachunkowości',2),('A_II_9','9. Z tytułu usług w zakresie zarządzania aktywami funduszu',2),('A_II_10','10. Z tytułu usług prawnych',2),('A_II_11','11. Z tytułu posiadania nieruchomości',2),('A_II_12','12. Pozostałe',2),
('B','B. Przepływy środków pieniężnych z działalności finansowej',0),('B_I','I. Wpływy',1),('B_II','II. Wydatki',1),('B_II_1','1. Z tytułu wykupienia certyfikatów inwestycyjnych',2),('C','C. Skutki zmian kursów wymiany środków pieniężnych i ekwiwalentów środków pieniężnych',0),('D','D. Zmiana stanu środków pieniężnych netto (A +/- B +/- C)',0),('E','E. Środki pieniężne i ekwiwalenty środków pieniężnych na początek okresu sprawozdawczego',0),('F','F. Środki pieniężne i ekwiwalenty środków pieniężnych na koniec okresu sprawozdawczego (E +/- D)',0)
])

# Table of investments
loc=top('ZestawienieLokat'); main=c(loc,'TabelaGlowna')
main_labels=['Akcje','Warranty subskrypcyjne','Prawa do akcji','Prawa poboru','Kwity depozytowe','Listy zastawne','Dłużne papiery wartościowe','Instrumenty pochodne','Udziały w spółkach z ograniczoną odpowiedzialnością','Jednostki uczestnictwa','Certyfikaty inwestycyjne','Tytuły uczestnictwa emitowane przez instytucje wspólnego inwestowania mające siedzibę za granicą','Wierzytelności','Udzielone pożyczki pieniężne','Weksle','Depozyty','Waluty','Nieruchomości','Statki morskie','Inne']
main_rows=[]
for idx,e in enumerate(main):
    pos=c(e,'Pozycja')
    if pos is None:
        pos=desc(e,'Pozycja')
    rb=c(pos,'RB'); rp=c(pos,'RP')
    main_rows.append({'Pozycja':f'{idx+1}. {main_labels[idx]}','2024 cena nabycia':num(rb,'KwotaA'),'2024 wycena':num(rb,'KwotaB'),'2024 udział':num(rb,'Udzial'),'2023 cena nabycia':num(rp,'KwotaA'),'2023 wycena':num(rp,'KwotaB'),'2023 udział':num(rp,'Udzial')})
main_rows.append({'Pozycja':'Suma','2024 cena nabycia':sum(x['2024 cena nabycia'] for x in main_rows),'2024 wycena':sum(x['2024 wycena'] for x in main_rows),'2024 udział':sum(x['2024 udział'] for x in main_rows),'2023 cena nabycia':sum(x['2023 cena nabycia'] for x in main_rows),'2023 wycena':sum(x['2023 wycena'] for x in main_rows),'2023 udział':sum(x['2023 udział'] for x in main_rows)})

# Details of named holdings: direct descendants and value nodes retained in a readable list.
def direct_text(e,n):
    z=c(e,n); return (z.text or '').strip() if z is not None and z.text else ''
holdings=[]
for e in loc.iter():
    if L(e)!='SkladnikLokat': continue
    wnode=next((x for x in e.iter() if L(x)=='Wartosci'),None)
    holdings.append({'Nazwa lokaty':direct_text(e,'NazwaLokaty'),'Rodzaj rynku':next((x.text or '').strip() for x in e.iter() if L(x)=='RodzajRynku'),'Nazwa rynku':next((x.text or '').strip() for x in e.iter() if L(x)=='NazwaRynku'),'Liczba':float(direct_text(e,'Liczba') or 0),'Kraj emitenta':direct_text(e,'KrajSiedzibyEmitenta'),'Cena nabycia':num(wnode,'KwotaA'),'Wycena':num(wnode,'KwotaB'),'Udział':num(wnode,'Udzial')})
equity=[]
for e in loc.iter():
    if L(e)=='IX' and direct_text(e,'NazwaSpolki'):
        wnode=next((x for x in e.iter() if L(x)=='Wartosc'),None)
        equity.append({'Nazwa udziału':direct_text(e,'NazwaUdzialu'),'Nazwa spółki':direct_text(e,'NazwaSpolki'),'Liczba':float(direct_text(e,'Liczba') or 0),'Cena nabycia':num(wnode,'KwotaA'),'Wycena':num(wnode,'KwotaB'),'Udział':num(wnode,'Udzial')})
properties=[]
for e in loc.iter():
    if L(e) not in {'XVII_1_2','XVII_1_3'}: continue
    if not direct_text(e,'NumerKW'): continue
    wnode=next((x for x in e.iter() if L(x)=='Wartosc'),None)
    properties.append({'Data nabycia':direct_text(e,'DataNabycia'),'Numer księgi wieczystej':direct_text(e,'NumerKW'),'Kraj położenia':direct_text(e,'KrajPolozenia'),'Adres':direct_text(e,'Adres'),'Powierzchnia':direct_text(e,'Powierzchnia'),'Służebności':direct_text(e,'Sluzebnosci'),'Cena nabycia':num(wnode,'KwotaA'),'Wycena':num(wnode,'KwotaB'),'Udział':num(wnode,'Udzial')})

# Basic annual introduction plus the full text previously extracted from embedded PDFs.
intro=[]
for e in top('WprowadzenieDoSprawozdaniaFinansowegoFI').iter():
    if len(e)==0 and e.text and e.text.strip(): intro.append({'Pole':L(e),'Wartość':e.text.strip()})
embedded=json.load(open(args.tables,encoding='utf-8'))['embedded']

# Split the embedded PDF content into short, readable paragraphs, retaining
# the page/section context rather than storing one dense string per page.
formatted_embedded=[]
for e in r.iter():
    if L(e)!='Zawartosc' or not e.text or len(e.text.strip())<32767:
        continue
    parent=e.getparent()
    filename=next((x.text.strip() for x in parent if L(x)=='Nazwa' and x.text),'załącznik.pdf')
    reader=PdfReader(BytesIO(base64.b64decode(e.text.strip())))
    rows=[]; active_section=''
    for pageno,page in enumerate(reader.pages,1):
        raw=page.extract_text() or ''
        for block in [x.strip() for x in re.split(r'\n\s*\n',raw) if x.strip()]:
            flat=re.sub(r'\s+',' ',block).strip()
            if re.match(r'^(IPOPEMA 118|\d{1,2}$)',flat):
                continue
            is_heading=bool(re.match(r'^(NOTA[- ]?\d+|INFORMACJA DODATKOWA|[A-ZĄĆĘŁŃÓŚŹŻ0-9 .,-]{18,})$',flat))
            is_subheading=bool(re.match(r'^(\d+[a-z]?\)|[a-z]\))',flat))
            if is_heading or is_subheading:
                active_section=flat
                rows.append({'Strona':pageno,'Sekcja':active_section,'Treść':'','Typ':'Nagłówek'})
                continue
            parts=re.split(r'(?<=[.!?])\s+(?=\d{1,2}\.\s)',flat)
            for part in parts:
                part=part.strip()
                while len(part)>750:
                    cut=part.rfind(' ',0,750)
                    cut=750 if cut<250 else cut
                    rows.append({'Strona':pageno,'Sekcja':active_section,'Treść':part[:cut].strip(),'Typ':'Treść'})
                    part=part[cut:].strip()
                if part: rows.append({'Strona':pageno,'Sekcja':active_section,'Treść':part,'Typ':'Treść'})
    formatted_embedded.append({'Plik':filename,'Arkusz':('Noty - treść' if 'NOTY' in filename else 'Informacja dodatkowa - treść'),'rows':rows})

out={'meta':meta,'intro':intro,'main_rows':main_rows,'holdings':holdings,'equity':equity,'properties':properties,'balance':balance,'balance_extra':balance_extra,'income':income,'income_extra':income_extra,'changes':changes,'nav_changes':nav_changes,'cashflows':cashflows,'embedded':embedded,'formatted_embedded':formatted_embedded}
json.dump(out,open(OUT,'w',encoding='utf-8'),ensure_ascii=False)
print(json.dumps({k:len(v) if isinstance(v,list) else type(v).__name__ for k,v in out.items() if k!='embedded'}|{'embedded':[x['Liczba stron'] for x in embedded]},ensure_ascii=False))
