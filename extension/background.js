// AgentPEC — script di sfondo.
//
// Riceve richieste dal programma ponte (native messaging) e risponde
// usando solo API di lettura di Thunderbird. Qui si applica la lista delle
// cartelle consentite: ciò che non è autorizzato non esce da Thunderbird.
//
// Per costruzione questo file NON usa: compose.sendMessage, messages.delete,
// messages.move, messages.copy, messages.archive, messages.update,
// folders.create/delete/rename, filtri, identità in scrittura.

"use strict";

const VERSIONE = messenger.runtime.getManifest().version;
const NOME_HOST = "agentpec";
const MAX_DATICERT = 256 * 1024;
const MAX_RACCOLTI = 2000;
const MAX_TESTO = 200000;

const PREFISSI_PEC = [
  "ACCETTAZIONE:",
  "CONSEGNA:",
  "POSTA CERTIFICATA:",
  "AVVISO DI NON ACCETTAZIONE",
  "AVVISO DI MANCATA CONSEGNA",
  "PRESA IN CARICO:",
  "ANOMALIA MESSAGGIO:",
  "PROBLEMA DI SICUREZZA:",
];

const INTESTAZIONI_TECNICHE = [
  "x-ricevuta",
  "x-trasporto",
  "x-riferimento-message-id",
  "x-tiporicevuta",
  "x-identificativo",
  "x-verificasicurezza",
  "message-id",
  "date",
];

class Errore extends Error {
  constructor(codice, dettaglio) {
    super(codice);
    this.codice = codice;
    this.dettaglio = dettaglio;
  }
}

// --- Allowlist -----------------------------------------------------------

async function cartelleConsentite() {
  const imp = await leggiImpostazioni();
  const account = new Set(imp.account);
  const valide = [];
  for (const id of imp.cartelle) {
    let f;
    try {
      f = await messenger.folders.get(id);
    } catch (e) {
      continue; // cartella rimossa o rinominata
    }
    if (f && f.accountId && account.has(f.accountId)) valide.push(f);
  }
  return { imp, cartelle: valide, ids: new Set(valide.map((f) => f.id)) };
}

async function richiediMessaggioConsentito(id) {
  if (!Number.isInteger(id)) throw new Errore("parametri_non_validi");
  const { imp, ids } = await cartelleConsentite();
  let h;
  try {
    h = await messenger.messages.get(id);
  } catch (e) {
    throw new Errore("messaggio_non_consentito");
  }
  if (!h || !h.folder || !ids.has(h.folder.id)) throw new Errore("messaggio_non_consentito");
  return { imp, h };
}

function scegliCartelle(richieste, ids) {
  if (ids.size === 0) throw new Errore("nessuna_cartella_consentita");
  if (!Array.isArray(richieste) || richieste.length === 0) return [...ids];
  for (const r of richieste) {
    if (typeof r !== "string" || !ids.has(r)) throw new Errore("cartella_non_consentita");
  }
  return richieste;
}

function impostazioniPubbliche(imp) {
  return { pseudonimizza: imp.pseudonimizza, consentiBozze: imp.consentiBozze };
}

// --- Conversioni ----------------------------------------------------------

function isoData(d) {
  try {
    return d ? new Date(d).toISOString() : null;
  } catch (e) {
    return null;
  }
}

function intestazione(h) {
  return {
    id: h.id,
    message_id: h.headerMessageId || null,
    data: isoData(h.date),
    mittente: h.author || null,
    destinatari: h.recipients || [],
    cc: h.ccList || [],
    oggetto: h.subject || "",
    cartella: h.folder ? { id: h.folder.id, nome: h.folder.name } : null,
    letto: !!h.read,
  };
}

function sceltaIntestazioni(headers) {
  const r = {};
  for (const nome of INTESTAZIONI_TECNICHE) {
    if (headers && headers[nome]) r[nome] = headers[nome];
  }
  return r;
}

function dataInizio(s) {
  if (!s) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new Errore("parametri_non_validi", "data: usa AAAA-MM-GG");
  return new Date(`${s}T00:00:00`);
}

