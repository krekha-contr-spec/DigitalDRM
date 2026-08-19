// DespatchChart.jsx — one Line chart PER CUSTOMER, automatically
// generated. No combined "all customers" chart — each customer (BMW,
// HMI, etc.) gets their own independent chart, built straight from
// whichever customer_name values already exist in the fetched history
// for the month. The moment a new customer's first entry is saved for
// this plant, a new chart for that customer appears here on the next
// refresh — nothing to configure.
import { Line } from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Title, Tooltip, Legend
} from "chart.js"
import SummaryTable from "../SummaryTable"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const NO_DATA = (
  <div style={{ textAlign: "center", color: "#94a3b8", padding: "60px 20px", fontSize: "15px" }}>
    📊 No Despatch data available for this period
  </div>
)

// A small, distinct, repeatable palette so each customer's chart looks
// visually consistent across refreshes (same customer = same colors
// every time, since it's keyed off the sorted customer name, not
// insertion order).
const PALETTE = [
  { plan: "#3b82f6", actual: "#10b981" }, // blue / green
  { plan: "#f59e0b", actual: "#ef4444" }, // amber / red
  { plan: "#8b5cf6", actual: "#06b6d4" }, // violet / cyan
  { plan: "#ec4899", actual: "#84cc16" }, // pink / lime
  { plan: "#0ea5e9", actual: "#f97316" }, // sky / orange
  { plan: "#6366f1", actual: "#14b8a6" }, // indigo / teal
]

function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate()
}
function pad2(n) { return String(n).padStart(2, "0") }
function isoDate(year, month, day) { return `${year}-${pad2(month)}-${pad2(day)}` }

// Scoped to ONE customer only — this is what makes each per-customer
// mini-chart independent of every other customer.
function buildCustomerDailyData(history, year, month, customerName) {
  const byDate = {}
  ;(history || []).forEach(r => {
    if (r.customer_name !== customerName) return
    if (!r.date || !r.date.startsWith(`${year}-${pad2(month)}`)) return
    byDate[r.date] = { plan: r.month_plan || 0, actual: r.mtd_actual || 0 }
  })
  return byDate
}

function buildLineChartData(labels, byDate, colors) {
  return {
    labels,
    datasets: [
      {
        label: "Month Plan", data: labels.map(d => (byDate[d] ? byDate[d].plan : null)),
        borderColor: colors.plan, backgroundColor: `${colors.plan}0D`,
        pointRadius: 3, pointBackgroundColor: colors.plan, pointHoverRadius: 5,
        tension: 0, borderWidth: 2, fill: false, spanGaps: true,
      },
      {
        label: "MTD Actual", data: labels.map(d => (byDate[d] ? byDate[d].actual : null)),
        borderColor: colors.actual, backgroundColor: `${colors.actual}0D`,
        pointRadius: 3, pointBackgroundColor: colors.actual, pointHoverRadius: 5,
        tension: 0, borderWidth: 2.5, fill: false, spanGaps: true,
      },
    ],
  }
}

function DespatchChart({ data, selectedYear, selectedMonth, history }) {
  const customers = data?.customers || []

  if (customers.length === 0 || !selectedYear || !selectedMonth) return NO_DATA

  const total = daysInMonth(selectedYear, selectedMonth)
  const labels = Array.from({ length: total }, (_, i) => isoDate(selectedYear, selectedMonth, i + 1))

  // Per-customer charts — automatically derived, sorted alphabetically
  // so the layout is stable rather than jumping around as new entries
  // come in. Any customer name that has EVER appeared in this month's
  // history gets its own card; no manual list to maintain anywhere.
  const customerNames = Array.from(
    new Set((history || []).map(r => r.customer_name).filter(Boolean))
  ).sort()

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      <SummaryTable summary={data.summary} type="despatch" />

      {customerNames.length === 0 ? NO_DATA : (
        <div style={{ marginTop: "20px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "20px" }}>
            {customerNames.map((name, i) => {
              const colors = PALETTE[i % PALETTE.length]
              const custByDate = buildCustomerDailyData(history, selectedYear, selectedMonth, name)
              const custChartData = buildLineChartData(labels, custByDate, colors)
              return (
                <div key={name} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "14px" }}>
                  <div style={{ fontSize: "13px", fontWeight: 700, color: "#0f172a", marginBottom: "8px" }}>
                    {name}
                  </div>
                  <div style={{ position: "relative", height: "280px" }}>
                    <Line data={custChartData} options={baseOptions(true)} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function baseOptions(compact = false) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { font: { size: compact ? 10 : 12, weight: "600" }, padding: compact ? 8 : 15, usePointStyle: true, pointStyle: "circle" } },
      title: { display: false },
    },
    scales: {
      y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { font: { size: compact ? 10 : 12 }, callback: v => v.toLocaleString() } },
      x: { grid: { color: "#f1f5f9" }, ticks: { font: { size: compact ? 9 : 11 }, maxRotation: 45, autoSkip: true, maxTicksLimit: compact ? 10 : undefined } },
    },
  }
}

export default DespatchChart