// __DT_MODAL_V1__
// UX-копия /adaptive_test_simple для модалки «Задач дня».
// Endpoint: POST /daily_tasks/<id>/submit_ai
(function(){
"use strict";

window.DT_PHOTO_BUFFER = window.DT_PHOTO_BUFFER || [];
var DT_MAX_PHOTOS = 8;
var _dtKbActiveField = null;

function _esc(s){
  if(s===null||s===undefined) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Эвристика: на основе формата правильного ответа подсказываем,
// в каком виде ожидается ответ от ученика.
function _buildAnswerFormatHint(correctAnswer){
  if(!correctAnswer) return '';
  var raw = String(correctAnswer).trim();
  if(!raw) return '';

  var rules = [];
  var multiVar = /([A-Za-zА-Яа-я])\s*=\s*[^,;]+(\s*[,;]\s*[A-Za-zА-Яа-я]\s*=\s*[^,;]+)+/;

  if(multiVar.test(raw)){
    rules.push('Запишите все неизвестные через запятую, например: <code>x = 4, y = 2</code>');
    rules.push('Используйте знак <code>=</code> между переменной и её значением');
    rules.push('Соблюдайте порядок переменных, указанный в условии');
  } else if(/^[A-Za-zА-Яа-я]\s*=\s*\S+/.test(raw)){
    rules.push('Запишите ответ в виде <code>' + raw.charAt(0) + ' = …</code> (с переменной и знаком равенства)');
  } else if(/^[^=]+,[^=]+/.test(raw) && raw.indexOf('=') === -1){
    rules.push('Перечислите все значения через запятую, например: <code>' + _esc(raw) + '</code>');
  } else if(/^[\[\(]\s*(?:-?\d+(?:[.,]\d+)?|[-+]?\\infty|[-+]?∞)\s*[;,]\s*(?:-?\d+(?:[.,]\d+)?|[-+]?\\infty|[-+]?∞)\s*[\)\]]\s*$/.test(raw)){
    // Только настоящий интервал — два числа/∞, разделённые ; или , в скобках.
    // Перечисление вида [1, 2, 5] сюда больше не попадает.
    rules.push('Запишите ответ интервалом, например: <code>(-∞; 2]</code> или <code>[1; 5)</code>');
  } else if(/\\frac|\//.test(raw)){
    rules.push('Дробь записывайте через <code>/</code> или используйте \\frac{a}{b} на матклавиатуре');
    rules.push('Сократите дробь, если это возможно');
  } else if(/^-?\d+[\.,]\d+$/.test(raw)){
    rules.push('Десятичную дробь пишите через запятую или точку, например: <code>' + _esc(raw) + '</code>');
  } else if(/^-?\d+$/.test(raw)){
    rules.push('Ответ — целое число. Запишите только число, без единиц измерения');
  }

  if(/\\sqrt|√/.test(raw)){
    rules.push('Корень записывайте как <code>\\sqrt{…}</code> или используйте кнопку <strong>√</strong> на матклавиатуре');
  }

  rules.push('Лишних пробелов и пояснений быть не должно — только сам ответ');

  var html = '';
  html += '<div class="dt-answer-format-hint">';
  html += '<div class="dt-answer-format-title">📐 Требования к ответу:</div>';
  html += '<ul class="dt-answer-format-list">';
  for(var i = 0; i < rules.length; i++){
    html += '<li>' + rules[i] + '</li>';
  }
  html += '</ul>';
  html += '</div>';
  return html;
}

function _key(label, val, cls){
  cls = cls || '';
  var esc = String(val).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
  return '<button type="button" class="dt-kb-key '+cls+'" onclick="dtKbInsert(\''+esc+'\')">'+label+'</button>';
}

function _buildMath(){
  var out = '';
  out += '<div class="dt-kb-row">';
  out += _key('α','\\alpha','math-greek')+_key('β','\\beta','math-greek')+_key('γ','\\gamma','math-greek');
  out += _key('δ','\\delta','math-greek')+_key('θ','\\theta','math-greek')+_key('λ','\\lambda','math-greek');
  out += _key('μ','\\mu','math-greek')+_key('π','\\pi','math-greek')+_key('σ','\\sigma','math-greek');
  out += _key('φ','\\phi','math-greek')+_key('ω','\\omega','math-greek');
  out += '</div>';
  out += '<div class="dt-kb-row">';
  out += _key('√','\\sqrt{}','math-symbol')+_key('∑','\\sum','math-symbol')+_key('∫','\\int','math-symbol');
  out += _key('±','\\pm','math-symbol')+_key('∞','\\infty','math-symbol')+_key('≈','\\approx','math-symbol');
  out += _key('≠','\\neq','math-symbol')+_key('≤','\\leq','math-symbol')+_key('≥','\\geq','math-symbol');
  out += _key('→','\\rightarrow','math-symbol');
  out += '</div>';
  out += '<div class="dt-kb-row">';
  out += _key('\\frac','\\frac{}{}','math-command')+_key('\\sqrt','\\sqrt{}','math-command');
  out += _key('\\cdot','\\cdot','math-command')+_key('\\times','\\times','math-command');
  out += _key('\\div','\\div','math-command')+_key('\\le','\\leq','math-command');
  out += _key('\\ge','\\geq','math-command')+_key('\\ne','\\neq','math-command');
  out += '</div>';
  out += '<div class="dt-kb-row">';
  for(var i=0;i<10;i++) out += _key(String(i), String(i));
  out += _key('.','.')+_key(',',',');
  out += '</div>';
  out += '<div class="dt-kb-row">';
  out += _key('(','(')+_key(')',')')+_key('[','[')+_key(']',']');
  out += _key('{','\\{')+_key('}','\\}');
  out += '<button type="button" class="dt-kb-key action wide" onclick="dtKbBackspace()">⌫</button>';
  out += '<button type="button" class="dt-kb-key space" onclick="dtKbInsert(\' \')">Пробел</button>';
  out += '<button type="button" class="dt-kb-key enter" onclick="dtKbInsert(\'\\\\quad \')">⏎</button>';
  out += '</div>';
  return out;
}
function _buildRegular(){
  var rows = ['йцукенгшщзхъ','фывапролджэ','ячсмитьбю.,','1234567890'];
  var out = '';
  for(var r=0;r<rows.length;r++){
    out += '<div class="dt-kb-row">';
    for(var c=0;c<rows[r].length;c++) out += _key(rows[r][c], rows[r][c]);
    out += '</div>';
  }
  out += '<div class="dt-kb-row">';
  out += '<button type="button" class="dt-kb-key action wide" onclick="dtKbBackspace()">⌫</button>';
  out += '<button type="button" class="dt-kb-key space" onclick="dtKbInsert(\' \')">Пробел</button>';
  out += '<button type="button" class="dt-kb-key enter" onclick="dtSubmitCurrent()">Готово ✓</button>';
  out += '</div>';
  return out;
}

// ── Photo helpers ──────────────────────────────────────────────────
function _fileToBase64(file){
  return new Promise(function(resolve, reject){
    var rd = new FileReader();
    rd.onload = function(){
      var r = rd.result || '';
      var ix = String(r).indexOf(',');
      resolve(ix >= 0 ? String(r).slice(ix+1) : String(r));
    };
    rd.onerror = function(){ reject(rd.error); };
    rd.readAsDataURL(file);
  });
}
function _compressImage(file, maxDim, quality){
  maxDim = maxDim || 1600; quality = quality || 0.82;
  if(!file.type || !file.type.indexOf('image/')!==0) return Promise.resolve(file);
  return createImageBitmap(file).then(function(bitmap){
    var w = bitmap.width, h = bitmap.height;
    if(Math.max(w,h) > maxDim){
      var k = maxDim / Math.max(w,h);
      w = Math.round(w*k); h = Math.round(h*k);
    }
    var cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    cv.getContext('2d').drawImage(bitmap, 0, 0, w, h);
    return new Promise(function(res){
      cv.toBlob(function(blob){
        if(!blob) return res(file);
        res(new File([blob], (file.name||'photo')+'.jpg', { type:'image/jpeg' }));
      }, 'image/jpeg', quality);
    });
  }).catch(function(){ return file; });
}

function dtRenderPhotoBuffer(){
  var list = document.getElementById('dt-photo-preview-list');
  var btnT = document.getElementById('dt-photo-btn-text');
  if(!list) return;
  list.innerHTML = '';
  if(!window.DT_PHOTO_BUFFER.length){
    list.classList.remove('has-items');
    if(btnT) btnT.textContent = 'Сфотографировать / Загрузить решение';
    return;
  }
  window.DT_PHOTO_BUFFER.forEach(function(f, idx){
    var wrap = document.createElement('div');
    wrap.className = 'dt-photo-thumb';
    var img = document.createElement('img');
    var rd = new FileReader();
    rd.onload = function(ev){ img.src = ev.target.result; };
    rd.readAsDataURL(f);
    wrap.appendChild(img);
    var b = document.createElement('div');
    b.className = 'dt-photo-thumb-badge';
    b.textContent = '#'+(idx+1);
    wrap.appendChild(b);
    var rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'dt-photo-thumb-remove';
    rm.textContent = '×';
    rm.onclick = function(ev){
      ev.preventDefault(); ev.stopPropagation();
      window.DT_PHOTO_BUFFER.splice(idx, 1);
      dtRenderPhotoBuffer();
    };
    wrap.appendChild(rm);
    list.appendChild(wrap);
  });
  list.classList.add('has-items');
  if(btnT) btnT.textContent = '+ Добавить ещё фото (сейчас '+window.DT_PHOTO_BUFFER.length+')';
}
window.dtRenderPhotoBuffer = dtRenderPhotoBuffer;

// ── Keyboard helpers ───────────────────────────────────────────────
function _isTA(el){ return el && el.tagName === 'TEXTAREA'; }
function _getV(el){
  if(!el) return '';
  if(_isTA(el)) return el.value || '';
  if(typeof el.getValue === 'function') return el.getValue('latex') || '';
  return el.value || '';
}
function _setV(el, v){
  if(!el) return;
  if(_isTA(el)) el.value = v;
  else if(typeof el.setValue === 'function') el.setValue(v);
  else el.value = v;
}
function _insertAt(el, text){
  if(_isTA(el)){
    var s = typeof el.selectionStart === 'number' ? el.selectionStart : el.value.length;
    var e = typeof el.selectionEnd === 'number' ? el.selectionEnd : el.value.length;
    el.value = el.value.substring(0,s) + text + el.value.substring(e);
    var p = s + text.length;
    try{ el.setSelectionRange(p,p); }catch(_){}
  } else {
    _setV(el, _getV(el) + text);
  }
}

function dtKbInsert(text){
  if(!_dtKbActiveField) _dtKbActiveField = document.getElementById('dt-user-answer');
  if(!_dtKbActiveField) return;
  try{
    if(_isTA(_dtKbActiveField) && text === '\\quad ') text = '\n';
    _insertAt(_dtKbActiveField, text);
    if(_dtKbActiveField.focus) _dtKbActiveField.focus();
    _dtKbActiveField.dispatchEvent(new Event('input', { bubbles:true }));
  } catch(e){ console.warn('dtKbInsert', e); }
}
window.dtKbInsert = dtKbInsert;

function dtKbBackspace(){
  if(!_dtKbActiveField) _dtKbActiveField = document.getElementById('dt-user-answer');
  if(!_dtKbActiveField) return;
  try{
    if(_isTA(_dtKbActiveField)){
      var el = _dtKbActiveField;
      var s = typeof el.selectionStart === 'number' ? el.selectionStart : el.value.length;
      var e = typeof el.selectionEnd === 'number' ? el.selectionEnd : el.value.length;
      if(s === e && s > 0){
        el.value = el.value.substring(0, s-1) + el.value.substring(e);
        try{ el.setSelectionRange(s-1, s-1); }catch(_){}
      } else if(s !== e){
        el.value = el.value.substring(0, s) + el.value.substring(e);
        try{ el.setSelectionRange(s, s); }catch(_){}
      }
      el.focus();
      el.dispatchEvent(new Event('input', { bubbles:true }));
      return;
    }
    var cur = _getV(_dtKbActiveField);
    if(cur && cur.length){
      _setV(_dtKbActiveField, cur.slice(0,-1));
      if(_dtKbActiveField.focus) _dtKbActiveField.focus();
      _dtKbActiveField.dispatchEvent(new Event('input', { bubbles:true }));
    }
  } catch(e){ console.warn('dtKbBackspace', e); }
}
window.dtKbBackspace = dtKbBackspace;

function dtToggleKeyboard(){
  var kb = document.getElementById('dt-keyboard');
  var btn = document.getElementById('dt-kb-toggle-btn');
  if(!kb) return;
  var open = kb.classList.toggle('open');
  if(btn) btn.classList.toggle('active', open);
  if(open && _dtKbActiveField && _dtKbActiveField.focus){
    try{ _dtKbActiveField.focus(); }catch(_){}
  }
}
window.dtToggleKeyboard = dtToggleKeyboard;

function dtSwitchKbTab(name){
  var tabs = document.querySelectorAll('.dt-modal-body .dt-kb-tab');
  var lays = document.querySelectorAll('.dt-modal-body .dt-kb-layout');
  for(var i=0;i<tabs.length;i++) tabs[i].classList.remove('active');
  for(var j=0;j<lays.length;j++) lays[j].classList.remove('active');
  var t = document.querySelector('.dt-modal-body .dt-kb-tab[data-tab="'+name+'"]');
  var l = document.getElementById('dt-kb-layout-'+name);
  if(t) t.classList.add('active');
  if(l) l.classList.add('active');
}
window.dtSwitchKbTab = dtSwitchKbTab;

function dtSubmitCurrent(){
  var f = document.getElementById('dt-answer-form');
  if(f) f.dispatchEvent(new Event('submit', { cancelable:true }));
}
window.dtSubmitCurrent = dtSubmitCurrent;

// ── autoMathify (как в adaptive_test_simple) ────────────────────────
function dtAutoMathify(raw){
  if(!raw) return raw;
  var PR = [];
  function protect(s, re){
    return s.replace(re, function(m){
      PR.push(m);
      return '\u0001'+(PR.length-1)+'\u0001';
    });
  }
  var s = String(raw);
  s = protect(s, /\$\$[\s\S]+?\$\$/g);
  s = protect(s, /\$[^\n$]+?\$/g);
  s = protect(s, /\\\([\s\S]+?\\\)/g);
  s = protect(s, /\\\[[\s\S]+?\\\]/g);
  s = s.replace(/(\\(?:frac|sqrt|cdot|sum|prod|int|lim|left|right|binom|gcd|overline|underline|vec|hat|bar|tilde|dot|ddot|pmod|bmod|geq|leq|neq|approx|equiv|times|div|pm|infty|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|phi|omega)(?:\{[^{}]*\})*)/g,
    function(m){ PR.push('\\('+m+'\\)'); return '\u0001'+(PR.length-1)+'\u0001'; });
  s = s.replace(/([A-Za-zА-Яа-я0-9])\^(\{[^{}]+\}|-?\d+|[A-Za-z])/g,
    function(m, base, exp){
      var e = exp.charAt(0) === '{' ? exp : '{'+exp+'}';
      PR.push('\\('+base+'^'+e+'\\)');
      return '\u0001'+(PR.length-1)+'\u0001';
    });
  s = s.replace(/([A-Za-z])_(\{[^{}]+\}|\d+|[A-Za-z])/g,
    function(m, base, idx){
      var i = idx.charAt(0) === '{' ? idx : '{'+idx+'}';
      PR.push('\\('+base+'_'+i+'\\)');
      return '\u0001'+(PR.length-1)+'\u0001';
    });
  s = s.replace(/([A-Za-zа-яА-Я0-9])([²³⁴⁵⁶⁷⁸⁹⁰¹])/g, function(m, base, sup){
    var map = { '²':'2','³':'3','⁴':'4','⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9','⁰':'0','¹':'1' };
    PR.push('\\('+base+'^{'+map[sup]+'}\\)');
    return '\u0001'+(PR.length-1)+'\u0001';
  });
  s = s.replace(/\u0001(\d+)\u0001/g, function(m, i){ return PR[parseInt(i,10)] || m; });
  return s;
}
window.dtAutoMathify = dtAutoMathify;

function _renderKatexSafe(el){
  if(window.renderMathInElement){
    try{
      window.renderMathInElement(el, {
        delimiters: window._dtKatexDelimiters || [
          {left:'$$', right:'$$', display:true},
          {left:'$',  right:'$',  display:false},
          {left:'\\(', right:'\\)', display:false},
          {left:'\\[', right:'\\]', display:true}
        ],
        throwOnError: false
      });
    } catch(_){}
  }
}

// ── openTaskModal — рендер карточки задачи ─────────────────────────
function openTaskModal(item, index){
  var overlay = document.getElementById('dt-modal-overlay');
  var title   = document.getElementById('dt-modal-title');
  var body    = document.getElementById('dt-modal-body');
  if(!overlay || !body) return;
  if(title) title.textContent = 'Задача '+(index+1)+' · '+(item.subtopic || '');
  overlay.classList.remove('dt-hidden');
  window.DT_PHOTO_BUFFER = [];
  _dtKbActiveField = null;

  var done = (item.user_answer !== null && item.user_answer !== undefined);
  var h = '';
  h += '<div class="dt-task-card">';
  h += '<div class="dt-task-meta">';
  h += '<span class="dt-difficulty-badge">⭐ Уровень: '+(item.difficulty || '?')+'/5</span>';
  if(item.subtopic) h += '<span class="dt-topic-chip">📚 '+_esc(item.subtopic)+'</span>';
  if(item.is_flagged) h += '<span class="dt-topic-chip" style="background:rgba(239,68,68,0.18);border-color:rgba(239,68,68,0.4);color:#fca5a5;">⚠️ Флаг</span>';
  h += '</div>';
  h += '<div class="dt-task-section-title">📋 Условие:</div>';
  h += '<div class="dt-task-text-html" id="dt-task-text-html">'+(item.task_text || '')+'</div>';

  if(done){
    var vc = item.is_correct ? 'success' : 'error';
    var vi = item.is_correct ? '✅' : '❌';
    var vt = item.is_correct ? 'Верно!' : 'Неверно';
    h += '<div class="dt-result-block show">';
    h += '<div class="dt-verdict '+vc+'">'+vi+' '+vt+'</div>';
    if(item.correct_answer){
      h += '<div class="dt-feedback-block"><div class="dt-feedback-title">📝 Правильный ответ:</div>';
      h += '<div class="dt-feedback-text"><code>'+escapeHtmlPreserveLatex(item.correct_answer)+'</code></div></div>';
      // Если ответ был не принят — напомним требования к формату.
      if(!item.is_correct){
        h += _buildAnswerFormatHint(item.correct_answer);
      }
    }
    if(item.solution){
      h += '<div class="dt-feedback-block"><div class="dt-feedback-title">📖 Эталонное решение:</div>';
      h += '<div class="dt-feedback-text">'+item.solution+'</div></div>';
    }
    h += '</div>';
    h += '</div>';
    body.innerHTML = h;
    if(typeof renderMath === 'function') renderMath(body);
    window.dtCurrentItemId = item.id;
    overlay.classList.add('dt-open');
    return;
  }

  // ── AI-решение (превью) — показываем сразу при открытии ──
  h += '<div id="dt-ai-loader" class="dt-ai-loader">';
  h += '<div class="dt-ai-spinner"></div>';
  h += '<div class="dt-ai-text-main">🤖 AI решает задачу...</div>';
  h += '<div class="dt-ai-text-sub">Это может занять 5–10 секунд</div>';
  h += '</div>';

  // Блок для решения от AI-тьютора (превью)
  h += '<div id="dt-result-block" class="dt-result-block" style="display:none">';
  h += '<div id="dt-verdict"></div>';
  h += '<div class="dt-feedback-block">';
  h += '<div class="dt-feedback-title">📖 Разбор от AI-тьютора:</div>';
  h += '<div id="dt-feedback-text" class="dt-feedback-text"></div>';
  h += '</div>';
  h += '</div>';

  // ── Форма для ответа ученика (скрыта, пока AI не решит) ──
  h += '<form id="dt-answer-form" style="display:none" enctype="multipart/form-data" autocomplete="off">';
  h += _buildAnswerFormatHint(item.correct_answer);
  h += '<div class="dt-solve-prompt">🤖 AI решил задачу. <strong>Теперь давай финальное идельное решение</strong></div>';
  h += '<label class="dt-field-label">✏️ Ваш ответ <span class="dt-field-label-extra">(можно писать доказательство!)</span></label>';
  h += '<math-field id="dt-user-answer" class="dt-math-field" virtual-keyboard-mode="manual" virtual-keyboard-theme="material"></math-field>';
  h += '<p class="dt-field-hint">💡 Нажмите «🔢» справа внизу поля для матклавиатуры (√, дроби, степени). Если задача — доказать утверждение, пишите доказательство прямо здесь или в поле ниже.</p>';
  h += '<label class="dt-field-label">📝 Ход решения / доказательство <span class="dt-field-label-extra">(опционально)</span></label>';
  h += '<textarea id="dt-solution-text" class="dt-solution-textarea" rows="6" placeholder="Пишите решение или доказательство по шагам, каждый шаг — с новой строки. Можно вставлять формулы: \\frac{1}{2}, x^2, \\sqrt{3} и т.д."></textarea>';
  h += '<p class="dt-field-hint">💡 Пишите <strong>по шагам</strong> — каждое действие или логический переход с новой строки. Формулы можно вставлять через «⌨️ Клавиатуру» ниже.</p>';
  h += '<div class="dt-kb-wrapper">';
  h += '<button type="button" id="dt-kb-toggle-btn" class="dt-kb-toggle" onclick="dtToggleKeyboard()">⌨️ Клавиатура</button>';
  h += '<div id="dt-keyboard" class="dt-keyboard">';
  h += '<div class="dt-kb-header">';
  h += '<span class="dt-kb-field-label"><span class="dot"></span><span id="dt-kb-field-name">Ответ</span></span>';
  h += '<button type="button" class="dt-kb-close" onclick="dtToggleKeyboard()">✕</button>';
  h += '</div>';
  h += '<div class="dt-kb-tabs">';
  h += '<button type="button" class="dt-kb-tab active" data-tab="math" onclick="dtSwitchKbTab(\'math\')">🔢 Математическая</button>';
  h += '<button type="button" class="dt-kb-tab" data-tab="regular" onclick="dtSwitchKbTab(\'regular\')">⌨️ Обычная</button>';
  h += '</div>';
  h += '<div id="dt-kb-layout-math" class="dt-kb-layout active">'+_buildMath()+'</div>';
  h += '<div id="dt-kb-layout-regular" class="dt-kb-layout">'+_buildRegular()+'</div>';
  h += '</div>';
  h += '</div>';
  h += '<div class="dt-photo-block">';
  h += '<label class="dt-field-label">📸 Фото решения из тетради (можно несколько, опционально):</label>';
  h += '<input type="file" id="dt-photo-input" accept="image/*" capture="environment" multiple style="display:none;">';
  h += '<button type="button" class="dt-photo-btn" onclick="document.getElementById(\'dt-photo-input\').click()">';
  h += '<span style="font-size:22px;">📷</span><span id="dt-photo-btn-text">Сфотографировать / Загрузить решение</span>';
  h += '</button>';
  h += '<div id="dt-photo-preview-list" class="dt-photo-preview-list"></div>';
  h += '<p class="dt-field-hint">💡 Нажимайте кнопку повторно, чтобы <strong>добавить</strong> ещё фото. Каждое распознаётся отдельно и подмешивается в решение для AI-тьютора.</p>';
  h += '</div>';
  h += '<div class="dt-actions">';
  h += '<button type="submit" id="dt-submit-btn" class="dt-btn dt-btn-primary">📤 Отправить ответ</button>';
  h += '<button type="button" class="dt-btn dt-btn-hint" onclick="getHint(\''+item.id+'\')">💡 Подсказка</button>';
  h += '</div>';
  h += '<div id="dt-hint-container"></div>';
  h += '</form>';
  h += '</div>';

  body.innerHTML = h;
  overlay.classList.add('dt-open');
  window.dtCurrentItemId = item.id;
  window.dtCurrentCorrectAnswer = item.correct_answer || '';

  var taskTextEl = document.getElementById('dt-task-text-html');
  if(taskTextEl && typeof renderMath === 'function') renderMath(taskTextEl);

  _bindForm(item);
  _dtSolveOnOpen(item);
}
window.openTaskModal = openTaskModal;

// ── _dtSolveOnOpen — AI решает задачу при открытии модалки ────────
function _dtSolveOnOpen(item){
  var loader = document.getElementById('dt-ai-loader');
  var rb = document.getElementById('dt-result-block');
  var verdict = document.getElementById('dt-verdict');
  var fb = document.getElementById('dt-feedback-text');
  var form = document.getElementById('dt-answer-form');
  if(!loader || !rb || !form) return;

  // Показываем loader
  loader.classList.add('show');

  fetch('/daily_tasks/'+item.id+'/solve', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': (typeof getCsrfToken === 'function' ? getCsrfToken() : '')
    },
    body: JSON.stringify({})
  })
  .then(function(r){ return r.json(); })
  .then(function(data){
    loader.classList.remove('show');

    if(data.status === 'success' && data.solution){
      var sol = data.solution;
      // Показываем решение в блоке результата
      if(verdict){
        verdict.innerHTML = '<div class="dt-verdict info">🤖 AI-разбор:</div>';
      }
      if(fb){
        sol = dtAutoMathify(sol);
        sol = sol.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
        fb.innerHTML = sol;
        _renderKatexSafe(fb);
        // Заменяем \n на <br> ПОСЛЕ KaTeX, чтобы не сломать LaTeX-окружения
        fb.innerHTML = fb.innerHTML.replace(/\n/g, '<br>');
      }
      rb.style.display = '';
      rb.classList.add('show');
    } else {
      // Решения нет — просто скрываем loader, показываем форму
      if(verdict){
        verdict.innerHTML = '';
      }
    }

    // Показываем форму для ответа ученика
    form.style.display = '';
  })
  .catch(function(err){
    console.error('_dtSolveOnOpen error:', err);
    loader.classList.remove('show');
    // Всё равно показываем форму
    form.style.display = '';
  });
}

// ── _bindForm ─────────────────────────────────────────────────────
function _bindForm(item){
  var KA = 'dt_answer_'+item.id;
  var KS = 'dt_solution_'+item.id;
  var mf = document.getElementById('dt-user-answer');
  if(mf){
    try{
      if(mf.setOptions){
        mf.setOptions({
          virtualKeyboardMode: 'manual',
          virtualKeyboardTheme: 'material',
          smartFence: true,
          smartMode: true
        });
      }
    } catch(_){}
    try{ var sa = localStorage.getItem(KA); if(sa) mf.setValue(sa); }catch(_){}
    mf.addEventListener('input', function(){
      try{ localStorage.setItem(KA, mf.getValue('latex') || ''); }catch(_){}
    });
  }
  var ta = document.getElementById('dt-solution-text');
  if(ta){
    try{ var ss = localStorage.getItem(KS); if(ss) ta.value = ss; }catch(_){}
    ta.addEventListener('input', function(){
      try{ localStorage.setItem(KS, ta.value || ''); }catch(_){}
    });
  }
  var pi = document.getElementById('dt-photo-input');
  if(pi){
    pi.addEventListener('change', function(e){
      var newFiles = Array.from(e.target.files || []);
      for(var i=0;i<newFiles.length;i++){
        if(window.DT_PHOTO_BUFFER.length >= DT_MAX_PHOTOS){
          alert('Можно прикрепить не больше '+DT_MAX_PHOTOS+' фото.');
          break;
        }
        var f = newFiles[i];
        var dup = window.DT_PHOTO_BUFFER.some(function(p){
          return p.name === f.name && p.size === f.size;
        });
        if(!dup) window.DT_PHOTO_BUFFER.push(f);
      }
      e.target.value = '';
      dtRenderPhotoBuffer();
    });
  }
  document.addEventListener('focusin', _focusHandler, false);
  var form = document.getElementById('dt-answer-form');
  if(form){
    form.addEventListener('submit', function(e){
      e.preventDefault();
      submitAnswer(item.id, KA, KS);
    });
  }
}

function _focusHandler(e){
  var el = e.target;
  if(el && (el.id === 'dt-user-answer' || el.id === 'dt-solution-text')){
    _dtKbActiveField = el;
  } else if(el && el.closest){
    var mf = el.closest('math-field');
    if(mf && mf.id === 'dt-user-answer') _dtKbActiveField = mf;
  }
  var label = document.getElementById('dt-kb-field-name');
  if(label && _dtKbActiveField){
    label.textContent = (_dtKbActiveField.id === 'dt-user-answer') ? 'Ответ' : 'Решение';
  }
}

// ── submitAnswer ───────────────────────────────────────────────────
function submitAnswer(itemId, KA, KS){
  var mf = document.getElementById('dt-user-answer');
  var ta = document.getElementById('dt-solution-text');
  var userAnswer = '';
  if(mf && typeof mf.getValue === 'function'){
    userAnswer = mf.getValue('latex') || '';
  } else if(mf){
    userAnswer = mf.value || '';
  }
  userAnswer = (userAnswer || '').trim();
  var userSolution = (ta ? (ta.value || '') : '').trim();
  if(!userAnswer){
    alert('Пожалуйста, введите ответ!');
    return;
  }

  var encodePhotos = Promise.resolve([]);
  if(window.DT_PHOTO_BUFFER && window.DT_PHOTO_BUFFER.length){
    encodePhotos = (function(){
      var out = [];
      var chain = Promise.resolve();
      window.DT_PHOTO_BUFFER.forEach(function(f){
        chain = chain.then(function(){
          return _compressImage(f).then(_fileToBase64).then(function(b64){ out.push(b64); });
        });
      });
      return chain.then(function(){ return out; });
    })();
  }

  _dtShowLoader();
  encodePhotos.then(function(images){
    var payload = {
      user_answer: userAnswer,
      user_solution: userSolution,
      solution_image_b64: images[0] || '',
      solution_images_b64: images,
      time_spent_seconds: 0
    };
    return fetch('/daily_tasks/'+itemId+'/submit_ai', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': (typeof getCsrfToken === 'function' ? getCsrfToken() : '')
      },
      body: JSON.stringify(payload)
    });
  }).then(function(r){
    return r.json().then(function(j){ return { ok:r.ok, body:j }; });
  }).then(function(res){
    _dtHideLoader();
    if(!res.ok || res.body.status === 'error'){
      var msg = (res.body && res.body.message) || 'Ошибка проверки';
      alert(msg);
      return;
    }
    _dtShowResult(res.body);
    // Clear localStorage drafts on success
    try{ if(KA) localStorage.removeItem(KA); if(KS) localStorage.removeItem(KS); }catch(_){}
  }).catch(function(err){
    console.error('submit error:', err);
    _dtHideLoader();
    alert('Ошибка соединения с сервером. Попробуйте ещё раз.');
  });
}
window.submitAnswer = submitAnswer;

