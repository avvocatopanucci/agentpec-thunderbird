"""Riconoscimento dei messaggi PEC e lettura del file daticert.xml.

Le intestazioni e la struttura di daticert.xml seguono le regole tecniche
della PEC (DPR 11 febbraio 2005, n. 68, art. 6, e DM 2 novembre 2005). Il parser è volutamente
prudente: estrae solo i campi noti, non risolve entità né DTD esterne
(defusedxml) e segnala ogni dato come "da verificare".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

# Valori di X-Ricevuta previsti dalle regole tecniche.
TIPI_RICEVUTA = {
    "accettazione": "Ricevuta di accettazione",
    "non-accettazione": "Avviso di non accettazione",
    "presa-in-carico": "Ricevuta di presa in carico",
    "avvenuta-consegna": "Ricevuta di avvenuta consegna",
    "errore-consegna": "Avviso di mancata consegna",
    "preavviso-errore-consegna": "Preavviso di mancata consegna",
    "rilevazione-virus": "Avviso di rilevazione virus",
}

# Valori di X-Trasporto (buste che contengono un messaggio).
TIPI_TRASPORTO = {
    "posta-certificata": "Busta di trasporto (messaggio PEC ricevuto)",
    "errore": "Busta di anomalia",
}

# Prefissi degli oggetti usati dai gestori: servono solo come primo filtro,
# la conferma viene dalle intestazioni X-Ricevuta / X-Trasporto.
PREFISSI_OGGETTO = (
    "ACCETTAZIONE:",
    "CONSEGNA:",
    "POSTA CERTIFICATA:",
    "AVVISO DI NON ACCETTAZIONE",
    "AVVISO DI MANCATA CONSEGNA",
    "AVVISO DI MANCATA CONSEGNA PER SUP. TEMPO MASSIMO",
    "PRESA IN CARICO:",
    "ANOMALIA MESSAGGIO:",
    "PROBLEMA DI SICUREZZA:",
)

NOTA_VERIFICA = (
    "Dati estratti automaticamente: da verificare sulla ricevuta originale "
    "prima di farvi affidamento per termini o adempimenti."
)


def oggetto_sembra_pec(oggetto: str | None) -> bool:
    if not oggetto:
        return False
    o = oggetto.strip().upper()
    return any(o.startswith(p) for p in PREFISSI_OGGETTO)


def _primo(headers: Mapping[str, Any], nome: str) -> str | None:
    """Thunderbird restituisce le intestazioni come {nome: [valori]} in minuscolo."""
    val = headers.get(nome.lower())
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        return str(val[0]).strip() if val else None
    return str(val).strip()


def pulisci_message_id(mid: str | None) -> str | None:
    if not mid:
        return None
    mid = mid.strip()
    if mid.startswith("<") and mid.endswith(">"):
        mid = mid[1:-1]
    return mid.strip() or None


@dataclass
class Classificazione:
    e_pec: bool
    categoria: str | None = None  # "ricevuta" | "trasporto" | None
    tipo: str | None = None  # es. "accettazione"
    descrizione: str | None = None
    tipo_ricevuta: str | None = None  # completa | breve | sintetica
    riferimento_message_id: str | None = None
    identificativo: str | None = None

    def come_dict(self) -> dict[str, Any]:
        return asdict(self)


def classifica_intestazioni(headers: Mapping[str, Any]) -> Classificazione:
    """Dice se un messaggio è una ricevuta PEC o una busta di trasporto."""
    h = {str(k).lower(): v for k, v in headers.items()}
    ricevuta = (_primo(h, "x-ricevuta") or "").lower()
    trasporto = (_primo(h, "x-trasporto") or "").lower()
    rif = pulisci_message_id(_primo(h, "x-riferimento-message-id"))
    ident = _primo(h, "x-identificativo") or _primo(h, "x-identificativo-messaggio")
    tipo_ric = _primo(h, "x-tiporicevuta")
    if ricevuta:
        return Classificazione(
            e_pec=True,
            categoria="ricevuta",
            tipo=ricevuta,
            descrizione=TIPI_RICEVUTA.get(ricevuta, "Ricevuta PEC di tipo non riconosciuto"),
            tipo_ricevuta=tipo_ric.lower() if tipo_ric else None,
            riferimento_message_id=rif,
            identificativo=ident,
        )
    if trasporto:
        return Classificazione(
            e_pec=True,
            categoria="trasporto",
            tipo=trasporto,
            descrizione=TIPI_TRASPORTO.get(trasporto, "Busta PEC di tipo non riconosciuto"),
            riferimento_message_id=rif,
            identificativo=ident,
        )
    return Classificazione(e_pec=False)


@dataclass
class Daticert:
    tipo: str | None = None
    errore: str | None = None
    errore_esteso: str | None = None
    mittente: str | None = None
    destinatari: list[dict[str, str]] = field(default_factory=list)
    risposte: str | None = None
    oggetto: str | None = None
    gestore_emittente: str | None = None
    data_giorno: str | None = None
    data_ora: str | None = None
    data_zona: str | None = None
    data_iso: str | None = None
    identificativo: str | None = None
    msgid: str | None = None
    ricevuta_tipo: str | None = None
    consegna: str | None = None
    avvertenze: list[str] = field(default_factory=list)

    def come_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["descrizione_tipo"] = TIPI_RICEVUTA.get(self.tipo or "") or TIPI_TRASPORTO.get(self.tipo or "")
        d["nota"] = NOTA_VERIFICA
        return d


class DaticertNonValido(ValueError):
    pass


_ZONA = re.compile(r"^([+-])(\d{2}):?(\d{2})$")

MAX_DIMENSIONE_DATICERT = 256 * 1024


def _testo(el) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _data_iso(giorno: str | None, ora: str | None, zona: str | None) -> tuple[str | None, list[str]]:
    avv: list[str] = []
    if not giorno or not ora:
        return None, ["Data o ora mancanti nel daticert."]
    try:
        dt = datetime.strptime(f"{giorno} {ora}", "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None, [f"Formato data non riconosciuto: {giorno} {ora}."]
    if zona:
        m = _ZONA.match(zona.strip())
        if m:
            segno = 1 if m.group(1) == "+" else -1
            delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
            dt = dt.replace(tzinfo=timezone(segno * delta))
        else:
            avv.append(f"Fuso orario non riconosciuto: {zona}.")
    else:
        avv.append("Fuso orario non indicato nel daticert.")
    return dt.isoformat(), avv


def leggi_daticert(xml: str | bytes) -> Daticert:
    """Legge il contenuto di daticert.xml e restituisce i campi noti."""
    if isinstance(xml, str):
        dati = xml.encode("utf-8")
    else:
        dati = xml
    if len(dati) > MAX_DIMENSIONE_DATICERT:
        raise DaticertNonValido("daticert.xml troppo grande per essere una ricevuta.")
    try:
        radice = SafeET.fromstring(dati, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as e:
        raise DaticertNonValido(f"daticert.xml rifiutato per motivi di sicurezza: {type(e).__name__}") from e
    except SafeET.ParseError as e:
        raise DaticertNonValido(f"daticert.xml non leggibile: {e}") from e

    if radice.tag != "postacert":
        raise DaticertNonValido(f"Elemento radice inatteso: {radice.tag!r} (atteso 'postacert').")

    d = Daticert()
    d.tipo = radice.get("tipo")
    d.errore = radice.get("errore")

    intest = radice.find("intestazione")
    dati_el = radice.find("dati")
    if intest is None or dati_el is None:
        d.avvertenze.append("Struttura incompleta: mancano 'intestazione' o 'dati'.")

    if intest is not None:
        d.mittente = _testo(intest.find("mittente"))
        for dest in intest.findall("destinatari"):
            indirizzo = _testo(dest)
            if indirizzo:
                d.destinatari.append({"indirizzo": indirizzo, "tipo": dest.get("tipo") or "non indicato"})
        d.risposte = _testo(intest.find("risposte"))
        d.oggetto = _testo(intest.find("oggetto"))

    if dati_el is not None:
        d.gestore_emittente = _testo(dati_el.find("gestore-emittente"))
        data_el = dati_el.find("data")
        if data_el is not None:
            d.data_zona = data_el.get("zona")
            d.data_giorno = _testo(data_el.find("giorno"))
            d.data_ora = _testo(data_el.find("ora"))
            d.data_iso, avv = _data_iso(d.data_giorno, d.data_ora, d.data_zona)
            d.avvertenze.extend(avv)
        else:
            d.avvertenze.append("Data mancante nel daticert.")
        d.identificativo = _testo(dati_el.find("identificativo"))
        d.msgid = pulisci_message_id(_testo(dati_el.find("msgid")))
        ric = dati_el.find("ricevuta")
        if ric is not None:
            d.ricevuta_tipo = ric.get("tipo")
        d.consegna = _testo(dati_el.find("consegna"))
        d.errore_esteso = _testo(dati_el.find("errore-esteso"))

    if d.tipo and d.tipo not in TIPI_RICEVUTA and d.tipo != "posta-certificata":
        d.avvertenze.append(f"Tipo di ricevuta non previsto: {d.tipo}.")
    if d.errore and d.errore != "nessuno":
        d.avvertenze.append(f"Il daticert segnala un errore: {d.errore}.")
    return d


def confronta_con_intestazioni(d: Daticert, c: Classificazione) -> list[str]:
    """Segnala incongruenze tra daticert.xml e le intestazioni del messaggio."""
    avv: list[str] = []
    if c.categoria == "ricevuta" and d.tipo and c.tipo and d.tipo != c.tipo:
        avv.append(f"Tipo diverso tra intestazione ({c.tipo}) e daticert ({d.tipo}).")
    if d.msgid and c.riferimento_message_id and d.msgid != c.riferimento_message_id:
        avv.append("Il riferimento al messaggio originale differisce tra intestazione e daticert.")
    return avv
