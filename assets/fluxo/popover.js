// ===================================================================
// Popover de confirmação do valor da alocação
// ===================================================================
// Abre no ponto da conexão (meio da curva), já com a sugestão do maior valor
// possível: min(livre na entrada, falta na saída). Valida em tempo real e só
// libera "Alocar" para 0 < valor <= máximo.

/** Aceita "1.234,56", "1234,56", "1234.56" e "R$ 1.234". */
function parseValor(texto) {
  let s = String(texto || "").replace(/[^\d,.-]/g, "");
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const v = Number.parseFloat(s);
  return Number.isFinite(v) ? round2(v) : NaN;
}

const fmtInput = (v) => v.toFixed(2).replace(".", ",");

/**
 * opts: { receita, despesa, existente, maximo, livre, falta, at, tol,
 *         onConfirm(valor), onCancel() }
 * Devolve uma função que fecha o popover.
 */
function abrirPopover(canvas, pop, opts) {
  const { receita, despesa, existente, maximo, livre, falta, at, tol } = opts;
  const limitante = livre <= falta ? "o saldo livre da entrada" : "o que falta cobrir da saída";

  pop.innerHTML = `
    <div class="fx-pop-head">
      <span class="fx-pop-ico">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/></svg>
      </span>
      <strong>${existente ? "Editar alocação" : "Nova alocação"}</strong>
    </div>
    <p class="fx-pop-q">Quanto deseja alocar desta entrada para esta saída?</p>
    <div class="fx-pop-route">
      <span class="fx-pop-in" title="${esc(receita.titulo)}">${esc(receita.titulo)}</span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
      <span class="fx-pop-out" title="${esc(despesa.titulo)}">${esc(despesa.titulo)}</span>
    </div>
    <label class="fx-pop-field">
      <span>R$</span>
      <input type="text" inputmode="decimal" autocomplete="off" aria-label="Valor a alocar">
    </label>
    <div class="fx-pop-quick">
      <button type="button" data-q="total">Alocar total · ${fmt(maximo)}</button>
      <button type="button" data-q="metade">50%</button>
    </div>
    <div class="fx-pop-hint">Livre na entrada: <b>${fmt(livre)}</b> · Falta na saída: <b>${fmt(falta)}</b></div>
    <div class="fx-pop-err" role="alert"></div>
    <div class="fx-pop-actions">
      <button type="button" class="fx-btn" data-a="cancelar">Cancelar</button>
      <button type="button" class="fx-btn fx-btn-primary" data-a="ok">${existente ? "Salvar" : "Alocar"}</button>
    </div>`;

  const input = pop.querySelector("input");
  const erro = pop.querySelector(".fx-pop-err");
  const ok = pop.querySelector('[data-a="ok"]');

  const validar = () => {
    const v = parseValor(input.value);
    let msg = "";
    if (!Number.isFinite(v) || v <= tol) msg = "Informe um valor maior que zero.";
    else if (v > maximo + tol) msg = `Máximo ${fmt(maximo)} — limite é ${limitante}.`;
    erro.textContent = msg;
    ok.disabled = !!msg;
    input.closest(".fx-pop-field").classList.toggle("is-invalid", !!msg);
    return msg ? null : v;
  };

  input.value = fmtInput(existente ? existente.valor : maximo);
  validar();

  // ---- posicionamento: centrado no ponto da conexão, preso dentro do canvas
  pop.hidden = false;
  const cw = canvas.clientWidth;
  const largura = Math.min(300, cw - 16);
  pop.style.width = `${largura}px`;
  const altura = pop.offsetHeight;
  const x = Math.min(Math.max(at.x - largura / 2, 8), cw - largura - 8);
  const y = Math.min(Math.max(at.y + 14, 8), Math.max(canvas.clientHeight - altura - 8, 8));
  pop.style.left = `${x}px`;
  pop.style.top = `${y}px`;
  pop.style.setProperty("--seta-x", `${Math.min(Math.max(at.x - x, 16), largura - 16)}px`);
  pop.classList.toggle("seta-oculta", y !== at.y + 14);
  requestAnimationFrame(() => pop.classList.add("is-open"));
  pop.scrollIntoView({ block: "nearest", behavior: "smooth" });

  let fechado = false;
  const fechar = () => {
    if (fechado) return;
    fechado = true;
    pop.classList.remove("is-open");
    pop.hidden = true;
    pop.replaceChildren();
    document.removeEventListener("pointerdown", foraDoPopover, true);
  };
  const cancelar = () => { fechar(); opts.onCancel(); };
  const confirmar = () => {
    const v = validar();
    if (v == null) return;
    fechar();
    opts.onConfirm(v);
  };

  // clique fora fecha (composedPath atravessa o shadow DOM)
  const foraDoPopover = (ev) => { if (!ev.composedPath().includes(pop)) cancelar(); };
  setTimeout(() => document.addEventListener("pointerdown", foraDoPopover, true), 0);

  input.addEventListener("input", validar);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); confirmar(); }
    if (ev.key === "Escape") { ev.preventDefault(); cancelar(); }
  });
  pop.querySelector('[data-q="total"]').addEventListener("click", () => {
    input.value = fmtInput(maximo); validar(); input.focus();
  });
  pop.querySelector('[data-q="metade"]').addEventListener("click", () => {
    input.value = fmtInput(round2(maximo / 2)); validar(); input.focus();
  });
  pop.querySelector('[data-a="cancelar"]').addEventListener("click", cancelar);
  ok.addEventListener("click", confirmar);

  setTimeout(() => { input.focus({ preventScroll: true }); input.select(); }, 30);
  return fechar;
}
