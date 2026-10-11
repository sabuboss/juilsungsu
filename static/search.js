/* 검색: 빌드 시 만든 /search-index.json 을 받아 브라우저에서 찾는다. 서버 없음. */
(function () {
  var q = document.getElementById("q"), out = document.getElementById("results"), empty = document.getElementById("empty");
  var idx = null;
  var ORD = { "첫째": "1", "둘째": "2", "셋째": "3", "넷째": "4", "다섯째": "5" };

  function norm(s) {
    s = (s || "").toLowerCase().replace(/\s+/g, " ").trim();
    s = s.replace(/(첫째|둘째|셋째|넷째|다섯째)\s*주(일)?/g, function (_, o) { return ORD[o] + "주"; });
    s = s.replace(/(\d)\s*주일/g, "$1주");
    return s;
  }
  function hay(p) {
    return norm([p.t, p.o, p.d, p.c, p.g, p.s, p.w, p.x, (p.tags || []).join(" ")].join(" "));
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function render(list) {
    out.innerHTML = list.slice(0, 40).map(function (p) {
      return '<a class="card" href="' + esc(p.u) + '"><span class="chips"><span class="chip">' + esc(p.s) + '</span><span class="chip">' + esc(p.w) + '</span>' +
        (p.g ? '<span class="chip">' + esc(p.g) + '</span>' : '') + '</span><b>' + esc(p.t) + '</b>' + (p.o ? '<span class="occ">' + esc(p.o) + '</span>' : '') + '<small>' + esc(p.d || "날짜 없음 · 상시") + '</small></a>';
    }).join("");
    empty.hidden = list.length > 0;
  }

  function search() {
    if (!idx) return;
    var terms = norm(q.value).split(" ").filter(Boolean);
    if (!terms.length) { render(idx.slice(0, 20)); empty.hidden = true; return; }
    var scored = [];
    idx.forEach(function (p) {
      var h = p._h || (p._h = hay(p)), score = 0;
      for (var i = 0; i < terms.length; i++) { if (h.indexOf(terms[i]) < 0) return; score += (norm(p.t).indexOf(terms[i]) >= 0 ? 2 : 1); }
      scored.push([score, p]);
    });
    scored.sort(function (a, b) { return b[0] - a[0] || (b[1].d > a[1].d ? 1 : -1); });
    render(scored.map(function (x) { return x[1]; }));
  }

  fetch("/search-index.json").then(function (r) { return r.json(); }).then(function (d) {
    idx = d; var init = new URLSearchParams(location.search).get("q"); if (init) q.value = init; search();
  });
  q.addEventListener("input", search);
})();
