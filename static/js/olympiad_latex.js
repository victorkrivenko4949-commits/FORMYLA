// === ДОПОЛНИТЕЛЬНЫЙ ПРОХОД KaTeX ===
// Догоняет формулы в динамически добавленном контенте
document.addEventListener('DOMContentLoaded', function() {
  if (typeof renderMathInElement !== 'undefined') {
    document.querySelectorAll('.katex-content').forEach(function(el) {
      renderMathInElement(el, {
        delimiters: [
          {left: '$$',  right: '$$',  display: true},
          {left: '$',   right: '$',   display: false},
          {left: '\\[', right: '\\]', display: true},
          {left: '\\(', right: '\\)', display: false}
        ],
        throwOnError: false,
        strict: false,
        trust: true,
        macros: {
          '\\N': '\\mathbb{N}',
          '\\Z': '\\mathbb{Z}',
          '\\Q': '\\mathbb{Q}',
          '\\R': '\\mathbb{R}',
          '\\floor': '\\left\\lfloor #1 \\right\\rfloor',
          '\\ceil':  '\\left\\lceil  #1 \\right\\rceil',
          '\\abs':   '\\left| #1 \\right|'
        }
      });
    });
  }
});

// === PRINT / PDF ===
function printOlymp() {
  window.print();
}

// === SHARE ===
function shareOlymp() {
  if (navigator.share) {
    navigator.share({
      title: document.title,
      url: window.location.href,
    });
  } else {
    navigator.clipboard
      .writeText(window.location.href)
      .then(function() {
        var btn = document.querySelector('.btn-share');
        if (btn) {
          btn.textContent = '[OK] Ссылка скопирована!';
          setTimeout(function() { btn.textContent = ' Поделиться'; }, 2000);
        }
      });
  }
}

// === PREVIEW ФОТО ===
function previewPhoto(input, taskNum) {
  var preview = document.getElementById('preview-' + taskNum);
  if (!input.files || !input.files[0]) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    preview.innerHTML =
      '<div class="preview-wrap">' +
        '<img src="' + e.target.result + '"' +
             ' alt="Фото решения ' + taskNum + '"' +
             ' style="max-width:100%;border-radius:12px;margin-top:10px;">' +
        '<button type="button" class="remove-photo"' +
                ' onclick="removePhoto(' + taskNum + ')">' +
          ' Удалить фото' +
        '</button>' +
      '</div>';
  };
  reader.readAsDataURL(input.files[0]);
}

function removePhoto(taskNum) {
  document.getElementById('solution_' + taskNum).value = '';
  document.getElementById('preview-' + taskNum).innerHTML = '';
}
