# Sicurezza

AgentPEC è **sperimentale**. Non usarlo sulla PEC reale di uno studio senza averlo provato a fondo su una casella di prova.

## Segnalare una vulnerabilità

Non aprire una issue pubblica per problemi di sicurezza. Usa la funzione **"Report a vulnerability"** (segnalazione privata) nella scheda *Security* del repository GitHub. Indica la versione, i passaggi per riprodurre il problema e l'effetto. Non includere mai messaggi reali, dati di clienti o credenziali: usa la casella di prova (`scripts/crea_casella_prova.py`).

## Modello di minaccia (versione 0.2)

| Rischio | Difesa | Limite noto |
|---|---|---|
| Un'email contiene istruzioni per l'IA (prompt injection) | Nessuna funzione di invio, inoltro, cancellazione o spostamento nel codice; testo racchiuso tra marcatori con codice casuale; segnalazione di frasi sospette; rimozione di caratteri invisibili | La segnalazione si basa su modelli di frase e può essere aggirata; l'agente potrebbe comunque riassumere in modo fuorviante un messaggio ostile |
| L'agente legge cartelle non pertinenti | Lista di account **e** cartelle consentiti, applicata nell'estensione (prima che i dati escano da Thunderbird) e ricontrollata sui risultati | Le sottocartelle vanno autorizzate una per una; una cartella autorizzata per errore è visibile |
| Un altro programma si collega al ponte | Socket Unix in una cartella 0700, socket 0600, codice di sessione casuale; nessuna porta di rete | Un programma che gira con il tuo stesso utente del Mac può leggere il codice di sessione |
| L'agente, manipolato, legge molta posta in poco tempo | Limite di messaggi aperti all'ora (60 di default), controllato a ogni apertura; pulsante di sospensione immediata; contatore visibile nella barra | Il limite conta i messaggi aperti, non le ricerche (che restituiscono solo intestazioni) |
| Una ricevuta falsa fa credere a una consegna | Avvertenza esplicita in ogni risposta | **La firma digitale delle ricevute non è ancora verificata** |
| Fuga di dati su disco | Nessuna cache dei messaggi; registro con soli metadati (0600) e impronte non reversibili delle cartelle | Il registro rivela quando e quante volte l'agente ha letto la posta |
| `daticert.xml` costruito ad arte | `defusedxml` (niente entità né riferimenti esterni), limite di 256 KB | — |
| Aggiornamento malevolo | Nessun `update_url`, nessun aggiornamento automatico, nessuna dipendenza scaricata a runtime | Le dipendenze Python (`mcp`, `defusedxml`) vengono installate da PyPI con `installa.sh` |
| Bozza inviata per errore | `prepara_bozza` è spenta di default e usa solo `compose.beginNew`, che apre la finestra; il permesso di invio (`compose.send`) non è richiesto | Chi usa la finestra può comunque premere "Invia" |
| Dati verso il fornitore del modello | Pseudonimizzazione facoltativa di CF, P.IVA, IBAN, telefoni ed email | Non è anonimizzazione: nomi e altri dati restano |

## Permessi richiesti dall'estensione

`accountsRead`, `messagesRead` (lettura), `storage` (impostazioni e contatori), `nativeMessaging` (collegamento al ponte), `compose` (solo per aprire la finestra di bozza). Nessuna Experiment API, nessun `host_permissions`. Un test automatico (`server/tests/test_sola_lettura.py`) fallisce se nel codice dell'estensione compaiono funzioni di scrittura, rete o aggiornamento.
