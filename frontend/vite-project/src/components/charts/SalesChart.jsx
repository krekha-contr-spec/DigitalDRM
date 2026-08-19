// SalesChart.jsx — Monthly (Jan-Dec of selectedYear) or Yearly Line chart.
// Sales is a monthly-closing metric (see backend reminder_service.py — it's
// only checked against month-end data), so this chart no longer shows a
// daily breakdown. "Daily" from the dashboard's view selector auto-falls
// back to Monthly here; "Yearly" totals every record per calendar year
// from the full `history` prop.
import { useState, useEffect } from "react"
import { Line } from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Title, Tooltip, Legend
} from "chart.js"
import SummaryTable from "../SummaryTable"
import { getSalesMonthlyTrend } from "../../services/api"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const NO_DATA = (
  <div style={{ textAlign: "center", color: "#94a3b8", padding: "60px 20px", fontSize: "15px" }}>
    📊 No Sales data available for this period
  </div>
)

// Sum month_plan / mtd_actual across every history record that falls in
// a given calendar year, one total per year present in the data.
function buildYearlyTotals(history) {
  const byYear = {}
  ;(history || []).forEach(r => {
    if (!r.date) return
    const year = r.date.slice(0, 4)
    if (!byYear[year]) byYear[year] = { plan: 0, actual: 0, has: false }
    byYear[year].plan   += r.month_plan || 0
    byYear[year].actual += r.mtd_actual || 0
    byYear[year].has = true
  })
  return byYear
}

function SalesChart({ data, selectedYear, selectedView, history, plantId }) {
  const segments = data?.segments || []
  // Sales has no Daily view — "daily" from the dashboard selector falls
  // back to Monthly for this chart specifically.
  const effectiveView = selectedView === "yearly" ? "yearly" : "monthly"

  const [monthly, setMonthly] = useState([])
  const [loadingMonthly, setLoadingMonthly] = useState(false)

  useEffect(() => {
    if (effectiveView !== "monthly" || !plantId || !selectedYear) return
    let cancelled = false
    setLoadingMonthly(true)
    getSalesMonthlyTrend(plantId, selectedYear)
      .then(res => { if (!cancelled) setMonthly(res?.data?.monthly || []) })
      .catch(() => { if (!cancelled) setMonthly([]) })
      .finally(() => { if (!cancelled) setLoadingMonthly(false) })
    return () => { cancelled = true }
  }, [effectiveView, plantId, selectedYear])

  if (segments.length === 0 && (history || []).length === 0) return NO_DATA
  if (effectiveView === "monthly" && loadingMonthly) return NO_DATA

  let labels, planData, actualData, footerNote

  if (effectiveView === "yearly") {
    const byYear = buildYearlyTotals(history)
    const years = Object.keys(byYear).sort()
    if (years.length === 0) return NO_DATA
    labels     = years
    planData   = years.map(y => (byYear[y].has ? byYear[y].plan   : null))
    actualData = years.map(y => (byYear[y].has ? byYear[y].actual : null))
    footerNote = "💡 Blue line = Month Plan | Pink line = MTD Actual (all segments combined) | Totals per year"
  } else {
    if (monthly.length === 0) return NO_DATA
    labels     = monthly.map(m => m.month_name)
    planData   = monthly.map(m => m.month_plan)
    actualData = monthly.map(m => m.mtd_actual)
    footerNote = `💡 Blue line = Month Plan | Pink line = MTD Actual (all segments combined) | ${selectedYear}, month-wise`
  }

  const chartData = {
    labels,
    datasets: [
      {
        label: "Month Plan", data: planData,
        borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,0.05)",
        pointRadius: 4, pointBackgroundColor: "#3b82f6", pointBorderColor: "#1e40af", pointHoverRadius: 6,
        tension: 0.4, borderWidth: 2, fill: false, spanGaps: true
      },
      {
        label: "MTD Actual", data: actualData,
        borderColor: "#ec4899", backgroundColor: "rgba(236,72,153,0.05)",
        pointRadius: 4, pointBackgroundColor: "#ec4899", pointBorderColor: "#be185d", pointHoverRadius: 6,
        tension: 0.4, borderWidth: 2.5, fill: false, spanGaps: true
      },
    ],
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      <SummaryTable summary={data.summary} type="sales" />
      <div style={{ flex: 1, position: "relative", minHeight: "350px", marginTop: "20px" }}>
        <Line data={chartData} options={baseOptions()} />
      </div>
      <div style={{ marginTop: "12px", padding: "10px", background: "#fdf2f8", borderRadius: "8px", fontSize: "12px", color: "#9d174d", textAlign: "center" }}>
        {footerNote}
      </div>
    </div>
  )
}

function baseOptions() {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { font: { size: 12, weight: "600" }, padding: 15, usePointStyle: true, pointStyle: "circle" } },
      title: { display: false },
    },
    scales: {
      y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { font: { size: 12 }, callback: v => v.toLocaleString() } },
      x: { grid: { color: "#f1f5f9" }, ticks: { font: { size: 11 }, maxRotation: 45 } },
    },
  }
}

export default SalesChart