function dataFine(s) {
  if (!s) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new Errore("parametri_non_validi", "data: usa AAAA-MM-GG");
  return new Date(`${s}T23:59:59.999`);
}

function stringaOpzionale(v) {
  if (v === undefined || v === null || v === "") return undefined;
  if (typeof v !== "string" || v.length > 500) throw new Errore("parametri_non_validi");
  return v;
}

async function raccogli(query, ids, filtro, limite) {
  const raccolti = [];
  let pagina = await messenger.messages.query(query);
  while (true) {
    for (const h of pagina.messages) {
      if (!h.folder || !ids.has(h.folder.id)) continue; // doppio controllo
      if (filtro && !filtro(h)) continue;
      raccolti.push(h);
    }
    if (!pagina.id || raccolti.length >= MAX_RACCOLTI) break;
    pagina = await messenger.messages.continueList(pagina.id);
  }
  if (pagina.id) {
    try {
      await messenger.messages.abortList(pagina.id);
    } catch (e) {}
  }
  raccolti.sort((a, b) => new Date(b.date) - new Date(a.date));
  return { messaggi: raccolti.slice(0, limite), troncato: raccolti.length > limite };
}

function limiteValido(v, predefinito) {
  const n = Number.isInteger(v) ? v : predefinito;
  return Math.min(Math.max(n, 1), 200);
}

async function leggiDaticert(id) {
  const allegati = await messenger.messages.listAttachments(id);
  const dc = allegati.find((a) => (a.name || "").toLowerCase() === "daticert.xml");
  if (!dc) return null;
  if (dc.size > MAX_DATICERT) throw new Errore("parametri_non_validi", "daticert.xml troppo grande");
  const file = await messenger.messages.getAttachmentFile(id, dc.partName);
  return await file.text();
}

function sembraPec(h) {
  const o = (h.subject || "").trim().toUpperCase();
  return PREFISSI_PEC.some((x) => o.startsWith(x));
}

// --- Operazioni ------------------------------------------------------------

