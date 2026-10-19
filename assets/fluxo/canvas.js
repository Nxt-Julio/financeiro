// ===================================================================
// Canvas principal — Entradas à esquerda, Saídas à direita, fios no meio
// ===================================================================
// Mecânica de conexão (pointer events, funciona com mouse e toque):
//   • arrastar do handle de uma Entrada e soltar sobre uma Saída (ou o
//     caminho inverso) → popover pergunta o valor → vínculo criado;
//   • tocar num handle e depois tocar no card do outro lado faz o mesmo
//     (mais preciso no celular, sem precisar arrastar);
//   • Saída → Saída / Entrada → Entrada, origem sem saldo livre ou destino já
//     coberto são recusados com aviso.
// Ao criar/editar/remover, os saldos são recalculados na hora (otimista) e a
// ação vai para o Python via setTriggerValue("acao", …), que grava e devolve
// os dados oficiais no próximo render.

export default function (component) {
  const { data, parentElement: host, setTriggerValue } = component;
  if (host.__fluxoCleanup) host.__fluxoCleanup();

  const TOL = data.tol ?? 0.005;
  const nodes = data.nodes || [];
  const porId = new Map(nodes.map((n) => [n.id, n]));
  let edges = (data.edges || []).map((e) => ({ ...e }));
  let saldos = calcularSaldos(nodes, edges, TOL);

  // ---------- estrutura ----------
  let root = host.querySelector(".fx-root");
  if (!root) {
    root = document.createElement("div");
    root.className = "fx-root";
    host.appendChild(root);
  }
  root.innerHTML = `
    <div class="fx-hint">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="3"/><circle cx="19" cy="12" r="3"/><path d="M8 12c4 0 4-6 8-6M8 12c4 0 4 6 8 6" /></svg>
      <span>Arraste do <b class="dot dot-in"></b> de uma entrada até o <b class="dot dot-out"></b> de uma saída — ou toque em um e depois no outro.</span>
    </div>
    <div class="fx-canvas">
      <svg class="fx-wires"><g class="fx-edges"></g><path class="fx-temp"/></svg>
      <section class="fx-col fx-col-in">
        <h4 class="fx-col-title"><span class="dot dot-in"></span>Entradas</h4>
      </section>
      <div class="fx-gutter" aria-hidden="true"></div>
      <section class="fx-col fx-col-out">
        <h4 class="fx-col-title"><span class="dot dot-out"></span>Saídas</h4>
      </section>
      <div class="fx-badges"></div>
      <div class="fx-pop" role="dialog" aria-label="Valor da alocação" hidden></div>
      <div class="fx-toast" role="status"></div>
    </div>`;

  const canvas = root.querySelector(".fx-canvas");
  const svg = root.querySelector(".fx-wires");
  const tempPath = root.querySelector(".fx-temp");
  const pop = root.querySelector(".fx-pop");
  const toastEl = root.querySelector(".fx-toast");
  const nodeEls = new Map();

  const colunas = { receita: root.querySelector(".fx-col-in"), despesa: root.querySelector(".fx-col-out") };
  ["receita", "despesa"].forEach((tipo) => {
    const lista = nodes.filter((n) => n.tipo === tipo);
    if (!lista.length) {
      const vazio = document.createElement("div");
      vazio.className = "fx-empty";
      vazio.textContent = tipo === "receita" ? "Nenhuma entrada neste filtro." : "Nenhuma saída neste filtro.";
      colunas[tipo].appendChild(vazio);
    }
    lista.forEach((n) => {
      const el = createNode(n);
      nodeEls.set(n.id, el);
      colunas[tipo].appendChild(el);
    });
  });

  // ---------- estado de interação ----------
  const ui = {
    hover: null, selected: null, focoNode: null,
    onHover: (id) => {
      clearTimeout(ui._t);
      // pequena folga para o mouse ir da linha até a badge sem ela sumir
      ui._t = setTimeout(() => { ui.hover = id; marcarEdges(ctx); }, id == null ? 120 : 0);
    },
    onSelect: (id) => { ui.selected = ui.selected === id ? null : id; marcarEdges(ctx); },
    onEdit: (e, meio) => editarEdge(e, meio),
    onRemove: (e) => removerEdge(e),
  };
  const ctx = {
    canvas, layerEdges: root.querySelector(".fx-edges"), layerBadges: root.querySelector(".fx-badges"),
    nodeEls, get edges() { return edges; }, ui,
  };

  const pintar = () => {
    saldos = calcularSaldos(nodes, edges, TOL);
    nodes.forEach((n) => paintNode(nodeEls.get(n.id), n, saldos.get(n.id), data.rotulos));
    redesenhar();
  };
  const redesenhar = () => {
    svg.setAttribute("width", canvas.scrollWidth);
    svg.setAttribute("height", canvas.scrollHeight);
    renderEdges(ctx);
  };

  let toastTimer;
  const toast = (msg, tipo = "aviso") => {
    toastEl.textContent = msg;
    toastEl.className = `fx-toast is-on is-${tipo}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("is-on"), 2600);
  };
  const tremer = (el) => {
    el.classList.remove("is-shake");
    void el.offsetWidth;
    el.classList.add("is-shake");
  };

  // ---------- regras de conexão ----------
  const par = (a, b) => (porId.get(a).tipo === "receita" ? [a, b] : [b, a]);
  const vinculo = (rid, did) => edges.find((e) => e.receita_id === rid && e.despesa_id === did);

  /** Folga do par (receita, despesa): quanto ainda cabe, somando o valor atual do par. */
  const folga = (rid, did) => {
    const atual = vinculo(rid, did)?.valor || 0;
    const livre = saldos.get(rid).disponivel;
    const falta = saldos.get(did).disponivel;
    return { atual, livre, falta, maximo: round2(Math.min(livre, falta) + atual) };
  };

  /** Pode iniciar um fio a partir deste nó? */
  const podeIniciar = (n) => {
    if (saldos.get(n.id).disponivel > TOL) return true;
    toast(n.tipo === "receita" ? "Esta entrada não tem saldo livre." : "Esta saída já está totalmente coberta.");
    tremer(nodeEls.get(n.id));
    return false;
  };

  /** Motivo pelo qual `alvo` não aceita fio vindo de `origem` (ou null). */
  const motivoInvalido = (origem, alvo) => {
    if (origem.id === alvo.id) return "mesmo";
    if (origem.tipo === alvo.tipo) {
      return origem.tipo === "receita" ? "Conecte uma entrada a uma saída." : "Conecte uma saída a uma entrada.";
    }
    const [rid, did] = par(origem.id, alvo.id);
    if (folga(rid, did).maximo <= TOL) {
      return alvo.tipo === "despesa" ? "Esta saída já está totalmente coberta." : "Esta entrada não tem saldo livre.";
    }
    return null;
  };

  // ---------- fio provisório (arrastar / tocar) ----------
  let fio = null; // { origem, handle, pointerId, inicio, moveu, modoToque, alvo }

  const pontoNoCanvas = (ev) => {
    const c = canvas.getBoundingClientRect();
    return { x: ev.clientX - c.left, y: ev.clientY - c.top };
  };

  const marcarAlvos = (origem) => {
    canvas.classList.add("is-wiring", `from-${origem.tipo}`);
    nodes.forEach((n) => {
      const el = nodeEls.get(n.id);
      const motivo = motivoInvalido(origem, n);
      el.classList.toggle("is-target", !motivo);
      el.classList.toggle("is-muted", !!motivo && n.id !== origem.id);
    });
    nodeEls.get(origem.id).classList.add("is-source");
  };

  const limparFio = () => {
    canvas.classList.remove("is-wiring", "from-receita", "from-despesa");
    nodeEls.forEach((el) => el.classList.remove("is-target", "is-muted", "is-source", "is-snap", "is-invalid"));
    desenharTemp(tempPath, null, null);
    pararAutoScroll();
    fio = null;
  };

  /** Nó sob o ponteiro, com "ímã" de 36px em volta dos handles. */
  const alvoEm = (p) => {
    let melhor = null;
    let dist = 36;
    const c = canvas.getBoundingClientRect();
    for (const n of nodes) {
      const el = nodeEls.get(n.id);
      const r = el.getBoundingClientRect();
      const dentro = p.x >= r.left - c.left && p.x <= r.right - c.left && p.y >= r.top - c.top && p.y <= r.bottom - c.top;
      if (dentro) return n;
      const a = ancora(canvas, el);
      const d = Math.hypot(a.x - p.x, a.y - p.y);
      if (d < dist) { dist = d; melhor = n; }
    }
    return melhor;
  };

  const atualizarFio = (p) => {
    const origemEl = nodeEls.get(fio.origem.id);
    const alvo = alvoEm(p);
    nodeEls.forEach((el) => el.classList.remove("is-snap", "is-invalid"));
    fio.alvo = null;
    let fim = p;
    let estado = "";
    if (alvo && alvo.id !== fio.origem.id) {
      fio.alvo = alvo; // inválido também: ao soltar, o motivo vira aviso
      const motivo = motivoInvalido(fio.origem, alvo);
      if (motivo) {
        nodeEls.get(alvo.id).classList.add("is-invalid");
        estado = "invalid";
      } else {
        nodeEls.get(alvo.id).classList.add("is-snap");
        fim = ancora(canvas, nodeEls.get(alvo.id));
        estado = "snap";
      }
    }
    desenharTemp(tempPath, ancora(canvas, origemEl), fim, estado);
  };

  // ---- auto-scroll da página quando o fio chega perto da borda da tela
  let scrollRaf = null;
  let scrollVel = 0;
  const scroller = (() => {
    let el = host.host || host; // ShadowRoot → elemento hospedeiro
    while (el && el !== document.documentElement) {
      const st = getComputedStyle(el);
      if (/(auto|scroll)/.test(st.overflowY) && el.scrollHeight > el.clientHeight) return el;
      el = el.parentElement || el.getRootNode().host;
    }
    return document.scrollingElement;
  })();
  const autoScroll = (clientY) => {
    const margem = 56;
    const h = window.innerHeight;
    scrollVel = clientY < margem ? -(margem - clientY) / 3 : clientY > h - margem ? (clientY - (h - margem)) / 3 : 0;
    if (scrollVel && !scrollRaf) {
      const passo = () => {
        if (!scrollVel || !fio) { scrollRaf = null; return; }
        scroller.scrollTop += scrollVel;
        if (fio.ultimo) atualizarFio(pontoNoCanvas(fio.ultimo));
        scrollRaf = requestAnimationFrame(passo);
      };
      scrollRaf = requestAnimationFrame(passo);
    }
  };
  const pararAutoScroll = () => { scrollVel = 0; };

  const iniciarFio = (n, handle, ev) => {
    if (!podeIniciar(n)) return;
    fio = { origem: n, handle, pointerId: ev.pointerId, inicio: { x: ev.clientX, y: ev.clientY }, moveu: false, modoToque: false };
    marcarAlvos(n);
    handle.setPointerCapture?.(ev.pointerId);
  };

  const concluirFio = (alvo) => {
    const origem = fio.origem;
    if (!alvo || alvo.id === origem.id) { limparFio(); return; }
    const motivo = motivoInvalido(origem, alvo);
    if (motivo) {
      toast(motivo);
      tremer(nodeEls.get(alvo.id));
      limparFio();
      return;
    }
    const [rid, did] = par(origem.id, alvo.id);
    fio.travado = true; // popover aberto: o fio para de seguir o ponteiro
    const a = ancora(canvas, nodeEls.get(rid));
    const b = ancora(canvas, nodeEls.get(did));
    // segura o fio desenhado (tracejado) enquanto o popover está aberto
    canvas.classList.remove("is-wiring");
    desenharTemp(tempPath, a, b, "hold");
    pedirValor(rid, did, curva(a, b).meio, () => limparFio());
  };

  // ---- handlers dos handles (delegados na raiz)
  canvas.addEventListener("pointerdown", (ev) => {
    const handle = ev.target.closest?.(".fx-handle");
    if (fio?.travado) return;
    if (fio && fio.modoToque) {
      // segundo toque do modo "tocar e tocar": em qualquer card ou handle
      const nodeEl = ev.target.closest?.(".fx-node");
      ev.preventDefault();
      if (nodeEl) concluirFio(porId.get(Number(nodeEl.dataset.id)));
      else limparFio();
      return;
    }
    if (!handle || ev.button > 0) return;
    ev.preventDefault();
    ev.stopPropagation();
    const n = porId.get(Number(handle.closest(".fx-node").dataset.id));
    iniciarFio(n, handle, ev);
  });

  canvas.addEventListener("pointermove", (ev) => {
    if (!fio) {
      const nodeEl = ev.target.closest?.(".fx-node");
      const foco = nodeEl ? Number(nodeEl.dataset.id) : null;
      if (foco !== ui.focoNode) { ui.focoNode = foco; marcarEdges(ctx); }
      return;
    }
    if (fio.travado || (!fio.modoToque && ev.pointerId !== fio.pointerId)) return;
    fio.ultimo = { clientX: ev.clientX, clientY: ev.clientY };
    if (!fio.moveu && Math.hypot(ev.clientX - fio.inicio.x, ev.clientY - fio.inicio.y) > 6) fio.moveu = true;
    if (fio.moveu || fio.modoToque) {
      atualizarFio(pontoNoCanvas(ev));
      if (!fio.modoToque) autoScroll(ev.clientY);
    }
  });

  canvas.addEventListener("pointerleave", () => {
    if (!fio && ui.focoNode != null) { ui.focoNode = null; marcarEdges(ctx); }
  });

  canvas.addEventListener("pointerup", (ev) => {
    if (!fio || fio.travado || fio.modoToque || ev.pointerId !== fio.pointerId) return;
    fio.handle.releasePointerCapture?.(ev.pointerId);
    pararAutoScroll();
    if (!fio.moveu) {
      // toque simples no handle → entra no modo "tocar e tocar"
      fio.modoToque = true;
      nodeEls.get(fio.origem.id).classList.add("is-source");
      toast(fio.origem.tipo === "receita" ? "Agora toque na saída que esta entrada vai cobrir." : "Agora toque na entrada que vai cobrir esta saída.", "info");
      return;
    }
    concluirFio(fio.alvo);
  });

  canvas.addEventListener("pointercancel", () => { if (fio && !fio.travado && !fio.modoToque) limparFio(); });

  // teclado: Enter/Espaço no handle = "tocar"
  canvas.addEventListener("keydown", (ev) => {
    if (fio?.travado) return;
    if (ev.key === "Escape" && fio) { limparFio(); return; }
    const handle = ev.target.closest?.(".fx-handle");
    if (!handle || (ev.key !== "Enter" && ev.key !== " ")) return;
    ev.preventDefault();
    const n = porId.get(Number(handle.closest(".fx-node").dataset.id));
    if (fio && fio.modoToque) { concluirFio(n); return; }
    if (!podeIniciar(n)) return;
    fio = { origem: n, handle, modoToque: true, moveu: false };
    marcarAlvos(n);
    toast("Escolha o outro lado com Tab + Enter (Esc cancela).", "info");
  });

  // no modo "tocar e tocar", tocar fora do canvas cancela
  const foraDoCanvas = (ev) => {
    if (fio && fio.modoToque && !ev.composedPath().includes(canvas)) limparFio();
  };
  document.addEventListener("pointerdown", foraDoCanvas, true);

  // clique no fundo do canvas limpa a seleção de linha
  canvas.addEventListener("click", (ev) => {
    if (ui.selected != null && !ev.target.closest?.(".fx-badge")) { ui.selected = null; marcarEdges(ctx); }
  });

  // ---------- popover de valor + sincronização com o Python ----------
  let fecharPop = null;

  const enviar = (acao) => setTriggerValue("acao", acao);

  const pedirValor = (rid, did, at, aoFechar) => {
    fecharPop?.();
    const f = folga(rid, did);
    const existente = vinculo(rid, did);
    if (f.maximo <= TOL) { toast("Não há saldo para este vínculo."); aoFechar?.(); return; }
    fecharPop = abrirPopover(canvas, pop, {
      receita: porId.get(rid), despesa: porId.get(did), existente,
      maximo: f.maximo, livre: f.livre, falta: f.falta, at, tol: TOL,
      onConfirm: (valor) => {
        fecharPop = null;
        aoFechar?.();
        if (existente) existente.valor = valor;
        else edges.push({ id: `novo-${rid}-${did}`, receita_id: rid, despesa_id: did, valor, pendente: true });
        if (existente) existente.pendente = true;
        pintar();
        enviar({ op: "salvar", receita_id: rid, despesa_id: did, valor });
      },
      onCancel: () => { fecharPop = null; aoFechar?.(); },
    });
  };

  const editarEdge = (e, meio) => {
    if (e.pendente) return;
    pedirValor(e.receita_id, e.despesa_id, meio);
  };

  const removerEdge = (e) => {
    if (e.pendente) return;
    edges = edges.filter((x) => x !== e);
    ui.hover = ui.selected = null;
    pintar();
    enviar({ op: "remover", id: e.id });
  };

  // ---------- render inicial + reflow ----------
  pintar();
  const ro = new ResizeObserver(() => redesenhar());
  ro.observe(canvas);
  const aoRedimensionar = () => redesenhar();
  window.addEventListener("resize", aoRedimensionar);
  // fontes/carregamento tardio podem mudar a altura dos cards
  document.fonts?.ready?.then(() => redesenhar());

  const cleanup = () => {
    ro.disconnect();
    window.removeEventListener("resize", aoRedimensionar);
    document.removeEventListener("pointerdown", foraDoCanvas, true);
    fecharPop?.();
    clearTimeout(toastTimer);
    clearTimeout(ui._t);
    scrollVel = 0;
    host.__fluxoCleanup = null;
  };
  host.__fluxoCleanup = cleanup;
  return cleanup;
}
