// DeptSummaryCard.jsx
// Reusable summary card for the dashboard grid.
// Each department gets its own accent colour; the left border stripe is
// the visual signature that makes the grid feel like a real ops board.

const STATUS_CONFIG = {
  green:  { color: "#16a34a", bg: "#dcfce7", label: "On Track",  dot: "🟢" },
  amber:  { color: "#d97706", bg: "#fef3c7", label: "Near Target", dot: "🟡" },
  red:    { color: "#dc2626", bg: "#fee2e2", label: "Below Target", dot: "🔴" },
  nodata: { color: "#64748b", bg: "#f1f5f9", label: "No Data",    dot: "⚪" },
}

const TREND_CONFIG = {
  up:     { icon: "↑", color: "#16a34a", label: "Improving" },
  down:   { icon: "↓", color: "#dc2626", label: "Declining" },
  stable: { icon: "→", color: "#d97706", label: "Stable"    },
  none:   { icon: "—", color: "#94a3b8", label: "No trend"  },
}

/**
 * Determine the color for Actual value based on performance against Target
 */
const getActualColor = (kpi, target, status) => {
  if (kpi === null || kpi === undefined || target === null || target === undefined) {
    return "#64748b"; // Gray for no data
  }

  // Use the already-calculated status from backend (preferred)
  if (status === "green") return "#16a34a"; // Green - On Track
  if (status === "amber") return "#d97706"; // Orange - Near Target
  if (status === "red") return "#dc2626";   // Red - Below Target

  // Fallback calculation (safety net)
  const actual = Number(kpi);
  const targetValue = Number(target);

  if (isNaN(actual) || isNaN(targetValue) || targetValue === 0) {
    return "#64748b";
  }

  const achievement = (actual / targetValue) * 100;

  if (achievement >= 100) return "#16a34a"; // Green
  if (achievement >= 90) return "#d97706";  // Orange
  return "#dc2626";                         // Red
};

