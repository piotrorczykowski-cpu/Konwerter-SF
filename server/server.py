import cgi
import os
import shutil
import subprocess
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'dist'
SCRIPTS=Path(__file__).parent

class App(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return str(STATIC / (path.split('?',1)[0].lstrip('/') or 'index.html'))

    def do_POST(self):
        if self.path!='/api/convert': self.send_error(404); return
        form=cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST','CONTENT_TYPE':self.headers.get('Content-Type','')})
        item=form['file'] if 'file' in form else None
        if item is None: self.send_error(400,'Brak pliku XML'); return
        if getattr(item,'file',None) is None: self.send_error(400,'Brak pliku XML'); return
        name=Path(item.filename or 'sprawozdanie.xml').name
        if not name.lower().endswith('.xml'): self.send_error(400,'Wymagany jest plik XML'); return
        with tempfile.TemporaryDirectory(prefix='sf-xml-') as d:
            d=Path(d); source=d/name; source.write_bytes(item.file.read())
            if source.stat().st_size>30*1024*1024: self.send_error(413,'Plik jest zbyt duży'); return
            tables=d/'tables.json'; model=d/'model.json'; output=d/(source.stem+'.xlsx')
            try:
                subprocess.run([sys.executable,str(SCRIPTS/'extract_xml_tables.py'),str(source),str(tables)],check=True,capture_output=True,text=True,timeout=90)
                subprocess.run([sys.executable,str(SCRIPTS/'extract_annual_sf_layout.py'),str(source),str(tables),str(model)],check=True,capture_output=True,text=True,timeout=90)
                subprocess.run([sys.executable,str(SCRIPTS/'build_workbook.py'),str(model),str(output)],check=True,capture_output=True,text=True,timeout=90)
            except subprocess.CalledProcessError as e: self.send_error(422,'Nie udało się odczytać struktury XML BES'); return
            except subprocess.TimeoutExpired: self.send_error(504,'Przetwarzanie pliku przekroczyło limit czasu'); return
            content=output.read_bytes()
        self.send_response(200); self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'); self.send_header('Content-Disposition',f'attachment; filename="{output.name}"'); self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),App).serve_forever()
