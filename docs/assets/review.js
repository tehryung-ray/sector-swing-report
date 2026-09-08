/* 복기 페이지 렌더러. docs/data/review.json 하나만 읽는다. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const el = (t, c, x) => {
    const n = document.createElement(t);
    if (c) n.className = c;
    if (x != null) n.textContent = x;
    return n;
  };
  const pct = (v, d = 2) => (v == null ? "-" : (v > 0 ? "+" : "") + Number(v).toFixed(d) + "%");
  const cls = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
  const won = (n) => (n == null ? "-" : Number(n).toLocaleString("ko-KR") + "원");

  function kpi(items) {
    const g = el("div", "kpi");
    items.forEach(([k, v, s]) => {
      const d = el("div");
      d.appendChild(el("div", "k", k));
      d.appendChild(el("div", "v", v));
      if (s) d.appendChild(el("div", "s", s));
      g.appendChild(d);
    });
    return g;
  }

  function tradeRow(t) {
    const box = el("div", "trow");
    const h = el("div", "trow-h");
    h.appendChild(el("span", "d", t.report_date));
    h.appendChild(el("span", "n", t.name));
    if (t.setup_label) h.appendChild(el("span", "st", t.setup_label));
    if (t.fill !== "filled") {
      h.appendChild(el("span", "st", t.fill_label.split(" (")[0]));
    } else {
      const c = t.pending ? "open" : (t.ret_pct > 0 ? "win" : "loss");
      h.appendChild(el("span", "st " + c, t.status_label));
      const r = el("span", "r " + cls(t.ret_pct));
      r.textContent = pct(t.ret_pct);
      h.appendChild(r);
    }
    box.appendChild(h);

    const b = el("div", "trow-b");
    if (t.fill === "filled") {
      b.textContent = "체결 " + won(t.fill_px) + " · 손절 " + won(t.stop)
        + " · 1차 " + won(t.tp1) + " · 2차 " + won(t.tp2)
        + (t.pending ? " · " + t.days + "일차 보유 중 (현재 " + won(t.last_px) + ")"
                     : " · " + t.days + "일 만에 종료");
    } else if (t.fill === "cancelled") {
      b.textContent = "시가 " + won(t.open_px) + "가 손절가 " + won(t.stop)
        + " 아래로 열려 주문을 취소했습니다.";
    } else if (t.fill === "not_filled") {
      b.textContent = "저가 " + won(t.low_px) + "까지만 내려와 진입가 "
        + won(t.entry) + "에 닿지 않았습니다.";
    } else {
      b.textContent = "진입가 " + won(t.entry) + " · 결과는 다음 거래일에 확인됩니다.";
    }
    box.appendChild(b);

    if (t.legs && t.legs.length) {
      const l = el("div", "trow-legs");
      t.legs.forEach((g) => l.appendChild(el("span", null,
        g.day + "일차 " + g.what + " " + Math.round(g.qty * 100) + "% @ " + won(g.px))));
      box.appendChild(l);
    }
    return box;
  }

  function barTable(rows, valKey, labelKey, extraHead) {
    const max = Math.max.apply(null, rows.map((r) => Math.abs(r[valKey])).concat([0.01]));
    const t = el("table", "tbl bars");
    rows.forEach((r) => {
      const tr = el("tr");
      tr.appendChild(el("td", null, r[labelKey]));
      const bd = el("td", "bar");
      const bar = el("div", "b" + (r[valKey] < 0 ? " neg" : ""));
      bar.style.width = (Math.abs(r[valKey]) / max * 100) + "%";
      bd.appendChild(bar);
      tr.appendChild(bd);
      const v = el("td", "n " + cls(r[valKey]));
      v.textContent = pct(r[valKey]);
      tr.appendChild(v);
      tr.appendChild(el("td", "n", String(r.n) + "건"));
      if (extraHead) {
        const w = r.win_rate != null ? r.win_rate : r.up_rate;
        tr.appendChild(el("td", "n", w + "%"));
      }
      t.appendChild(tr);
    });
    return t;
  }

  function render(d) {
    $("#meta").textContent = "생성 " + d.generated_at_kst.replace("T", " ").slice(0, 16) + " KST";

    // --- 실제 추천 기록 ---
    const L = d.live.stats;
    const liveBox = $("#live");
    liveBox.innerHTML = "";
    if (!L.n) {
      liveBox.appendChild(el("div", "empty-sm", "아직 기록이 없습니다."));
    } else {
      liveBox.appendChild(kpi([
        ["추천", L.n + "건", d.live.since ? d.live.since + "부터" : ""],
        ["체결", L.fill_rate == null ? "-" : L.fill_rate + "%", L.filled + "건"],
        ["승률", L.win_rate == null ? "-" : L.win_rate + "%", "종료 " + L.closed + "건"],
        ["평균 손익", L.avg_ret == null ? "-" : pct(L.avg_ret),
         L.stopped ? "손절 " + L.stopped + "건" : ""],
      ]));
      if (L.waiting) {
        liveBox.appendChild(el("div", "banner note",
          L.waiting + "건은 아직 장이 열리지 않아 결과를 확인할 수 없습니다. "
          + "체결률·승률 계산에서는 제외했습니다."));
      }
      d.live.trades.forEach((t) => liveBox.appendChild(tradeRow(t)));
    }

    // --- 보유 중 / 대기 중 ---
    const open = d.live.open || [];
    const waiting = d.live.waiting || [];
    $("#open-cnt").textContent = open.length ? open.length + "건" : "";
    const ob = $("#open");
    ob.innerHTML = "";
    if (open.length) {
      open.forEach((t) => ob.appendChild(tradeRow(t)));
    } else {
      ob.appendChild(el("div", "empty-sm", "보유 중인 포지션이 없습니다."));
    }
    $("#wait-cnt").textContent = waiting.length ? waiting.length + "건" : "";
    const wt = $("#waiting");
    wt.innerHTML = "";
    if (waiting.length) {
      wt.appendChild(el("p", "lead",
        "주문을 걸어둔 종목입니다. 체결 여부는 다음 거래일에 확인됩니다."));
      waiting.forEach((t) => wt.appendChild(tradeRow(t)));
      $("#waiting-sec").hidden = false;
    } else {
      $("#waiting-sec").hidden = true;
    }

    // --- 대전제 검증 ---
    const P = d.premise;
    const pb = $("#premise");
    pb.innerHTML = "";
    pb.appendChild(el("p", "lead",
      "미국 섹터 신호별로, 연결된 한국 ETF가 이후 " + P.days
      + "거래일 동안 실제로 어떻게 움직였는지입니다. 이 전략 전체가 "
      + "“미국에서 강한 섹터가 다음날 한국으로 이어진다”는 가정 위에 있어, "
      + "그 가정이 지금도 살아있는지 확인하는 지표입니다."));
    if (P.by_signal && P.by_signal.length) {
      const card = el("div", "g-card");
      card.appendChild(barTable(P.by_signal, "avg", "label", true));
      pb.appendChild(card);
      pb.appendChild(el("div", "callout " + (P.holds ? "info" : "danger"),
        P.holds
          ? "강한 상승 섹터가 하락세 섹터보다 " + pct(P.strong_minus_weak)
            + "p 앞섭니다. 전제가 유지되고 있습니다."
          : "강한 상승과 하락세의 차이가 " + pct(P.strong_minus_weak)
            + "p입니다. 전제가 흔들리고 있어 전략을 재검토해야 합니다."));
    } else {
      pb.appendChild(el("div", "empty-sm", "표본이 부족합니다."));
    }

    // --- 관망 점검 ---
    const wb = $("#watch");
    wb.innerHTML = "";
    const W = d.watch.by_reason || [];
    wb.appendChild(el("p", "lead",
      "관망한 종목이 이후 " + d.watch.days + "거래일 동안 어떻게 움직였는지입니다. "
      + "수치가 낮을수록 거르길 잘한 것이고, 높으면 그 기준이 기회를 버리고 있다는 신호입니다."));
    if (!W.length) {
      wb.appendChild(el("div", "empty-sm", "아직 집계할 관망 기록이 없습니다."));
    } else {
      const c = el("div", "g-card");
      c.appendChild(barTable(W, "avg", "reason", true));
      wb.appendChild(c);
    }

    // --- 백테스트 참고 ---
    const B = d.backtest.stats;
    const bb = $("#bt");
    bb.innerHTML = "";
    bb.appendChild(el("div", "bt-note",
      "⚠ 아래는 실제 추천 기록이 아닙니다. " + d.backtest.since
      + " 이후 구간을 같은 로직으로 재현한 결과이며 참고용입니다."));
    if (!B.n) {
      bb.appendChild(el("div", "empty-sm", "데이터가 없습니다."));
    } else {
      bb.appendChild(kpi([
        ["신호", B.n + "건", d.backtest.since + "~"],
        ["체결", B.fill_rate + "%", B.filled + "건"],
        ["승률", B.win_rate + "%", "종료 " + B.closed + "건"],
        ["평균 손익", pct(B.avg_ret), "손절 " + B.stopped + "건"],
        ["평균 이익", pct(B.avg_win), ""],
        ["평균 손실", pct(B.avg_loss), ""],
      ]));
    }
  }

  fetch("data/review.json?t=" + Date.now())
    .then((r) => { if (!r.ok) throw new Error("review.json (" + r.status + ")"); return r.json(); })
    .then(render)
    .catch((e) => { $("#meta").textContent = "복기 데이터를 불러오지 못했습니다: " + e.message; });
})();
