function addCopyButtons() {
  document.querySelectorAll("pre").forEach((block) => {
    const button = document.createElement("button");
    button.className = "copy-button";
    button.type = "button";
    button.textContent = "Copy";
    button.addEventListener("click", async () => {
      const text = block.innerText;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        window.setTimeout(() => {
          button.textContent = "Copy";
        }, 1200);
      } catch (err) {
        console.error("[copy-button] clipboard write failed:", err);
        button.textContent = "Error";
        window.setTimeout(() => {
          button.textContent = "Copy";
        }, 1200);
      }
    });
    block.appendChild(button);
  });
}

addCopyButtons();
