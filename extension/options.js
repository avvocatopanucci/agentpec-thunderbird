"use strict";

function el(tag, attrs = {}, ...figli) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "checked" || k === "disabled") e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const f of figli) e.append(f);
  return e;
}

async function disegna() {
  const imp = await leggiImpostazioni();
  const account = await messenger.accounts.list(true);
  const contenitore = document.getElementById("elenco");
  contenitore.textContent = "";
  if (account.length === 0) {
    contenitore.textContent = "Nessun account configurato in Thunderbird.";
  }
  for (const acc of account) {
    const indirizzi = (acc.identities || []).map((i) => i.email).filter(Boolean).join(", ");
    const casella = el("input", { type: "checkbox", class: "acc", "data-id": acc.id, checked: imp.account.includes(acc.id) });
    const blocco = el("div", { class: "account" },
      el("label", {}, casella, ` ${acc.name}`, el("span", { class: "uso" }, indirizzi ? `(${indirizzi})` : "")));
    const sotto = el("div", { class: "cartelle" });
    for (const f of appiattisciCartelle(acc.rootFolder)) {
      const profondita = (f.path.match(/\//g) || []).length - 1;
      const c = el("input", { type: "checkbox", class: "cart", "data-id": f.id, "data-acc": acc.id,
        checked: imp.cartelle.includes(f.id), disabled: !imp.account.includes(acc.id) });
      const uso = (f.specialUse || []).join(", ");
      const riga = el("label", { style: `padding-left:${Math.max(profondita, 0) * 1.2}rem` },
        c, el("span", {}, ` ${f.name}`, el("span", { class: "uso" }, uso ? `[${uso}]` : "")));
      sotto.append(riga);
    }
    casella.addEventListener("change", () => {
      for (const c of sotto.querySelectorAll("input")) c.disabled = !casella.checked;
    });
    blocco.append(sotto);
    contenitore.append(blocco);
  }
  document.getElementById("pseudonimizza").checked = imp.pseudonimizza;
  const { limiteOrario } = await messenger.storage.local.get({ limiteOrario: 60 });
  document.getElementById("limiteOrario").value = limiteOrario;
  document.getElementById("consentiBozze").checked = imp.consentiBozze;
}

async function salva() {
  const accountScelti = [...document.querySelectorAll("input.acc:checked")].map((c) => c.dataset.id);
  const cartelleScelte = [...document.querySelectorAll("input.cart:checked")]
    .filter((c) => accountScelti.includes(c.dataset.acc))
    .map((c) => c.dataset.id);
  await messenger.storage.local.set({
    account: accountScelti,
    cartelle: cartelleScelte,
    pseudonimizza: document.getElementById("pseudonimizza").checked,
    consentiBozze: document.getElementById("consentiBozze").checked,
    limiteOrario: Math.max(0, Math.min(10000, parseInt(document.getElementById("limiteOrario").value, 10) || 0)),
  });
  const esito = document.getElementById("esito");
  esito.textContent = `Salvato: ${cartelleScelte.length} cartelle consentite.`;
  setTimeout(() => (esito.textContent = ""), 4000);
}

document.getElementById("salva").addEventListener("click", salva);
disegna();
