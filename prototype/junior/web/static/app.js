// Copy buttons: <button data-copy="#element-id">
document.querySelectorAll("[data-copy]").forEach((btn) => {
  const label = btn.textContent;
  btn.addEventListener("click", async () => {
    const el = document.querySelector(btn.dataset.copy);
    const text = el.value ?? el.textContent;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard API needs https or localhost; fall back to the old way elsewhere.
      const temp = document.createElement("textarea");
      temp.value = text;
      document.body.appendChild(temp);
      temp.select();
      document.execCommand("copy");
      temp.remove();
    }
    btn.textContent = "Copied!";
    setTimeout(() => (btn.textContent = label), 1500);
  });
});

// Live character counters: <textarea data-limit="280" data-counter="#count-id">
document.querySelectorAll("textarea[data-limit]").forEach((ta) => {
  const out = document.querySelector(ta.dataset.counter);
  const limit = Number(ta.dataset.limit);
  const update = () => {
    out.textContent = `${ta.value.length} / ${limit}`;
    out.classList.toggle("over", ta.value.length > limit);
  };
  ta.addEventListener("input", update);
  update();
});
