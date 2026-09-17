(() => {
  const form = document.getElementById("filters");
  const dateFrom = document.getElementById("dateFrom");
  const dateTo = document.getElementById("dateTo");
  const presetsEl = document.getElementById("presets");
  const status = document.getElementById("status");
  const periodLabel = document.getElementById("periodLabel");
  const btn = form.querySelector("button.btn");

  const charts = {};
  let activePreset = "month";
  const fmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });
  const fmt0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const fmt1 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

  function setStatus(text, isError = false) {
    status.textContent = text;
    status.classList.toggle("error", isError);
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

  function paintKpis(k) {
    document.getElementById("kpis").hidden = false;
    document.querySelector('[data-kpi="production"]').textContent = `${fmt1.format(k.production_t)} т`;
    document.querySelector('[data-kpi-cap="production"]').textContent =
      `${fmt0.format(k.shift_count)} смен за период`;
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

  function paintProduction(p, period) {
    const block = document.getElementById("blockProduction");
    block.hidden = false;
    block.querySelectorAll("[data-period]").forEach((el) => {
      el.textContent = period;
    });
    document.getElementById("prodNote").textContent = p.note || "";

    const empty = document.getElementById("prodEmpty");
    const canvas = document.getElementById("chartProdDays");
    destroyChart("prod");
    if (!p.days.length) {
      empty.hidden = false;
      canvas.hidden = true;
    } else {
      empty.hidden = true;
      canvas.hidden = false;
      charts.prod = new Chart(canvas, {
        type: "bar",
        data: {
          labels: p.days,
          datasets: p.brigades.map((b) => ({
            label: b.name,
            data: b.values,
            backgroundColor: b.color,
            stack: "s",
            borderRadius: 4,
          })),
        },
        options: {
          responsive: true,
          plugins: {
            legend: { labels: { color: "#8aa396" } },
            tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt.format(c.raw)} кг` } },
          },
          scales: {
            x: { stacked: true, ticks: { color: "#8aa396" }, grid: { color: "rgba(140,190,160,.08)" } },
            y: { stacked: true, ticks: { color: "#8aa396", callback: (v) => fmt0.format(v) }, grid: { color: "rgba(140,190,160,.08)" } },
          },
        },
      });
    }

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
        `<tr class="total"><td>Итого · ${fmt0.format(p.shift_count)} смен</td>
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
      const labels = s.trips.map((t) => t.number);
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
          responsive: true,
          plugins: {
            legend: { labels: { color: "#8aa396" } },
            tooltip: {
              callbacks: {
                label: (c) =>
                  c.dataset.type === "line"
                    ? `медиана ${fmt1.format(c.raw)}%`
                    : `${fmt1.format(c.raw)}% (${fmt0.format(s.trips[c.dataIndex].shrink_kg)} кг)`,
              },
            },
          },
          scales: {
            x: { ticks: { color: "#8aa396", maxRotation: 90, minRotation: 45, autoSkip: true, maxTicksLimit: 20 }, grid: { display: false } },
            y: { ticks: { color: "#8aa396", callback: (v) => `${v}%` }, grid: { color: "rgba(140,190,160,.08)" } },
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
    charts.prices = new Chart(canvas, {
      type: "line",
      data: {
        labels: p.months,
        datasets: p.series.map((s) => ({
          label: `${s.name}${s.last_index != null ? ` · ${s.last_index}` : ""}`,
          data: s.indexes,
          borderColor: s.color,
          backgroundColor: s.color,
          tension: 0.25,
          spanGaps: true,
          pointRadius: 3,
        })),
      },
      options: {
        responsive: true,
        plugins: {
          legend: { labels: { color: "#8aa396" } },
          tooltip: {
            callbacks: {
              label: (c) => {
                const s = p.series[c.datasetIndex];
                const price = s.prices[c.dataIndex];
                return `${s.name}: индекс ${c.raw}, ${price != null ? fmt0.format(price) + " ₽/т" : "—"}`;
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: "#8aa396" }, grid: { color: "rgba(140,190,160,.08)" } },
          y: { ticks: { color: "#8aa396" }, grid: { color: "rgba(140,190,160,.08)" }, title: { display: true, text: "индекс", color: "#8aa396" } },
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
    periodLabel.textContent = period;
    btn.disabled = true;

    try {
      const res = await fetch(`/api/data?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Ошибка API");

      paintKpis(data.kpis);
      paintProduction(data.production, period);
      paintShrink(data.shrinkage, period);
      paintWarehouse(data.warehouse);
      paintPrices(data.prices);
      paintSales(data.sales, period);

      setStatus(
        `Выработка ${fmt1.format(data.kpis.production_t)} т · вывезено ${fmt1.format(data.kpis.shipped_t)} т · ` +
          `усушка ${fmt1.format(data.kpis.shrink_pct)}%`
      );
    } catch (err) {
      ["kpis", "blockProduction", "blockShrink", "blockWarehouse", "blockPrices", "blockSales"].forEach(
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
