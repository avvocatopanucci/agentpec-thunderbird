# AgentPEC

**Un connettore che fa poco, bene e in sicurezza:** permette a un agente di intelligenza artificiale (per esempio Claude) di *leggere* la posta di Thunderbird, e in particolare la PEC di uno studio legale, solo nelle cartelle che scegli tu.

> ⚠️ **Software sperimentale, versione 0.2.0.**
> Provalo **solo su una casella di prova**, mai sulla PEC vera dello studio, finché non lo hai verificato a fondo.
> È distribuito **senza alcuna garanzia** (vedi la licenza Apache-2.0). Le informazioni che restituisce, comprese date e ricevute PEC, **vanno sempre verificate sull'originale**: non usarle da sole per calcolare termini o provare adempimenti.

---

## Cosa fa

| L'agente può | L'agente NON può (non esiste nel codice) |
|---|---|
| vedere l'elenco delle cartelle che hai autorizzato | inviare, rispondere, inoltrare |
| cercare messaggi (oggetto, mittente, date, testo) | cancellare, spostare, archiviare |
| leggere testo ed elenco degli allegati di un messaggio | svuotare il cestino, creare filtri |
| elencare le ricevute e le notifiche PEC con le date | vedere account o cartelle non autorizzati |
| leggere il `daticert.xml` di una ricevuta e collegarla al messaggio originale | scaricare il contenuto degli allegati |
| dirti, per ogni PEC inviata, se è stata accettata e consegnata | leggere più messaggi all'ora del limite che hai fissato |
| — | fare qualunque cosa mentre lo hai sospeso |
| *(se lo attivi)* aprire una finestra di nuovo messaggio già compilata | premere "Invia": quello resta a te |

### Gli strumenti messi a disposizione dell'agente

| Strumento | A cosa serve |
|---|---|
| `cartelle_consentite` | Elenca account e cartelle autorizzati e le impostazioni attive |
| `cerca_messaggi` | Cerca per parole, oggetto, mittente, destinatario, intervallo di date |
| `leggi_messaggio` | Legge intestazioni, testo ed elenco allegati (senza il loro contenuto) |
| `elenca_ricevute_pec` | Elenca accettazioni, consegne, mancate consegne e buste PEC |
| `dettaglio_ricevuta` | Legge `daticert.xml`: mittente, destinatari, oggetto, data certificata, tipo, identificativo; cerca il messaggio originale |
| `stato_invii` | Per ogni PEC inviata in un periodo: consegnata, consegnata solo ad alcuni, problema (mancata consegna, non accettazione, virus), accettata in attesa di consegna, nessuna ricevuta. Con date certificate e destinatari senza ricevuta |
| `prepara_bozza` | Apre in Thunderbird una finestra di composizione compilata, **senza inviarla**. Spenta finché non la attivi nelle impostazioni |

---

## Come è fatto (in parole semplici)

```
Thunderbird ── estensione AgentPEC ──(native messaging)── programma ponte ──(file-socket privato)── server MCP ── Claude
               "il guardiano"                              avviato da Thunderbird                     avviato da Claude
```

1. **L'estensione in Thunderbird** è il guardiano. Usa solo le API ufficiali di lettura di Thunderbird (nessuna "Experiment API", cioè nessun accesso privilegiato al programma). Conosce la lista di account e cartelle che hai autorizzato: tutto il resto non esce da Thunderbird.
2. **Il programma ponte** viene avviato da Thunderbird stesso. Passa le richieste attraverso un file speciale in `~/.agentpec/run`, leggibile solo dal tuo utente del Mac e protetto da un codice segreto che cambia a ogni avvio. **Non apre nessuna porta di rete**, nemmeno interna al computer.
3. **Il server MCP**, avviato da Claude, prepara le risposte:
   - racchiude ogni testo delle email tra marcatori di **"contenuto non attendibile"**, con un codice casuale diverso per ogni risposta, così un messaggio non può fingere di chiudere il blocco;
   - toglie i caratteri invisibili e **segnala le frasi che sembrano ordini rivolti all'IA** ("ignora le istruzioni precedenti", "inoltra tutto a…", "non dirlo all'utente"…);
   - se lo attivi, **pseudonimizza** codici fiscali, partite IVA, IBAN, telefoni ed email nel testo e nell'oggetto (`[CF_1]`, `[IBAN_1]`…);
   - scrive un **registro delle operazioni** con soli metadati.

