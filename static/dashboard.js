(() => {
  const form = document.getElementById("filters");
  const dateFrom = document.getElementById("dateFrom");
  const dateTo = document.getElementById("dateTo");
  const presetsEl = document.getElementById("presets");
  const status = document.getElementById("status");
  const btn = form.querySelector("button.btn");

  const charts = {};
  let activePreset = "month";
  const fmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });
  const fmt0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const fmt1 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

  function setStatus(text, isError = false) {
    status.textContent = text;
    status.classList.toggle("error", isError);
    status.hidden = !text; // при успешной загрузке строка не занимает место
  }

  function iso(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function formatRu(isoDate) {
    return new Date(isoDate + "T00:00:00").toLocaleDateString("ru-RU");
  }

  const MONTHS_DATIVE = [
    "январю", "февралю", "марту", "апрелю", "маю", "июню",
    "июлю", "августу", "сентябрю", "октябрю", "ноябрю", "декабрю",
  ];

  // «2025-10» → «октябрю 2025» — для подписи «+14% к октябрю 2025»
  function monthRu(monthKey) {
    if (!monthKey) return "первому месяцу";
    const [y, m] = monthKey.split("-");
    return `${MONTHS_DATIVE[Number(m) - 1] || monthKey} ${y}`;
  }

  const MONTHS_SHORT = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
  ];

  // «2025-10» → «окт 2025» — подпись оси
  function monthShort(monthKey) {
    const [y, m] = (monthKey || "").split("-");
    return MONTHS_SHORT[Number(m) - 1] ? `${MONTHS_SHORT[Number(m) - 1]} ${y}` : monthKey;
  }

  // «2026-09-01» → «01.09» — подпись оси
  function dayShort(isoDate) {
    const [, m, d] = (isoDate || "").split("-");
    return m && d ? `${d}.${m}` : isoDate;
  }

  function plural(n, one, few, many) {
    const n10 = n % 10;
    const n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return one;
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
    return many;
  }

  function rangeForPreset(preset, anchor = new Date()) {
    const y = anchor.getFullYear();
    const m = anchor.getMonth();
    if (preset === "year") {
      return { from: new Date(y, 0, 1), to: new Date(y, 11, 31) };
    }
    if (preset === "quarter") {
      const q0 = Math.floor(m / 3) * 3;
      return { from: new Date(y, q0, 1), to: new Date(y, q0 + 3, 0) };
    }
    if (preset === "week") {
      const day = (anchor.getDay() + 6) % 7; // пн = 0
      const from = new Date(y, m, anchor.getDate() - day);
      const to = new Date(from.getFullYear(), from.getMonth(), from.getDate() + 6);
      return { from, to };
    }
    // month
    return { from: new Date(y, m, 1), to: new Date(y, m + 1, 0) };
  }

  function presetName(p) {
    return { week: "Неделя", month: "Месяц", quarter: "Квартал", year: "Год", custom: "Период" }[p] || "Период";
  }

  function setPresetActive(preset) {
    activePreset = preset;
    presetsEl.querySelectorAll(".preset").forEach((b) => {
      b.classList.toggle("active", b.dataset.preset === preset);
    });
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
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  }

  // Смены с бирками БПВ и ББА — автоматические под россыпь, в число смен не входят.
  const AUTO_SHIFT_TAGS = new Set(["БПВ", "ББА"]);

  function realShiftCount(rows) {
    const docs = new Set();
    rows.forEach((r) => {
      if (!AUTO_SHIFT_TAGS.has((r.tag || "").trim())) docs.add(`${r.date}|${r.number}`);
    });
    return docs.size;
  }

  function paintKpis(k, rows) {
    document.getElementById("kpis").hidden = false;
    document.querySelector('[data-kpi="production"]').textContent = `${fmt1.format(k.production_t)} т`;
    const shifts = rows && rows.length ? realShiftCount(rows) : k.shift_count;
    document.querySelector('[data-kpi-cap="production"]').textContent =
      `${fmt0.format(shifts)} ${plural(shifts, "смена", "смены", "смен")} за период`;
    document.querySelector('[data-kpi="shipped"]').textContent = `${fmt1.format(k.shipped_t)} т`;
    document.querySelector('[data-kpi-cap="shipped"]').textContent =
      `${fmt0.format(k.trip_count)} рейсов по весам`;
    document.querySelector('[data-kpi="sold"]').textContent = money(k.sold_rub);
    document.querySelector('[data-kpi-cap="sold"]').textContent =
      `${fmt1.format(k.sold_tons)} т за период`;
    document.querySelector('[data-kpi="shrink"]').textContent = `${fmt1.format(k.shrink_pct)}%`;
    const kg = k.shrink_kg;
    const cls = kg < 0 ? "neg" : "";
    document.querySelector('[data-kpi-cap="shrink"]').innerHTML =
      `<span class="${cls}">${kg > 0 ? "" : ""}${fmt0.format(Math.round(kg))} кг</span>` +
      ` ≈ ${money(k.shrink_rub || 0)}`;
  }

  // Временный список россыпных фракций: в 1С у фракции есть признак «хранится россыпью»,
  // когда его отдадут в API — брать оттуда, а не по названию.
  const BULK_FRACTIONS = new Set(["Стекло", "Макулатура", "Металл", "Перо"]);

  // Выработка бригад за период без россыпи: её вес делится между бригадами поровну
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
      .map(([name, v]) => ({ name, kg: v.kg, shifts: v.shifts.size }))
      .sort((a, b) => b.kg - a.kg);
  }

  function paintSelection(s, period) {
    const block = document.getElementById("blockSelection");
    block.hidden = false;
    block.querySelectorAll("[data-period]").forEach((el) => {
      el.textContent = period;
    });
    const days = (s && s.days) || [];
    const has = days.some((d) => d.arrived_kg || d.selected_kg);
    document.getElementById("pickArrived").textContent = `${fmt1.format(s.arrived_t || 0)} т`;
    document.getElementById("pickSelected").textContent = `${fmt1.format(s.selected_t || 0)} т`;
    document.getElementById("pickPct").textContent =
      s.pct == null ? "—" : `${fmt1.format(s.pct)}%`;

    const empty = document.getElementById("pickEmpty");
    const canvas = document.getElementById("chartSelection");
    destroyChart("selection");
    if (!has) {
      empty.hidden = false;
      canvas.parentElement.hidden = true;
      return;
    }
    empty.hidden = true;
    canvas.parentElement.hidden = false;
    const pcts = days.map((d) => d.pct).filter((v) => v != null);
    pcts.sort((a, b) => a - b);
    const mid = Math.floor(pcts.length / 2);
    const medianPct = pcts.length
      ? (pcts.length % 2 ? pcts[mid] : (pcts[mid - 1] + pcts[mid]) / 2)
      : null;
    charts.selection = new Chart(canvas, {
      type: "bar",
      data: {
        labels: days.map((d) => dayShort(d.date)),
        datasets: [
          {
            data: days.map((d) => d.pct),
            backgroundColor: "#3dba7a",
            borderRadius: 4,
            barPercentage: 0.72,
          },
          {
            type: "line",
            label: medianPct == null ? "медиана" : `медиана ${fmt1.format(medianPct)}%`,
            data: days.map(() => medianPct),
            borderColor: "#e2b45a",
            borderDash: [6, 4],
            pointRadius: 0,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: medianPct != null,
            onClick: () => {},
            labels: {
              color: "#8aa396",
              boxWidth: 12,
              generateLabels: () => [
                {
                  text: `медиана ${fmt1.format(medianPct)}%`,
                  fillStyle: "transparent",
                  strokeStyle: "#e2b45a",
                  lineWidth: 2,
                  lineDash: [6, 4],
                },
              ],
            },
          },
          tooltip: {
            titleFont: { size: 14 },
            callbacks: {
              title: (items) => formatRu(days[items[0].dataIndex].date),
              label: (c) => {
                if (c.dataset.type === "line") return `медиана ${fmt1.format(c.raw)}%`;
                const d = days[c.dataIndex];
                const pct = d.pct == null ? "—" : `${fmt1.format(d.pct)}%`;
                return [
                  `Приехало ${fmt1.format(d.arrived_kg / 1000)} т`,
                  `Отобрано ${fmt1.format(d.selected_kg / 1000)} т`,
                  `Процент отбора ${pct}`,
                ];
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: "#8aa396", maxRotation: 0, autoSkip: true }, grid: { display: false } },
          y: {
            ticks: { color: "#8aa396", callback: (v) => `${fmt1.format(v)}%` },
            grid: { color: "rgba(140,190,160,.08)" },
            title: { display: true, text: "процент отбора", color: "#8aa396" },
          },
        },
      },
    });
  }

  function paintProduction(p, period, rows) {
    const block = document.getElementById("blockProduction");
    block.hidden = false;
    block.querySelectorAll("[data-period]").forEach((el) => {
      el.textContent = period;
    });
    document.getElementById("prodNote").textContent = p.note || "";

    const empty = document.getElementById("prodEmpty");
    const canvas = document.getElementById("chartProdDays");
    destroyChart("prod");
    const totals = brigadeTotals(rows);
    if (!totals.length) {
      empty.hidden = false;
      canvas.hidden = true;
    } else {
      empty.hidden = true;
      canvas.hidden = false;
      const colorOf = (name) => (p.brigades.find((b) => b.name === name) || {}).color || "#3dba7a";
      charts.prod = new Chart(canvas, {
        type: "bar",
        data: {
          labels: totals.map((t) => t.name),
          datasets: [
            {
              data: totals.map((t) => t.kg),
              backgroundColor: totals.map((t) => colorOf(t.name)),
              borderRadius: 6,
              barPercentage: 0.6,
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (c) => {
                  const t = totals[c.dataIndex];
                  return `${fmt.format(t.kg)} кг · ${t.shifts} ${plural(t.shifts, "смена", "смены", "смен")}`;
                },
              },
            },
          },
          scales: {
            x: { ticks: { color: "#8aa396", callback: (v) => fmt0.format(v) }, grid: { color: "rgba(140,190,160,.08)" } },
            y: { ticks: { color: "#8aa396" }, grid: { display: false } },
          },
        },
      });
    }

    const shiftCount = rows && rows.length ? realShiftCount(rows) : p.shift_count;
    const tb = document.getElementById("tbodyWorkshops");
    if (!p.workshops.length) {
      tb.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
    } else {
      const rows = p.workshops
        .map(
          (w) => `<tr>
            <td>${w.name}</td>
            <td class="num">${fmt.format(w.quantity)}</td>
            <td class="num">${fmt1.format(w.share_pct)}%</td>
          </tr>`
        )
        .join("");
      tb.innerHTML =
        rows +
        `<tr class="total"><td>Итого · ${fmt0.format(shiftCount)} ${plural(shiftCount, "смена", "смены", "смен")}</td>
         <td class="num">${fmt.format(p.total_kg)}</td><td class="num">100%</td></tr>`;
    }
  }

  function paintShrink(s, period) {
    const block = document.getElementById("blockShrink");
    block.hidden = false;
    block.querySelectorAll("[data-period]").forEach((el) => {
      el.textContent = period;
    });

    const empty = document.getElementById("shrinkEmpty");
    const canvas = document.getElementById("chartShrinkTrips");
    destroyChart("shrink");
    if (!s.trips.length) {
      empty.hidden = false;
      canvas.hidden = true;
    } else {
      empty.hidden = true;
      canvas.hidden = false;
      // по оси — дата рейса; повтор в тот же день не печатаем, порядок сохраняется
      let prevDay = "";
      const labels = s.trips.map((t) => {
        const day = dayShort(t.date);
        if (day === prevDay) return "";
        prevDay = day;
        return day;
      });
      const values = s.trips.map((t) => t.shrink_pct);
      const colors = s.trips.map((t) =>
        t.anomaly ? "rgba(224,122,106,.55)" : t.mixed ? "rgba(226,180,90,.85)" : "rgba(61,186,122,.85)"
      );
      charts.shrink = new Chart(canvas, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "%",
              data: values,
              backgroundColor: colors,
              borderColor: s.trips.map((t) => (t.mixed ? "#e2b45a" : "transparent")),
              borderWidth: s.trips.map((t) => (t.mixed ? 2 : 0)),
              borderDash: [4, 4],
            },
            {
              type: "line",
              label: `медиана ${fmt1.format(s.median_pct)}%`,
              data: labels.map(() => s.median_pct),
              borderColor: "#e2b45a",
              borderDash: [6, 4],
              pointRadius: 0,
              borderWidth: 2,
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          responsive: true,
          plugins: {
            legend: {
              onClick: () => {},
              labels: {
                color: "#8aa396",
                boxWidth: 12,
                generateLabels: () => [
                  { text: "обычный рейс", fillStyle: "rgba(61,186,122,.85)", strokeStyle: "rgba(61,186,122,.85)", lineWidth: 0 },
                  { text: "несколько фракций", fillStyle: "rgba(226,180,90,.85)", strokeStyle: "#e2b45a", lineWidth: 2 },
                  { text: "расхождение больше 15%", fillStyle: "rgba(224,122,106,.55)", strokeStyle: "rgba(224,122,106,.55)", lineWidth: 0 },
                  {
                    text: `медиана ${fmt1.format(s.median_pct)}%`,
                    fillStyle: "transparent",
                    strokeStyle: "#e2b45a",
                    lineWidth: 2,
                    lineDash: [6, 4],
                  },
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
                  if (t.fractions && t.fractions.length) {
                    t.fractions.forEach((f) => {
                      const scale = f.scale_kg != null ? f.scale_kg : f.kg;
                      const loss = f.shrink_kg != null ? f.shrink_kg : 0;
                      out.push(
                        `${f.name}: бирки ${fmt0.format(f.kg)} кг, по весам ${fmt0.format(scale)} кг, потеря ${fmt0.format(loss)} кг`
                      );
                    });
                  }
                  return out;
                },
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "#8aa396", maxRotation: 60, minRotation: 45, autoSkip: false },
              // вертикальная линия там, где начинается новый день
              grid: {
                display: true,
                drawOnChartArea: true,
                offset: true,
                color: (ctx) => (labels[ctx.index] ? "rgba(140,190,160,.22)" : "transparent"),
              },
            },
            // рамка ±30%: редкие выбросы уходят за край, чтобы не прижимать обычные рейсы
            y: {
              min: -30,
              max: 30,
              ticks: { color: "#8aa396", callback: (v) => `${v}%` },
              grid: { color: "rgba(140,190,160,.08)" },
            },
          },
        },
      });
    }

    const tb = document.getElementById("tbodyShrinkFrac");
    if (!s.by_fraction.length) {
      tb.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
    } else {
      tb.innerHTML =
        s.by_fraction
          .map(
            (f) => `<tr>
              <td><span class="dot" style="background:${f.color}"></span>${f.name}</td>
              <td class="num">${fmt1.format(f.trip_count)}</td>
              <td class="num">${fmt1.format(f.shrink_pct)}%</td>
            </tr>`
          )
          .join("") +
        `<tr class="total"><td>Все рейсы</td>
          <td class="num">${fmt0.format(s.total.trip_count)}</td>
          <td class="num">${fmt1.format(s.total.shrink_pct)}%</td></tr>`;
    }
  }

  function paintWarehouse(w) {
    document.getElementById("blockWarehouse").hidden = false;
    const tb = document.getElementById("tbodyWarehouse");
    if (!w.rows.length) {
      tb.innerHTML = `<tr><td colspan="5">остатков нет</td></tr>`;
      return;
    }
    tb.innerHTML =
      w.rows
        .map(
          (r) => `<tr>
            <td><span class="dot" style="background:${r.color}"></span>${r.name}</td>
            <td class="num">${fmt.format(r.quantity_kg)}</td>
            <td><div class="bar"><i style="width:${Math.min(r.share_pct, 100)}%;background:${r.color}"></i></div>
              <span class="muted">${fmt1.format(r.share_pct)}%</span></td>
            <td class="num">${fmt0.format(r.price_per_t)}</td>
            <td class="num">${fmt0.format(r.value_rub)}</td>
          </tr>`
        )
        .join("") +
      `<tr class="total"><td>Итого на площадке</td>
        <td class="num">${fmt.format(w.total_kg)}</td><td></td><td></td>
        <td class="num">${fmt0.format(w.total_rub)}</td></tr>`;
  }

  function paintPrices(p) {
    document.getElementById("blockPrices").hidden = false;
    const empty = document.getElementById("pricesEmpty");
    const canvas = document.getElementById("chartPrices");
    destroyChart("prices");
    if (!p.series.length || !p.months.length) {
      empty.hidden = false;
      canvas.hidden = true;
      return;
    }
    empty.hidden = true;
    canvas.hidden = false;
    let multiPoint = false;
    const pctLabel = (index) => (index == null ? "—" : `${index - 100 >= 0 ? "+" : "−"}${fmt1.format(Math.abs(index - 100))}%`);

    charts.prices = new Chart(canvas, {
      type: "line",
      data: {
        labels: p.months.map(monthShort),
        datasets: p.series.map((s) => ({
          label: s.name,
          data: s.indexes,
          borderColor: s.color,
          backgroundColor: s.color,
          tension: 0,
          spanGaps: true,
          pointRadius: 3,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#8aa396", boxWidth: 12, padding: 12 } },
          tooltip: {
            titleFont: { size: 14 },
            callbacks: {
              title: (items) => {
                multiPoint = items.length > 1;
                return multiPoint
                  ? monthShort(p.months[items[0].dataIndex])
                  : p.series[items[0].datasetIndex].name;
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
          x: { ticks: { color: "#8aa396" }, grid: { color: "rgba(140,190,160,.08)" } },
          y: {
            ticks: { color: "#8aa396", callback: (v) => pctLabel(v) },
            grid: { color: "rgba(140,190,160,.08)" },
            title: { display: true, text: "изменение цены к первому месяцу", color: "#8aa396" },
          },
        },
      },
    });
  }

  function paintSales(s, period) {
    document.getElementById("blockSales").hidden = false;
    document.querySelectorAll("#blockSales [data-period]").forEach((el) => {
      el.textContent = period;
    });

    const warn = document.getElementById("concWarn");
    if (s.concentration) {
      warn.hidden = false;
      warn.textContent =
        `Концентрация: ${s.concentration.name} — ${fmt1.format(s.concentration.share_pct)}% выручки ` +
        `(${money(s.concentration.rub)})`;
    } else {
      warn.hidden = true;
    }

    const empty = document.getElementById("salesEmpty");
    const canvas = document.getElementById("chartSalesFrac");
    destroyChart("sales");
    if (!s.by_fraction.length) {
      empty.hidden = false;
      canvas.hidden = true;
    } else {
      empty.hidden = true;
      canvas.hidden = false;
      charts.sales = new Chart(canvas, {
        type: "bar",
        data: {
          labels: s.by_fraction.map((f) => f.name),
          datasets: [
            {
              data: s.by_fraction.map((f) => f.rub),
              backgroundColor: s.by_fraction.map((f) => f.color),
              borderRadius: 6,
            },
          ],
        },
        options: {
        maintainAspectRatio: false,
          indexAxis: "y",
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (c) => {
                  const f = s.by_fraction[c.dataIndex];
                  return `${money(f.rub)} · ${fmt1.format(f.tons)} т`;
                },
              },
            },
          },
          scales: {
            x: { ticks: { color: "#8aa396", callback: (v) => money(v) }, grid: { color: "rgba(140,190,160,.08)" } },
            y: { ticks: { color: "#cfe0d6" }, grid: { display: false } },
          },
        },
      });
    }

    const tb = document.getElementById("tbodyBuyers");
    if (!s.buyers.length) {
      tb.innerHTML = `<tr><td colspan="3">за период данных нет</td></tr>`;
    } else {
      tb.innerHTML = s.buyers
        .slice(0, 12)
        .map(
          (b) => `<tr class="${b.share_pct > 50 ? "hot" : ""}">
            <td>${b.name}</td>
            <td class="num">${fmt0.format(b.rub)}</td>
            <td class="num">${fmt1.format(b.share_pct)}%</td>
          </tr>`
        )
        .join("");
    }
  }

  async function loadData() {
    const from = dateFrom.value;
    const to = dateTo.value;
    if (!from || !to) {
      setStatus("Укажите даты периода", true);
      return;
    }
    const period = `${presetName(activePreset)}: ${formatRu(from)} — ${formatRu(to)}`;
    setStatus(`Загрузка ${period}…`);
    btn.disabled = true;

    try {
      const res = await fetch(`/api/data?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Ошибка API");

      paintKpis(data.kpis, data.rows || []);
      paintSelection(data.selection || {}, period);
      paintProduction(data.production, period, data.rows || []);
      paintShrink(data.shrinkage, period);
      paintWarehouse(data.warehouse);
      paintPrices(data.prices);
      paintSales(data.sales, period);

      setStatus("");
    } catch (err) {
      ["kpis", "blockSelection", "blockProduction", "blockShrink", "blockWarehouse", "blockPrices", "blockSales"].forEach(
        (id) => {
          const el = document.getElementById(id);
          if (el) el.hidden = true;
        }
      );
      setStatus(err.message || String(err), true);
    } finally {
      btn.disabled = false;
    }
  }

  presetsEl.addEventListener("click", (e) => {
    const b = e.target.closest(".preset");
    if (!b) return;
    applyPreset(b.dataset.preset);
    loadData();
  });

  function onManualDate() {
    setPresetActive("custom");
  }
  dateFrom.addEventListener("change", onManualDate);
  dateTo.addEventListener("change", onManualDate);

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    loadData();
  });

  applyPreset("month");
  loadData();
})();
