(() => {
  const form = document.getElementById("filters");
  const dateFrom = document.getElementById("dateFrom");
  const dateTo = document.getElementById("dateTo");
  const presetsEl = document.getElementById("presets");
  const status = document.getElementById("status");
  const btnRefresh = document.getElementById("btnRefresh");

  const charts = {};
  let activePreset = "month";
  const fmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });
  const fmt0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const fmt1 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

  // Цвета фракций и бригад приходят из API (FRACTION_COLORS в db.py) — одинаковые во всех блоках
  const C = {
    ink: "#233255", muted: "#6b7a99", grid: "#e2e8f3",
    blue: "#5082e6", cyan: "#5ad2ff", green: "#22a06b", yellow: "#fabe00", red: "#e62d32",
  };
  const BULK_COLOR = "#b4bdd0";
  const colorOf = (item) => (item && item.color) || "#7c8aa0";

  Chart.defaults.font.family = '"Inter", "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = C.muted;
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: C.ink, titleColor: "#fff", bodyColor: "#e6ebf6",
    padding: 10, cornerRadius: 8, boxPadding: 4,
  });

  function setStatus(text, isError = false) {
    status.textContent = text;
    status.classList.toggle("error", isError);
    status.hidden = !text;
  }

  function iso(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function formatRu(isoDate) {
    return new Date(isoDate + "T00:00:00").toLocaleDateString("ru-RU");
  }
  const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  function monthShort(monthKey) {
    const [y, m] = (monthKey || "").split("-");
    return MONTHS_SHORT[Number(m) - 1] ? `${MONTHS_SHORT[Number(m) - 1]} ${y}` : monthKey;
  }
  function dayShort(isoDate) {
    const [, m, d] = (isoDate || "").split("-");
    return m && d ? `${d}.${m}` : isoDate;
  }
  function plural(n, one, few, many) {
    const n10 = n % 10, n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return one;
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
    return many;
  }

  function rangeForPreset(preset, anchor = new Date()) {
    const y = anchor.getFullYear();
    const m = anchor.getMonth();
    if (preset === "year") return { from: new Date(y, 0, 1), to: new Date(y, 11, 31) };
    if (preset === "quarter") {
      const q0 = Math.floor(m / 3) * 3;
      return { from: new Date(y, q0, 1), to: new Date(y, q0 + 3, 0) };
    }
    if (preset === "week") {
      const day = (anchor.getDay() + 6) % 7;
      const from = new Date(y, m, anchor.getDate() - day);
      return { from, to: new Date(from.getFullYear(), from.getMonth(), from.getDate() + 6) };
    }
    return { from: new Date(y, m, 1), to: new Date(y, m + 1, 0) };
  }
  function presetName(p) {
    return { week: "Неделя", month: "Месяц", quarter: "Квартал", year: "Год", custom: "Период" }[p] || "Период";
  }
  function setPresetActive(preset) {
    activePreset = preset;
    presetsEl.querySelectorAll(".preset").forEach((b) => b.classList.toggle("active", b.dataset.preset === preset));
    document.getElementById("dates").classList.toggle("custom", preset === "custom");
  }
  function applyPreset(preset) {
    const { from, to } = rangeForPreset(preset);
    dateFrom.value = iso(from);
    dateTo.value = iso(to);
    setPresetActive(preset);
  }

  function money(rub) {
    const a = Math.abs(rub);
    if (a >= 1_000_000) return `${fmt1.format(rub / 1_000_000)} млн ₽`;
    if (a >= 1_000) return `${fmt0.format(Math.round(rub / 1000))} тыс ₽`;
    return `${fmt0.format(Math.round(rub))} ₽`;
  }
  function destroyChart(key) {
    if (charts[key]) { charts[key].destroy(); charts[key] = null; }
  }
  function setPeriod(root, period) {
    root.querySelectorAll("[data-period]").forEach((el) => { el.textContent = period; });
  }

  const AUTO_SHIFT_TAGS = new Set(["БПВ", "ББА"]);
  function realShiftCount(rows) {
    const docs = new Set();
    rows.forEach((r) => { if (!AUTO_SHIFT_TAGS.has((r.tag || "").trim())) docs.add(`${r.date}|${r.number}`); });
    return docs.size;
  }

  function paintKpis(k, rows, period) {
    const block = document.getElementById("kpis");
    block.hidden = false;
    setPeriod(block, period);
    document.querySelector('[data-kpi="production"]').textContent = `${fmt1.format(k.production_t)} т`;
    const shifts = rows && rows.length ? realShiftCount(rows) : k.shift_count;
    document.querySelector('[data-kpi-cap="production"]').textContent =
      `${fmt0.format(shifts)} ${plural(shifts, "смена", "смены", "смен")} за период`;
    document.querySelector('[data-kpi="shipped"]').textContent = `${fmt1.format(k.shipped_t)} т`;
    document.querySelector('[data-kpi-cap="shipped"]').textContent = `${fmt0.format(k.trip_count)} рейсов по весам`;
    document.querySelector('[data-kpi="sold"]').textContent = money(k.sold_rub);
    document.querySelector('[data-kpi-cap="sold"]').textContent = `${fmt1.format(k.sold_tons)} т за период`;
    document.getElementById("chipAvg").textContent = k.sold_tons ? `${fmt0.format(k.sold_rub / k.sold_tons)} ₽/т` : "—";
    document.querySelector('[data-kpi="shrink"]').textContent = `${fmt1.format(k.shrink_pct)}%`;
    const kg = k.shrink_kg;
    document.querySelector('[data-kpi-cap="shrink"]').innerHTML =
      `<span class="${kg < 0 ? "neg" : ""}">${fmt0.format(Math.round(kg))} кг</span> ≈ ${money(k.shrink_rub || 0)}`;
  }

  // Временный список россыпных фракций — пока признак «хранится россыпью» не отдают в API
  const BULK_FRACTIONS = new Set(["Стекло", "Макулатура", "Металл", "Перо"]);
  function brigadeTotals(rows) {
    const by = new Map();
    rows.forEach((r) => {
      if (BULK_FRACTIONS.has(r.nomenclature)) return;
      const cur = by.get(r.brigade) || { kg: 0, shifts: new Set() };
      cur.kg += r.quantity;
      cur.shifts.add(`${r.date}|${r.number}`);
      by.set(r.brigade, cur);
    });
    return [...by.entries()]
      .map(([name, v]) => ({ name, kg: v.kg, shifts: v.shifts.size, perShift: v.shifts.size ? v.kg / v.shifts.size : 0 }))
      .sort((a, b) => b.perShift - a.perShift);
  }

  const axisX = (extra = {}) => ({ ticks: { color: C.muted }, grid: { color: C.grid }, border: { display: false }, ...extra });
  const dashedLegend = (text) => ({
    text, fillStyle: "transparent", strokeStyle: C.yellow, lineWidth: 2, lineDash: [6, 4], fontColor: C.ink,
  });

  function paintSelection(s, period, rows) {
    const block = document.getElementById("blockSelection");
    block.hidden = false;
    setPeriod(block, period);
    const days = (s && s.days) || [];
    const has = days.some((d) => d.arrived_kg || d.selected_kg);
    document.getElementById("pickArrived").textContent = `${fmt1.format(s.arrived_t || 0)} т`;
    document.getElementById("pickSelected").textContent = `${fmt1.format(s.selected_t || 0)} т`;
    document.getElementById("pickPct").textContent = s.pct == null ? "—" : `${fmt1.format(s.pct)}%`;

    // Россыпь по дням — из строк смен: она попадает в смены в день отгрузки
    const bulkByDay = new Map();
    rows.forEach((r) => {
      if (BULK_FRACTIONS.has(r.nomenclature)) bulkByDay.set(r.date, (bulkByDay.get(r.date) || 0) + r.quantity);
    });
    const bulkOf = (d) => Math.min(bulkByDay.get(d.date) || 0, d.selected_kg || 0);
    const bulkTotal = days.reduce((a, d) => a + bulkOf(d), 0);
    document.getElementById("pickSelectedCap").textContent =
      `Отобрано · из них россыпь ${fmt1.format(bulkTotal / 1000)} т`;
    const partPct = (kg, d) => (d.arrived_kg ? (kg / d.arrived_kg) * 100 : null);

    const empty = document.getElementById("pickEmpty");
    const canvas = document.getElementById("chartSelection");
    destroyChart("selection");
    if (!has) { empty.hidden = false; canvas.parentElement.hidden = true; return; }
    empty.hidden = true;
    canvas.parentElement.hidden = false;
    const pcts = days.map((d) => d.pct).filter((v) => v != null).sort((a, b) => a - b);
    const mid = Math.floor(pcts.length / 2);
    const medianPct = pcts.length ? (pcts.length % 2 ? pcts[mid] : (pcts[mid - 1] + pcts[mid]) / 2) : null;
    charts.selection = new Chart(canvas, {
      type: "bar",
      data: {
        labels: days.map((d) => dayShort(d.date)),
        datasets: [
          { label: "тюки", data: days.map((d) => partPct(d.selected_kg - bulkOf(d), d)), backgroundColor: C.blue, hoverBackgroundColor: "#3f6fd0", barPercentage: 0.72, stack: "s", order: 1 },
          { label: "россыпь", data: days.map((d) => partPct(bulkOf(d), d)), backgroundColor: BULK_COLOR, hoverBackgroundColor: "#8f9bb5", borderRadius: { topLeft: 5, topRight: 5 }, barPercentage: 0.72, stack: "s", order: 1 },
          { type: "line", stack: "median", data: days.map(() => medianPct), borderColor: C.yellow, borderDash: [6, 4], pointRadius: 0, borderWidth: 2, order: 0 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: {
            align: "end", onClick: () => {},
            labels: {
              boxWidth: 14,
              generateLabels: () => [
                { text: "тюки", fillStyle: C.blue, strokeStyle: C.blue, lineWidth: 0, fontColor: C.ink },
                { text: "россыпь", fillStyle: BULK_COLOR, strokeStyle: BULK_COLOR, lineWidth: 0, fontColor: C.ink },
                ...(medianPct != null ? [dashedLegend(`медиана ${fmt1.format(medianPct)}%`)] : []),
              ],
            },
          },
          tooltip: {
            mode: "index", intersect: false,
            displayColors: false,
            filter: (item) => item.datasetIndex === 0,
            callbacks: {
              title: (items) => formatRu(days[items[0].dataIndex].date),
              label: (c) => {
                const d = days[c.dataIndex];
                const bulk = bulkOf(d);
                const pct = (kg) => (d.arrived_kg ? ` (${fmt1.format((kg / d.arrived_kg) * 100)}%)` : "");
                const lines = [
                  `Приехало ${fmt1.format(d.arrived_kg / 1000)} т`,
                  `Тюки ${fmt1.format((d.selected_kg - bulk) / 1000)} т${pct(d.selected_kg - bulk)}`,
                  `Россыпь ${fmt1.format(bulk / 1000)} т${pct(bulk)}`,
                  `Процент отбора ${d.pct == null ? "—" : fmt1.format(d.pct) + "%"}`,
                ];
                if (medianPct != null) lines.push(`Медиана периода ${fmt1.format(medianPct)}%`);
                return lines;
              },
            },
          },
        },
        scales: {
          x: axisX({ stacked: true, ticks: { color: C.muted, maxRotation: 0, autoSkip: true }, grid: { display: false } }),
          y: axisX({ stacked: true, ticks: { color: C.muted, callback: (v) => `${fmt1.format(v)}%` }, title: { display: true, text: "процент отбора", color: C.muted } }),
        },
      },
    });
  }

  function paintProduction(p, period, rows) {
    const block = document.getElementById("blockProduction");
    block.hidden = false;
    setPeriod(block, period);
    document.getElementById("prodNote").textContent = p.note || "";

    const empty = document.getElementById("prodEmpty");
    const canvas = document.getElementById("chartProdDays");
    destroyChart("prod");
    const totals = brigadeTotals(rows);
    const brigNote = document.getElementById("brigNote");
    if (totals.length >= 2 && totals[1].perShift > 0) {
      const diff = ((totals[0].perShift - totals[1].perShift) / totals[1].perShift) * 100;
      brigNote.textContent = `${totals[0].name} в среднем на ${fmt0.format(diff)}% выше за смену.`;
    } else {
      brigNote.textContent = "";
    }
    const brigadeColor = (name) => colorOf(p.brigades.find((b) => b.name === name));
    if (!totals.length) {
      empty.hidden = false; canvas.hidden = true;
    } else {
      empty.hidden = true; canvas.hidden = false;
      charts.prod = new Chart(canvas, {
        type: "bar",
        data: {
          labels: totals.map((t) => t.name),
          datasets: [{ data: totals.map((t) => t.perShift / 1000), backgroundColor: totals.map((t) => brigadeColor(t.name)), borderRadius: 6, barPercentage: 0.6 }],
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (c) => {
                  const t = totals[c.dataIndex];
                  return [
                    `${fmt1.format(t.perShift / 1000)} т за смену`,
                    `всего ${fmt1.format(t.kg / 1000)} т за ${t.shifts} ${plural(t.shifts, "смену", "смены", "смен")}`,
                  ];
                },
              },
            },
          },
          scales: {
            x: axisX({ beginAtZero: true, ticks: { color: C.muted, callback: (v) => `${fmt1.format(v)} т` } }),
            y: axisX({ ticks: { color: C.ink, font: { weight: 600 } }, grid: { display: false } }),
          },
        },
      });
    }

    const shiftCount = rows && rows.length ? realShiftCount(rows) : p.shift_count;
    const tb = document.getElementById("tbodyWorkshops");
    if (!p.workshops.length) {
      tb.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
    } else {
      tb.innerHTML =
        p.workshops.map((w) => `<tr><td>${w.name}</td><td class="num">${fmt.format(w.quantity)}</td><td class="num">${fmt1.format(w.share_pct)}%</td></tr>`).join("") +
        `<tr class="total"><td>Итого · ${fmt0.format(shiftCount)} ${plural(shiftCount, "смена", "смены", "смен")}</td>
         <td class="num">${fmt.format(p.total_kg)}</td><td class="num">100%</td></tr>`;
    }
  }

  function paintShrink(s, period) {
    const block = document.getElementById("blockShrink");
    block.hidden = false;
    setPeriod(block, period);

    const empty = document.getElementById("shrinkEmpty");
    const canvas = document.getElementById("chartShrinkTrips");
    destroyChart("shrink");
    if (!s.trips.length) {
      empty.hidden = false; canvas.hidden = true;
    } else {
      empty.hidden = true; canvas.hidden = false;
      let prevDay = "";
      const labels = s.trips.map((t) => {
        const day = dayShort(t.date);
        if (day === prevDay) return "";
        prevDay = day;
        return day;
      });
      const NORMAL = "rgba(80,130,230,.85)", MIXED = "rgba(250,190,0,.8)", ANOMALY = "rgba(230,45,50,.6)";
      charts.shrink = new Chart(canvas, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              data: s.trips.map((t) => t.shrink_pct),
              backgroundColor: s.trips.map((t) => (t.anomaly ? ANOMALY : t.mixed ? MIXED : NORMAL)),
              borderColor: s.trips.map((t) => (t.mixed ? "#d9a300" : "transparent")),
              borderWidth: s.trips.map((t) => (t.mixed ? 2 : 0)),
              borderRadius: 3,
            },
            { type: "line", data: labels.map(() => s.median_pct), borderColor: C.ink, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
          ],
        },
        options: {
          maintainAspectRatio: false, responsive: true,
          plugins: {
            legend: {
              align: "end", onClick: () => {},
              labels: {
                boxWidth: 14,
                generateLabels: () => [
                  { text: "обычный рейс", fillStyle: NORMAL, strokeStyle: NORMAL, lineWidth: 0, fontColor: C.ink },
                  { text: "несколько фракций", fillStyle: MIXED, strokeStyle: "#d9a300", lineWidth: 2, fontColor: C.ink },
                  { text: "расхождение больше 15%", fillStyle: ANOMALY, strokeStyle: ANOMALY, lineWidth: 0, fontColor: C.ink },
                  { text: `медиана ${fmt1.format(s.median_pct)}%`, fillStyle: "transparent", strokeStyle: C.ink, lineWidth: 1.5, lineDash: [6, 4], fontColor: C.ink },
                ],
              },
            },
            tooltip: {
              callbacks: {
                title: (items) => {
                  const t = s.trips[items[0].dataIndex];
                  return `${formatRu(t.date)} · отгрузка №${Number(t.number) || t.number}`;
                },
                label: (c) => {
                  if (c.dataset.type === "line") return `медиана ${fmt1.format(c.raw)}%`;
                  const t = s.trips[c.dataIndex];
                  const out = [
                    `Потеря: ${fmt1.format(t.shrink_pct)}% (${fmt0.format(t.shrink_kg)} кг)`,
                    `Тюки на складе: ${fmt0.format(t.bale_weight)} кг`,
                    `По весам на выезде: ${fmt0.format(t.scale_weight)} кг`,
                    `№ весы софт: ${t.vesy_soft_number || "—"}`,
                  ];
                  if (t.vehicle) out.push(`Машина: ${t.vehicle}`);
                  (t.fractions || []).forEach((f) => {
                    const scale = f.scale_kg != null ? f.scale_kg : f.kg;
                    const loss = f.shrink_kg != null ? f.shrink_kg : 0;
                    out.push(`${f.name}: бирки ${fmt0.format(f.kg)} кг, по весам ${fmt0.format(scale)} кг, потеря ${fmt0.format(loss)} кг`);
                  });
                  return out;
                },
              },
            },
          },
          scales: {
            x: axisX({
              ticks: { color: C.muted, maxRotation: 60, minRotation: 45, autoSkip: false },
              grid: { display: true, drawOnChartArea: true, offset: true, color: (ctx) => (labels[ctx.index] ? "#d5deed" : "transparent") },
            }),
            y: axisX({ min: -30, max: 30, ticks: { color: C.muted, callback: (v) => `${v}%` } }),
          },
        },
      });
    }

    const tb = document.getElementById("tbodyShrinkFrac");
    if (!s.by_fraction.length) {
      tb.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
    } else {
      tb.innerHTML =
        s.by_fraction.filter((f) => !BULK_FRACTIONS.has(f.name.trim())).map((f) => `<tr>
            <td><span class="name"><span class="dot" style="background:${colorOf(f)}"></span><span>${f.name}</span></span></td>
            <td class="num">${fmt1.format(f.trip_count)}</td>
            <td class="num">${fmt1.format(f.shrink_pct)}%</td></tr>`).join("") +
        `<tr class="total"><td>Все рейсы</td><td class="num">${fmt0.format(s.total.trip_count)}</td><td class="num">${fmt1.format(s.total.shrink_pct)}%</td></tr>`;
    }
  }

  function paintWarehouse(w) {
    document.getElementById("blockWarehouse").hidden = false;
    document.getElementById("chipWh").textContent = `${fmt1.format(w.total_kg / 1000)} т · ${money(w.total_rub)}`;
    const tb = document.getElementById("tbodyWarehouse");
    if (!w.rows.length) { tb.innerHTML = `<tr><td colspan="5">остатков нет</td></tr>`; return; }
    tb.innerHTML =
      w.rows.map((r) => {
        const col = colorOf(r);
        const sold = r.price_per_t > 0;
        const tip = sold
          ? `${fmt0.format(r.quantity_kg)} кг × ${fmt0.format(r.price_per_t)} ₽/т = ${fmt0.format(r.value_rub)} ₽ · ${fmt1.format(w.total_rub ? (r.value_rub / w.total_rub) * 100 : 0)}% стоимости склада`
          : "Фракцию ещё не продавали — цены нет, в стоимость склада не входит";
        return `<tr title="${tip}">
            <td><span class="name"><span class="dot" style="background:${col}"></span><span>${r.name}</span></span></td>
            <td class="num">${fmt.format(r.quantity_kg)}</td>
            <td style="white-space:nowrap"><span class="bar"><i style="width:${Math.min(r.share_pct, 100)}%;background:${col}"></i></span><span class="muted">${fmt1.format(r.share_pct)}%</span></td>
            <td class="num ${sold ? "" : "muted"}">${sold ? fmt0.format(r.price_per_t) : "—"}</td>
            <td class="num ${sold ? "" : "muted"}">${sold ? fmt0.format(r.value_rub) : "нет продаж"}</td></tr>`;
      }).join("") +
      `<tr class="total"><td>Итого на площадке</td><td class="num">${fmt.format(w.total_kg)}</td><td></td><td></td><td class="num">${fmt0.format(w.total_rub)}</td></tr>`;
  }

  function paintPrices(p) {
    document.getElementById("blockPrices").hidden = false;
    const empty = document.getElementById("pricesEmpty");
    const canvas = document.getElementById("chartPrices");
    destroyChart("prices");
    const tbLast = document.getElementById("tbodyLastPrice");
    if (!p.series.length || !p.months.length) {
      empty.hidden = false; canvas.hidden = true;
      tbLast.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
      return;
    }
    const lastOf = (s) => {
      for (let i = s.prices.length - 1; i >= 0; i--) if (s.prices[i] != null) return i;
      return -1;
    };
    const firstOf = (s) => s.prices.findIndex((v) => v != null);
    tbLast.innerHTML = p.series
      .map((s) => ({ s, li: lastOf(s), fi: firstOf(s) }))
      .filter((x) => x.li >= 0)
      .sort((a, b) => b.s.prices[b.li] - a.s.prices[a.li])
      .map(({ s, li, fi }) => {
        const ch = s.indexes[li] != null ? s.indexes[li] - 100 : null;
        const cls = ch > 0 ? "up" : ch < 0 ? "down" : "muted";
        const chText = ch == null ? "—" : `${ch > 0 ? "↑ +" : ch < 0 ? "↓ −" : ""}${fmt1.format(Math.abs(ch))}%`;
        const tip = `${monthShort(p.months[li])}: ${fmt0.format(s.prices[li])} ₽/т · ${monthShort(p.months[fi])}: ${fmt0.format(s.prices[fi])} ₽/т`;
        return `<tr title="${tip}">
          <td><span class="name"><span class="dot" style="background:${colorOf(s)}"></span><span>${s.name}</span></span></td>
          <td class="num">${fmt0.format(s.prices[li])}</td>
          <td class="num ${cls}">${chText}</td></tr>`;
      })
      .join("");
    empty.hidden = true; canvas.hidden = false;
    let multiPoint = false;
    const pctLabel = (index) => (index == null ? "—" : `${index - 100 >= 0 ? "+" : "−"}${fmt1.format(Math.abs(index - 100))}%`);
    charts.prices = new Chart(canvas, {
      type: "line",
      data: {
        labels: p.months.map(monthShort),
        datasets: p.series.map((s) => ({
          label: s.name, data: s.indexes, borderColor: colorOf(s), backgroundColor: colorOf(s),
          tension: 0, spanGaps: true, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: true },
        plugins: {
          legend: { position: "bottom", labels: { color: C.ink, boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 } },
          tooltip: {
            callbacks: {
              title: (items) => {
                multiPoint = items.length > 1;
                return multiPoint ? monthShort(p.months[items[0].dataIndex]) : p.series[items[0].datasetIndex].name;
              },
              label: (c) => {
                const s = p.series[c.datasetIndex];
                const price = s.prices[c.dataIndex];
                const text = `${price != null ? fmt0.format(price) + " ₽/т" : "—"} · ${pctLabel(c.raw)}`;
                return multiPoint ? `${s.name}: ${text}` : text;
              },
            },
          },
        },
        scales: {
          x: axisX(),
          y: axisX({ ticks: { color: C.muted, callback: (v) => pctLabel(v) }, title: { display: true, text: "изменение цены к первому месяцу", color: C.muted } }),
        },
      },
    });
  }

  function paintSales(s, period) {
    const block = document.getElementById("blockSales");
    block.hidden = false;
    setPeriod(block, period);

    const warn = document.getElementById("concWarn");
    if (s.concentration) {
      warn.hidden = false;
      warn.textContent = `Концентрация: ${s.concentration.name} — ${fmt1.format(s.concentration.share_pct)}% выручки (${money(s.concentration.rub)})`;
    } else {
      warn.hidden = true;
    }

    const empty = document.getElementById("salesEmpty");
    const canvas = document.getElementById("chartSalesFrac");
    destroyChart("sales");
    if (!s.by_fraction.length) {
      empty.hidden = false; canvas.hidden = true;
    } else {
      empty.hidden = true; canvas.hidden = false;
      charts.sales = new Chart(canvas, {
        type: "bar",
        data: {
          labels: s.by_fraction.map((f) => f.name),
          datasets: [{ data: s.by_fraction.map((f) => f.rub), backgroundColor: s.by_fraction.map((f) => colorOf(f)), borderRadius: 5, barPercentage: 0.75 }],
        },
        options: {
          maintainAspectRatio: false, indexAxis: "y", responsive: true, layout: { padding: { left: 6 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (c) => {
                  const f = s.by_fraction[c.dataIndex];
                  const lines = [`${fmt0.format(f.rub)} ₽ · ${fmt1.format(f.tons)} т`];
                  if (f.tons) lines.push(`средняя цена ${fmt0.format(f.rub / f.tons)} ₽/т`);
                  if (s.total_rub) lines.push(`${fmt1.format((f.rub / s.total_rub) * 100)}% выручки периода`);
                  return lines;
                },
              },
            },
          },
          scales: {
            x: axisX({ ticks: { color: C.muted, callback: (v) => money(v) } }),
            y: axisX({ ticks: { color: C.ink }, grid: { display: false } }),
          },
        },
      });
    }

    const tb = document.getElementById("tbodyBuyers");
    if (!s.buyers.length) {
      tb.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
    } else {
      tb.innerHTML = s.buyers.slice(0, 12).map((b) => `<tr class="${b.share_pct > 50 ? "hot" : ""}" title="${b.name.replace(/"/g, "&quot;")}: ${fmt0.format(b.rub)} ₽ · ${fmt1.format(b.share_pct)}% выручки">
            <td>${b.name}</td><td class="num">${fmt0.format(b.rub)}</td><td class="num">${fmt1.format(b.share_pct)}%</td></tr>`).join("");
    }
  }

  async function loadData() {
    const from = dateFrom.value;
    const to = dateTo.value;
    if (!from || !to) { setStatus("Укажите даты периода", true); return; }
    const period = `${presetName(activePreset)}: ${formatRu(from)} — ${formatRu(to)}`;
    setStatus(`Загрузка — ${period}…`);
    btnRefresh.disabled = true;

    try {
      const res = await fetch(`/api/data?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Ошибка API");

      btnRefresh.title = `Обновить данные · загружены ${new Date().toLocaleString("ru-RU")}`;

      paintKpis(data.kpis, data.rows || [], period);
      paintSelection(data.selection || {}, period, data.rows || []);
      paintProduction(data.production, period, data.rows || []);
      paintShrink(data.shrinkage, period);
      paintWarehouse(data.warehouse);
      paintPrices(data.prices);
      paintSales(data.sales, period);
      setStatus("");
    } catch (err) {
      ["kpis", "blockSelection", "blockProduction", "blockShrink", "blockWarehouse", "blockPrices", "blockSales"].forEach((id) => {
        document.getElementById(id).hidden = true;
      });
      setStatus(err.message || String(err), true);
    } finally {
      btnRefresh.disabled = false;
    }
  }

  presetsEl.addEventListener("click", (e) => {
    const b = e.target.closest(".preset");
    if (!b) return;
    applyPreset(b.dataset.preset);
    loadData();
  });
  // Свои даты применяются сразу, без отдельной кнопки
  function onManualDate() {
    setPresetActive("custom");
    if (dateFrom.value && dateTo.value && dateFrom.value <= dateTo.value) loadData();
  }
  dateFrom.addEventListener("change", onManualDate);
  dateTo.addEventListener("change", onManualDate);
  form.addEventListener("submit", (e) => { e.preventDefault(); loadData(); });
  btnRefresh.addEventListener("click", loadData);

  // Подсветка пункта меню: последний раздел, чей верх уже под закреплённой строкой
  const links = [...document.querySelectorAll("#nav a")];
  const targets = links.map((a) => document.querySelector(a.getAttribute("href")));
  function spy() {
    const line = document.querySelector(".topbar").offsetHeight + 24;
    let cur = 0;
    targets.forEach((t, i) => { if (t && !t.hidden && t.getBoundingClientRect().top <= line) cur = i; });
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) cur = links.length - 1;
    links.forEach((a, i) => a.classList.toggle("active", i === cur));
  }
  addEventListener("scroll", spy, { passive: true });
  addEventListener("resize", spy);

  applyPreset("month");
  // Ждём шрифт: иначе Chart.js меряет подписи осей другим шрифтом и обрезает их
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(loadData);
})();
