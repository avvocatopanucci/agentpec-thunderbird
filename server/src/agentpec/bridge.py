"""Programma ponte avviato da Thunderbird (native messaging).

Thunderbird lo avvia quando l'estensione AgentPEC chiama
runtime.connectNative("agentpec") e gli parla su stdin/stdout con
messaggi JSON preceduti da 4 byte di lunghezza.

Il server MCP, avviato invece dall'app di Claude, si collega al ponte con
un socket Unix locale: un file in ~/.agentpec/run (cartella 0700, socket
0600), protetto anche da un codice di sessione casuale rigenerato a ogni
avvio. Nessuna porta di rete viene aperta.

Il ponte non legge né conserva la posta: inoltra richieste e risposte.
Nel log (stderr) scrive solo eventi tecnici, mai contenuti.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import secrets
import signal
import struct
import sys
from typing import Any

from .percorsi import assicura_cartella_privata, cartella_run, percorso_socket, percorso_token

TIMEOUT_RICHIESTA = 90.0
LIMITE_RIGA = 64 * 1024 * 1024
MAX_RICHIESTA_VERSO_TB = 900 * 1024  # Thunderbird accetta al massimo 1 MB dal programma nativo.


def log(msg: str) -> None:
    print(f"[agentpec-bridge] {msg}", file=sys.stderr, flush=True)


class Ponte:
    def __init__(self) -> None:
        self._contatore = itertools.count(1)
        self._in_attesa: dict[int, asyncio.Future] = {}
        self._scrittura = asyncio.Lock()
        self._token = secrets.token_urlsafe(32)
        self._stdout = sys.stdout.buffer
        self._fine = asyncio.Event()

    # --- lato Thunderbird -------------------------------------------------

    async def invia_a_thunderbird(self, messaggio: dict[str, Any]) -> None:
        dati = json.dumps(messaggio, ensure_ascii=False).encode("utf-8")
        if len(dati) > MAX_RICHIESTA_VERSO_TB:
            raise ValueError("richiesta_troppo_grande")
        async with self._scrittura:
            self._stdout.write(struct.pack("=I", len(dati)))
            self._stdout.write(dati)
            self._stdout.flush()

    async def leggi_da_thunderbird(self) -> None:
        loop = asyncio.get_running_loop()
        lettore = asyncio.StreamReader(limit=LIMITE_RIGA)
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(lettore), sys.stdin.buffer)
        try:
            while True:
                testa = await lettore.readexactly(4)
                (lunghezza,) = struct.unpack("=I", testa)
                corpo = await lettore.readexactly(lunghezza)
                try:
                    msg = json.loads(corpo.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    log("messaggio non valido da Thunderbird, ignorato")
                    continue
                self._consegna(msg)
        except asyncio.IncompleteReadError:
            log("Thunderbird ha chiuso il collegamento")
        finally:
            for fut in self._in_attesa.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("thunderbird_chiuso"))
            self._fine.set()

    def _consegna(self, msg: dict[str, Any]) -> None:
        if msg.get("tipo") == "ciao":
            log(f"estensione collegata, versione {msg.get('versione')!s:.20}")
            return
        rid = msg.get("id")
        fut = self._in_attesa.pop(rid, None) if isinstance(rid, int) else None
        if fut and not fut.done():
            fut.set_result(msg)

    async def chiedi(self, metodo: str, parametri: dict[str, Any]) -> dict[str, Any]:
        rid = next(self._contatore)
        fut = asyncio.get_running_loop().create_future()
        self._in_attesa[rid] = fut
        try:
            await self.invia_a_thunderbird({"id": rid, "metodo": metodo, "parametri": parametri})
            return await asyncio.wait_for(fut, TIMEOUT_RICHIESTA)
        finally:
            self._in_attesa.pop(rid, None)

    # --- lato server MCP --------------------------------------------------

    async def gestisci_client(self, lettore: asyncio.StreamReader, scrittore: asyncio.StreamWriter) -> None:
        try:
            prima = await asyncio.wait_for(lettore.readline(), 5)
            try:
                saluto = json.loads(prima)
            except json.JSONDecodeError:
                saluto = {}
            if not isinstance(saluto, dict) or not secrets.compare_digest(str(saluto.get("token", "")), self._token):
                log("collegamento rifiutato: codice di sessione errato")
                return
            while not lettore.at_eof():
                riga = await lettore.readline()
                if not riga:
                    break
                try:
                    req = json.loads(riga)
                    cid = req.get("id")
                    metodo = str(req["metodo"])
                    parametri = req.get("parametri") or {}
                    if not isinstance(parametri, dict):
                        raise ValueError
                except (json.JSONDecodeError, KeyError, ValueError, AttributeError):
                    risposta = {"id": None, "errore": {"codice": "richiesta_non_valida"}}
                else:
                    try:
                        r = await self.chiedi(metodo, parametri)
                        risposta = {"id": cid, **{k: v for k, v in r.items() if k != "id"}}
                    except asyncio.TimeoutError:
                        risposta = {"id": cid, "errore": {"codice": "tempo_scaduto"}}
                    except (ConnectionError, ValueError) as e:
                        risposta = {"id": cid, "errore": {"codice": str(e) or "errore_ponte"}}
                scrittore.write(json.dumps(risposta, ensure_ascii=False).encode("utf-8") + b"\n")
                await scrittore.drain()
        except (asyncio.TimeoutError, ConnectionError, asyncio.LimitOverrunError, ValueError):
            pass
        finally:
            scrittore.close()

    async def esegui(self) -> None:
        assicura_cartella_privata(cartella_run().parent)
        assicura_cartella_privata(cartella_run())
        sock = percorso_socket()
        if sock.exists() or sock.is_symlink():
            sock.unlink()
        vecchia = os.umask(0o177)
        try:
            server = await asyncio.start_unix_server(self.gestisci_client, path=str(sock), limit=LIMITE_RIGA)
        finally:
            os.umask(vecchia)
        os.chmod(sock, 0o600)
        tok = percorso_token()
        fd = os.open(tok, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(self._token)
        log("pronto")
        lettura = asyncio.create_task(self.leggi_da_thunderbird())
        loop = asyncio.get_running_loop()
        for s in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(s, self._fine.set)
        try:
            await self._fine.wait()
        finally:
            lettura.cancel()
            server.close()
            for p in (sock, tok):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
            log("chiuso")


def main() -> None:
    try:
        asyncio.run(Ponte().esegui())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
