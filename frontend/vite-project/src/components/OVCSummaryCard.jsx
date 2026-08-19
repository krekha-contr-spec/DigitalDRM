// OVCSummaryCard.jsx
// Compact summary card for the OVC Elements department — same size and
// footprint as every other DeptSummaryCard in the grid. The only
// difference from a plain department card is a small colour-coded strip
// showing each sub-element's status at a glance (no table, no extra
// detail) — click through to DepartmentDetail for the full breakdown.

const STATUS_CONFIG = {
  green:  { color: "#16a34a", bg: "#dcfce7", label: "On Track" },
  amber:  { color: "#d97706", bg: "#fef3c7", label: "Near Target" },
  red:    { color: "#dc2626", bg: "#fee2e2", label: "Below Target" },
  nodata: { color: "#64748b", bg: "#f1f5f9", label: "No Data" },
}

const TREND_CONFIG = {
  up:     { icon: "↑", color: "#16a34a", label: "Improving" },
  down:   { icon: "↓", color: "#dc2626", label: "Declining" },
  stable: { icon: "→", color: "#d97706", label: "Stable" },
  none:   { icon: "—", color: "#94a3b8", label: "No trend" },
}

function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—"
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

// Small coloured dot per sub-element, using the exact same status
// thresholds as everywhere else in the app (>=100 green, >=80 amber,
// below red) — a glance-only summary, not a table.
function elementStatusColor(el) {
  const actual = el.actual || 0
  const target = el.plan || 0
  const achv = target > 0 ? (actual / target) * 100 : 0
  if (achv >= 100) return STATUS_CONFIG.green.color
  if (achv >= 80) return STATUS_CONFIG.amber.color
  return STATUS_CONFIG.red.color
}

function OVCSummaryCard({ dept, ovcData, onClick, wide }) {
  const { name, icon, accentColor, status, trend, latestValue, latestLabel, lastUpdated } = dept

  const summary  = ovcData?.summary  || { plan_total: 0, actual_total: 0, achieved_percent: 0 }
  const elements = ovcData?.elements || []

  const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.nodata

  return (
    <div
      onClick={onClick}
      style={{
        background: "white",
        borderRadius: "12px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.07)",
        border: "1px solid #e2e8f0",
        borderLeft: `4px solid ${accentColor}`,
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
        e.currentTarget.style.boxShadow = "0 8px 24px rgba(0,0,0,0.12)"
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
            fontSize: "20px", width: "32px", height: "32px", background: `${accentColor}18`,
            borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>{icon}</span>
          <span style={{ fontWeight: 700, fontSize: "13px", color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {name}
          </span>
        </div>
        <span style={{
          background: statusCfg.bg, color: statusCfg.color, fontSize: "11px", fontWeight: 700,
          padding: "3px 8px", borderRadius: "20px", whiteSpace: "nowrap", flexShrink: 0,
        }}>
          ● {statusCfg.label}
        </span>
      </div>

      {/* Sub-elements — compact list: name, actual/target, status icon.
          2-column layout only when this card is explicitly rendered wide
          (spans 2 grid columns, e.g. PlantDashboard.jsx); a normal
          single-column card (e.g. President's plant drill-down grid)
          keeps a single column so text never gets cut off at the edge. */}
      {elements.length > 0 && (
        <div style={{
          display: "grid", gridTemplateColumns: wide ? "1fr 1fr" : "1fr", columnGap: "16px", rowGap: "6px",
          borderTop: "1px solid #f1f5f9", paddingTop: "8px",
        }}>
          {elements.map(el => {
            const actual = el.actual || 0
            const target = el.plan || 0
            const color = elementStatusColor(el)
            return (
              <div key={el.element_type} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px", fontSize: "13px", minWidth: 0 }}>
                <span style={{ display: "flex", alignItems: "center", gap: "5px", color: "#334155", fontWeight: 500, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: color, flexShrink: 0 }} />
                  {el.element_type}
                </span>
                <span style={{ color: "#94a3b8", whiteSpace: "nowrap", flexShrink: 0, fontSize: "13px" }}>
                  <span style={{ fontWeight: 700, color, fontSize: "13px" }}>{fmt(actual)}</span> / {fmt(target)}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Last updated */}
      <div style={{ fontSize: "11px", color: "#94a3b8", borderTop: elements.length > 0 ? "none" : "1px solid #f1f5f9", paddingTop: elements.length > 0 ? 0 : "8px" }}>
        Last updated: {lastUpdated || "—"}
      </div>

      {/* Click hint */}
      <div style={{ fontSize: "11px", color: accentColor, fontWeight: 600, textAlign: "right", marginTop: "-4px" }}>
        View Details →
      </div>
    </div>
  )
}

export default OVCSummaryCard