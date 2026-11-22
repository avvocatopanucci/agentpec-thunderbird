"""Controllo statico: l'estensione non contiene funzioni di scrittura, rete o aggiornamento."""

import json
import re
from pathlib import Path

EST = Path(__file__).resolve().parents[2] / "extension"

VIETATI_CODICE = [
    r"sendMessage\s*\(",          # compose.sendMessage / messages.sendMessage
    r"messages\.(delete|move|copy|archive|update|import|createTag|deleteTag)\b",
    r"folders\.(create|delete|rename|move|copy|update|markAsRead)\b",
    r"compose\.(saveMessage|setComposeDetails|addAttachment)\b",
    r"identities\.(create|update|delete|setDefault)\b",
    r"\bfetch\s*\(",
    r"XMLHttpRequest",
    r"WebSocket",
    r"sendBeacon",
    r"\beval\s*\(",
    r"new\s+Function\s*\(",
]

PERMESSI_AMMESSI = {"accountsRead", "messagesRead", "storage", "nativeMessaging", "compose"}


def _senza_commenti(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.DOTALL)
    return "\n".join(r.split("//")[0] if "://" not in r else r for r in js.splitlines())


def test_nessuna_api_di_scrittura_o_rete():
    for f in EST.glob("*.js"):
        codice = _senza_commenti(f.read_text(encoding="utf-8"))
        for v in VIETATI_CODICE:
            assert not re.search(v, codice), f"{f.name}: trovato {v}"


def test_manifest_minimo():
    m = json.loads((EST / "manifest.json").read_text(encoding="utf-8"))
    assert set(m["permissions"]) == PERMESSI_AMMESSI
    assert "experiment_apis" not in m
    assert "host_permissions" not in m
    assert "update_url" not in json.dumps(m)  # nessun aggiornamento automatico
    assert m["manifest_version"] == 3


def test_beginNew_solo_in_bozza():
    codice = _senza_commenti((EST / "background.js").read_text(encoding="utf-8"))
    assert codice.count("compose.beginNew") == 1
    assert "consentiBozze" in codice