const operazioni = {
  async cartelle() {
    const { imp, cartelle } = await cartelleConsentite();
    const risultato = [];
    for (const f of cartelle) {
      let acc = null;
      try {
        acc = await messenger.accounts.get(f.accountId, false);
      } catch (e) {}
      risultato.push({
        id: f.id,
        nome: f.name,
        percorso: f.path,
        uso: f.specialUse || [],
        account: acc
          ? { id: acc.id, nome: acc.name, tipo: acc.type, indirizzi: (acc.identities || []).map((i) => i.email).filter(Boolean) }
          : { id: f.accountId },
      });
    }
    return { cartelle: risultato, impostazioni: impostazioniPubbliche(imp) };
  },

  async cerca(p) {
    const { imp, ids } = await cartelleConsentite();
    const scelte = scegliCartelle(p.cartelle, ids);
    const q = { folderId: scelte, messagesPerPage: 100, autoPaginationTimeout: 0 };
    const testo = stringaOpzionale(p.testo);
    const oggetto = stringaOpzionale(p.oggetto);
    const mittente = stringaOpzionale(p.mittente);
    const destinatario = stringaOpzionale(p.destinatario);
    if (testo) q.fullText = testo;
    if (oggetto) q.subject = oggetto;
    if (mittente) q.author = mittente;
    if (destinatario) q.recipients = destinatario;
    const da = dataInizio(p.dal);
    const a = dataFine(p.al);
    if (da) q.fromDate = da;
    if (a) q.toDate = a;
    if (p.soloNonLetti === true) q.read = false;
    const r = await raccogli(q, ids, null, limiteValido(p.limite, 25));
    return { messaggi: r.messaggi.map(intestazione), troncato: r.troncato, impostazioni: impostazioniPubbliche(imp) };
  },

  async leggi(p) {
    const { imp, h } = await richiediMessaggioConsentito(p.id);
    Spia.contaApertura();
    const completo = await messenger.messages.getFull(h.id);
    const parti = await messenger.messages.listInlineTextParts(h.id);
    const testo = parti.filter((x) => x.contentType === "text/plain").map((x) => x.content).join("\n\n");
    const html = testo ? null : parti.filter((x) => x.contentType === "text/html").map((x) => x.content).join("\n\n");
    const allegati = await messenger.messages.listAttachments(h.id);
    return {
      intestazione: intestazione(h),
      intestazioni_tecniche: sceltaIntestazioni(completo.headers),
      testo: testo ? testo.slice(0, MAX_TESTO) : null,
      html: html ? html.slice(0, MAX_TESTO * 2) : null,
      allegati: allegati.map((a) => ({ nome: a.name, tipo: a.contentType, dimensione: a.size })),
      impostazioni: impostazioniPubbliche(imp),
    };
  },

  async ricevute(p) {
    const { imp, ids } = await cartelleConsentite();
    const scelte = scegliCartelle(p.cartelle, ids);
    const q = { folderId: scelte, messagesPerPage: 100, autoPaginationTimeout: 0 };
    const da = dataInizio(p.dal);
    const a = dataFine(p.al);
    if (da) q.fromDate = da;
    if (a) q.toDate = a;
    const r = await raccogli(q, ids, sembraPec, limiteValido(p.limite, 50));
    const messaggi = [];
    for (const h of r.messaggi) {
      Spia.contaApertura();
      const completo = await messenger.messages.getFull(h.id);
      messaggi.push({ ...intestazione(h), intestazioni_tecniche: sceltaIntestazioni(completo.headers) });
    }
    return { messaggi, troncato: r.troncato, impostazioni: impostazioniPubbliche(imp) };
  },

  async dettaglio_ricevuta(p) {
    const { imp, h } = await richiediMessaggioConsentito(p.id);
    Spia.contaApertura();
    const completo = await messenger.messages.getFull(h.id);
    const xml = await leggiDaticert(h.id);
    return {
      intestazione: intestazione(h),
      intestazioni_tecniche: sceltaIntestazioni(completo.headers),
      daticert_xml: xml,
      impostazioni: impostazioniPubbliche(imp),
    };
  },

  async stato_invii(p) {
    const { imp, cartelle, ids } = await cartelleConsentite();
    if (ids.size === 0) throw new Errore("nessuna_cartella_consentita");
    // Cartelle della posta inviata: quelle indicate, oppure le consentite con uso "sent".
    let inviati = Array.isArray(p.cartelleInviati) && p.cartelleInviati.length ? p.cartelleInviati : null;
    if (inviati) {
      scegliCartelle(inviati, ids);
    } else {
      inviati = cartelle.filter((f) => (f.specialUse || []).includes("sent")).map((f) => f.id);
      if (inviati.length === 0) throw new Errore("cartella_inviati_mancante");
    }
    const da = dataInizio(p.dal);
    const a = dataFine(p.al);
    if (!da || !a) throw new Errore("parametri_non_validi", "servono dal e al");
    if (a - da > 400 * 86400000) throw new Errore("parametri_non_validi", "intervallo massimo un anno");
    const inviatiSet = new Set(inviati);
    const orig = await raccogli(
      { folderId: inviati, fromDate: da, toDate: a, messagesPerPage: 100, autoPaginationTimeout: 0 },
      inviatiSet, (h) => !sembraPec(h), limiteValido(p.limite, 50));
    // Le ricevute arrivano dopo l'invio: si cercano fino a tre giorni oltre la data finale.
    const fineRicevute = new Date(a.getTime() + 3 * 86400000);
    const ric = await raccogli(
      { folderId: [...ids], fromDate: da, toDate: fineRicevute, messagesPerPage: 100, autoPaginationTimeout: 0 },
      ids, sembraPec, 500);
    const ricevute = [];
    for (const h of ric.messaggi) {
      Spia.contaApertura();
      const completo = await messenger.messages.getFull(h.id);
      const tecniche = sceltaIntestazioni(completo.headers);
      if (!tecniche["x-ricevuta"]) continue;
      ricevute.push({ ...intestazione(h), intestazioni_tecniche: tecniche, daticert_xml: await leggiDaticert(h.id) });
    }
    return {
      originali: orig.messaggi.map(intestazione),
      ricevute,
      troncato: orig.troncato || ric.troncato,
      impostazioni: impostazioniPubbliche(imp),
    };
  },

  async per_message_id(p) {
    const { imp, ids } = await cartelleConsentite();
    if (ids.size === 0) throw new Errore("nessuna_cartella_consentita");
    let mid = stringaOpzionale(p.message_id);
    if (!mid) throw new Errore("parametri_non_validi");
    mid = mid.replace(/^<|>$/g, "");
    const r = await raccogli({ headerMessageId: mid, folderId: [...ids], autoPaginationTimeout: 0 }, ids, null, 10);
    return { messaggi: r.messaggi.map(intestazione), impostazioni: impostazioniPubbliche(imp) };
  },

  async bozza(p) {
    const imp = await leggiImpostazioni();
    if (!imp.consentiBozze) throw new Errore("bozze_disattivate");
    const dest = p.destinatari;
    if (!Array.isArray(dest) || dest.length === 0 || dest.length > 20 || dest.some((d) => typeof d !== "string" || d.length > 320)) {
      throw new Errore("parametri_non_validi");
    }
    if (typeof p.oggetto !== "string" || typeof p.testo !== "string") throw new Errore("parametri_non_validi");
    let accountId = p.accountId || imp.account[0];
    if (!accountId || !imp.account.includes(accountId)) throw new Errore("account_non_consentito");
    const acc = await messenger.accounts.get(accountId, false);
    const identita = acc && acc.identities && acc.identities[0];
    const dettagli = { to: dest, subject: p.oggetto.slice(0, 500), plainTextBody: p.testo.slice(0, 100000), isPlainText: true };
    if (identita) dettagli.identityId = identita.id;
    // beginNew apre soltanto la finestra: l'invio resta all'utente.
    await messenger.compose.beginNew(dettagli);
    return { aperta: true };
  },
};