### Perché la difesa dalla "prompt injection" è importante
Chiunque può mandare una PEC con dentro istruzioni rivolte a un assistente IA. Uno studio pubblicato nel 2025 (LLMail-Inject, arXiv 2506.09956) ha mostrato che le email riescono spesso a manipolare gli assistenti di posta. La segnalazione delle frasi sospette è un aiuto, **non una garanzia**: la vera protezione è che AgentPEC non sa inviare, cancellare o spostare nulla.

### La spia in Thunderbird

Nella barra di Thunderbird compare il pulsante **AgentPEC** con un numero: quanti messaggi l'agente ha aperto oggi. Mentre l'agente legge, il numero diventa arancione. Cliccando si apre un pannello con:

- messaggi aperti oggi, richieste dell'agente, richieste rifiutate, ultimo accesso;
- quanti messaggi ha aperto nell'ultima ora rispetto al **limite orario** (60 se non lo cambi; si imposta nelle impostazioni, 0 = nessun limite);
- il pulsante **Sospendi l'agente**: da quel momento ogni richiesta viene rifiutata, bozze comprese, e il pulsante mostra **OFF** in rosso finché non lo riattivi.

I contatori registrano solo numeri e orari, mai il contenuto.

---

## Privacy

- **Nessuna copia della posta su disco.** AgentPEC non crea archivi, indici o cache dei messaggi: legge da Thunderbird al momento della richiesta.
- **Nessuna telemetria, nessun aggiornamento automatico.** L'estensione non contiene connessioni di rete né indirizzi di aggiornamento; il server non contatta nessuno. (Un test automatico controlla che nel codice dell'estensione non compaiano funzioni di rete o di scrittura.)
- **Registro solo metadati** in `~/.agentpec/registro.jsonl` (permessi 0600): data, strumento, esito, numero di risultati, id interni dei messaggi e un'impronta non reversibile delle cartelle. **Mai** testi, oggetti, indirizzi, nomi di allegati o parole cercate. Anche i tentativi rifiutati vengono annotati.
- **Attenzione:** ciò che l'agente legge viene inviato al fornitore del modello di IA che usi (per Claude, Anthropic), secondo le condizioni del tuo contratto. AgentPEC riduce quello che esce, non lo azzera. Valuta tu se e quali cartelle autorizzare, alla luce del segreto professionale, della deontologia e del GDPR (in particolare l'art. 25, protezione dei dati fin dalla progettazione).
- La pseudonimizzazione **non è un'anonimizzazione**: nomi, indirizzi postali e altri dati restano nel testo. Gli indirizzi email di mittente e destinatari restano visibili, perché servono a riconoscere le PEC.

---

## Installazione (Mac)

