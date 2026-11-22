# Registro delle modifiche

## 0.2.0 — 22 novembre 2026 (sperimentale, non pubblicata)

- Nuovo strumento `stato_invii`: per ogni PEC inviata, stato delle ricevute (consegnata, parziale, problema, in attesa, nessuna ricevuta), con date dal daticert e destinatari senza ricevuta.
- Spia in Thunderbird: pulsante nella barra con i messaggi aperti oggi, pannello con contatori, sospensione immediata dell'agente, limite di messaggi aperti all'ora.
- Il registro annota anche gli id dei messaggi nelle richieste rifiutate.
- Corretto: il collegamento al ponte usa il percorso di Thunderbird su macOS; lo sfondo dell'estensione parte all'avvio di Thunderbird.

## 0.1.0 — 22 novembre 2026 (sperimentale, non pubblicata)

- Prima versione: estensione Thunderbird (Manifest V3, solo API ufficiali), programma ponte via native messaging, server MCP.
- Strumenti: `cartelle_consentite`, `cerca_messaggi`, `leggi_messaggio`, `elenca_ricevute_pec`, `dettaglio_ricevuta`, `prepara_bozza` (spenta di default).
- Lista di account e cartelle consentiti, involucro "contenuto non attendibile", segnalazione di prompt injection, pseudonimizzazione facoltativa, registro dei soli metadati.
- Provata con Thunderbird 160 su macOS, su una casella di prova con PEC inventate.