function _dtShowLoader(){
  var form = document.getElementById('dt-answer-form');
  var loader = document.getElementById('dt-ai-loader');
  var btn = document.getElementById('dt-submit-btn');
  if(form) form.style.display = 'none';
  if(loader) loader.classList.add('show');
  if(btn) btn.disabled = true;
}
function _dtHideLoader(){
  var loader = document.getElementById('dt-ai-loader');
  if(loader) loader.classList.remove('show');
}

function _dtShowResult(result){
  var rb = document.getElementById('dt-result-block');
  var verdict = document.getElementById('dt-verdict');
  var fb = document.getElementById('dt-feedback-text');
  if(!rb || !verdict || !fb) return;

  var score = (typeof result.score === 'number') ? result.score : 0;
  var html = '';
  var isWrong = false;
  if(score === 2){
    html = '<div class="dt-verdict success">✅ Верно! Отличная работа</div>';
  } else if(score === 1){
    html = '<div class="dt-verdict partial">⚠️ Частично верно</div>';
  } else if(score === 0){
    html = '<div class="dt-verdict partial">ℹ️ Ответ принят</div>';
  } else {
    html = '<div class="dt-verdict error">❌ Неверно</div>';
    isWrong = true;
  }

  // Если ответ неверный — дополнительно показываем правильный ответ
  // и требования к формату записи, чтобы ученик мог сравнить.
  var correct = (result && result.correct_answer) || window.dtCurrentCorrectAnswer || '';
  if(isWrong && correct){
    html += '<div class="dt-feedback-block"><div class="dt-feedback-title">📝 Правильный ответ:</div>';
    html += '<div class="dt-feedback-text"><code>' + escapeHtmlPreserveLatex(correct) + '</code></div></div>';
    html += _buildAnswerFormatHint(correct);
  }
  verdict.innerHTML = html;

  var feedback = result.feedback || '';
  feedback = dtAutoMathify(feedback);
  feedback = feedback.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
  fb.innerHTML = feedback;
  _renderKatexSafe(fb);
  // Заменяем \n на <br> ПОСЛЕ KaTeX, чтобы не сломать LaTeX-окружения
  fb.innerHTML = fb.innerHTML.replace(/\n/g, '<br>');

  rb.classList.add('show');
}

// ── getHint ────────────────────────────────────────────────────────
function getHint(itemId){
  var container = document.getElementById('dt-hint-container');
  if(!container) return;
  container.innerHTML = '<div class="dt-hint-box">⏳ Загрузка подсказки…</div>';
  fetch('/daily_tasks/'+itemId+'/hint')
    .then(function(r){
      if(!r.ok) return r.json().then(function(e){ throw new Error(e.message || 'Ошибка'); });
      return r.json();
    })
    .then(function(d){
      var t = d.hint || d.text || 'Подсказка недоступна';
      container.innerHTML = '<div class="dt-hint-box"><strong>💡 Подсказка:</strong><br>'+t+'</div>';
      if(typeof renderMath === 'function') renderMath(container);
    })
    .catch(function(err){
      container.innerHTML = '<div class="dt-hint-box">⚠️ '+_esc(err.message)+'</div>';
    });
}
window.getHint = getHint;

})();
