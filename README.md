# SF XML Converter — aplikacja webowa

Publiczna aplikacja internetowa do konwersji rocznych i półrocznych plików XML BES funduszy do skoroszytu XLSX w układzie SF półrocznego.

## Działanie

- formularz przyjmuje jeden plik XML;
- `POST /api/convert` waliduje rozszerzenie i przetwarza plik w katalogu tymczasowym;
- wynik XLSX jest zwracany bezpośrednio do przeglądarki;
- katalog tymczasowy jest usuwany po przesłaniu odpowiedzi; aplikacja nie prowadzi historii plików.

## Uruchomienie lokalne

```bash
python -m pip install -r requirements.txt
python server/server.py
```

Następnie otwórz `http://localhost:8080`.

## Wdrożenie

Repozytorium zawiera `Dockerfile`; można je wdrożyć na platformie obsługującej kontenery, np. Render, Railway, Fly.io lub Azure App Service. Należy pozostawić zmienną `PORT` ustawianą przez platformę.

Przed publicznym uruchomieniem warto ustawić limit żądań na poziomie hostingu / CDN, choć aplikacja nie wymaga logowania.
