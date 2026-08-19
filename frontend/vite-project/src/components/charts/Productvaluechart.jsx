// ProductValueChart.jsx — single daily Line chart, every day of the selected month shown without skipping
import { Line } from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Title, Tooltip, Legend
} from "chart.js"
import SummaryTable from "../SummaryTable"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const NO_DATA = (
  <div style={{ textAlign: "center", color: "#94a3b8", padding: "60px 20px", fontSize: "15px" }}>
    📊 No Product Value data available for this period
  </div>
)

function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate()
}
function pad2(n) { return String(n).padStart(2, "0") }
function isoDate(year, month, day) { return `${year}-${pad2(month)}-${pad2(day)}` }

function ProductValueChart({ data, selectedYear, selectedMonth }) {
  const trend = data?.trend || []

  if (trend.length === 0) return NO_DATA

  // Build every calendar day of the selected month so the X-axis never skips a date
  const byDate = {}
  trend.forEach(r => { byDate[r.date] = r })

  let labels
  if (selectedYear && selectedMonth) {
    const total = daysInMonth(selectedYear, selectedMonth)
    labels = Array.from({ length: total }, (_, i) => isoDate(selectedYear, selectedMonth, i + 1))
  } else {
    labels = trend.map(r => r.date)
  }
  const planData   = labels.map(d => byDate[d]?.plan ?? null)
  const actualData = labels.map(d => byDate[d]?.actual ?? null)

  const chartData = {
    labels,
    datasets: [
      {
        label: "Target Value", data: planData,
        borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,0.05)",
        pointRadius: 4, pointBackgroundColor: "#3b82f6", pointBorderColor: "#1e40af", pointHoverRadius: 6,
        tension: 0.4, borderWidth: 2, fill: false, spanGaps: true
      },
      {
        label: "Actual Value", data: actualData,
        borderColor: "#8b5cf6", backgroundColor: "rgba(139,92,246,0.05)",
        pointRadius: 4, pointBackgroundColor: "#8b5cf6", pointBorderColor: "#6d28d9", pointHoverRadius: 6,
        tension: 0.4, borderWidth: 2.5, fill: false, spanGaps: true
      },
    ],
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      <SummaryTable summary={data.summary} type="production" />

      {/* Fixed, explicit height — avoids Chart.js canvas growing unbounded
          when a parent flex container briefly reports zero/undefined height. */}
      <div style={{ position: "relative", height: "350px", width: "100%", overflow: "hidden", marginTop: "20px" }}>
        <Line data={chartData} options={baseOptions()} redraw />
      </div>

      <div style={{ marginTop: "12px", padding: "10px", background: "#f5f3ff", borderRadius: "8px", fontSize: "12px", color: "#5b21b6", textAlign: "center" }}>
        💡 Blue line = Target | Purple line = Actual | Shows every day of the month
      </div>
    </div>
  )
}

function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
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

export default ProductValueChart