import asyncio
import aiohttp
import json
import csv
import time
import os
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

        # Rinominato per chiarezza: la lista dei target disponibili
        self.targets = self.config.get('targets', [])
        self.parallel = self.config.get('parallel_users', 1)
        self.total_reqs = self.config.get('total_requests', 10)
        self.delay = self.config.get('delay_ms', 0) / 1000.0

        self.stats = defaultdict(list)
        os.makedirs(LOG_DIR, exist_ok=True)

    def init_csv(self):
        with open(DETAIL_CSV, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Aggiunta colonna Global_ID per tracciare l'ordine globale
            writer.writerow(
                ['Timestamp', 'Global_ID', 'Worker', 'Method', 'URL', 'Status', 'Duration(s)', 'Response_Snippet'])

    def log_request(self, global_id, worker_name, method, url, status, duration, response_text):
        snippet = response_text[:50].replace('\n', ' ') + "..." if response_text else "No Body"

        with open(DETAIL_CSV, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                global_id,  # ID progressivo globale (1, 2, 3...)
                worker_name,  # Chi ha eseguito il lavoro
                method,
                url,
                status,
                f"{duration:.4f}",
                snippet
            ])

        key = (method, url)
        self.stats[key].append({'code': status, 'time': duration})

    async def fetch(self, session, item, worker_name):
        """
        Esegue la chiamata.
        item è una tupla: (global_index, target_data)
        """
        global_id, target = item
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
                response_text = await response.text()

        except Exception as e:
            status = "ERROR"
            response_text = str(e)
        finally:
            duration = time.time() - start_time
            self.log_request(global_id, worker_name, method, url, status, duration, response_text)
            print(f"[{worker_name}] Req #{global_id} -> {method} {url} ({status})")

    async def worker(self, name, queue, session):
        """
        Il worker non ha un indice. Prende solo il prossimo ticket dalla coda globale.
        """
        while True:
            try:
                # Prende il prossimo task disponibile (ordine FIFO garantito)
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            await self.fetch(session, item, name)
            queue.task_done()

            if self.delay > 0:
                await asyncio.sleep(self.delay)

    async def run(self):
        self.init_csv()
        queue = asyncio.Queue()

        # --- PREPARAZIONE CODA GLOBALE ---
        # Qui definiamo l'ordine ESATTO delle chiamate.
        # Se targets = [A, B] e total = 5 -> Coda: [A, B, A, B, A]
        # I worker preleveranno in questo esatto ordine.
        print("Preparazione coda globale condivisa...")
        for i in range(self.total_reqs):
            target = self.targets[i % len(self.targets)]
            # Inseriamo nella coda una tupla: (NumeroProgressivo, DatiTarget)
            queue.put_nowait((i + 1, target))

        print(f"🚀 Starting Stress Test: {self.total_reqs} requests in Global Queue, {self.parallel} workers...")

        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(self.parallel):
                # Lanciamo i worker. Loro condivideranno la stessa istanza di 'queue'
                task = asyncio.create_task(self.worker(f"W-{i + 1}", queue, session))
                tasks.append(task)

            await queue.join()

            for task in tasks:
                task.cancel()

        self.generate_report()
        print(f"\n✅ Done. Logs saved in {LOG_DIR}/")

    def generate_report(self):
        print("Generating Summary Report...")
        with open(SUMMARY_CSV, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Method', 'URL', 'Response Code', 'Count', 'Avg Duration(s)', 'Min', 'Max'])

            for (method, url), data in self.stats.items():
                codes = defaultdict(list)
                for entry in data:
                    codes[entry['code']].append(entry['time'])

                for code, times in codes.items():
                    avg_time = sum(times) / len(times)
                    writer.writerow([
                        method, url, code, len(times),
                        f"{avg_time:.4f}", f"{min(times):.4f}", f"{max(times):.4f}"
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