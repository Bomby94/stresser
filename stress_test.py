import asyncio
import aiohttp
import json
import csv
import time
import os
import random
from collections import defaultdict
from datetime import datetime

# Configurazione percorsi
CONFIG_FILE = 'config.json'
LOG_DIR = 'logs'
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
DETAIL_CSV = os.path.join(LOG_DIR, f'stress_log_{TIMESTAMP}.csv')
SUMMARY_CSV = os.path.join(LOG_DIR, f'stress_summary_{TIMESTAMP}.csv')


class StressTester:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.targets = self.config.get('targets', [])
        self.parallel = self.config.get('parallel_users', 1)
        self.total_reqs = self.config.get('total_requests', 10)
        self.delay = self.config.get('delay_ms', 0) / 1000.0

        # Struttura per il report finale
        # Key: (method, url) -> Value: list of (status, duration)
        self.stats = defaultdict(list)

        # Creazione cartella logs se non esiste
        os.makedirs(LOG_DIR, exist_ok=True)

    def init_csv(self):
        """Inizializza il file CSV di log dettagliato"""
        with open(DETAIL_CSV, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Method', 'URL', 'Status', 'Duration(s)', 'Response_Snippet'])

    def log_request(self, method, url, status, duration, response_text):
        """Scrive una riga nel CSV dettagliato e aggiorna le stats in memoria"""
        # Scrittura su file (append mode)
        snippet = response_text[:50].replace('\n', ' ') + "..." if response_text else "No Body"

        with open(DETAIL_CSV, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                method,
                url,
                status,
                f"{duration:.4f}",
                snippet
            ])

        # Aggiornamento statistiche per report finale
        key = (method, url)
        self.stats[key].append({
            'code': status,
            'time': duration
        })

    async def fetch(self, session, target):
        """Esegue la singola chiamata HTTP"""
        url = target['url']
        method = target['method'].upper()
        body = target.get('body')

        start_time = time.time()
        response_text = ""
        status = 0

        try:
            kwargs = {}
            if body and method in ['POST', 'PUT', 'PATCH']:
                kwargs['json'] = body

            async with session.request(method, url, **kwargs) as response:
                status = response.status
                # Leggiamo il testo solo per loggarlo (attenzione se sono file giganti)
                response_text = await response.text()

        except Exception as e:
            status = "ERROR"
            response_text = str(e)
        finally:
            duration = time.time() - start_time
            self.log_request(method, url, status, duration, response_text)

            # Output a console minimale per vedere che scorre
            print(f"[{status}] {method} {url} - {duration:.2f}s")

    async def worker(self, name, queue, session):
        """Il worker consuma la coda di richieste"""
        while True:
            # Prende un task dalla coda
            try:
                target = queue.get_nowait()
            except asyncio.QueueEmpty:
                break  # Coda finita

            await self.fetch(session, target)
            queue.task_done()

            # Delay configurato
            if self.delay > 0:
                await asyncio.sleep(self.delay)

    async def run(self):
        self.init_csv()
        queue = asyncio.Queue()

        # Popoliamo la coda distribuendo i target in round-robin fino al totale
        for i in range(self.total_reqs):
            target = self.targets[i % len(self.targets)]
            queue.put_nowait(target)

        print(f"🚀 Starting Stress Test: {self.total_reqs} requests, {self.parallel} workers...")

        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(self.parallel):
                task = asyncio.create_task(self.worker(f"worker-{i}", queue, session))
                tasks.append(task)

            # Attende che la coda sia vuota
            await queue.join()

            # Cancella i worker (anche se dovrebbero uscire da soli col break)
            for task in tasks:
                task.cancel()

        self.generate_report()
        print(f"\n✅ Done. Logs saved in {LOG_DIR}/")

    def generate_report(self):
        """Genera il CSV riepilogativo"""
        print("Generating Summary Report...")
        with open(SUMMARY_CSV, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(
                ['Method', 'URL', 'Response Code', 'Count', 'Avg Duration(s)', 'Min Duration(s)', 'Max Duration(s)'])

            for (method, url), data in self.stats.items():
                # Raggruppa per status code all'interno dello stesso URL
                codes = defaultdict(list)
                for entry in data:
                    codes[entry['code']].append(entry['time'])

                for code, times in codes.items():
                    avg_time = sum(times) / len(times)
                    min_time = min(times)
                    max_time = max(times)
                    writer.writerow([
                        method,
                        url,
                        code,
                        len(times),
                        f"{avg_time:.4f}",
                        f"{min_time:.4f}",
                        f"{max_time:.4f}"
                    ])


if __name__ == "__main__":
    if not os.path.exists(CONFIG_FILE):
        print(f"Errore: {CONFIG_FILE} non trovato.")
        exit(1)

    tester = StressTester(CONFIG_FILE)
    try:
        asyncio.run(tester.run())
    except KeyboardInterrupt:
        print("\n🛑 Test interrotto manualmente.")
        tester.generate_report()