// Funzioni condivise tra background e pagina delle impostazioni.

const IMPOSTAZIONI_PREDEFINITE = {
  account: [],          // id degli account autorizzati
  cartelle: [],         // id delle cartelle autorizzate
  pseudonimizza: false, // sostituisce CF, P.IVA, IBAN, telefoni ed email nel testo
  consentiBozze: false, // consente a prepara_bozza di aprire una finestra di composizione
};

async function leggiImpostazioni() {
  const s = await messenger.storage.local.get(IMPOSTAZIONI_PREDEFINITE);
  return {
    account: Array.isArray(s.account) ? s.account : [],
    cartelle: Array.isArray(s.cartelle) ? s.cartelle : [],
    pseudonimizza: s.pseudonimizza === true,
    consentiBozze: s.consentiBozze === true,
  };
}

function appiattisciCartelle(cartella, risultato = []) {
  if (!cartella) return risultato;
  if (!cartella.isRoot) risultato.push(cartella);
  for (const sotto of cartella.subFolders || []) appiattisciCartelle(sotto, risultato);
  return risultato;
}
