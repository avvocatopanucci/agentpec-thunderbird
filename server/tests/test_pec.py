from pathlib import Path

import pytest

from agentpec.pec import (
    DaticertNonValido,
    classifica_intestazioni,
    confronta_con_intestazioni,
    leggi_daticert,
    oggetto_sembra_pec,
    pulisci_message_id,
)

FIX = Path(__file__).parent / "fixture"


def leggi(nome: str) -> str:
    return (FIX / nome).read_text(encoding="utf-8")


def test_accettazione():
    d = leggi_daticert(leggi("daticert_accettazione.xml"))
    assert d.tipo == "accettazione"
    assert d.errore == "nessuno"
    assert d.mittente == "studio.prova@pec.example.it"
    assert d.destinatari == [
        {"indirizzo": "controparte.prova@pec.example.it", "tipo": "certificato"},
        {"indirizzo": "ufficio@example.org", "tipo": "esterno"},
    ]
    assert d.oggetto == "Diffida e messa in mora - pratica di prova 1/2026"
    assert d.gestore_emittente == "GESTORE DI PROVA S.P.A."
    assert d.data_giorno == "20/11/2026" and d.data_ora == "09:41:12" and d.data_zona == "+0100"
    assert d.data_iso == "2026-11-20T09:41:12+01:00"
    assert d.identificativo == "opec001.20261120094112.00001.01.1.1@pec.example.it"
    assert d.msgid == "originale-prova-001@studio.example.it"
    assert d.consegna is None
    assert d.avvertenze == []
    dd = d.come_dict()
    assert dd["descrizione_tipo"] == "Ricevuta di accettazione"
    assert "verificare" in dd["nota"]


def test_avvenuta_consegna():
    d = leggi_daticert(leggi("daticert_consegna.xml").encode("utf-8"))
    assert d.tipo == "avvenuta-consegna"
    assert d.ricevuta_tipo == "completa"
    assert d.consegna == "controparte.prova@pec.example.it"
    assert d.data_iso == "2026-11-20T09:41:15+01:00"
    assert d.come_dict()["descrizione_tipo"] == "Ricevuta di avvenuta consegna"


def test_errore_consegna_segnala_errore():
    d = leggi_daticert(leggi("daticert_errore_consegna.xml"))
    assert d.tipo == "errore-consegna"
    assert d.errore == "no-dest"
    assert d.errore_esteso == "5.1.1 - Utente non esistente"
    assert d.data_iso == "2026-07-15T18:02:00+02:00"
    assert any("errore" in a for a in d.avvertenze)


@pytest.mark.parametrize("nome", ["daticert_bomba.xml", "daticert_esterna.xml"])
def test_xml_pericolosi_rifiutati(nome):
    with pytest.raises(DaticertNonValido, match="sicurezza"):
        leggi_daticert(leggi(nome))


def test_xml_non_valido():
    with pytest.raises(DaticertNonValido):
        leggi_daticert("<postacert><intestazione>")


def test_radice_sbagliata():
    with pytest.raises(DaticertNonValido, match="radice"):
        leggi_daticert("<altro/>")


def test_troppo_grande():
    with pytest.raises(DaticertNonValido, match="grande"):
        leggi_daticert("<postacert>" + "x" * 300_000 + "</postacert>")


def test_dati_mancanti_avvertono():
    d = leggi_daticert('<postacert tipo="accettazione" errore="nessuno"><intestazione/></postacert>')
    assert d.data_iso is None
    assert any("Struttura incompleta" in a for a in d.avvertenze)


def test_data_malformata_e_fuso_assente():
    xml = (
        '<postacert tipo="accettazione" errore="nessuno"><intestazione/><dati>'
        "<data><giorno>31/02/2026</giorno><ora>10:00:00</ora></data></dati></postacert>"
    )
    d = leggi_daticert(xml)
    assert d.data_iso is None
    assert any("Formato data" in a for a in d.avvertenze)
    xml2 = xml.replace("31/02", "01/02")
    d2 = leggi_daticert(xml2)
    assert d2.data_iso == "2026-02-01T10:00:00"
    assert any("Fuso orario non indicato" in a for a in d2.avvertenze)


def test_tipo_sconosciuto():
    d = leggi_daticert('<postacert tipo="inventato" errore="nessuno"><intestazione/><dati/></postacert>')
    assert any("non previsto" in a for a in d.avvertenze)


def test_classifica_ricevuta():
    h = {
        "X-Ricevuta": ["avvenuta-consegna"],
        "x-riferimento-message-id": ["<originale-prova-001@studio.example.it>"],
        "X-TipoRicevuta": ["completa"],
    }
    c = classifica_intestazioni(h)
    assert c.e_pec and c.categoria == "ricevuta" and c.tipo == "avvenuta-consegna"
    assert c.descrizione == "Ricevuta di avvenuta consegna"
    assert c.riferimento_message_id == "originale-prova-001@studio.example.it"
    assert c.tipo_ricevuta == "completa"


def test_classifica_trasporto_e_normale():
    assert classifica_intestazioni({"x-trasporto": ["posta-certificata"]}).categoria == "trasporto"
    assert classifica_intestazioni({"x-trasporto": "errore"}).descrizione == "Busta di anomalia"
    assert not classifica_intestazioni({"subject": ["ciao"]}).e_pec


def test_confronto_incongruenze():
    d = leggi_daticert(leggi("daticert_consegna.xml"))
    c = classifica_intestazioni({"x-ricevuta": ["accettazione"], "x-riferimento-message-id": ["<altro@x>"]})
    avv = confronta_con_intestazioni(d, c)
    assert len(avv) == 2
    c_ok = classifica_intestazioni({"x-ricevuta": ["avvenuta-consegna"],
                                    "x-riferimento-message-id": ["<originale-prova-001@studio.example.it>"]})
    assert confronta_con_intestazioni(d, c_ok) == []


def test_oggetto_sembra_pec():
    assert oggetto_sembra_pec("ACCETTAZIONE: Diffida")
    assert oggetto_sembra_pec("  consegna: Diffida")
    assert oggetto_sembra_pec("AVVISO DI MANCATA CONSEGNA: x")
    assert not oggetto_sembra_pec("Re: accettazione incarico")
    assert not oggetto_sembra_pec(None)


def test_pulisci_message_id():
    assert pulisci_message_id(" <a@b> ") == "a@b"
    assert pulisci_message_id("a@b") == "a@b"
    assert pulisci_message_id("<>") is None
    assert pulisci_message_id(None) is None
