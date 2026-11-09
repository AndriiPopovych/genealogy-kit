const button = document.getElementById('copy-prompt');
const prompt = document.getElementById('prompt-text');
const status = document.getElementById('copy-status');
button.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(prompt.textContent.trim());
    button.textContent = 'Скопійовано ✓';
    status.textContent = 'Тепер вставте запит у чат з агентом.';
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(prompt);
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = 'Текст виділено. Скопіюйте його через Ctrl+C або ⌘C.';
  }
});
