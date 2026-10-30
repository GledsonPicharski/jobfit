// Botões "Copiar": <button data-copiar="id-do-textarea" data-rotulo="Copiar">.
// 127.0.0.1 é contexto seguro, então a área de transferência funciona sem HTTPS.
document.addEventListener("click", async (evento) => {
  const botao = evento.target.closest("[data-copiar]");
  if (!botao) return;
  const alvo = document.getElementById(botao.dataset.copiar);
  try {
    await navigator.clipboard.writeText(alvo.value);
    botao.textContent = "Copiado!";
  } catch {
    alvo.select();
    botao.textContent = "Texto selecionado: use Ctrl+C";
  }
  setTimeout(() => { botao.textContent = botao.dataset.rotulo; }, 2500);
});
