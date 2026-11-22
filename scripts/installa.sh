#!/bin/sh
# Installa AgentPEC sul Mac dell'utente corrente.
#
# - crea un ambiente Python dedicato in ~/.agentpec/venv (richiede uv);
# - registra il programma ponte presso Thunderbird (native messaging);
# - stampa il comando per collegare il server MCP a Claude Code.
#
# Non scarica nulla oltre alle dipendenze Python dichiarate
# (mcp, defusedxml) e non modifica Thunderbird.

set -eu

QUI="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${AGENTPEC_HOME:-$HOME/.agentpec}"
VENV="$BASE/venv"
ID_ESTENSIONE="agentpec@agentpec.invalid"

case "$BASE" in
  *" "*) echo "Il percorso $BASE contiene spazi: non supportato." >&2; exit 1 ;;
esac

if ! command -v uv >/dev/null 2>&1; then
  echo "Serve uv (https://docs.astral.sh/uv/). Installalo e riprova." >&2
  exit 1
fi

mkdir -p "$BASE"
chmod 700 "$BASE"

echo "1/3  Ambiente Python in $VENV"
uv venv --quiet --allow-existing "$VENV"
uv pip install --quiet --python "$VENV/bin/python" --reinstall-package agentpec "$QUI/server"

PONTE="$VENV/bin/agentpec-bridge"
SERVER="$VENV/bin/agentpec-server"

echo "2/3  Registrazione del programma ponte presso Thunderbird"
# Thunderbird su macOS cerca i programmi nativi dell'utente in
# ~/Library/Mozilla/NativeMessagingHosts (verificato con Thunderbird 160;
# Firefox usa invece ~/Library/Application Support/Mozilla/...).
for CARTELLA in "$HOME/Library/Mozilla/NativeMessagingHosts"; do
  mkdir -p "$CARTELLA"
  cat > "$CARTELLA/agentpec.json" <<EOF
{
  "name": "agentpec",
  "description": "AgentPEC: ponte in sola lettura tra Thunderbird e il server MCP",
  "path": "$PONTE",
  "type": "stdio",
  "allowed_extensions": ["$ID_ESTENSIONE"]
}
EOF
  echo "     scritto $CARTELLA/agentpec.json"
done

# Pacchetto dell'estensione fuori dalla Scrivania, così Thunderbird non deve
# chiedere l'accesso alla cartella Desktop quando lo carichi.
XPI="$BASE/agentpec-estensione.xpi"
rm -f "$XPI"
(cd "$QUI/extension" && zip -qr "$XPI" . -x '.*')
echo "     estensione pronta: $XPI"

echo "3/3  Fatto. Per collegare AgentPEC a Claude Code:"
echo
echo "     claude mcp add agentpec -- \"$SERVER\""
echo
echo "Poi in Thunderbird: Componenti aggiuntivi > ingranaggio > Debug componenti aggiuntivi >"
echo "Carica componente aggiuntivo temporaneo... e scegli $XPI"
echo "Infine apri le impostazioni di AgentPEC e scegli account e cartelle."
