// AgentPEC — spia visibile in Thunderbird.
//
// Tiene il conto (solo numeri e orari, mai contenuti) di quante volte
// l'agente ha usato il connettore e di quanti messaggi ha aperto, lo mostra
// sul pulsante nella barra, permette di sospendere l'agente e applica un
// limite di messaggi aperti all'ora.

"use strict";

const COLORE_ATTIVO = "#1a5fb4";
const COLORE_LETTURA = "#e66100";
const COLORE_SOSPESO = "#c01c28";
const UN_ORA = 3600000;

const Spia = {
  stato: {
    giorno: null,        // AAAA-MM-GG locale
    operazioni: 0,       // richieste dell'agente oggi
    aperti: 0,           // messaggi aperti oggi (testo, intestazioni complete o allegati)
    rifiutate: 0,        // richieste rifiutate oggi (sospensione, limite, cartelle non consentite)
    ultimo: null,        // ISO dell'ultima richiesta
    recenti: [],         // istanti delle aperture nell'ultima ora
    collegato: false,
  },
  imp: { sospeso: false, limiteOrario: 60 },
  _spegni: null,

  oggi() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  },

  async carica() {
    const s = await messenger.storage.local.get({ attivita: null, sospeso: false, limiteOrario: 60 });
    if (s.attivita && typeof s.attivita === "object") Object.assign(this.stato, s.attivita);
    this.imp.sospeso = s.sospeso === true;
    this.imp.limiteOrario = Number.isInteger(s.limiteOrario) && s.limiteOrario >= 0 ? s.limiteOrario : 60;
    this._nuovoGiorno();
    await this.aggiornaPulsante();
  },

  _nuovoGiorno() {
    const g = this.oggi();
    if (this.stato.giorno !== g) {
      Object.assign(this.stato, { giorno: g, operazioni: 0, aperti: 0, rifiutate: 0 });
    }
    const soglia = Date.now() - UN_ORA;
    this.stato.recenti = (this.stato.recenti || []).filter((t) => t > soglia);
  },

  async salva() {
    await messenger.storage.local.set({ attivita: { ...this.stato } });
  },

  // Prima di ogni richiesta dell'agente.
  async prima() {
    this._nuovoGiorno();
    this.stato.operazioni += 1;
    this.stato.ultimo = new Date().toISOString();
    if (this.imp.sospeso) throw new Errore("sospeso");
    await messenger.action.setBadgeBackgroundColor({ color: COLORE_LETTURA });
    await messenger.action.setTitle({ title: "AgentPEC: l'agente sta leggendo la posta" });
  },

  // Ogni messaggio aperto passa da qui: si controlla il limite orario.
  contaApertura() {
    const soglia = Date.now() - UN_ORA;
    this.stato.recenti = this.stato.recenti.filter((t) => t > soglia);
    if (this.imp.limiteOrario > 0 && this.stato.recenti.length >= this.imp.limiteOrario) {
      throw new Errore("limite_raggiunto");
    }
    this.stato.recenti.push(Date.now());
    this.stato.aperti += 1;
  },

  // Dopo ogni richiesta, riuscita o no.
  async dopo(rifiutata) {
    if (rifiutata) this.stato.rifiutate += 1;
    await this.salva();
    clearTimeout(this._spegni);
    this._spegni = setTimeout(() => this.aggiornaPulsante(), 2500);
  },

  async impostaCollegato(valore) {
    if (this.stato.collegato === valore) return;
    this.stato.collegato = valore;
    await this.salva();
    await this.aggiornaPulsante();
  },

  async aggiornaPulsante() {
    this._nuovoGiorno();
    const ora = this.stato.ultimo ? new Date(this.stato.ultimo).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : "mai";
    if (this.imp.sospeso) {
      await messenger.action.setBadgeText({ text: "OFF" });
      await messenger.action.setBadgeBackgroundColor({ color: COLORE_SOSPESO });
      await messenger.action.setTitle({ title: "AgentPEC: SOSPESO — l'agente non può leggere la posta" });
      return;
    }
    await messenger.action.setBadgeText({ text: this.stato.aperti ? String(this.stato.aperti) : "" });
    await messenger.action.setBadgeBackgroundColor({ color: COLORE_ATTIVO });
    await messenger.action.setTitle({
      title: `AgentPEC: attivo — oggi ${this.stato.aperti} messaggi aperti dall'agente, ultimo accesso ${ora}`
        + (this.stato.collegato ? "" : " (ponte non collegato)"),
    });
  },
};

messenger.storage.onChanged.addListener(async (changes, area) => {
  if (area !== "local") return;
  if ("sospeso" in changes) Spia.imp.sospeso = changes.sospeso.newValue === true;
  if ("limiteOrario" in changes) {
    const v = changes.limiteOrario.newValue;
    Spia.imp.limiteOrario = Number.isInteger(v) && v >= 0 ? v : 60;
  }
  if ("sospeso" in changes || "limiteOrario" in changes) await Spia.aggiornaPulsante();
});
