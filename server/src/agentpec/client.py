"""Collegamento dal server MCP al programma ponte, tramite socket Unix locale."""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

from .percorsi import percorso_socket, percorso_token

_contatore = itertools.count(1)

MESSAGGI_ERRORE = {
    "non_collegato": (
        "Thunderbird non risulta aperto, oppure l'estensione AgentPEC non è attiva. "
        "Apri Thunderbird e controlla che l'estensione sia caricata."
    ),
    "cartella_non_consentita": "La cartella non è tra quelle consentite nelle impostazioni di AgentPEC.",
    "messaggio_non_consentito": (
        "Il messaggio non esiste, si trova in una cartella non consentita, oppure l'id non è più "
        "valido: gli id cambiano a ogni riavvio di Thunderbird e valgono solo per messaggi già "
        "restituiti da una ricerca. Rifai prima cerca_messaggi o elenca_ricevute_pec."
    ),
    "nessuna_cartella_consentita": (
        "Nelle impostazioni di AgentPEC non è stata scelta nessuna cartella: "
        "l'agente non vede nulla finché non ne autorizzi almeno una."
    ),
    "bozze_disattivate": (
        "La preparazione di bozze è disattivata nelle impostazioni di AgentPEC."
    ),
    "cartella_inviati_mancante": (
        "Non trovo la cartella della posta inviata tra quelle consentite: autorizzala nelle "
        "impostazioni di AgentPEC oppure indicane l'id nel parametro cartelle_inviati."
    ),
    "sospeso": "AgentPEC è sospeso dall'utente in Thunderbird: nessuna lettura è possibile finché non lo riattiva.",
    "limite_raggiunto": (
        "Raggiunto il limite di letture all'ora impostato dall'utente in AgentPEC. Riprova più tardi "
        "o chiedi all'utente di alzare il limite."
    ),
    "account_non_consentito": "L'account indicato non è tra quelli consentiti.",
    "parametri_non_validi": "Parametri non validi.",
    "tempo_scaduto": "Thunderbird non ha risposto in tempo.",
    "thunderbird_chiuso": "Thunderbird è stato chiuso durante la richiesta.",
    "metodo_sconosciuto": "Operazione non prevista dall'estensione.",
}


class ErroreAgentPEC(Exception):
    def __init__(self, codice: str, dettaglio: str | None = None) -> None:
        self.codice = codice
        msg = MESSAGGI_ERRORE.get(codice, f"Errore: {codice}")
        if dettaglio:
            msg = f"{msg} ({dettaglio})"
        super().__init__(msg)


async def chiedi(metodo: str, parametri: dict[str, Any] | None = None, timeout: float = 120.0) -> dict[str, Any]:
    """Invia una richiesta all'estensione e restituisce il campo 'risultato'."""
    try:
        token = percorso_token().read_text().strip()
        lettore, scrittore = await asyncio.wait_for(
            asyncio.open_unix_connection(str(percorso_socket()), limit=64 * 1024 * 1024), 5
        )
    except (FileNotFoundError, ConnectionRefusedError, OSError, asyncio.TimeoutError):
        raise ErroreAgentPEC("non_collegato") from None
    try:
        rid = next(_contatore)
        scrittore.write(json.dumps({"token": token}).encode() + b"\n")
        scrittore.write(
            json.dumps({"id": rid, "metodo": metodo, "parametri": parametri or {}}, ensure_ascii=False).encode("utf-8")
            + b"\n"
        )
        await scrittore.drain()
        riga = await asyncio.wait_for(lettore.readline(), timeout)
        if not riga:
            raise ErroreAgentPEC("non_collegato")
        risposta = json.loads(riga)
    except asyncio.TimeoutError:
        raise ErroreAgentPEC("tempo_scaduto") from None
    finally:
        scrittore.close()
    if "errore" in risposta and risposta["errore"]:
        e = risposta["errore"]
        raise ErroreAgentPEC(str(e.get("codice", "errore")), e.get("dettaglio"))
    return risposta.get("risultato") or {}
