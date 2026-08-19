function SummaryTable({ summary, type = "production" }) {
  if (!summary) {
    return (
      <div style={{ color: "#94a3b8", textAlign: "center", padding: "16px", fontSize: "13px" }}>
        No summary data
      </div>
    )
  }

  // Handle different field names for different types
  const isSalesType = type === "sales" || type === "despatch"
  const planKey = isSalesType ? "month_plan_total" : "plan_total"
  const actualKey = isSalesType ? "mtd_actual_total" : "actual_total"

  const plan = summary[planKey] || 0
  const actual = summary[actualKey] || 0
  const variance = summary.variance || 0
  const achievedPercent = summary.achieved_percent || 0

  const varianceColor = variance < 0 ? "#dc2626" : "#16a34a"
  const varianceSign = variance >= 0 ? "+" : ""

  return (
    <div style={{
      marginBottom: "32px",
      padding: "20px",
      background: "#f8fafc",
      borderRadius: "12px",
      border: "1px solid #e2e8f0"
    }}>
      <h3 style={{
        color: "#1e293b",
        fontSize: "14px",
        fontWeight: "700",
        margin: "0 0 16px 0"
      }}>
        📊 Department Summary
      </h3>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap: "20px"
      }}>
        {/* Plan */}
        <div style={{
          background: "white",
          padding: "16px",
          borderRadius: "8px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", marginBottom: "8px" }}>
            Plan / Target
          </div>
          <div style={{
            color: "#3b82f6",
            fontSize: "24px",
            fontWeight: "700",
            marginBottom: "4px"
          }}>
            {plan.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div style={{ color: "#94a3b8", fontSize: "11px" }}>
            Total planned
          </div>
        </div>

        {/* Actual */}
        <div style={{
          background: "white",
          padding: "16px",
          borderRadius: "8px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", marginBottom: "8px" }}>
            Actual Achieved
          </div>
          <div style={{
            color: "#16a34a",
            fontSize: "24px",
            fontWeight: "700",
            marginBottom: "4px"
          }}>
            {actual.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div style={{ color: "#94a3b8", fontSize: "11px" }}>
            Total achieved
          </div>
        </div>

        {/* Variance */}
        <div style={{
          background: "white",
          padding: "16px",
          borderRadius: "8px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", marginBottom: "8px" }}>
            Variance
          </div>
          <div style={{
            color: varianceColor,
            fontSize: "24px",
            fontWeight: "700",
            marginBottom: "4px"
          }}>
            {varianceSign}{variance.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div style={{ color: "#94a3b8", fontSize: "11px" }}>
            {variance >= 0 ? "Over" : "Under"} target
          </div>
        </div>

        {/* Achieved % */}
        <div style={{
          background: "white",
          padding: "16px",
          borderRadius: "8px",
          border: "1px solid #e2e8f0",
          textAlign: "center"
        }}>
          <div style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", marginBottom: "8px" }}>
            Achieved %
          </div>
          <div style={{
            color: achievedPercent >= 100 ? "#16a34a" : achievedPercent >= 80 ? "#ea580c" : "#dc2626",
            fontSize: "24px",
            fontWeight: "700",
            marginBottom: "4px"
          }}>
            {achievedPercent.toLocaleString(undefined, { maximumFractionDigits: 1 })}%
          </div>
          <div style={{ color: "#94a3b8", fontSize: "11px" }}>
            {achievedPercent >= 100 ? "✅ Exceeded" : achievedPercent >= 80 ? "⚠️ Near target" : "❌ Below target"}
          </div>
        </div>
      </div>
    </div>
  )
}

export default SummaryTable