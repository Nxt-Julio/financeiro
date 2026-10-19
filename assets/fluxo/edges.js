// ===================================================================
// Arestas (linhas de conexão) — curvas Bezier em SVG + badge de valor
// ===================================================================
// Cada vínculo vira um <g> com dois paths: um largo e transparente (área de
// hover/toque) e a linha visível. A badge (valor + botão X) é HTML posicionado
// no ponto médio da curva, numa camada acima do SVG.

const SVG_NS = "http://www.w3.org/2000/svg";

/** Centro do handle de um nó, em coordenadas do canvas. */
function ancora(canvas, nodeEl) {
  const h = nodeEl.querySelector(".fx-handle");
  const r = h.getBoundingClientRect();
  const c = canvas.getBoundingClientRect();
  return { x: r.left + r.width / 2 - c.left, y: r.top + r.height / 2 - c.top };
}

/** Bezier horizontal da esquerda (a) para a direita (b), como no n8n. */
function curva(a, b) {
  const dx = Math.max(40, Math.abs(b.x - a.x) * 0.55);
  return {
    d: `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`,
    // ponto em t = 0,5 da cúbica: (P0 + 3P1 + 3P2 + P3) / 8
    meio: { x: (a.x + 3 * (a.x + dx) + 3 * (b.x - dx) + b.x) / 8, y: (a.y + b.y) / 2 },
  };
}

function svgEl(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

/**
 * Redesenha todas as arestas. `ui` traz o estado de hover/seleção e os
 * callbacks de interação (onHover, onSelect, onEdit, onRemove).
 */
function renderEdges(ctx) {
  const { canvas, layerEdges, layerBadges, nodeEls, edges, ui } = ctx;
  layerEdges.replaceChildren();
  layerBadges.replaceChildren();

  edges.forEach((e) => {
    const de = nodeEls.get(e.receita_id);
    const para = nodeEls.get(e.despesa_id);
    if (!de || !para) return;
    const { d, meio } = curva(ancora(canvas, de), ancora(canvas, para));
    const ativo = ui.hover === e.id || ui.selected === e.id;
    const relacionado = ui.focoNode != null && (e.receita_id === ui.focoNode || e.despesa_id === ui.focoNode);

    const g = svgEl("g", { class: "fx-edge", "data-id": e.id });
    g.classList.toggle("is-on", ativo);
    g.classList.toggle("is-related", relacionado);
    g.classList.toggle("is-pending", !!e.pendente);
    g.appendChild(svgEl("path", { d, class: "fx-edge-line" }));
    const hit = svgEl("path", { d, class: "fx-edge-hit" });
    g.appendChild(hit);
    layerEdges.appendChild(g);

    hit.addEventListener("pointerenter", () => ui.onHover(e.id));
    hit.addEventListener("pointerleave", () => ui.onHover(null));
    hit.addEventListener("click", (ev) => { ev.stopPropagation(); ui.onSelect(e.id); });

    const badge = document.createElement("div");
    badge.className = "fx-badge";
    badge.classList.toggle("is-on", ativo);
    badge.style.left = `${meio.x}px`;
    badge.style.top = `${meio.y}px`;
    badge.innerHTML = `
      <button type="button" class="fx-badge-val" title="Editar valor">${fmt(e.valor)}</button>
      <button type="button" class="fx-badge-x" aria-label="Excluir vínculo" title="Excluir vínculo">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>`;
    badge.addEventListener("pointerenter", () => ui.onHover(e.id));
    badge.addEventListener("pointerleave", () => ui.onHover(null));
    badge.querySelector(".fx-badge-val").addEventListener("click", (ev) => {
      ev.stopPropagation();
      ui.onEdit(e, meio);
    });
    badge.querySelector(".fx-badge-x").addEventListener("click", (ev) => {
      ev.stopPropagation();
      ui.onRemove(e);
    });
    layerBadges.appendChild(badge);
  });
}

/** Liga/desliga o destaque sem redesenhar (hover é frequente). */
function marcarEdges(ctx) {
  const { layerEdges, layerBadges, edges, ui } = ctx;
  const gs = layerEdges.children;
  const bs = layerBadges.children;
  let i = 0;
  edges.forEach((e) => {
    if (!ctx.nodeEls.get(e.receita_id) || !ctx.nodeEls.get(e.despesa_id)) return;
    const ativo = ui.hover === e.id || ui.selected === e.id;
    const relacionado = ui.focoNode != null && (e.receita_id === ui.focoNode || e.despesa_id === ui.focoNode);
    gs[i]?.classList.toggle("is-on", ativo);
    gs[i]?.classList.toggle("is-related", relacionado);
    bs[i]?.classList.toggle("is-on", ativo || relacionado);
    i += 1;
  });
}

/** Linha provisória enquanto o usuário arrasta (ou com o popover aberto). */
function desenharTemp(path, a, b, estado) {
  if (!a || !b) {
    path.setAttribute("d", "");
    path.setAttribute("class", "fx-temp");
    return;
  }
  const [esq, dir] = a.x <= b.x ? [a, b] : [b, a];
  path.setAttribute("d", curva(esq, dir).d);
  path.setAttribute("class", `fx-temp ${estado ? `is-${estado}` : ""}`);
}
