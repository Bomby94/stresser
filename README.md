# Python HTTP Stress Tester

Uno strumento leggero e asincrono scritto in Python per eseguire stress test su endpoint HTTP (API, pagine web, script PHP, ecc.). 

Lo script esegue chiamate in parallelo, registra ogni singola risposta e genera un report statistico finale.

## 🚀 Funzionalità

- **Esecuzione Asincrona**: Utilizza `asyncio` e `aiohttp` per alte prestazioni e bassa occupazione di memoria.
- **Configurabile via JSON**: Definisci endpoint, payload, concorrenza e delay facilmente.
- **Logging in tempo reale**: Crea un CSV con i dettagli di ogni singola chiamata (status, durata, risposta).
- **Reportistica**: Genera un CSV riepilogativo raggruppato per Endpoint e Status Code con tempi medi di risposta.

## 📋 Prerequisiti

- Python 3.8 o superiore
- pip

## 🛠️ Installazione

1. Clona il repository o scarica i file.
2. (Opzionale ma consigliato) Crea un virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Su Windows: venv\Scripts\activate
   ```
3. Esegui `pip install -r requirements.txt`.
