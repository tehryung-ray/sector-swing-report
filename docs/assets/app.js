/* 섹터 스윙 리포트 렌더러. 데이터는 docs/data/*.json 이 전부다. */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const el = (t, cls, txt) => {
    const n = document.createElement(t);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  };
  const won = (n) => (n == null ? "-" : Number(n).toLocaleString("ko-KR") + "원");
  const sign = (n) => (n > 0 ? "+" : "") + Number(n).toFixed(2) + "%";
  const cls = (n) => (n > 0 ? "pos" : n < 0 ? "neg" : "");
  const isMobile = () => window.matchMedia("(max-width: 640px)").matches;

  /* 종목 링크. URL 패턴이 바뀌면 파이썬 links.py 와 여기만 고치면 된다. */
  function linkRow(p) {
    const box = el("div", "links");
    const naver = el("a", "naver", "네이버증권");
    naver.href = isMobile() ? p.links.naver_m : p.links.naver_pc;
    const toss = el("a", "toss", "토스증권");
    toss.href = p.links.toss;
    [naver, toss].forEach((a) => {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      box.appendChild(a);
    });
    return box;
  }

  function priceTable(p) {
    const t = el("table", "px");
    const row = (label, val, delta, rowCls) => {
      const tr = el("tr", rowCls);
      tr.appendChild(el("td", null, label));
      const v = el("td", "v", won(val));
      tr.appendChild(v);
      const d = el("td", "d " + (delta == null ? "" : cls(delta)));
      d.textContent = delta == null ? "" : sign(delta);
      tr.appendChild(d);
      return tr;
    };
    t.appendChild(row("전일 종가", p.last_close, null));
    t.appendChild(row("진입 (지정가)", p.entry, p.entry_vs_last_pct, "entry"));
    t.appendChild(row("1차 익절", p.tp1, p.tp1_pct));
    t.appendChild(row("2차 익절", p.tp2, p.tp2_pct));
    t.appendChild(row("손절", p.stop, p.stop_pct));
    return t;
  }

  function newsBlock(p, disclaimer) {
    if (!p.issues || !p.issues.length) return null;
    const box = el("div", "news");
    const s = p.issue_summary || {};
    const via = (s.classifier || "").startsWith("gemini") ? "AI 분류" : "키워드 분류";
    box.appendChild(el("div", "news-h",
      `섹터 이슈 · 긍정 ${s.positive || 0} / 부정 ${s.negative || 0} / 중립 ${s.neutral || 0} · ${via} · 참고용`));
    const ul = el("ul");
    p.issues.forEach((n) => {
      const li = el("li");
      const tag = el("span", "tone " + n.tone, n.tone_label);
      li.appendChild(tag);
      const a = el("a", null, n.title);
      a.href = n.link; a.target = "_blank"; a.rel = "noopener noreferrer";
      li.appendChild(a);
      if (n.source) li.appendChild(el("span", "src", " · " + n.source));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    box.title = disclaimer || "";
    return box;
  }


  /* ---- 수량 계산기 ----
     손실 감당 금액에서 수량을 역산한다. "얼마어치 살까"가 아니라
     "틀렸을 때 얼마까지 잃어도 되나"에서 출발하므로, 손절폭이 좁은 종목은
     많이 넓은 종목은 적게 사게 되어 종목마다 위험이 같아진다.

     값은 메모리에만 있다. 저장하지 않으므로 새로고침하면 사라진다. */
  let riskAmount = 0;
  const calcs = [];                       // {input, render} - 카드 간 입력 동기화용
  const PRESETS = [100000, 200000, 300000, 500000, 1000000];
  const manwon = (n) => (n % 10000 === 0 ? `${n / 10000}만` : n.toLocaleString("ko-KR"));

  function syncCalcs(source) {
    calcs.forEach((c) => {
      if (c.input !== source) c.input.value = riskAmount ? riskAmount.toLocaleString("ko-KR") : "";
      c.render();
    });
  }

  function calcBlock(p) {
    const risk = p.entry - p.stop;        // 1주당 위험폭
    const box = el("div", "calc");

    const head = el("div", "calc-h");
    head.appendChild(el("b", null, "수량 계산기"));
    head.appendChild(document.createTextNode(
      `1주당 위험 ${won(risk)} (진입 ${p.entry.toLocaleString("ko-KR")} − 손절 ${p.stop.toLocaleString("ko-KR")})`));
    box.appendChild(head);

    const field = el("div", "calc-field");
    const input = el("input");
    input.type = "text";
    input.inputMode = "numeric";
    input.placeholder = "손실 감당 금액";
    input.setAttribute("aria-label", `${p.name} 손실 감당 금액`);
    if (riskAmount) input.value = riskAmount.toLocaleString("ko-KR");
    field.appendChild(input);
    field.appendChild(el("span", "unit", "원"));
    box.appendChild(field);

    const pre = el("div", "calc-pre");
    PRESETS.forEach((v) => {
      const b = el("button", null, manwon(v));
      b.type = "button";
      b.addEventListener("click", () => {
        riskAmount = v;
        input.value = v.toLocaleString("ko-KR");
        render();
        syncCalcs(input);
      });
      pre.appendChild(b);
    });
    box.appendChild(pre);

    const out = el("div", "calc-out");
    box.appendChild(out);

    function render() {
      out.innerHTML = "";
      if (!riskAmount) {
        out.appendChild(el("div", "calc-note",
          "감당할 손실 금액을 넣으면 수량이 나옵니다. 보통 전체 자금의 0.5~1%로 잡습니다. 저장되지 않습니다."));
        return;
      }
      if (risk <= 0) {
        out.appendChild(el("div", "calc-warn", "위험폭을 계산할 수 없습니다."));
        return;
      }
      const qty = Math.floor(riskAmount / risk);
      if (qty < 1) {
        out.appendChild(el("div", "calc-warn",
          `1주도 살 수 없습니다. 이 종목은 최소 ${won(risk)} 이상이 필요합니다.`));
        return;
      }
      const cost = qty * p.entry;
      const maxLoss = qty * risk;
      const half = Math.floor(qty / 2);
      const profit = half * (p.tp1 - p.entry) + (qty - half) * (p.tp2 - p.entry);

      const t = el("table");
      const row = (label, val, cls) => {
        const tr = el("tr", cls);
        tr.appendChild(el("td", null, label));
        tr.appendChild(el("td", "v", val));
        t.appendChild(tr);
      };
      row("수량", `${qty.toLocaleString("ko-KR")}주`, "calc-qty");
      row("필요 자금", won(cost));
      row("손절 시 손실", `−${won(maxLoss).replace("원", "")}원`);
      row("목표 달성 시 수익", `+${won(profit).replace("원", "")}원`);
      out.appendChild(t);
      out.appendChild(el("div", "calc-note",
        `수익은 1차에서 ${half.toLocaleString("ko-KR")}주, 2차에서 ${(qty - half).toLocaleString("ko-KR")}주를 판 경우입니다. 수수료·세금은 빠져 있습니다.`));
    }

    input.addEventListener("input", () => {
      const digits = input.value.replace(/[^0-9]/g, "");
      riskAmount = digits ? parseInt(digits, 10) : 0;
      input.value = riskAmount ? riskAmount.toLocaleString("ko-KR") : "";
      render();
      syncCalcs(input);
    });

    calcs.push({ input, render });
    render();
    return box;
  }

  function pickCard(p, disclaimer) {
    const c = el("div", "card");

    const top = el("div", "card-top");
    const left = el("div");
    left.appendChild(el("div", "nm", p.name));
    left.appendChild(el("span", "code", p.code));
    top.appendChild(left);
    top.appendChild(el("div", "spacer"));
    const chips = el("div", "chips");
    chips.appendChild(el("span", "chip setup", p.setup_label));
    chips.appendChild(el("span", "chip " + p.signal, p.signal_label));
    top.appendChild(chips);
    c.appendChild(top);

    c.appendChild(el("div", "from",
      `미국 ${p.us_name} (${p.us_ticker}) 20일 ${sign(p.us_r20)} · 20일선 이격 ${sign(p.ext_pct)}`));

    c.appendChild(el("div", "howto", p.setup_howto));
    c.appendChild(priceTable(p));

    c.appendChild(el("div", "sub",
      `손익비 ${p.rr}\u2003목표근거 ${p.target_basis}\u2003거래대금 ${p.turnover_eok}억\u2003돌파참고선 ${won(p.breakout_ref)}`));
    c.appendChild(el("div", "cancel",
      `⚠ 시가가 ${won(p.cancel_below)} 아래로 열리면 예약주문을 취소하세요. 진입가 위로 갭상승하면 체결되지 않으니 추격하지 마세요.`));

    c.appendChild(linkRow(p));
    c.appendChild(calcBlock(p));
    const nb = newsBlock(p, disclaimer);
    if (nb) c.appendChild(nb);
    return c;
  }

  function heatmap(sectors) {
    const g = el("div", "heat");
    sectors.forEach((s) => {
      const cell = el("div", "hcell");
      cell.appendChild(el("div", "t", s.name));
      const r = el("div", "r " + cls(s.r20));
      r.textContent = sign(s.r20);
      cell.appendChild(r);
      cell.appendChild(el("div", "s", `${s.ticker} · ${s.signal_label}`));
      const a = Math.min(Math.abs(s.r20) / 12, 1) * 0.16;
      cell.style.background = s.r20 > 0
        ? `rgba(217,43,43,${a})` : `rgba(31,111,208,${a})`;
      g.appendChild(cell);
    });
    return g;
  }

  function watchList(rows) {
    const d = el("details", "watch");
    const sm = el("summary", null, `관망 ${rows.length}종목`);
    d.appendChild(sm);
    rows.forEach((w) => {
      const r = el("div", "wrow");
      const n = el("div", "wn", `${w.name} ${w.setup_label ? "· " + w.setup_label : ""}`);
      r.appendChild(n);
      r.appendChild(el("div", "wr", (w.reasons || []).join(" · ")));
      d.appendChild(r);
    });
    return d;
  }

  function render(d) {
    $("#title").textContent = `${d.report_date} 섹터 스윙 리포트`;
    $("#meta").innerHTML =
      `미국 <b>${d.us_asof}</b> 종가 · 한국 <b>${d.kr_asof}</b> 종가 기준` +
      `<br>생성 ${d.generated_at_kst.replace("T", " ").slice(0, 16)} KST`;

    const banners = $("#banners");
    banners.innerHTML = "";
    if (d.freshness.status !== "ok") {
      const b = el("div", "banner " + (d.freshness.status === "failed" ? "err" : "warn"),
        "⚠ " + d.freshness.message + " 주문 전 반드시 실제 시세를 확인하세요.");
      banners.appendChild(b);
    }
    banners.appendChild(el("div", "banner note",
      "본 페이지는 정보 제공 목적이며 투자 권유가 아닙니다. 모든 수치는 과거 시세로 계산한 기술적 참고값이고, 투자 판단과 그 결과의 책임은 이용자 본인에게 있습니다."));

    const h = $("#headline");
    h.innerHTML = "";
    h.appendChild(document.createTextNode(d.headline));
    h.appendChild(el("span", "regime",
      `시장 국면: ${d.market_regime.label} · ${d.market_regime.note}`));

    const picks = $("#picks");
    picks.innerHTML = "";
    calcs.length = 0;                     // 이전 리포트의 계산기 참조 제거
    if (!d.picks.length) {
      picks.appendChild(el("div", "empty",
        "오늘은 진입 조건을 만족하는 종목이 없습니다. 관망이 가장 좋은 매매입니다."));
    } else {
      d.picks.forEach((p) => picks.appendChild(pickCard(p, d.issue_disclaimer)));
    }
    $("#picks-cnt").textContent = `${d.picks.length}종목`;

    $("#heat").replaceChildren(heatmap(d.us_sectors));
    $("#watch").replaceChildren(watchList(d.watch));
    $("#issue-disc").textContent = d.issue_disclaimer || "";
  }

  async function load(date) {
    const f = date ? `data/${date}.json` : "data/latest.json";
    const r = await fetch(`${f}?t=${Date.now()}`);
    if (!r.ok) throw new Error(`${f} (${r.status})`);
    render(await r.json());
  }

  async function initArchive() {
    try {
      const r = await fetch("data/archive.json?t=" + Date.now());
      const { dates } = await r.json();
      const sel = $("#archive");
      dates.forEach((dt, i) => {
        const o = el("option", null, dt + (i === 0 ? " (최신)" : ""));
        o.value = dt;
        sel.appendChild(o);
      });
      sel.addEventListener("change", () => load(sel.value).catch(showErr));
      $("#archive-sec").hidden = dates.length < 2;
    } catch { $("#archive-sec").hidden = true; }
  }

  function showErr(e) {
    $("#banners").innerHTML = "";
    $("#banners").appendChild(el("div", "banner err",
      "리포트를 불러오지 못했습니다: " + e.message));
  }

  load().catch(showErr);
  initArchive();
})();
