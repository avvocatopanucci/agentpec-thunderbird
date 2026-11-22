from pathlib import Path

from agentpec.invii import calcola_stati, indirizzi

FIX = Path(__file__).parent / "fixture"


def originale(id, mid, dest, cc=None):
    return {"id": id, "message_id": mid, "destinatari": dest, "cc": cc or [], "oggetto": "x", "data": "2026-11-20T08:41:10Z"}


def ricevuta(id, tipo, rif, daticert=None, data="2026-11-20T08:41:15Z"):
    return {
        "id": id, "data": data,
        "intestazioni_tecniche": {"x-ricevuta": [tipo], "x-riferimento-message-id": [f"<{rif}>"]},
        "daticert_xml": (FIX / daticert).read_text() if daticert else None,
    }


def test_indirizzi():
    assert indirizzi(["Studio <A@Pec.it>", "b@pec.it", "a@pec.it", "senza-chiocciola"]) == ["a@pec.it", "b@pec.it"]


def test_consegnata():
    o = [originale(2, "<originale-prova-001@studio.example.it>", ["Controparte <controparte.prova@pec.example.it>"])]
    r = [
        ricevuta(4, "accettazione", "originale-prova-001@studio.example.it", "daticert_accettazione.xml"),
        ricevuta(5, "avvenuta-consegna", "originale-prova-001@studio.example.it", "daticert_consegna.xml"),
    ]
    s = calcola_stati(o, r)
    inv = s["invii"][0]
    assert inv["stato"] == "consegnata"
    assert inv["accettazione"]["data"] == "2026-11-20T09:41:12+01:00"
    assert inv["accettazione"]["data_da_daticert"] is True
    assert inv["consegne"][0]["destinatario"] == "controparte.prova@pec.example.it"
    assert inv["destinatari_senza_ricevuta"] == []
    assert s["riepilogo"]["consegnata"] == 1
    assert "firma digitale" in s["nota"]


def test_consegna_parziale():
    o = [originale(2, "originale-prova-001@studio.example.it",
                   ["controparte.prova@pec.example.it"], cc=["altro@pec.example.it"])]
    r = [ricevuta(5, "avvenuta-consegna", "originale-prova-001@studio.example.it", "daticert_consegna.xml")]
    inv = calcola_stati(o, r)["invii"][0]
    assert inv["stato"] == "consegna_parziale"
    assert inv["destinatari_senza_ricevuta"] == ["altro@pec.example.it"]


def test_mancata_consegna():
    o = [originale(1, "originale-prova-002@studio.example.it", ["inesistente@pec.example.it"])]
    r = [ricevuta(3, "errore-consegna", "originale-prova-002@studio.example.it", "daticert_errore_consegna.xml")]
    inv = calcola_stati(o, r)["invii"][0]
    assert inv["stato"] == "problema"
    assert inv["problemi"][0]["errore"] == "5.1.1 - Utente non esistente"
    assert inv["destinatari_senza_ricevuta"] == []


def test_solo_accettazione_e_nessuna():
    o = [originale(1, "a@x", ["d@pec.it"]), originale(2, "b@x", ["d@pec.it"])]
    r = [ricevuta(9, "accettazione", "a@x")]  # senza daticert: data del messaggio
    s = calcola_stati(o, r)
    assert [i["stato"] for i in s["invii"]] == ["in_attesa_consegna", "nessuna_ricevuta"]
    assert s["invii"][0]["accettazione"]["data_da_daticert"] is False


def test_ricevute_non_collegate_e_buste_ignorate():
    o = [originale(1, "a@x", ["d@pec.it"])]
    busta = {"id": 7, "intestazioni_tecniche": {"x-trasporto": ["posta-certificata"]}}
    s = calcola_stati(o, [ricevuta(8, "avvenuta-consegna", "altro@x"), busta])
    assert s["ricevute_non_collegate"] == 1
    assert s["invii"][0]["stato"] == "nessuna_ricevuta"


def test_consegna_a_indirizzo_estraneo_avverte():
    o = [originale(2, "originale-prova-001@studio.example.it", ["altro@pec.it"])]
    r = [ricevuta(5, "avvenuta-consegna", "originale-prova-001@studio.example.it", "daticert_consegna.xml")]
    inv = calcola_stati(o, r)["invii"][0]
    assert any("non presente tra i destinatari" in a for a in inv["avvertenze"])


def test_daticert_malevolo_non_blocca():
    o = [originale(1, "a@x", ["d@pec.it"])]
    r = [ricevuta(9, "accettazione", "a@x", "daticert_bomba.xml")]
    s = calcola_stati(o, r)
    assert s["invii"][0]["stato"] == "in_attesa_consegna"
    assert any("sicurezza" in a for a in s["avvertenze"])
