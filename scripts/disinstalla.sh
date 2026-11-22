#!/bin/sh
# Rimuove la registrazione del programma ponte e l'ambiente Python di AgentPEC.
# Il registro delle operazioni (~/.agentpec/registro.jsonl) viene conservato:
# cancellalo a mano se non ti serve.

set -eu
BASE="${AGENTPEC_HOME:-$HOME/.agentpec}"

rm -f "$HOME/Library/Mozilla/NativeMessagingHosts/agentpec.json"
rm -rf "$BASE/venv" "$BASE/run"
echo "Rimossi il programma ponte e l'ambiente Python."
echo "Ricorda: rimuovi l'estensione da Thunderbird e, se l'avevi aggiunto, esegui: claude mcp remove agentpec"
echo "Registro conservato in $BASE/registro.jsonl"
