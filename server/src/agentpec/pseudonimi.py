"""Pseudonimizzazione facoltativa dei dati identificativi nel testo.

Sostituisce codici fiscali, partite IVA, IBAN, numeri di telefono e
indirizzi email con segnaposto come [CF_1], [EMAIL_2]. Lo stesso valore
riceve lo stesso segnaposto finché il server resta acceso; la tabella di
corrispondenza sta solo in memoria e non viene mai scritta su disco né
restituita all'agente.

È una riduzione del rischio, non un'anonimizzazione: nomi, indirizzi
postali e altri dati restano nel testo.
"""

from __future__ import annotations

import re
import threading

# Codice fiscale delle persone fisiche (con omocodia).
_CF = re.compile(
    r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b",
    re.IGNORECASE,
)
# IBAN: due lettere, due cifre di controllo, poi 11-30 caratteri, anche a gruppi di 4.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
# Partita IVA: 11 cifre, eventualmente precedute da IT.
_PIVA = re.compile(r"\b(?:IT[ ]?)?(\d{11})\b", re.IGNORECASE)
# Telefoni italiani: fissi (0...) e mobili (3...), con +39/0039 facoltativo.
_TEL = re.compile(
    r"(?<![\w+])(?:(?:\+|00)39[ .\-]?)?(?:3\d{2}|0\d{1,3})(?:[ .\-/]?\d){5,8}(?![\w])"
)

_DISPARI_CF = {
    **{str(i): v for i, v in enumerate([1, 0, 5, 7, 9, 13, 15, 17, 19, 21])},
    **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
               [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23])),
}


def cf_valido(cf: str) -> bool:
    cf = cf.upper()
    if len(cf) != 16:
        return False
    somma = 0
    for i, c in enumerate(cf[:15]):
        if i % 2 == 0:  # posizioni dispari (1-based)
            somma += _DISPARI_CF[c]
        else:
            somma += int(c) if c.isdigit() else ord(c) - ord("A")
    return chr(ord("A") + somma % 26) == cf[15]


def piva_valida(piva: str) -> bool:
    if len(piva) != 11 or not piva.isdigit():
        return False
    somma = 0
    for i, c in enumerate(piva[:10]):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        somma += n
    return (10 - somma % 10) % 10 == int(piva[10])


def iban_valido(iban: str) -> bool:
    s = iban.replace(" ", "").upper()
    if len(s) < 15 or len(s) > 34:
        return False
    riordinato = s[4:] + s[:4]
    numeri = "".join(str(int(c, 36)) for c in riordinato)
    return int(numeri) % 97 == 1


class Pseudonimizzatore:
    def __init__(self) -> None:
        self._mappa: dict[tuple[str, str], str] = {}
        self._contatori: dict[str, int] = {}
        self._lock = threading.Lock()

    def _segnaposto(self, tipo: str, valore: str) -> str:
        chiave = (tipo, re.sub(r"[\s.\-/]", "", valore.upper()))
        with self._lock:
            if chiave not in self._mappa:
                self._contatori[tipo] = self._contatori.get(tipo, 0) + 1
                self._mappa[chiave] = f"[{tipo}_{self._contatori[tipo]}]"
            return self._mappa[chiave]

    def applica(self, testo: str | None) -> str | None:
        if not testo:
            return testo
        t = _EMAIL.sub(lambda m: self._segnaposto("EMAIL", m.group(0)), testo)
        t = _IBAN.sub(lambda m: self._segnaposto("IBAN", m.group(0)) if iban_valido(m.group(0)) else m.group(0), t)
        t = _CF.sub(lambda m: self._segnaposto("CF", m.group(0)) if cf_valido(m.group(0)) else m.group(0), t)
        t = _PIVA.sub(lambda m: self._segnaposto("PIVA", m.group(1)) if piva_valida(m.group(1)) else m.group(0), t)
        t = _TEL.sub(lambda m: self._segnaposto("TEL", m.group(0)), t)
        return t
