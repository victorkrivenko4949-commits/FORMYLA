/**
 * FORMYLA.net — виджет «Поделиться с другом» ОТКЛЮЧЁН.
 * Скрипт удаляет все кнопки .share-friend-btn, плавающую кнопку и модалку,
 * включая добавленные динамически.
 */
(function () {
  'use strict';
  var SEL = '.share-friend-btn, #shareFriendFab, #shareFriendOverlay';
  var st = document.createElement('style');
  st.textContent = SEL + '{display:none !important;}';
  (document.head || document.documentElement).appendChild(st);
  function purge(root) {
    (root || document).querySelectorAll(SEL).forEach(function (el) { el.remove(); });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { purge(); });
  } else { purge(); }
  try {
    new MutationObserver(function () { purge(); })
      .observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
  window.openShareWithFriend = function () {};
  window.ShareWithFriend = { open: function () {}, bind: function () {} };
})();
