"""Stato degli invii PEC: per ogni messaggio inviato, quali ricevute sono arrivate.

Funzione pura, senza accesso a Thunderbird: riceve i messaggi inviati e le
ricevute (con intestazioni e daticert.xml) e calcola lo stato di ciascun
invio. Le conclusioni sono indicative e vanno verificate sulle ricevute
originali; in questa versione la firma digitale delle ricevute NON è
verificata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email.utils import getaddresses
from typing import Any, Iterable

from .pec import DaticertNonValido, classifica_intestazioni, leggi_daticert, pulisci_message_id

TIPI_ERRORE = {"non-accettazione", "errore-consegna", "preavviso-errore-consegna", "rilevazione-virus"}

STATI = {
    "consegnata": "Consegnata a tutti i destinatari",
    "consegna_parziale": "Consegnata solo ad alcuni destinatari, per gli altri nessuna ricevuta",
    "problema": "Almeno un avviso di mancata consegna, non accettazione o virus",
    "in_attesa_consegna": "Accettata dal gestore, nessuna ricevuta di consegna",
    "nessuna_ricevuta": "Nessuna ricevuta trovata nelle cartelle consentite",
}

NOTA = (
    "Stato ricostruito automaticamente dalle ricevute presenti nelle cartelle consentite. "
    "La firma digitale delle ricevute non è verificata in questa versione e una ricevuta "
    "potrebbe trovarsi in una cartella non autorizzata: verificare sempre sulle ricevute "
    "originali prima di farvi affidamento."
)


def indirizzi(valori: Iterable[str] | None) -> list[str]:
    """Estrae gli indirizzi email (minuscoli) da voci come 'Nome <a@b.it>'."""
    risultato: list[str] = []
    for _, indirizzo in getaddresses(list(valori or [])):
        a = indirizzo.strip().lower()
        if a and "@" in a and a not in risultato:
            risultato.append(a)
    return risultato


@dataclass
class EventoRicevuta:
    id: int | None
    tipo: str
    data: str | None  # data certificata se c'è il daticert, altrimenti data del messaggio
    data_certificata: bool
    destinatario: str | None
    errore: str | None = None

    def come_dict(self) -> dict[str, Any]:
        d = {"id": self.id, "tipo": self.tipo, "data": self.data,
             "data_da_daticert": self.data_certificata, "destinatario": self.destinatario}
        if self.errore:
            d["errore"] = self.errore
        return d


@dataclass
class StatoInvio:
    originale: dict[str, Any]
    destinatari: list[str]
    accettazione: EventoRicevuta | None = None
    consegne: list[EventoRicevuta] = field(default_factory=list)
    problemi: list[EventoRicevuta] = field(default_factory=list)
    altre: list[EventoRicevuta] = field(default_factory=list)
    avvertenze: list[str] = field(default_factory=list)

    @property
    def consegnati(self) -> list[str]:
        return sorted({e.destinatario for e in self.consegne if e.destinatario})

    @property
    def senza_ricevuta(self) -> list[str]:
        coperti = set(self.consegnati) | {e.destinatario for e in self.problemi if e.destinatario}
        return [d for d in self.destinatari if d not in coperti]

    @property
    def stato(self) -> str:
        if self.problemi:
            return "problema"
        if self.consegne:
            return "consegnata" if not self.senza_ricevuta else "consegna_parziale"
        if self.accettazione:
            return "in_attesa_consegna"
        return "nessuna_ricevuta"

    def come_dict(self) -> dict[str, Any]:
        return {
            "originale": self.originale,
            "stato": self.stato,
            "descrizione_stato": STATI[self.stato],
            "destinatari": self.destinatari,
            "accettazione": self.accettazione.come_dict() if self.accettazione else None,
            "consegne": [e.come_dict() for e in self.consegne],
            "problemi": [e.come_dict() for e in self.problemi],
            "altre_ricevute": [e.come_dict() for e in self.altre],
            "destinatari_senza_ricevuta": self.senza_ricevuta,
            "avvertenze": self.avvertenze,
        }


def _evento(ricevuta: dict[str, Any]) -> tuple[str | None, EventoRicevuta | None, list[str]]:
    """Ricava riferimento al messaggio originale ed evento da una ricevuta."""
    avv: list[str] = []
    c = classifica_intestazioni(ricevuta.get("intestazioni_tecniche", {}))
    if c.categoria != "ricevuta" or not c.tipo:
        return None, None, avv
    rif = c.riferimento_message_id
    data, certificata, destinatario, errore = ricevuta.get("data"), False, None, None
    xml = ricevuta.get("daticert_xml")
    if xml:
        try:
            d = leggi_daticert(xml)
        except DaticertNonValido as e:
            avv.append(f"Ricevuta {ricevuta.get('id')}: {e}")
        else:
            rif = d.msgid or rif
            if d.data_iso:
                data, certificata = d.data_iso, True
            destinatario = (d.consegna or "").strip().lower() or None
            if d.errore and d.errore != "nessuno":
                errore = d.errore_esteso or d.errore
            if d.tipo and d.tipo != c.tipo:
                avv.append(f"Ricevuta {ricevuta.get('id')}: tipo diverso tra intestazione e daticert.")
    return pulisci_message_id(rif), EventoRicevuta(
        id=ricevuta.get("id"), tipo=c.tipo, data=data, data_certificata=certificata,
        destinatario=destinatario, errore=errore,
    ), avv


def calcola_stati(originali: list[dict[str, Any]], ricevute: list[dict[str, Any]]) -> dict[str, Any]:
    stati: dict[str, StatoInvio] = {}
    ordine: list[str] = []
    for o in originali:
        mid = pulisci_message_id(o.get("message_id"))
        if not mid or mid in stati:
            continue
        stati[mid] = StatoInvio(
            originale=o,
            destinatari=indirizzi(list(o.get("destinatari") or []) + list(o.get("cc") or [])),
        )
        ordine.append(mid)

    non_collegate = 0
    avvertenze_generali: list[str] = []
    for r in ricevute:
        rif, ev, avv = _evento(r)
        avvertenze_generali.extend(avv)
        if ev is None:
            continue
        s = stati.get(rif or "")
        if s is None:
            non_collegate += 1
            continue
        if ev.tipo == "accettazione":
            if s.accettazione is None:
                s.accettazione = ev
            else:
                s.altre.append(ev)
                s.avvertenze.append("Più ricevute di accettazione per lo stesso messaggio.")
        elif ev.tipo == "avvenuta-consegna":
            s.consegne.append(ev)
            if ev.destinatario and ev.destinatario not in s.destinatari:
                s.avvertenze.append(
                    f"Ricevuta di consegna per un indirizzo non presente tra i destinatari: {ev.destinatario}."
                )
        elif ev.tipo in TIPI_ERRORE:
            s.problemi.append(ev)
        else:
            s.altre.append(ev)

    elenco = [stati[m].come_dict() for m in ordine]
    riepilogo: dict[str, int] = {k: 0 for k in STATI}
    for e in elenco:
        riepilogo[e["stato"]] += 1
    return {
        "invii": elenco,
        "riepilogo": riepilogo,
        "ricevute_non_collegate": non_collegate,
        "avvertenze": avvertenze_generali,
        "nota": NOTA,
    }


_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def data_valida(s: str | None) -> bool:
    return s is None or bool(_DATA.match(s))
