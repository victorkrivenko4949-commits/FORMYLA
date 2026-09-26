(() => {
  "use strict";
  const root = document.getElementById("geoexact");
  if (!root) return;
  const el = id => document.getElementById("gx-" + id);
  const api = root.dataset.api;
  const recognizeApi = root.dataset.recognize;
  let activeJob = null, result = null, polling = false, urls = [];
  // Распознанное фото: {plain, raw}. Если пользователь не редактировал текст,
  // в конвейер уходит raw-версия (полная, с LaTeX-формулами), а пользователь
  // видит её же в читаемом виде без LaTeX.
  let recognized = null;
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
      const userText = el("problem").value;
      // Текст после распознавания не меняли — конвейер получает полную
      // (LaTeX) версию условия, пользователь видел её без LaTeX.
      const problem = recognized && userText === recognized.plain ? recognized.raw : userText;
      const data = await jsonResponse(await fetch(api, {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf},
        body: JSON.stringify({
          problem,
          with_aux: root.querySelector('input[name="gx-mode"]:checked').value === "aux"
        })
      }));
      activeJob = data.job_id; await poll();
    } catch (error) { status(error.message); el("submit").disabled = false; }
  });
  el("resume").addEventListener("click", poll);
  el("toggle").addEventListener("change", render);
  window.addEventListener("pagehide", clearUrls);

  // ── Распознавание фото (кнопка «Распознать по фото» + Ctrl+V) ────────
  function latexToPlain(src) {
    if (!src) return "";
    let t = String(src);
    // Math-разделители $...$ / $$...$$ / \(...\) / \[...\]
    t = t.replace(/\$\$([\s\S]*?)\$\$/g, "$1").replace(/\$([^$\n]*)\$/g, "$1");
    t = t.replace(/\\\[([\s\S]*?)\\\]/g, "$1").replace(/\\\((.*?)\\\)/g, "$1");
    t = t.replace(/\\%/g, "%");
    // Дроби: \frac{a}{b} -> a/b (простые аргументы) или (a)/(b)
    const frac = (m, a, b) =>
      (/^[\wА-Яа-яёЁ]+$/.test(a) && /^[\wА-Яа-яёЁ]+$/.test(b)) ? a + "/" + b : "(" + a + ")/(" + b + ")";
    for (let i = 0; i < 3; i++) t = t.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, frac);
    // Корни и текстовые команды с одним аргументом
    t = t.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
    t = t.replace(/\\(?:text|mbox)\s*\{([^{}]*)\}/g, "$1");
    t = t.replace(/\\(?:overline|vec)\s*\{([^{}]*)\}/g, "$1");
    // Частые команды -> символы
    const map = {
      "\\angle": "∠", "\\triangle": "△", "\\circ": "°", "\\degree": "°",
      "\\cdot": "·", "\\times": "×", "\\div": ":", "\\perp": "⊥",
      "\\parallel": "∥", "\\cong": "≅", "\\sim": "∼", "\\approx": "≈",
      "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\delta": "δ",
      "\\varepsilon": "ε", "\\epsilon": "ε", "\\theta": "θ", "\\varphi": "φ",
      "\\phi": "φ", "\\omega": "ω", "\\lambda": "λ", "\\mu": "μ", "\\pi": "π",
      "\\Rightarrow": "⇒", "\\rightarrow": "→", "\\left": "", "\\right": "",
      "\\quad": " ", "\\qquad": " ", "\\;": " ", "\\,": " ", "\\ ": " "
    };
    for (const k of Object.keys(map)) t = t.split(k).join(map[k]);
    t = t.replace(/\^\{?\\?circ\}?/g, "°");
    t = t.replace(/\^°/g, "°");   // 60^\circ -> 60° после замены \\circ
    // Остальные неизвестные команды убираем
    t = t.replace(/\\[a-zA-Z]+/g, " ");
    t = t.replace(/[{}]/g, "");
    t = t.replace(/[ \t]{2,}/g, " ");
    return t.trim();
  }

  // Сжатие/конвертация фото (HEIC с iPhone и тяжёлые JPEG -> JPEG ≤1600px),
  // тот же приём, что и у загрузки фото-решений.
  function compressPhoto(file) {
    if (typeof createImageBitmap !== "function") return Promise.resolve(file);
    return createImageBitmap(file).then(bitmap => {
      const maxDim = 1600, quality = 0.82;
      let w = bitmap.width, h = bitmap.height;
      if (Math.max(w, h) > maxDim) {
        const k = maxDim / Math.max(w, h);
        w = Math.round(w * k); h = Math.round(h * k);
      }
      const cv = document.createElement("canvas");
      cv.width = w; cv.height = h;
      cv.getContext("2d").drawImage(bitmap, 0, 0, w, h);
      if (bitmap.close) bitmap.close();
      return new Promise(resolve => {
        cv.toBlob(blob => {
          if (!blob) { resolve(file); return; }
          const nm = (file.name || "photo").replace(/\.[^.]+$/, "");
          resolve(new File([blob], nm + ".jpg", {type: "image/jpeg"}));
        }, "image/jpeg", quality);
      });
    }).catch(() => file);
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result || "").split(",")[1] || "");
      fr.onerror = () => reject(new Error("Не удалось прочитать файл."));
      fr.readAsDataURL(file);
    });
  }

  let recognizing = false;
  async function recognizePhoto(file) {
    if (!file || !(file.type || "").startsWith("image/")) return;
    if (recognizing || activeJob) return;
    recognizing = true; el("submit").disabled = true;
    status("Распознаём фото…");
    try {
      const compressed = await compressPhoto(file);
      const b64 = await fileToBase64(compressed);
      const r = await fetch(recognizeApi, {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf},
        body: JSON.stringify({image: b64, mime: compressed.type || "image/jpeg"})
      });
      const d = await jsonResponse(r);
      const raw = String(d.text || "").trim();
      if (raw.length < 10) throw new Error("На фото не найден текст условия.");
      recognized = {plain: latexToPlain(raw), raw};
      el("problem").value = recognized.plain;
      status("Фото распознано. Проверьте текст и нажмите «Построить чертёж».");
      el("problem").focus();
    } catch (error) {
      status(error.message);
    } finally {
      recognizing = false; el("submit").disabled = false;
    }
  }

  const photoInput = el("photo-input");
  if (photoInput) photoInput.addEventListener("change", () => {
    if (photoInput.files && photoInput.files[0]) recognizePhoto(photoInput.files[0]);
    photoInput.value = "";
  });

  // Ctrl+V: вставка фото прямо в поле условия (или в любую точку блока)
  root.addEventListener("paste", event => {
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item.type && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) { event.preventDefault(); recognizePhoto(file); }
        return;
      }
    }
  });

  // Refreshing the page must not force another paid generation.
  el("submit").disabled = true;
  fetch(root.dataset.active, {credentials: "same-origin", cache: "no-store"})
    .then(jsonResponse).then(data => {
      if (data.job_id) { activeJob = data.job_id; return poll(); }
      el("submit").disabled = false;
    }).catch(error => { status(error.message); el("submit").disabled = false; });
})();