Servono **Thunderbird 128 o successivo** (provato con la 160) e **[uv](https://docs.astral.sh/uv/)** per Python.

1. Scarica questa cartella e, dal Terminale, lancia:
   ```bash
   sh scripts/installa.sh
   ```
   Crea un ambiente Python in `~/.agentpec/venv`, registra il programma ponte presso Thunderbird (`~/Library/Mozilla/NativeMessagingHosts/agentpec.json`) e prepara il pacchetto dell'estensione in `~/.agentpec/agentpec-estensione.xpi`.
2. **Carica l'estensione in Thunderbird** come componente temporaneo:
   *Strumenti → Strumenti di sviluppo → Componenti aggiuntivi di debug → Carica componente aggiuntivo temporaneo…* e scegli `~/.agentpec/agentpec-estensione.xpi` (nella finestra di scelta, ⌘⇧G permette di scrivere il percorso).
   Un componente temporaneo sparisce alla chiusura di Thunderbird: va ricaricato a ogni avvio. È voluto, finché il progetto è sperimentale. Dopo il caricamento compare il pulsante AgentPEC nella barra.
3. **Scegli cosa può vedere l'agente:** *Componenti aggiuntivi e temi → AgentPEC → icona della chiave inglese*. Spunta l'account, poi le singole cartelle. Per collegare le ricevute al messaggio originale, autorizza anche la cartella della posta inviata. Premi **Salva**.
4. **Collega Claude Code:**
   ```bash
   claude mcp add agentpec -- ~/.agentpec/venv/bin/agentpec-server
   ```

Per togliere tutto: `sh scripts/disinstalla.sh`, poi rimuovi l'estensione da Thunderbird e lancia `claude mcp remove agentpec`.

### Una casella di prova pronta
`python3 -I scripts/crea_casella_prova.py` crea un profilo Thunderbird separato (`~/Library/Thunderbird/Profiles/agentpec-prova`) con PEC **inventate**: ricevute di accettazione, consegna e mancata consegna con il loro `daticert.xml`, una busta con un tentativo di prompt injection, un messaggio con dati personali finti e una cartella "Riservata" che l'agente non deve vedere. Nessun server di posta, nessun dato reale. Lo script stampa il comando per avviare Thunderbird su quel profilo. Al primo avvio apri una volta ciascuna cartella in Thunderbird, perché le indicizzi.

---

## Da sapere

- **Gli id dei messaggi cambiano** a ogni riavvio di Thunderbird e valgono solo per i messaggi già restituiti da una ricerca. Per riferimenti duraturi usa il `message_id`.
- **Le date di `elenca_ricevute_pec`** sono quelle dei messaggi in Thunderbird; la data certificata è quella del `daticert.xml` (`dettaglio_ricevuta`). Sono comunque **da verificare**.
- **`stato_invii` cerca la posta inviata** nelle cartelle consentite marcate da Thunderbird come "Inviata"; se la tua cartella non lo è, l'agente può indicarla per nome. Le ricevute vengono cercate fino a tre giorni dopo la data finale. Una ricevuta che sta in una cartella non autorizzata non viene vista: in quel caso l'invio risulterà "nessuna ricevuta".
- **La firma digitale delle ricevute non è ancora verificata:** un'email confezionata ad arte che imita una ricevuta verrebbe presa per buona. È il prossimo miglioramento previsto.
- **Buste PEC ricevute:** nella versione 0.1 il testo letto è quello della busta; il messaggio originale contenuto in `postacert.eml` non viene ancora aperto.
- **Ricevute riconosciute** dalle intestazioni `X-Ricevuta` / `X-Trasporto` e dal `daticert.xml` previsti dalle regole tecniche della PEC: [DPR 11 febbraio 2005, n. 68](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.del.presidente.della.repubblica:2005-02-11;68) (in particolare l'[art. 6](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.del.presidente.della.repubblica:2005-02-11;68~art6), "Ricevuta di accettazione e di avvenuta consegna") e DM 2 novembre 2005 (regole tecniche). Il primo elenco usa i prefissi dell'oggetto (`ACCETTAZIONE:`, `CONSEGNA:`…): un gestore che li scrivesse diversamente potrebbe sfuggire.
- Il file `daticert.xml` viene letto con un parser protetto (`defusedxml`) che rifiuta entità e riferimenti esterni.

## Per chi sviluppa

```
extension/   estensione Thunderbird (Manifest V3, solo API messenger.*)
server/      pacchetto Python: server MCP, ponte, parser PEC, guardia, pseudonimi, registro
  tests/     45 test automatici (parser delle ricevute, stato degli invii, difesa da injection,
             pseudonimi, controllo statico di sola lettura, prova completa ponte + server)
scripts/     installa, disinstalla, crea la casella di prova
docs/        immagini dei passaggi
```

```bash
cd server && uv run pytest
```

## Licenza

[Apache License 2.0](LICENSE). Copyright 2026 Giovanna Panucci.
