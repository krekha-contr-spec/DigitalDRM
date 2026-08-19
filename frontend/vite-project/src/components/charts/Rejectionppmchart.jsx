// RejectionPPMChart.jsx — Monthly Trend View (like Sales chart)
import { useState, useEffect } from "react"
import { Line } from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Title, Tooltip, Legend
} from "chart.js"
import SummaryTable from "../SummaryTable"
import { getRejectionPPMMonthlyTrend } from "../../services/api"

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const NO_DATA = (
  <div style={{ textAlign: "center", color: "#94a3b8", padding: "60px 20px", fontSize: "15px" }}>
    📊 No Rejection PPM data available for this period
  </div>
)

function RejectionPPMChart({ data, selectedYear, selectedView, history, plantId }) {
  const [monthlyData, setMonthlyData] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!plantId || !selectedYear) return
    let cancelled = false
    setLoading(true)
    
    // Fetch monthly trend data
    getRejectionPPMMonthlyTrend(plantId, selectedYear)
      .then(res => { 
        if (!cancelled) {
          const data = res?.data?.monthly || []
          setMonthlyData(data)
        }
      })
      .catch(() => { if (!cancelled) setMonthlyData([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [plantId, selectedYear])

  // If no data
  if (monthlyData.length === 0 && !loading) {
    return NO_DATA
  }

  // Prepare data for all 12 months
  const allMonths = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
  ]
  
  // Create a map of month data
  const monthMap = {}
  monthlyData.forEach(m => {
    monthMap[m.month] = {
      plan: m.plan || 0,
      actual: m.actual || 0,
      month_name: m.month_name
    }
  })
  
  // Build data arrays for all 12 months
  const labels = allMonths
  const planData = allMonths.map((_, index) => {
    const monthNum = index + 1
    return monthMap[monthNum] ? monthMap[monthNum].plan : 0
  })
  const actualData = allMonths.map((_, index) => {
    const monthNum = index + 1
    return monthMap[monthNum] ? monthMap[monthNum].actual : 0
  })

  // Calculate totals
  const totalPlan = planData.reduce((sum, val) => sum + val, 0)
  const totalActual = actualData.reduce((sum, val) => sum + val, 0)
  const totalVariance = totalActual - totalPlan
  const totalAchieved = totalPlan > 0 ? ((totalActual / totalPlan) * 100) : 0
  const isOverTarget = totalVariance >= 0

  const chartConfig = {
    labels,
    datasets: [
      {
        label: "Target (PPM)",
        data: planData,
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59,130,246,0.05)",
        pointRadius: 4,
        pointBackgroundColor: "#3b82f6",
        pointBorderColor: "#1e40af",
        pointHoverRadius: 6,
        tension: 0.4,
        borderWidth: 2,
        fill: false,
        spanGaps: true
      },
      {
        label: "Actual (PPM)",
        data: actualData,
        borderColor: "#ef4444",
        backgroundColor: "rgba(239,68,68,0.05)",
        pointRadius: 4,
        pointBackgroundColor: "#ef4444",
        pointBorderColor: "#b91c1c",
        pointHoverRadius: 6,
        tension: 0.4,
        borderWidth: 2.5,
        fill: false,
        spanGaps: true
      },
    ],
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      
      {/* Department Summary Cards */}
      <div style={{ 
        display: "grid", 
        gridTemplateColumns: "repeat(4, 1fr)", 
        gap: "12px", 
        marginBottom: "20px"
      }}>
        <div style={{ 
          background: "white", 
          borderRadius: "8px", 
          padding: "16px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ fontSize: "11px", color: "#64748b", fontWeight: "600", textTransform: "uppercase" }}>
            Total Target
          </div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "#0f172a", marginTop: "4px" }}>
            {totalPlan.toLocaleString()}
          </div>
          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "2px" }}>
            Unit: PPM
          </div>
        </div>
        
        <div style={{ 
          background: "white", 
          borderRadius: "8px", 
          padding: "16px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ fontSize: "11px", color: "#64748b", fontWeight: "600", textTransform: "uppercase" }}>
            Actual Achieved
          </div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "#0f172a", marginTop: "4px" }}>
            {totalActual.toLocaleString()}
          </div>
          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "2px" }}>
            Unit: PPM
          </div>
        </div>
        
        <div style={{ 
          background: "white", 
          borderRadius: "8px", 
          padding: "16px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ fontSize: "11px", color: "#64748b", fontWeight: "600", textTransform: "uppercase" }}>
            Variance
          </div>
          <div style={{ 
            fontSize: "20px", 
            fontWeight: "700", 
            color: isOverTarget ? "#16a34a" : "#dc2626",
            marginTop: "4px"
          }}>
            {isOverTarget ? "+" : ""}{totalVariance.toLocaleString()}
          </div>
          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "2px" }}>
            Unit: PPM
          </div>
        </div>
        
        <div style={{ 
          background: "white", 
          borderRadius: "8px", 
          padding: "16px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ fontSize: "11px", color: "#64748b", fontWeight: "600", textTransform: "uppercase" }}>
            Achievement
          </div>
          <div style={{ 
            fontSize: "20px", 
            fontWeight: "700", 
            color: totalAchieved >= 100 ? "#16a34a" : totalAchieved >= 80 ? "#f59e0b" : "#dc2626",
            marginTop: "4px"
          }}>
            {totalAchieved.toFixed(1)}%
          </div>
          <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "2px" }}>
            {isOverTarget ? "✅ Over Target" : "⚠️ Below Target"}
          </div>
        </div>
      </div>

      {/* Chart Section */}
      <div style={{ 
        background: "white", 
        borderRadius: "12px", 
        border: "1px solid #e2e8f0",
        padding: "20px"
      }}>
        <div style={{ 
          display: "flex", 
          justifyContent: "space-between", 
          alignItems: "center",
          marginBottom: "16px"
        }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: "700", color: "#0f172a" }}>
              Rejection PPM Trend
            </h3>
            <p style={{ margin: "2px 0 0 0", fontSize: "12px", color: "#64748b" }}>
              {selectedYear} · Month-wise Comparison
            </p>
          </div>
        </div>
        
        <div style={{ height: "320px", position: "relative" }}>
          <Line data={chartConfig} options={chartOptions} redraw />
        </div>
        
        {/* Legend */}
        <div style={{ 
          display: "flex", 
          justifyContent: "center", 
          gap: "24px",
          marginTop: "16px",
          paddingTop: "12px",
          borderTop: "1px solid #f1f5f9"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ 
              width: "20px", 
              height: "3px", 
              background: "#3b82f6",
              borderRadius: "2px"
            }}></span>
            <span style={{ fontSize: "12px", color: "#475569" }}>Target (PPM)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ 
              width: "20px", 
              height: "3px", 
              background: "#ef4444",
              borderRadius: "2px"
            }}></span>
            <span style={{ fontSize: "12px", color: "#475569" }}>Actual (PPM)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ 
              fontSize: "11px", 
              color: "#94a3b8"
            }}>
              📊 Lower actual = Better
            </span>
          </div>
        </div>
      </div>

      {/* Footer Note */}
      <div style={{ 
        marginTop: "12px", 
        padding: "10px 16px", 
        background: "#f8fafc", 
        borderRadius: "8px",
        border: "1px solid #e2e8f0",
        fontSize: "11px",
        color: "#64748b",
        textAlign: "center"
      }}>
        💡 Showing month-wise Rejection PPM data for {selectedYear}
      </div>
    </div>
  )
}

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { 
    mode: "index", 
    intersect: false 
  },
  plugins: {
    legend: { 
      display: false
    },
    tooltip: {
      callbacks: {
        title: function(items) {
          return `${items[0].label} ${items[0].dataset.label}`;
        },
        label: function(context) {
          let label = context.dataset.label || '';
          let value = context.raw || 0;
          return `${label}: ${value.toLocaleString()} PPM`;
        }
      }
    }
  },
  scales: {
    y: { 
      beginAtZero: true, 
      grid: { color: "#f1f5f9" }, 
      ticks: { 
        font: { size: 11 },
        callback: function(value) {
          return value.toLocaleString();
        }
      },
      title: { 
        display: true, 
        text: "PPM", 
        font: { size: 11, weight: "600" }, 
        color: "#64748b" 
      }
    },
    x: { 
      grid: { display: false },
      ticks: { 
        font: { size: 11 },
        maxRotation: 0
      },
      title: { 
        display: true, 
        text: "Month", 
        font: { size: 11, weight: "600" }, 
        color: "#64748b" 
      }
    },
  },
}

export default RejectionPPMChart