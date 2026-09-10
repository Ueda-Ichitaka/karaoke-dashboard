// Progressive enhancement: live search + song picker. Works without JS too.
(function () {
  "use strict";

  function debounce(fn, ms) {
    let t;
    return function () {
      clearTimeout(t);
      const args = arguments;
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  async function fetchFragment(url) {
    const res = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!res.ok) throw new Error("request failed: " + res.status);
    return res.text();
  }

  // ---- live search on the songs page -----------------------------------
  document.querySelectorAll("input[data-live-search]").forEach((input) => {
    const target = document.querySelector(input.dataset.target);
    const endpoint = input.dataset.endpoint;
    if (!target || !endpoint) return;

    const run = debounce(async () => {
      const q = input.value.trim();
      const url = endpoint + "?q=" + encodeURIComponent(q);
      try {
        target.innerHTML = await fetchFragment(url);
        const params = new URLSearchParams(window.location.search);
        if (q) params.set("q", q); else params.delete("q");
        params.delete("page");
        const qs = params.toString();
        window.history.replaceState(null, "", qs ? "?" + qs : window.location.pathname);
      } catch (e) {
        /* leave the server-rendered list in place */
      }
    }, 200);

    input.addEventListener("input", run);
  });

  // ---- song picker (report page) --------------------------------------
  document.querySelectorAll("[data-picker]").forEach((picker) => {
    const endpoint = picker.dataset.endpoint;
    const hidden = document.querySelector(picker.dataset.input);
    const search = picker.querySelector("[data-picker-search]");
    const results = picker.querySelector("[data-picker-results]");
    const chosen = picker.querySelector("[data-chosen]");
    if (!endpoint || !hidden || !search || !results || !chosen) return;

    function selectOption(folder, label) {
      hidden.value = folder;
      chosen.textContent = label;
      chosen.classList.remove("empty");
      results.hidden = true;
      search.value = "";
    }

    results.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".picker-option");
      if (!btn) return;
      selectOption(btn.dataset.folder, btn.dataset.label);
    });

    const run = debounce(async () => {
      const q = search.value.trim();
      if (!q) { results.hidden = true; return; }
      try {
        results.innerHTML = await fetchFragment(endpoint + "?q=" + encodeURIComponent(q));
        results.hidden = false;
      } catch (e) {
        results.hidden = true;
      }
    }, 200);

    search.addEventListener("input", run);
    search.addEventListener("focus", () => { if (search.value.trim()) run(); });
    document.addEventListener("click", (ev) => {
      if (!picker.contains(ev.target)) results.hidden = true;
    });
  });
})();
