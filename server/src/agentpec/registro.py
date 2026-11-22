"""Registro locale delle operazioni: solo metadati, mai contenuti.

Ogni riga è un oggetto JSON con data, strumento, esito, numero di
risultati e identificativi tecnici (id interni di Thunderbird e impronte
non reversibili degli id delle cartelle). Non vengono registrati: testo dei messaggi, oggetti,
indirizzi, nomi di allegati, parole cercate.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Iterable

from .percorsi import assicura_cartella_privata, percorso_registro

CAMPI_AMMESSI = {"ts", "strumento", "esito", "n_risultati", "id_messaggi", "id_cartelle", "errore"}


def impronta(valore: object) -> str:
    return hashlib.sha256(str(valore).encode("utf-8")).hexdigest()[:12]


def registra(
    strumento: str,
    esito: str,
    *,
    n_risultati: int | None = None,
    id_messaggi: Iterable[int] | None = None,
    id_cartelle: Iterable[str] | None = None,
    errore: str | None = None,
) -> None:
    voce: dict = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "strumento": strumento,
        "esito": esito,
    }
    if n_risultati is not None:
        voce["n_risultati"] = int(n_risultati)
    if id_messaggi is not None:
        voce["id_messaggi"] = [int(i) for i in id_messaggi][:200]
    if id_cartelle is not None:
        # Gli id delle cartelle contengono il loro nome (che può essere il nome
        # di un cliente): si registra solo un'impronta non reversibile.
        voce["id_cartelle"] = [impronta(c) for c in id_cartelle][:50]
    if errore is not None:
        # Solo il codice dell'errore, non il messaggio (potrebbe contenere dati).
        voce["errore"] = str(errore)[:60]
    assert set(voce) <= CAMPI_AMMESSI
    p = percorso_registro()
    assicura_cartella_privata(p.parent)
    fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")
