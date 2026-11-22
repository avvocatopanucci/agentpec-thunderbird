"""Percorsi locali di AgentPEC.

Tutto sta in una cartella leggibile solo dall'utente (permessi 0700).
Qui NON viene mai salvato il contenuto della posta: solo il socket di
collegamento, il codice di sessione e il registro dei metadati.
"""

from __future__ import annotations

import os
from pathlib import Path

NOME_HOST_NATIVO = "agentpec"


def cartella_base() -> Path:
    personalizzata = os.environ.get("AGENTPEC_HOME")
    base = Path(personalizzata) if personalizzata else Path.home() / ".agentpec"
    return base


def cartella_run() -> Path:
    return cartella_base() / "run"


def percorso_socket() -> Path:
    return cartella_run() / "agentpec.sock"


def percorso_token() -> Path:
    return cartella_run() / "sessione.token"


def percorso_registro() -> Path:
    return cartella_base() / "registro.jsonl"


def assicura_cartella_privata(p: Path) -> Path:
    """Crea la cartella con permessi 0700 e li riforza se esiste già."""
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p
