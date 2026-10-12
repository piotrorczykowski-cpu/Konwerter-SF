import json
import re
import base64
import argparse
from io import BytesIO
from collections import Counter, defaultdict
from lxml import etree
from pypdf import PdfReader

parser = argparse.ArgumentParser(description='Ekstrakcja pomocnicza z XML BES funduszu.')
parser.add_argument('source', help='Źródłowy plik XML BES')
parser.add_argument('output', help='Docelowy plik JSON')
args = parser.parse_args()
SOURCE = args.source
OUT = args.output

root = etree.parse(SOURCE).getroot()

def local(element):
    return etree.QName(element).localname

def indexed_path(element):
    pieces=[]
    cur=element
    while cur is not None and cur is not root:
        parent=cur.getparent()
        same=[x for x in parent if local(x)==local(cur)] if parent is not None else []
        pos=(same.index(cur)+1) if len(same)>1 else None
        pieces.append(local(cur)+(f' [{pos}]' if pos else ''))
        cur=parent
    return ' / '.join(reversed(pieces))

def section(element):
    cur=element
    while cur.getparent() is not root and cur.getparent() is not None:
        cur=cur.getparent()
    return 'Podpisy cyfrowe' if local(cur)=='Signature' else local(cur)

def attrs(element):
    out=[]
    for k,v in element.attrib.items():
        out.append(f'{etree.QName(k).localname}={v}')
    return '; '.join(out)

leaves=[]
embedded=[]
for i,e in enumerate(root.iter()):
    if len(e)==0 and (e.text is not None or e.attrib):
        raw=(e.text or '').strip()
        # The two long Zawartosc fields are base64-encoded PDFs. Excel cannot
        # hold these values in one cell; their substantive page text is added
        # below in dedicated searchable tables.
        if local(e)=='Zawartosc' and len(raw)>32767:
            parent=e.getparent()
            filename=next((x.text.strip() for x in parent if local(x)=='Nazwa' and x.text), 'załącznik.pdf')
            try:
                reader=PdfReader(BytesIO(base64.b64decode(raw)))
                pages=[]
                for page_no,page in enumerate(reader.pages,1):
                    txt=re.sub(r'\s+', ' ', (page.extract_text() or '')).strip()
                    # Excel permits up to 32,767 characters per cell; retain text in chunks.
                    for chunk_no,start in enumerate(range(0, len(txt) or 1, 30000),1):
                        pages.append({'Strona':page_no,'Część strony':chunk_no,'Treść':txt[start:start+30000] if txt else ''})
                embedded.append({'Plik':filename,'Format':'PDF','Rozmiar Base64 (znaki)':len(raw),'Liczba stron':len(reader.pages),'Arkusz treści':('Noty - treść' if 'NOTY' in filename else 'Informacja dodatkowa - treść'),'rows':pages})
                raw=f'[Treść osadzonego PDF wyodrębniona do arkusza: {embedded[-1]["Arkusz treści"]}; plik: {filename}; Base64: {len((e.text or "").strip())} znaków.]'
            except Exception as ex:
                raw=f'[Nie udało się odczytać osadzonego PDF: {ex}]'
        leaves.append({
            'Lp.':i+1,
            'Sekcja':section(e),
            'Ścieżka XML':indexed_path(e),
            'Pole':local(e),
            'Wartość':raw,
            'Atrybuty':attrs(e),
            'Podpis techniczny':'Tak' if section(e)=='Podpisy cyfrowe' else 'Nie'
        })

sections=defaultdict(list)
for r in leaves: sections[r['Sekcja']].append(r)

# Nodes with immediate children used in the financial statement. This compact table
# preserves the code and all immediate values as separate columns.
financial=[]
financial_sections={'ZestawienieLokat','Bilans','RachunekWynikuZOperacji','AktywaZmiany','Przeplywy'}
for e in root.iter():
    s=section(e)
    if s not in financial_sections:
        continue
    direct={local(c):(c.text or '').strip() for c in e if len(c)==0 and (c.text is not None or c.attrib)}
    numeric_keys={'KwotaA','KwotaB','KwotaB1','WartoscA','WartoscB','Udzial','LiczbaA','LiczbaB','LiczbaB1','Liczba'}
    if not any(k in direct for k in numeric_keys):
        continue
    row={'Sekcja':s,'Kod pozycji':local(e),'Ścieżka XML':indexed_path(e)}
    row.update(direct)
    financial.append(row)

# Named investment records: preserve direct and nested leaf fields in a single row.
holdings=[]
for e in root.iter():
    if local(e) not in {'SkladnikLokat','IX','XVII_1_2','XVII_1_3'}:
        continue
    values=defaultdict(list)
    for d in e.iterdescendants():
        if len(d)==0 and d.text and d.text.strip():
            values[local(d)].append(d.text.strip())
    if not (values.get('NazwaLokaty') or values.get('NazwaUdzialu') or values.get('NazwaSpolki') or values.get('Adres')):
        continue
    row={'Typ rekordu':local(e),'Ścieżka XML':indexed_path(e)}
    for k,v in values.items(): row[k]=' | '.join(v)
    holdings.append(row)

order=['Naglowek','WprowadzenieDoSprawozdaniaFinansowegoFI','ZestawienieLokat','Bilans','RachunekWynikuZOperacji','AktywaZmiany','Przeplywy','NotyObjasniajaceFI','InformacjaDodatkowaFI','Podpisy cyfrowe']
labels={
 'Naglowek':'Nagłówek','WprowadzenieDoSprawozdaniaFinansowegoFI':'Wprowadzenie',
 'ZestawienieLokat':'Zestawienie lokat','Bilans':'Bilans',
 'RachunekWynikuZOperacji':'Rachunek wyniku z operacji','AktywaZmiany':'Zmiany aktywów netto',
 'Przeplywy':'Rachunek przepływów','NotyObjasniajaceFI':'Noty objaśniające',
 'InformacjaDodatkowaFI':'Informacja dodatkowa','Podpisy cyfrowe':'Podpisy cyfrowe'
}
summary=[]
for key in order:
    summary.append({'Zakładka':labels[key], 'Sekcja XML':key, 'Liczba pól':len(sections.get(key,[])), 'Zawartość':'Pełna tabela wszystkich pól z tej części XML'})

with open(OUT,'w',encoding='utf-8') as f:
    json.dump({'summary':summary,'leaves':leaves,'sections':sections,'financial':financial,'holdings':holdings,'embedded':embedded,'labels':labels},f,ensure_ascii=False)

print(json.dumps({'fields':len(leaves),'financial_rows':len(financial),'holding_rows':len(holdings),'embedded':[(x['Plik'],x['Liczba stron'],len(x['rows'])) for x in embedded],'section_counts':{k:len(v) for k,v in sections.items()}},ensure_ascii=False))