// --- Collegamento con il programma ponte ---------------------------------

let porta = null;
let attesa = 1000;

function collega() {
  try {
    porta = messenger.runtime.connectNative(NOME_HOST);
  } catch (e) {
    console.warn("AgentPEC: programma ponte non disponibile", e);
    porta = null;
    riprova();
    return;
  }
  porta.onMessage.addListener(gestisci);
  porta.onDisconnect.addListener((p) => {
    const err = (p && p.error) || messenger.runtime.lastError;
    console.warn("AgentPEC: collegamento chiuso", err ? err.message : "");
    porta = null;
    Spia.impostaCollegato(false);
    riprova();
  });
  porta.postMessage({ tipo: "ciao", versione: VERSIONE });
}

function riprova() {
  setTimeout(collega, attesa);
  attesa = Math.min(attesa * 2, 60000);
}

async function gestisci(msg) {
  attesa = 1000; // il ponte risponde: collegamento sano, si azzera l'attesa
  Spia.impostaCollegato(true);
  if (!msg || typeof msg !== "object" || !Number.isInteger(msg.id)) return;
  const op = Object.prototype.hasOwnProperty.call(operazioni, msg.metodo) ? operazioni[msg.metodo] : null;
  let risposta;
  let rifiutata = false;
  try {
    if (!op) throw new Errore("metodo_sconosciuto");
    await Spia.prima();
    const parametri = msg.parametri && typeof msg.parametri === "object" ? msg.parametri : {};
    risposta = { id: msg.id, risultato: await op(parametri) };
  } catch (e) {
    rifiutata = e instanceof Errore;
    const codice = e instanceof Errore ? e.codice : "errore_thunderbird";
    if (!(e instanceof Errore)) console.error("AgentPEC:", e);
    risposta = { id: msg.id, errore: { codice, dettaglio: e instanceof Errore ? e.dettaglio : String(e && e.message).slice(0, 200) } };
  }
  if (porta) porta.postMessage(risposta);
  try {
    await Spia.dopo(rifiutata);
  } catch (e) {}
}

// In Manifest V3 lo script di sfondo parte solo su eventi: l'ascolto di
// onStartup e onInstalled lo fa partire insieme a Thunderbird. La porta
// nativa aperta lo tiene poi attivo.
messenger.runtime.onStartup.addListener(() => {});
messenger.runtime.onInstalled.addListener(() => {});

Spia.carica().finally(collega);
