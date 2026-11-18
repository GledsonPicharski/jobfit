// Ícone de copiar no canto da caixa: <button data-copiar="id-do-textarea">.
// 127.0.0.1 é contexto seguro, então a área de transferência funciona sem HTTPS.
document.addEventListener("click", async (evento) => {
  const botao = evento.target.closest("[data-copiar]");
  if (!botao) return;
  const alvo = document.getElementById(botao.dataset.copiar);
  try {
    await navigator.clipboard.writeText(alvo.value);
    botao.classList.add("copiado");
    botao.title = "Copiado!";
  } catch {
    alvo.select();
    botao.title = "Texto selecionado: use Ctrl+C";
  }
  setTimeout(() => {
    botao.classList.remove("copiado");
    botao.title = "Copiar";
  }, 2000);
});
