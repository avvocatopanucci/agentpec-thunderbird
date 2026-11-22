"use strict";

const UN_ORA = 3600000;

function oggi() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

async function disegna() {
  const s = await messenger.storage.local.get({ attivita: null, sospeso: false, limiteOrario: 60 });
  const a = s.attivita || {};
  const delGiorno = a.giorno === oggi();
  const recenti = (a.recenti || []).filter((t) => t > Date.now() - UN_ORA).length;
  document.getElementById("aperti").textContent = delGiorno ? a.aperti || 0 : 0;
  document.getElementById("operazioni").textContent = delGiorno ? a.operazioni || 0 : 0;
  document.getElementById("rifiutate").textContent = delGiorno ? a.rifiutate || 0 : 0;
  document.getElementById("ultimo").textContent = a.ultimo
    ? new Date(a.ultimo).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "mai";
  document.getElementById("ora").textContent = s.limiteOrario > 0 ? `${recenti} / ${s.limiteOrario}` : `${recenti} (nessun limite)`;

  const pallino = document.getElementById("pallino");
  const stato = document.getElementById("stato");
  const bottone = document.getElementById("interruttore");
  if (s.sospeso) {
    pallino.className = "pallino sospeso";
    stato.textContent = "AgentPEC è sospeso";
    bottone.textContent = "Riattiva l'agente";
    bottone.className = "riprendi";
  } else {
    pallino.className = a.collegato ? "pallino attivo" : "pallino scollegato";
    stato.textContent = a.collegato ? "AgentPEC è attivo" : "AgentPEC è attivo (ponte non collegato)";
    bottone.textContent = "Sospendi l'agente";
    bottone.className = "sospendi";
  }
  bottone.onclick = async () => {
    await messenger.storage.local.set({ sospeso: !s.sospeso });
    disegna();
  };
}

disegna();
