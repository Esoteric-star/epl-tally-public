/* Display-only JS. Nothing here enforces anything — the server does that.
   This just makes the +/- steppers work and shows a live "changed" count
   on the save bar before the form is submitted. */

document.addEventListener("click", (e) => {
  const btn = e.target.closest(".step");
  if (!btn) return;
  const input = document.getElementById(btn.dataset.target);
  if (!input) return;
  const cur = parseInt(input.value, 10);
  const base = isNaN(cur) ? 0 : cur;
  const next = Math.max(0, Math.min(19, base + parseInt(btn.dataset.d, 10)));
  input.value = next;
  input.dispatchEvent(new Event("input", { bubbles: true }));
});

const saveBar = document.getElementById("saveBar");
const saveCount = document.getElementById("saveCount");
if (saveBar && saveCount) {
  const inputs = Array.from(document.querySelectorAll(".num[data-original]"));
  const update = () => {
    const dirty = inputs.filter((el) => el.value !== el.dataset.original);
    saveCount.textContent = dirty.length;
    saveBar.classList.toggle("is-up", dirty.length > 0);
    inputs.forEach((el) => el.classList.toggle("is-dirty", el.value !== el.dataset.original));
  };
  inputs.forEach((el) => el.addEventListener("input", update));
  update();
}

/* Inline fixture stats toggle -- collapsed by default, only one open at
   a time. Pure display: doesn't touch prediction inputs or form data. */
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".fx__statstoggle");
  if (!btn) return;
  const panel = document.getElementById(btn.dataset.panel);
  if (!panel) return;
  const wasOpen = btn.getAttribute("aria-expanded") === "true";

  document.querySelectorAll('.fx__statstoggle[aria-expanded="true"]').forEach((other) => {
    if (other === btn) return;
    other.setAttribute("aria-expanded", "false");
    const otherPanel = document.getElementById(other.dataset.panel);
    if (otherPanel) otherPanel.hidden = true;
  });

  btn.setAttribute("aria-expanded", String(!wasOpen));
  panel.hidden = wasOpen;
});

/* Team page back control: prefer real browser history so it returns to
   whichever matchday/tab the badge was tapped from, falling back to the
   href (Predict) if there's nothing to go back to. */
const teamBack = document.getElementById("teamBack");
if (teamBack) {
  teamBack.addEventListener("click", (e) => {
    if (window.history.length > 1) {
      e.preventDefault();
      window.history.back();
    }
  });
}
