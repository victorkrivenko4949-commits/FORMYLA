(() => {
  "use strict";
  const root = document.getElementById("geoexact");
  if (!root) return;
  const el = id => document.getElementById("gx-" + id);
  const api = root.dataset.api;
  const recognizeApi = root.dataset.recognize;
  const solutionApi = root.dataset.solution;
  let activeJob = null, result = null, polling = false, urls = [];
  // Задание «полное решение»: тот же диалог с Луной продолжается просьбой
  // решить задачу, DeepSeek оформляет ответ в LaTeX, KaTeX рисует формулы.
  let solutionJob = null;
  // Распознанное фото: {plain, raw}. Если пользователь не редактировал текст,
  // в конвейер уходит raw-версия (полная, с LaTeX-формулами), а пользователь
  // видит её же в читаемом виде без LaTeX.
  let recognized = null;
  const status = text => { el("status").textContent = text; };
  // Обновление страницы не должно терять условие, режим и готовый чертёж: текст и
  // номер последнего готового задания хранятся в браузере, сам результат — на сервере.
  const storeKey = "gx-state:" + (root.dataset.user || "");
  const loadState = () => {
    try { return JSON.parse(localStorage.getItem(storeKey)) || {}; } catch (e) { return {}; }
  };
  const saveState = patch => {
    try { localStorage.setItem(storeKey, JSON.stringify(Object.assign(loadState(), patch))); } catch (e) { /* private mode */ }
  };
  const currentMode = () => root.querySelector('input[name="gx-mode"]:checked')?.value || "base";
  const persistForm = () => saveState({problem: el("problem").value, recognized, mode: currentMode()});
  function clearUrls() { urls.forEach(URL.revokeObjectURL); urls = []; }
  function imageURL(svg) {
    const url = URL.createObjectURL(new Blob([svg], {type: "image/svg+xml"}));
    urls.push(url); return url;
  }
  // Черточки равных отрезков можно скрыть: равенство остаётся видимым
  // по цвету (цвета групп зашиты в сам SVG серверным рендером).
  // Правило дописывается в <style> картинки — она остаётся обычным <img>.
  function withTicks(svg, show) {
    if (show || !svg || svg.indexOf("</style>") < 0) return svg;
    return svg.replace("</style>", "\n    .tick { display: none; }\n  </style>");
  }
  function render() {
    clearUrls();
    const full = !result.svg_base || el("toggle").checked;
    const raw = full ? result.svg : result.svg_base;
    const url = imageURL(withTicks(raw, el("ticks").checked));
    el("image").src = url; el("download").href = url;
    // Переключатель виден всегда, пока есть чертёж; без черточек он неактивен.
    const hasTicks = !!raw && raw.indexOf('<path class="tick') >= 0;
    el("ticks-wrap").hidden = false;
    el("ticks").disabled = !hasTicks;
    el("ticks-wrap").title = hasTicks ? "" : "В этом чертеже нет черточек равенства";
    el("ticks-wrap").style.opacity = hasTicks ? "" : "0.5";
    el("detail").hidden = !full || !result.svg_detail;
    if (full && result.svg_detail)
      el("detail-image").src = imageURL(withTicks(result.svg_detail, el("ticks").checked));
    else el("detail-image").removeAttribute("src");
  }
  function show(data) {
    result = data;
    el("toggle").checked = true;
    el("toggle-wrap").hidden = !data.with_aux || !data.svg_base;
    el("another").hidden = !(data.with_aux && lastJob);
    // Полное решение доступно для любого готового чертежа: сервер продолжит
    // диалог с Луной, если он был, или начнёт новый по этому условию.
    el("solution").hidden = !lastJob;
    el("another").textContent = Array.isArray(data.expert_history) && data.expert_history.length
      ? "Использовать другое доп. построение" : "Луна не ответила: повторить запрос";
    const fail = data.with_aux && data.expert_status && data.expert_status !== "OK";
    el("expert-note").hidden = !fail;
    const rejected = fail && String(data.expert_status).startsWith("REJECTED:");
    el("expert-note").textContent = !fail ? "" : rejected
      ? "Луна предложила построение, но его не удалось нарисовать (" + data.expert_status.slice(9).trim() +
        "). Кнопка ниже попросит другое."
      : "Луна не дала доп. построение (код " + data.expert_status + "). Кнопка ниже отправит запрос заново.";
    el("result").hidden = false;
    const value = data.measured;
    el("measured").textContent = value == null ? "" :
      "Измерено на чертеже: " + Number(value).toLocaleString("ru-RU", {maximumSignificantDigits: 8}) +
      ". Это не доказанный ответ.";
    el("warnings").replaceChildren();
    // Technical codes (APPROXIMATE:, SKETCH:, ...) are for logs; users see text.
    const warnings = (data.warnings || [])
      .filter(w => !/^(SKETCH|SIMPLIFIED):/.test(String(w)))
      .map(w => String(w).replace(/^[A-Z_]+:\s*/, ""));
    const notice = {
      approximate: "Чертёж построен, но автоматическая проверка подтвердила не всё условие. Сверьте его с текстом задачи.",
      simplified: "Чертёж построен по упрощённой схеме: часть условий могла быть не учтена.",
      sketch: "Показан схематичный чертёж по ключевым словам условия; пропорции условные."
    }[data.verification];
    if (notice) warnings.unshift(notice);
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
  let lastJob = null;
  // Markdown решения от DeepSeek -> безопасный HTML (формулы $...$ остаются
  // для KaTeX). Экранирование сначала, теги внутри — только наши.
  function solutionHTML(markdown) {
    const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const lines = esc(String(markdown || "")).split(/\r?\n/);
    const out = [];
    let list = null, para = [];
    const flushPara = () => {
      if (para.length) { out.push("<p>" + para.join("<br>") + "</p>"); para = []; } };
    const flushList = () => { if (list) { out.push("</" + list + ">"); list = null; } };
    for (const line of lines) {
      const t = line.trim();
      if (!t) { flushPara(); flushList(); continue; }
      const bold = s => s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      const h = t.match(/^#{1,4}\s+(.*)$/);
      if (h) { flushPara(); flushList(); out.push("<h3>" + bold(h[1]) + "</h3>"); continue; }
      const ul = t.match(/^[-*]\s+(.*)$/);
      if (ul) { flushPara(); if (list !== "ul") { flushList(); out.push("<ul>"); list = "ul"; } out.push("<li>" + bold(ul[1]) + "</li>"); continue; }
      const ol = t.match(/^\d+[.)]\s+(.*)$/);
      if (ol) { flushPara(); if (list !== "ol") { flushList(); out.push("<ol>"); list = "ol"; } out.push("<li>" + bold(ol[1]) + "</li>"); continue; }
      para.push(bold(t));
    }
    flushPara(); flushList();
    return out.join("\n");
  }
  function renderSolution(res) {
    const box = el("solution-box"), text = el("solution-text");
    text.innerHTML = solutionHTML(res.markdown);
    box.hidden = false;
    try { if (typeof reRenderMath === "function") reRenderMath(text); } catch (e) { /* KaTeX не загрузился — формулы останутся текстом */ }
    box.scrollIntoView({behavior: "smooth", block: "nearest"});
  }
  async function poll() {
    if (polling || !activeJob) return;
    polling = true; el("resume").hidden = true;
    const started = Date.now();
    const isSolution = activeJob === solutionJob;
    try {
      for (let i = 0; i < 620; i++) {
        const data = await jsonResponse(await fetch(api + "/" + activeJob,
          {credentials: "same-origin", cache: "no-store"}));
        if (data.status === "done" || data.status === "failed") {
          if (data.result?.ok && data.result.kind === "solution") {
            activeJob = null;
            el("submit").disabled = false;
            renderSolution(data.result);
            status("Полное решение готово.");
            return;
          }
          lastJob = activeJob;
          saveState({job: data.result?.ok ? lastJob : null});
          activeJob = null;
          el("submit").disabled = false;
          if (data.result?.ok) {
            show(data.result);
            status(["approximate", "simplified", "sketch"].includes(data.result.verification)
              ? "Чертёж готов (приближённый)." : "Чертёж готов.");
          }
          else status((data.result?.detail || "Не удалось построить чертёж.") +
            (data.result?.reason ? " Код: " + data.result.reason : ""));
          return;
        }
        const sec = Math.round((Date.now() - started) / 1000);
        const clock = Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
        const auxMode = root.querySelector('input[name="gx-mode"]:checked')?.value === "aux";
        status(data.status === "running"
          ? (isSolution ? "Луна пишет полное решение, DeepSeek оформляет его в LaTeX… " + clock
              : "Строим и проверяем чертёж… " + clock + (!auxMode ? "" : (sec > 60
              ? " — сложная задача, около 100 секунд, не дольше 3 минут"
              : " — с доп. построением обычно около 50 секунд, сложные около 100")))
          : "Запрос в очереди… " + clock);
        await new Promise(resolve => setTimeout(resolve, 3000));
      }
      throw new Error("Ожидание затянулось. Можно проверить готовность без нового платного запроса.");
    } catch (error) {
      status(error.message); el("resume").hidden = false;
    } finally { polling = false; }
  }
  el("another").addEventListener("click", () => {
    if (activeJob || !lastJob) return;
    submitJob(lastJob);
  });
  el("solution").addEventListener("click", async () => {
    // «Запросить полное решение»: тот же диалог с Луной продолжается
    // просьбой решить задачу; кнопка не делает нового чертежа.
    if (activeJob || !lastJob) return;
    el("solution").disabled = true;
    el("solution-box").hidden = true;
    status("Запрашиваем полное решение…");
    try {
      const data = await jsonResponse(await fetch(solutionApi, {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf},
        body: JSON.stringify({job_id: lastJob})
      }));
      solutionJob = data.job_id;
      activeJob = data.job_id;
      await poll();
    } catch (error) { status(error.message); }
    finally { el("solution").disabled = false; }
  });
  el("form").addEventListener("submit", event => {
    event.preventDefault();
    submitJob(null);
  });
  async function submitJob(retryOf) {
    if (activeJob) return;
    el("submit").disabled = true; el("another").disabled = true;
    persistForm(); saveState({job: null});
    el("result").hidden = true; clearUrls(); status("Отправляем запрос…");
    try {
      const userText = el("problem").value;
      // Текст после распознавания не меняли — конвейер получает полную
      // (LaTeX) версию условия, пользователь видел её без LaTeX.
      const problem = recognized && userText === recognized.plain ? recognized.raw : userText;
      const data = await jsonResponse(await fetch(api, {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf},
        body: JSON.stringify(Object.assign({
          problem,
          with_aux: retryOf ? true : root.querySelector('input[name="gx-mode"]:checked').value === "aux"
        }, retryOf ? {retry_of: retryOf} : {}))
      }));
      activeJob = data.job_id; await poll();
    } catch (error) { status(error.message); el("submit").disabled = false; }
    finally { el("another").disabled = false; }
  }
  el("resume").addEventListener("click", poll);
  el("toggle").addEventListener("change", () => { saveState({full: el("toggle").checked}); render(); });
  el("ticks").addEventListener("change", () => { saveState({ticks: el("ticks").checked}); render(); });
  el("problem").addEventListener("input", persistForm);
  root.querySelectorAll('input[name="gx-mode"]').forEach(r => r.addEventListener("change", persistForm));
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
    t = t.replace(/\\(?:operatorname|mathrm)\s*\{\s*(cos|sin|tan|cot|arccos|arcsin|arctan|ln|log)\s*\}/gi, "$1");
    t = t.replace(/\\(?:overline|vec)\s*\{([^{}]*)\}/g, "$1");
    // Частые команды -> символы
    const map = {
      "\\angle": "∠", "\\triangle": "△", "\\circ": "°", "\\degree": "°",
      "\\cdot": "·", "\\times": "×", "\\div": ":", "\\perp": "⊥",
      "\\parallel": "∥", "\\cong": "≅", "\\sim": "∼", "\\approx": "≈",
      "\\arccos": "arccos", "\\arcsin": "arcsin", "\\arctan": "arctan",
      "\\cos": "cos", "\\sin": "sin", "\\tan": "tan", "\\cot": "cot",
      "\\ln": "ln", "\\log": "log",
      "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\delta": "δ",
      "\\varepsilon": "ε", "\\epsilon": "ε", "\\theta": "θ", "\\varphi": "φ",
      "\\phi": "φ", "\\omega": "ω", "\\lambda": "λ", "\\mu": "μ", "\\pi": "π",
      "\\Rightarrow": "⇒", "\\rightarrow": "→", "\\left": "", "\\right": "",
      "\\quad": " ", "\\qquad": " ", "\\;": " ", "\\,": " ", "\\ ": " "
    };
    for (const k of Object.keys(map)) t = t.split(k).join(map[k]);
    t = t.replace(/\^\{?\\?circ\}?/g, "°");
    t = t.replace(/\^°/g, "°");   // 60^\circ -> 60° после замены \\circ
    // Неизвестные команды оставляем видимыми: молчаливое удаление \cos
    // превращало осмысленное условие в невозможное «(2∠CAN) = -1/4».
    t = t.replace(/[{}]/g, "");
    t = t.replace(/[ \t]{2,}/g, " ");
    return t.trim();
  }

  // Сжатие/конвертация фото (HEIC с iPhone и тяжёлые JPEG -> JPEG ≤1600px),
  // тот же приём, что и у загрузки фото-решений.
  function compressPhoto(file) {
    // Некоторые мобильные браузеры не умеют createImageBitmap или не
    // декодируют им HEIC/нестандартные файлы с камеры. Резерв — обычный
    // <img> через object URL: он декодирует всё, что показывает браузер,
    // а canvas заодно убирает EXIF-поворот и перекодирует в JPEG.
    const loadViaImg = () => new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        resolve({width: img.naturalWidth, height: img.naturalHeight,
          draw: (cv, w, h) => cv.getContext("2d").drawImage(img, 0, 0, w, h)});
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error(
        "Браузер не смог открыть фото. Сохраните его как JPEG/PNG и попробуйте снова.")); };
      img.src = url;
    });
    const loadBitmap = typeof createImageBitmap === "function"
      ? () => createImageBitmap(file, {imageOrientation: "from-image"})
          .then(bitmap => ({width: bitmap.width, height: bitmap.height,
            draw: (cv, w, h) => cv.getContext("2d").drawImage(bitmap, 0, 0, w, h),
            close: () => bitmap.close && bitmap.close()}))
          .catch(loadViaImg)
      : loadViaImg;
    return loadBitmap().then(bitmap => {
      const maxDim = 1600, quality = 0.82;
      let w = bitmap.width, h = bitmap.height;
      if (Math.max(w, h) > maxDim) {
        const k = maxDim / Math.max(w, h);
        w = Math.round(w * k); h = Math.round(h * k);
      }
      const cv = document.createElement("canvas");
      cv.width = w; cv.height = h;
      bitmap.draw(cv, w, h);
      if (bitmap.close) bitmap.close();
      return new Promise((resolve, reject) => {
        cv.toBlob(blob => {
          // Пустой blob (приватный режим iOS и др.) — отправлять исходный
          // файл нельзя: сервер может не понять его формат. Честная ошибка
          // полезнее молчаливой отправки неподдерживаемых байтов.
          if (!blob) { reject(new Error("Не удалось подготовить фото. Попробуйте снимок меньшего размера.")); return; }
          const nm = (file.name || "photo").replace(/\.[^.]+$/, "");
          resolve(new File([blob], nm + ".jpg", {type: "image/jpeg"}));
        }, "image/jpeg", quality);
      });
    });
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
    // На части мобильных браузеров file.type пуст даже для корректного JPEG
    // с камеры — нельзя молча выходить: фото обязано попасть в конвейер.
    const looksImage = !file.type || file.type.startsWith("image/") ||
      /\.(jpe?g|png|webp|heic|heif|bmp|gif)$/i.test(file.name || "");
    if (!file || !looksImage) return;
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
      persistForm();
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
  const saved = loadState();
  if (typeof saved.problem === "string" && !el("problem").value) {
    el("problem").value = saved.problem;
    if (saved.recognized && saved.recognized.plain && saved.recognized.raw) recognized = saved.recognized;
    const radio = root.querySelector('input[name="gx-mode"][value="' + saved.mode + '"]');
    if (radio) radio.checked = true;
    if (typeof saved.ticks === "boolean") el("ticks").checked = saved.ticks;
  }
  async function restoreResult(job) {
    // Готовый чертёж берётся с сервера повторно, без нового платного запроса.
    try {
      const data = await jsonResponse(await fetch(api + "/" + job,
        {credentials: "same-origin", cache: "no-store"}));
      if (data.status === "done" && data.result?.ok
          && data.result.kind !== "solution") {
        lastJob = job;
        if (!el("problem").value && data.result.problem_text) el("problem").value = data.result.problem_text;
        const radio = root.querySelector('input[name="gx-mode"][value="' + (data.result.with_aux ? "aux" : "base") + '"]');
        if (radio && !saved.problem) radio.checked = true;
        show(data.result);
        if (saved.full === false && !el("toggle-wrap").hidden) { el("toggle").checked = false; render(); }
        status("Чертёж восстановлен после обновления страницы.");
        return;
      }
    } catch (e) { /* задание удалено или недоступно */ }
    saveState({job: null});
  }
  el("submit").disabled = true;
  fetch(root.dataset.active, {credentials: "same-origin", cache: "no-store"})
    .then(jsonResponse).then(async data => {
      if (data.job_id) { activeJob = data.job_id; return poll(); }
      // Последний готовый чертёж хранится на сервере: обновление страницы (и другое
      // устройство) не теряет его, даже если браузер не сохранил своё состояние.
      let job = saved.job;
      if (!job) {
        try { job = (await jsonResponse(await fetch(root.dataset.last,
          {credentials: "same-origin", cache: "no-store"}))).job_id; } catch (e) { job = null; }
      }
      if (job) await restoreResult(job);
      el("submit").disabled = false;
    }).catch(error => { status(error.message); el("submit").disabled = false; });
})();