function DeptSummaryCard({ dept, onClick, deemphasizeVariance, primary }) {
  const { 
    name, 
    icon, 
    accentColor, 
    status, 
    trend, 
    latestValue, 
    latestLabel, 
    lastUpdated, 
    kpi, 
    kpiLabel, 
    target, 
    targetLabel 
  } = dept

  const statusCfg  = STATUS_CONFIG[status]  || STATUS_CONFIG.nodata
  const trendCfg   = TREND_CONFIG[trend]    || TREND_CONFIG.none
  
  // Determine actual value color based on performance
  const actualColor = getActualColor(kpi, target, status);
  
  // Variance color for the percentage text (keep existing logic)
  const varianceColor = (latestValue && latestValue.startsWith("+")) ? "#16a34a"
                       : (latestValue && latestValue.startsWith("-")) ? "#dc2626"
                       : accentColor

  return (
    <div
      onClick={onClick}
      style={{
        background: "white",
        borderRadius: "12px",
        boxShadow: primary ? "0 4px 14px rgba(0,0,0,0.1)" : "0 2px 8px rgba(0,0,0,0.07)",
        border: "1px solid #e2e8f0",
        borderLeft: `${primary ? 6 : 4}px solid ${accentColor}`,
        padding: "20px 20px 16px",
        cursor: "pointer",
        transition: "transform 0.15s, box-shadow 0.15s",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        minWidth: 0,
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = "translateY(-3px)"
        e.currentTarget.style.boxShadow = `0 8px 24px rgba(0,0,0,0.12)`
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = "translateY(0)"
        e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.07)"
      }}
    >
      {/* Top row: icon + name + status badge */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
          <span style={{
            fontSize: "20px",
            width: "32px",
            height: "32px",
            background: `${accentColor}18`,
            borderRadius: "8px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}>{icon}</span>
          <span style={{ fontWeight: "700", fontSize: "13px", color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {name}
          </span>
          {primary && (
            <span style={{
              fontSize: "9px", fontWeight: 700, color: accentColor, background: `${accentColor}18`,
              padding: "2px 6px", borderRadius: "10px", whiteSpace: "nowrap", flexShrink: 0,
            }}>
              PRIMARY KPI
            </span>
          )}
        </div>
        <span style={{
          background: statusCfg.bg,
          color: statusCfg.color,
          fontSize: "11px",
          fontWeight: "700",
          padding: "3px 8px",
          borderRadius: "20px",
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}>
          {statusCfg.dot} {statusCfg.label}
        </span>
      </div>

      {/* Target vs Actual — the two numbers a plant/department card must
          answer at a glance, always shown big regardless of view. */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: "18px" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "2px" }}>
            {kpiLabel || "Actual"}
          </div>
          {/* Actual value - Color based on performance against Target */}
          <div style={{ 
            fontSize: "28px", 
            fontWeight: "800", 
            lineHeight: 1.1, 
            color: actualColor,
            transition: "color 0.3s ease"
          }}>
            {kpi !== null && kpi !== undefined ? kpi : "—"}
          </div>
        </div>
        <div style={{ fontSize: "20px", color: "#cbd5e1", fontWeight: 300, paddingBottom: "2px" }}>/</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "2px" }}>
            {targetLabel || "Target"}
          </div>
          {/* Target value - Always Blue */}
          <div style={{ 
            fontSize: "28px", 
            fontWeight: "800", 
            lineHeight: 1.1, 
            color: "#4e4e4e" // Fixed blue for all departments
          }}>
            {target !== null && target !== undefined ? target : "—"}
          </div>
        </div>
      </div>

      {deemphasizeVariance ? (
        <>
          {/* President view: trend row unchanged. */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
            <span style={{
              display: "flex", alignItems: "center", gap: "4px",
              fontSize: "12px", fontWeight: "600", color: trendCfg.color,
            }}>
              <span style={{ fontSize: "14px" }}>{trendCfg.icon}</span>
              {trendCfg.label}
            </span>
          </div>

          {/* Last updated (unchanged) + % Achieved, now moved here as
              secondary info in the bottom-right corner — never the
              headline figure. Already capped at 100%: only the excess
              is shown (e.g. 120% -> +20%); values at or under 100%
              show their variance from target as before. */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", borderTop: "1px solid #f1f5f9", paddingTop: "8px" }}>
            <span style={{ fontSize: "11px", color: "#94a3b8" }}>
              Last updated: {lastUpdated || "—"}
            </span>
            <span style={{ display: "flex", alignItems: "baseline", gap: "4px" }}>
              <span style={{ fontSize: "13px", fontWeight: 700, color: varianceColor }}>
                {latestValue !== null && latestValue !== undefined ? latestValue : "—"}
              </span>
              <span style={{ fontSize: "16px", color: "#94a3b8" }}>% Achieved</span>
            </span>
          </div>
        </>
      ) : (
        <>
          {/* Plant Head / Staff view: trend + %-vs-target variance shown
              together, right below the big Target/Actual numbers above. */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
            <span style={{
              display: "flex", alignItems: "center", gap: "4px",
              fontSize: "12px", fontWeight: "600", color: trendCfg.color,
            }}>
              <span style={{ fontSize: "14px" }}>{trendCfg.icon}</span>
              {trendCfg.label}
            </span>
            <span style={{ fontSize: "12px", fontWeight: 700, color: varianceColor }}>
              {latestValue !== null && latestValue !== undefined ? latestValue : "—"}
              <span style={{ fontWeight: 400, color: "#94a3b8" }}> {latestLabel}</span>
            </span>
          </div>

          {/* Last updated */}
          <div style={{ fontSize: "11px", color: "#94a3b8", borderTop: "1px solid #f1f5f9", paddingTop: "8px" }}>
            Last updated: {lastUpdated || "—"}
          </div>
        </>
      )}

      {/* Click hint */}
      <div style={{ fontSize: "11px", color: accentColor, fontWeight: "600", textAlign: "right", marginTop: "-4px" }}>
        View Details →
      </div>
    </div>
  )
}

export default DeptSummaryCard