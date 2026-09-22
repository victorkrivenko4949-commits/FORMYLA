(() => {
  "use strict";
  const root = document.getElementById("geoexact");
  if (!root) return;
  const el = id => document.getElementById("gx-" + id);
  const api = root.dataset.api;
  let activeJob = null, result = null, polling = false, urls = [];
  const status = text => { el("status").textContent = text; };
  function clearUrls() { urls.forEach(URL.revokeObjectURL); urls = []; }
  function imageURL(svg) {
    const url = URL.createObjectURL(new Blob([svg], {type: "image/svg+xml"}));
    urls.push(url); return url;
  }
  function render() {
    clearUrls();
    const full = !result.svg_base || el("toggle").checked;
    const url = imageURL(full ? result.svg : result.svg_base);
    el("image").src = url; el("download").href = url;
    el("detail").hidden = !full || !result.svg_detail;
    if (full && result.svg_detail) el("detail-image").src = imageURL(result.svg_detail);
    else el("detail-image").removeAttribute("src");
  }
  function show(data) {
    result = data;
    el("toggle").checked = true;
    el("toggle-wrap").hidden = !data.with_aux || !data.svg_base;
    el("result").hidden = false;
    const value = data.measured;
    el("measured").textContent = value == null ? "" :
      "Измерено на чертеже: " + Number(value).toLocaleString("ru-RU", {maximumSignificantDigits: 8}) +
      ". Это не доказанный ответ.";
    el("warnings").replaceChildren();
    const warnings = [...(data.warnings || [])];
    if (data.space === "space") warnings.push("Размеры и углы вычислены в 3D. Плоская проекция может выглядеть иначе.");
    warnings.forEach(text => {
      const li = document.createElement("li"); li.textContent = text;
      el("warnings").appendChild(li);
    });
    render();
  }
  async function jsonResponse(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || (response.status === 401
      ? "Войдите в аккаунт и обновите страницу." : "Ошибка сервера. Попробуйте позже."));
    return data;
  }
  async function poll() {
    if (polling || !activeJob) return;
    polling = true; el("resume").hidden = true;
    try {
      for (let i = 0; i < 620; i++) {
        const data = await jsonResponse(await fetch(api + "/" + activeJob,
          {credentials: "same-origin", cache: "no-store"}));
        if (data.status === "done" || data.status === "failed") {
          activeJob = null;
          el("submit").disabled = false;
          if (data.result?.ok) { show(data.result); status("Чертёж готов."); }
          else status((data.result?.detail || "Не удалось построить чертёж.") +
            (data.result?.reason ? " Код: " + data.result.reason : ""));
          return;
        }
        status(data.status === "running" ? "Строим и проверяем чертёж…" : "Запрос в очереди…");
        await new Promise(resolve => setTimeout(resolve, 3000));
      }
      throw new Error("Ожидание затянулось. Можно проверить готовность без нового платного запроса.");
    } catch (error) {
      status(error.message); el("resume").hidden = false;
    } finally { polling = false; }
  }
  el("form").addEventListener("submit", async event => {
    event.preventDefault();
    if (activeJob) return;
    el("submit").disabled = true;
    el("result").hidden = true; clearUrls(); status("Отправляем запрос…");
    try {
      const data = await jsonResponse(await fetch(api, {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf},
        body: JSON.stringify({
          problem: el("problem").value,
          with_aux: root.querySelector('input[name="gx-mode"]:checked').value === "aux"
        })
      }));
      activeJob = data.job_id; await poll();
    } catch (error) { status(error.message); el("submit").disabled = false; }
  });
  el("resume").addEventListener("click", poll);
  el("toggle").addEventListener("change", render);
  window.addEventListener("pagehide", clearUrls);
  // Refreshing the page must not force another paid generation.
  el("submit").disabled = true;
  fetch(root.dataset.active, {credentials: "same-origin", cache: "no-store"})
    .then(jsonResponse).then(data => {
      if (data.job_id) { activeJob = data.job_id; return poll(); }
      el("submit").disabled = false;
    }).catch(error => { status(error.message); el("submit").disabled = false; });
})();
