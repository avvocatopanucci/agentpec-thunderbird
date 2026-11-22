"""Conversione prudente da HTML a testo semplice, senza dipendenze esterne."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCCHI = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table", "hr"}
_IGNORATI = {"script", "style", "head", "title", "template", "noscript"}


class _Estrattore(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parti: list[str] = []
        self._ignora = 0
        self.nascosti = 0

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORATI:
            self._ignora += 1
        if tag in _BLOCCHI:
            self.parti.append("\n")
        stile = (dict(attrs).get("style") or "").replace(" ", "").lower()
        if "display:none" in stile or "font-size:0" in stile or "visibility:hidden" in stile:
            # Il testo nascosto resta incluso (l'agente lo "vedrebbe" comunque),
            # ma lo contiamo per segnalarlo.
            self.nascosti += 1

    def handle_endtag(self, tag):
        if tag in _IGNORATI and self._ignora:
            self._ignora -= 1
        if tag in _BLOCCHI:
            self.parti.append("\n")

    def handle_data(self, data):
        if not self._ignora:
            self.parti.append(data)


def html_in_testo(sorgente: str) -> tuple[str, int]:
    e = _Estrattore()
    try:
        e.feed(sorgente)
        e.close()
    except Exception:  # HTML malformato: ripiego grezzo
        return html.unescape(re.sub(r"<[^>]+>", " ", sorgente)), 0
    t = "".join(e.parti)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip(), e.nascosti


def tronca(t: str, massimo: int) -> tuple[str, bool]:
    if len(t) <= massimo:
        return t, False
    return t[:massimo], True
