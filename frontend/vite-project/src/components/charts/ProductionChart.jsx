import { Line } from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Title, Tooltip, Legend
} from "chart.js"
import SummaryTable from "../SummaryTable"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

function ProductionChart({ data, plantId }) {
  if (!data || !data.trend || data.trend.length === 0) {
    return (
      <div style={{
        textAlign: "center",
        color: "#94a3b8",
        padding: "40px",
        fontSize: "16px"
      }}>
        📊 No production data available for this period
      </div>
    )
  }

  const labels = data.trend.map(d => d.date)
  const actualData = data.trend.map(d => d.actual || 0)

  // Target line is drawn as a single straight, flat horizontal value for
  // the whole period — same visual treatment as the Despatch chart's
  // Month Plan line — instead of a day-by-day zig-zag. The flat value is
  // the average of whatever daily plan/target values were entered for
  // this period, so it still reflects real data even if individual days
  // were entered with slightly different targets.
  const planValues = data.trend.map(d => d.plan).filter(v => v !== null && v !== undefined)
  const targetValue = planValues.length
    ? planValues.reduce((sum, v) => sum + v, 0) / planValues.length
    : 0
  const planData = labels.map(() => targetValue)

  const chartData = {
    labels,
    datasets: [
      {
        label: "Plan / Target",
        data: planData,
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59, 130, 246, 0.05)",
        pointRadius: 0,
        pointHoverRadius: 0,
        tension: 0,
        borderWidth: 2,
        borderDash: [6, 4],
        fill: false,
        spanGaps: true
      },
      {
        label: "Actual Achieved",
        data: actualData,
        borderColor: "#16a34a",
        backgroundColor: "rgba(22, 163, 74, 0.05)",
        pointRadius: 4,
        pointBackgroundColor: "#16a34a",
        pointBorderColor: "#15803d",
        pointHoverRadius: 6,
        tension: 0,
        borderWidth: 2.5,
        fill: false,
        spanGaps: true
      }
    ]
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: "index",
      intersect: false
    },
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          font: { size: 12, weight: "600" },
          padding: 15,
          usePointStyle: true,
          pointStyle: "circle"
        }
      },
      title: { display: false },
      filler: { propagate: true }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: { color: "#f1f5f9", drawBorder: true },
        ticks: {
          font: { size: 12 },
          callback: function (value) {
            return value.toLocaleString()
          }
        }
      },
      x: {
        grid: { color: "#f1f5f9", display: true },
        ticks: {
          font: { size: 11 }
        }
      }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      {/* Summary Table */}
      <SummaryTable summary={data.summary} type="production" />

      {/* Chart */}
      <div style={{
        flex: 1,
        position: "relative",
        minHeight: "350px",
        marginTop: "20px"
      }}>
        <Line data={chartData} options={options} />
      </div>

      {/* Info Footer */}
      <div style={{
        marginTop: "24px",
        padding: "12px",
        background: "#f0f9ff",
        borderRadius: "8px",
        fontSize: "12px",
        color: "#0369a1",
        textAlign: "center"
      }}>
        💡 Dashed blue line = Target (flat) | Green line = Actual | Shows every day of the period
      </div>
    </div>
  )
}

export default ProductionChart