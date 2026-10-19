// ===================================================================
// Nó (card) do canvas — estilo n8n
// ===================================================================
// Entrada (receita): handle de SAÍDA na borda direita.
// Saída (despesa):   handle de ENTRADA na borda esquerda.
// O elemento é criado uma vez (createNode) e repintado a cada mudança de
// saldo (paintNode), para não perder hover/foco durante a interação.

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmt = (v) => BRL.format(v || 0);
const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;

function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const ICONES = {
  // seta entrando (dinheiro que chega)
  receita: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 7 7 17M7 9v8h8"/></svg>',
  // seta saindo (dinheiro que sai)
  despesa: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8"/></svg>',
};

/** Mesma regra de utils/allocation.classificar. */
function classificar(total, alocado, tol) {
  if (alocado > total + tol) return "excedido";
  if (alocado <= tol) return "nenhum";
  if (total - alocado <= tol) return "total";
  return "parcial";
}

/** Saldos de todos os nós a partir dos vínculos atuais (inclusive otimistas). */
function calcularSaldos(nodes, edges, tol) {
  const usado = new Map();
  nodes.forEach((n) => usado.set(n.id, n.externo || 0));
  edges.forEach((e) => {
    if (usado.has(e.receita_id)) usado.set(e.receita_id, usado.get(e.receita_id) + e.valor);
    if (usado.has(e.despesa_id)) usado.set(e.despesa_id, usado.get(e.despesa_id) + e.valor);
  });
  const saldos = new Map();
  nodes.forEach((n) => {
    const total = round2(n.total);
    const alocado = round2(usado.get(n.id));
    saldos.set(n.id, {
      total,
      alocado,
      disponivel: round2(Math.max(total - alocado, 0)),
      percentual: total > 0 ? Math.min(alocado / total, 1) : 0,
      status: classificar(total, alocado, tol),
    });
  });
  return saldos;
}

function createNode(n) {
  const eh = n.tipo === "receita";
  const el = document.createElement("article");
  el.className = `fx-node fx-${n.tipo}`;
  el.dataset.id = n.id;
  el.innerHTML = `
    <header class="fx-node-head">
      <span class="fx-ico">${ICONES[n.tipo]}</span>
      <div class="fx-node-tt">
        <div class="fx-title" title="${esc(n.titulo)}">${esc(n.titulo)}</div>
        <div class="fx-meta">${esc(n.meta)}</div>
      </div>
    </header>
    <span class="fx-tag"></span>
    <dl class="fx-body">
      <div><dt>Total</dt><dd class="fx-v-total"></dd></div>
      <div><dt>${eh ? "Alocado" : "Coberto"}</dt><dd class="fx-v-alocado"></dd></div>
      <div><dt>${eh ? "Restante" : "Falta"}</dt><dd class="fx-v-resto"></dd></div>
    </dl>
    <div class="fx-bar"><i></i></div>
    <button type="button" class="fx-handle ${eh ? "fx-handle-out" : "fx-handle-in"}"
      aria-label="${eh ? "Conectar esta entrada a uma saída" : "Conectar esta saída a uma entrada"}"></button>`;
  return el;
}

function paintNode(el, n, s, rotulos) {
  const [rotulo, classe] = rotulos[n.tipo][s.status];
  el.classList.remove("st-total", "st-parcial", "st-nenhum", "st-excedido");
  el.classList.add(`st-${s.status}`);
  const tag = el.querySelector(".fx-tag");
  tag.className = `fx-tag ${classe}`;
  tag.textContent = rotulo;
  el.querySelector(".fx-v-total").textContent = fmt(s.total);
  el.querySelector(".fx-v-alocado").textContent = fmt(s.alocado);
  el.querySelector(".fx-v-resto").textContent = fmt(s.disponivel);
  el.querySelector(".fx-bar i").style.width = `${(s.percentual * 100).toFixed(1)}%`;
  el.classList.toggle("is-full", s.disponivel <= 0.005);
}
