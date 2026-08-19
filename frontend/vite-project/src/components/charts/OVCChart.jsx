import { useState, useEffect, useMemo, Component } from "react"
import { Line, Bar } from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, BarElement, Title, Tooltip, Legend
} from "chart.js"
import SummaryTable from "../SummaryTable"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend)

const GREEN  = "#16a34a"
const YELLOW = "#f59e0b"
const RED    = "#dc2626"
const GRAY   = "#cbd5e1"

// Define the 6 allowed categories
const ALLOWED_CATEGORIES = [
  "Consumable Cost",
  "Direct Labour Cost",
  "Freight Cost",
  "Plant Overall Overrun",
  "Power Cost",
  "Rejection Cost"
]

function statusColor(pct, hasData) {
  if (!hasData || pct === null || pct === undefined) return GRAY
  if (pct >= 100) return GREEN
  if (pct >= 80) return YELLOW
  return RED
}

/**
 * Daily OVC Trend Dashboard
 * Read-only. Built entirely from the `history` (day-level OVC records) and
 * `data` (monthly trend/summary) props already supplied by DepartmentDetail —
 * no new API calls, no backend or database changes.
 */
function OVCTrendDashboard({ data, plantId, selectedYear, selectedMonth, history }) {
  const allHistory = history || []

  // ── OVC element filter (only show the 6 allowed categories) ──────────────────
  const elementTypes = useMemo(() => {
    const set = new Set(allHistory.map(h => h.element_type).filter(Boolean))
    // Filter to only include allowed categories
    return Array.from(set)
      .filter(el => ALLOWED_CATEGORIES.includes(el))
      .sort((a, b) => {
        // Sort by the order defined in ALLOWED_CATEGORIES
        return ALLOWED_CATEGORIES.indexOf(a) - ALLOWED_CATEGORIES.indexOf(b)
      })
  }, [allHistory])

  const [selectedElement, setSelectedElement] = useState("")

  useEffect(() => {
    if (elementTypes.length > 0 && !elementTypes.includes(selectedElement)) {
      setSelectedElement(elementTypes[0])
    }
    if (elementTypes.length === 0 && selectedElement !== "") {
      setSelectedElement("")
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elementTypes])

  const year  = Number(selectedYear)  || new Date().getFullYear()
  const month = Number(selectedMonth) || (new Date().getMonth() + 1)

  // ── Build the full calendar for the selected month/year/element ─────────
  const daysInMonth = new Date(year, month, 0).getDate()

  const dailySeries = useMemo(() => {
    const byDay = {}
    allHistory.forEach(r => {
      if (!r || r.element_type !== selectedElement || !r.date) return
      const parts = String(r.date).split("-").map(Number)
      if (parts.length !== 3 || parts.some(n => Number.isNaN(n))) return
      const [ry, rm, rd] = parts
      if (ry === year && rm === month) byDay[rd] = r
    })

    const out = []
    for (let d = 1; d <= daysInMonth; d++) {
      const row = byDay[d]
      out.push({
        day: d,
        date: row ? row.date : `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
        plan: row ? row.plan : null,
        actual: row ? row.actual : null,
        variance: row ? row.variance : null,
        achieved_percent: row ? row.achieved_percent : null,
        hasData: !!row,
      })
    }
    return out
  }, [allHistory, selectedElement, year, month, daysInMonth])

  const hasAnyDataThisMonth = dailySeries.some(d => d.hasData)

  if (elementTypes.length === 0) {
    return (
      <div style={{ textAlign: "center", color: "#94a3b8", padding: "40px", fontSize: "16px" }}>
        📊 No OVC data available for the 6 categories in this period
      </div>
    )
  }

  const dayLabels = dailySeries.map(d => d.day)

  // ── Chart 1: Target vs Actual (daily line chart) ─────────────────────────
  const targetVsActualData = {
    labels: dayLabels,
    datasets: [
      {
        label: "Target",
        data: dailySeries.map(d => d.plan),
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59, 130, 246, 0.05)",
        pointRadius: 3,
        pointBackgroundColor: "#3b82f6",
        pointBorderColor: "#1e40af",
        pointHoverRadius: 6,
        tension: 0.35,
        borderWidth: 2,
        fill: false,
        spanGaps: true,
      },
      {
        label: "Actual",
        data: dailySeries.map(d => d.actual),
        borderColor: GREEN,
        backgroundColor: "rgba(22, 163, 74, 0.05)",
        pointRadius: 3,
        pointBackgroundColor: GREEN,
        pointBorderColor: "#15803d",
        pointHoverRadius: 6,
        tension: 0.35,
        borderWidth: 2.5,
        fill: false,
        spanGaps: true,
      },
    ],
  }

  const targetVsActualOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { font: { size: 12, weight: "600" }, padding: 15, usePointStyle: true, pointStyle: "circle" } },
      title: { display: false },
      tooltip: {
        callbacks: {
          title: items => `Day ${items[0].label} — ${selectedElement}`,
          afterBody: items => {
            const d = dailySeries[items[0].dataIndex]
            if (!d.hasData) return ["No data submitted for this day"]
            const variance = d.variance !== null && d.variance !== undefined ? d.variance : ((d.actual ?? 0) - (d.plan ?? 0))
            const achieved = d.achieved_percent !== null && d.achieved_percent !== undefined ? d.achieved_percent : 0
            return [`Variance: ${variance >= 0 ? "+" : ""}${variance.toLocaleString(undefined, { maximumFractionDigits: 2 })}`, `Achieved: ${achieved.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`]
          },
        },
      },
    },
    scales: {
      y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { font: { size: 12 }, callback: v => v.toLocaleString() } },
      x: { grid: { display: false }, ticks: { font: { size: 11 } }, title: { display: true, text: `Day of ${monthName(month)} ${year}`, font: { size: 11, weight: "600" }, color: "#64748b" } },
    },
  }

  // ── Chart 2: Daily Variance (bar chart) ──────────────────────────────────
  const varianceColors = dailySeries.map(d => (!d.hasData ? GRAY : (d.variance ?? 0) >= 0 ? GREEN : RED))

  const varianceChartData = {
    labels: dayLabels,
    datasets: [
      {
        label: "Daily Variance (Actual − Target)",
        data: dailySeries.map(d => (d.hasData ? d.variance : null)),
        backgroundColor: varianceColors,
        borderColor: varianceColors,
        borderWidth: 1,
        borderRadius: 4,
        borderSkipped: false,
      },
    ],
  }

  const varianceChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: { display: false },
      tooltip: {
        callbacks: {
          title: items => `Day ${items[0].label} — ${selectedElement}`,
          label: ctx => {
            const d = dailySeries[ctx.dataIndex]
            if (!d.hasData) return "No data submitted"
            return `Variance: ${d.variance >= 0 ? "+" : ""}${d.variance.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
          },
          afterLabel: ctx => {
            const d = dailySeries[ctx.dataIndex]
            if (!d.hasData) return ""
            return `Target: ${d.plan ?? "—"}  |  Actual: ${d.actual ?? "—"}`
          },
        },
      },
    },
    scales: {
      y: { grid: { color: "#f1f5f9" }, ticks: { font: { size: 12 }, callback: v => v.toLocaleString() } },
      x: { grid: { display: false }, ticks: { font: { size: 11 } }, title: { display: true, text: `Day of ${monthName(month)} ${year}`, font: { size: 11, weight: "600" }, color: "#64748b" } },
    },
  }

  // ── Chart 3: Achievement % trend (line chart with 100% reference) ───────
  const achievementChartData = {
    labels: dayLabels,
    datasets: [
      {
        label: "Achievement %",
        data: dailySeries.map(d => (d.hasData ? d.achieved_percent : null)),
        borderColor: "#d97706",
        backgroundColor: "rgba(217, 119, 6, 0.06)",
        pointRadius: 3,
        pointBackgroundColor: dailySeries.map(d => statusColor(d.achieved_percent, d.hasData)),
        pointBorderColor: "#92400e",
        pointHoverRadius: 6,
        tension: 0.35,
        borderWidth: 2,
        fill: true,
        spanGaps: true,
      },
      {
        label: "100% Target Line",
        data: dayLabels.map(() => 100),
        borderColor: "#94a3b8",
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
      },
    ],
  }

  const achievementChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { font: { size: 12, weight: "600" }, padding: 15, usePointStyle: true, pointStyle: "circle" } },
      title: { display: false },
      tooltip: {
        callbacks: {
          title: items => `Day ${items[0].label} — ${selectedElement}`,
          afterBody: items => {
            const d = dailySeries[items[0].dataIndex]
            if (!d.hasData) return ["No data submitted for this day"]
            return [`Target: ${d.plan ?? "—"}`, `Actual: ${d.actual ?? "—"}`]
          },
        },
      },
    },
    scales: {
      y: { grid: { color: "#f1f5f9" }, ticks: { font: { size: 12 }, callback: v => `${v}%` } },
      x: { grid: { display: false }, ticks: { font: { size: 11 } }, title: { display: true, text: `Day of ${monthName(month)} ${year}`, font: { size: 11, weight: "600" }, color: "#64748b" } },
    },
  }

  // ── Chart 4: Variance Bar Chart ──────────────────────────────────────────
  const varianceBarData = {
    labels: dayLabels,
    datasets: [
      {
        label: "Variance",
        data: dailySeries.map(d => (d.hasData ? d.variance : null)),
        backgroundColor: dailySeries.map(d => {
          if (!d.hasData) return GRAY
          return (d.variance ?? 0) >= 0 ? "rgba(22, 163, 74, 0.7)" : "rgba(220, 38, 38, 0.7)"
        }),
        borderColor: dailySeries.map(d => {
          if (!d.hasData) return GRAY
          return (d.variance ?? 0) >= 0 ? "#16a34a" : "#dc2626"
        }),
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  }

  const varianceBarOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: { display: false },
      tooltip: {
        callbacks: {
          title: items => `Day ${items[0].label} — ${selectedElement}`,
          label: ctx => {
            const d = dailySeries[ctx.dataIndex]
            if (!d.hasData) return "No data submitted"
            return `Variance: ${d.variance >= 0 ? "+" : ""}${d.variance.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
          },
        },
      },
    },
    scales: {
      y: { grid: { color: "#f1f5f9" }, ticks: { font: { size: 12 }, callback: v => v.toLocaleString() } },
      x: { grid: { display: false }, ticks: { font: { size: 11 } }, title: { display: true, text: `Day of ${monthName(month)} ${year}`, font: { size: 11, weight: "600" }, color: "#64748b" } },
    },
  }

  return (

    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      <SummaryTable summary={data?.summary} type="ovc" />
        {/* Monthly Heat Map */}
      <SectionHeader title="🗓️ Monthly Achievement Heat Map" />
      <HeatMap dailySeries={dailySeries} elementName={selectedElement} monthLabel={`${monthName(month)} ${year}`} />

      <div style={{ marginTop: "24px", padding: "12px", background: "#f0f9ff", borderRadius: "8px", fontSize: "12px", color: "#0369a1", textAlign: "center" }}>
        💡 Blue line = Target | Green line = Actual | 🟢 ≥100% &nbsp; 🟡 80–99% &nbsp; 🔴 &lt;80% &nbsp; ⚪ No Data — hover any point/day for details
      </div>
      {/* Element filter - Only showing 6 categories */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginTop: "20px", marginBottom: "4px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "12px", fontWeight: "700", color: "#475569" }}>📐 OVC Element:</span>
        <select
          value={selectedElement}
          onChange={e => setSelectedElement(e.target.value)}
          style={{ 
            padding: "6px 10px", 
            border: "1px solid #cbd5e1", 
            borderRadius: "6px", 
            fontSize: "12px", 
            color: "#1e293b", 
            background: "white", 
            cursor: "pointer", 
            minWidth: "180px" 
          }}
        >
          {elementTypes.map(el => <option key={el} value={el}>{el}</option>)}
        </select>
        <span style={{ fontSize: "12px", color: "#94a3b8" }}>
          Showing {monthName(month)} {year} · read-only
        </span>
        <span style={{ 
          fontSize: "11px", 
          color: "#64748b", 
          background: "#f1f5f9", 
          padding: "2px 10px", 
          borderRadius: "12px" 
        }}>
          {elementTypes.length} of 6 categories
        </span>
      </div>

      {!hasAnyDataThisMonth && (
        <div style={{ textAlign: "center", color: "#94a3b8", padding: "24px", fontSize: "13px" }}>
          📊 No entries submitted for {selectedElement} in {monthName(month)} {year}
        </div>
      )}

      {/* Target vs Actual */}
      <SectionHeader title="🎯 Target vs Actual — Daily Trend" />
      <div style={{ position: "relative", minHeight: "300px", marginBottom: "28px" }}>
        <Line data={targetVsActualData} options={targetVsActualOptions} />
      </div>

      {/* Variance Bar Chart */}
      <SectionHeader title="📊 Daily Variance" />
      <div style={{ position: "relative", minHeight: "250px", marginBottom: "28px" }}>
        <Bar data={varianceBarData} options={varianceBarOptions} />
      </div>

      {/* Achievement % Trend
      <SectionHeader title="📈 Achievement % Trend" />
      <div style={{ position: "relative", minHeight: "300px", marginBottom: "28px" }}>
        <Line data={achievementChartData} options={achievementChartOptions} />
      </div> */}

    
    </div>
  )
}

function SectionHeader({ title }) {
  return (
    <h3 style={{ margin: "0 0 10px 0", fontSize: "13px", fontWeight: "700", color: "#0f172a" }}>
      {title}
    </h3>
  )
}

function monthName(m) {
  return ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][m] || ""
}

function HeatMap({ dailySeries, elementName, monthLabel }) {
  return (
    <div>
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(42px, 1fr))",
        gap: "6px",
      }}>
        {dailySeries.map(d => {
          const color = statusColor(d.achieved_percent, d.hasData)
          const title = d.hasData
            ? `Day ${d.day} (${d.date})\n${elementName}\nTarget: ${d.plan ?? "—"}\nActual: ${d.actual ?? "—"}\nVariance: ${d.variance !== null && d.variance !== undefined ? (d.variance >= 0 ? "+" : "") + d.variance : "—"}\nAchieved: ${d.achieved_percent !== null && d.achieved_percent !== undefined ? d.achieved_percent.toFixed(1) + "%" : "—"}`
            : `Day ${d.day} (${d.date})\nNo data submitted`
          return (
            <div
              key={d.day}
              title={title}
              style={{
                background: color,
                color: color === GRAY ? "#64748b" : "white",
                borderRadius: "6px",
                aspectRatio: "1 / 1",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "11px",
                fontWeight: "700",
                cursor: "default",
                userSelect: "none",
              }}
            >
              {d.day}
            </div>
          )
        })}
      </div>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "12px", fontSize: "11px", color: "#475569" }}>
        <LegendDot color={GREEN}  label="≥ 100% (On Target)" />
        <LegendDot color={YELLOW} label="80–99% (Near Target)" />
        <LegendDot color={RED}    label="< 80% (Below Target)" />
        <LegendDot color={GRAY}   label="No Data" />
      </div>
      <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "4px" }}>{monthLabel} · hover a day for details</div>
    </div>
  )
}

function LegendDot({ color, label }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
      <span style={{ width: "10px", height: "10px", borderRadius: "3px", background: color, display: "inline-block" }} />
      {label}
    </span>
  )
}

// Local error boundary — keeps a failure inside this chart from taking
// down the rest of the app (e.g. leaving the whole page blank).
class OVCChartErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  componentDidCatch(error, info) {
    console.error("OVC Trend Dashboard failed to render:", error, info)
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ textAlign: "center", color: "#dc2626", padding: "40px", fontSize: "14px" }}>
          ⚠️ The OVC Trend Dashboard couldn't be displayed. Please try switching month/year or refreshing.
        </div>
      )
    }
    return this.props.children
  }
}

function OVCChart(props) {
  return (
    <OVCChartErrorBoundary>
      <OVCTrendDashboard {...props} />
    </OVCChartErrorBoundary>
  )
}

export default OVCChart