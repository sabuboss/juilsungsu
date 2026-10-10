/* 기도문 상세: 전체 복사(본문만) · 공유 · 글씨 크기. (SPEC 9.2 동작 세부) */
(function () {
  var SIZES = [18, 20, 24, 28];
  var KEY = "prayer-fs";

  function toast(m) {
    var t = document.getElementById("toast");
    if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
    t.textContent = m; t.className = "toast show";
    clearTimeout(t._tm); t._tm = setTimeout(function () { t.className = "toast"; }, 1800);
  }

  function bodyText() {
    var ps = document.querySelectorAll("#prayer p");
    return Array.prototype.map.call(ps, function (p) { return p.textContent.trim(); }).join("\n\n");
  }

  function copyText(text, done) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { legacy(text, done); });
    } else legacy(text, done);
  }
  function legacy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.top = "-1000px";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("복사하지 못했습니다. 본문을 직접 선택해 주세요."); }
    document.body.removeChild(ta);
  }

  // 글씨 크기: localStorage 에 기억 (실패해도 기본값으로 동작)
  function getFs() { try { var v = parseInt(localStorage.getItem(KEY), 10); if (SIZES.indexOf(v) >= 0) return v; } catch (e) {} return 20; }
  function setFs(v) { document.documentElement.style.setProperty("--fs", v + "px"); try { localStorage.setItem(KEY, String(v)); } catch (e) {} }
  var fs = getFs(); setFs(fs);

  document.getElementById("btn-copy").addEventListener("click", function () {
    copyText(bodyText(), function () { toast("복사되었습니다"); });
  });

  var sh = document.getElementById("btn-share");
  sh.addEventListener("click", function () {
    var url = sh.getAttribute("data-url") || location.href.split("#")[0];
    var title = sh.getAttribute("data-title") || document.title;
    if (navigator.share) {
      navigator.share({ title: title, text: title, url: url }).catch(function () {});
    } else {
      copyText(url, function () { toast("링크가 복사되었습니다"); });
    }
  });

  Array.prototype.forEach.call(document.querySelectorAll("[data-fs]"), function (b) {
    b.addEventListener("click", function () {
      var i = SIZES.indexOf(fs);
      i = b.getAttribute("data-fs") === "+" ? Math.min(i + 1, SIZES.length - 1) : Math.max(i - 1, 0);
      fs = SIZES[i]; setFs(fs); toast("글씨 " + fs + "px");
    });
  });
})();
