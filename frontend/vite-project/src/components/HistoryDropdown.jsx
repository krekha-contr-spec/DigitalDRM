// HistoryDropdown.jsx
// Floating "History" control for a single department's detail page.
// Fixed to the bottom-right corner of the viewport (position: fixed) so it
// never participates in normal document flow and can never push/shift the
// main dashboard layout. Collapsed by default; clicking the pill toggles a
// panel that expands/collapses with a smooth CSS transition (max-height +
// opacity + slide), rather than being mounted/unmounted abruptly.

import { useState } from "react"

function HistoryDropdown({ deptName, accentColor = "#3b82f6", columns, rows }) {
  const [open, setOpen] = useState(false)

  const hasRows = Array.isArray(rows) && rows.length > 0

  return (
    <div
      style={{
        position: "fixed",
        bottom: "24px",
        right: "24px",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column-reverse", // button stays anchored at the bottom, panel grows upward
        alignItems: "flex-end",
        gap: "10px",
        pointerEvents: "none", // re-enabled on children so it never blocks clicks elsewhere on the page
      }}
    >
      {/* Toggle pill */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          pointerEvents: "auto",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          background: "white",
          color: "#0f172a",
          border: `1px solid ${accentColor}55`,
          borderRadius: "999px",
          padding: "10px 18px",
          fontSize: "13px",
          fontWeight: 700,
          cursor: "pointer",
          boxShadow: "0 6px 18px rgba(15,23,42,0.18)",
          transition: "transform 0.15s, box-shadow 0.15s",
        }}
        onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)" }}
        onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)" }}
        aria-expanded={open}
        aria-controls="dept-history-panel"
      >
        <span style={{ fontSize: "15px" }}>🕘</span>
        History
        <span
          style={{
            display: "inline-block",
            fontSize: "10px",
            color: accentColor,
            transition: "transform 0.25s ease",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
        >
          ▲
        </span>
      </button>

      {/* Expand/collapse panel */}
      <div
        id="dept-history-panel"
        style={{
          pointerEvents: open ? "auto" : "none",
          width: "min(92vw, 560px)",
          maxHeight: open ? "min(60vh, 460px)" : "0px",
          opacity: open ? 1 : 0,
          transform: open ? "translateY(0)" : "translateY(12px)",
          overflow: "hidden",
          background: "white",
          borderRadius: "14px",
          border: "1px solid #e2e8f0",
          boxShadow: "0 16px 40px rgba(15,23,42,0.22)",
          transition: "max-height 0.35s ease, opacity 0.28s ease, transform 0.28s ease",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", maxHeight: "min(60vh, 460px)" }}>
          <div
            style={{
              padding: "14px 18px",
              borderBottom: "1px solid #f1f5f9",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexShrink: 0,
            }}
          >
            <div style={{ fontSize: "13px", fontWeight: 700, color: "#0f172a" }}>
              {deptName} · History
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{
                border: "none",
                background: "transparent",
                color: "#94a3b8",
                fontSize: "16px",
                cursor: "pointer",
                lineHeight: 1,
              }}
              aria-label="Close history"
            >
              ✕
            </button>
          </div>

          <div style={{ overflowY: "auto", flex: 1 }}>
            {!hasRows ? (
              <div style={{ padding: "28px 18px", textAlign: "center", color: "#94a3b8", fontSize: "13px" }}>
                No history records yet
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "#f8fafc" }}>
                    {columns.map(col => (
                      <th
                        key={col.key}
                        style={{
                          textAlign: "left",
                          padding: "8px 12px",
                          color: "#64748b",
                          fontWeight: 700,
                          whiteSpace: "nowrap",
                          borderBottom: "1px solid #e2e8f0",
                        }}
                      >
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      {columns.map(col => {
                        const value = row[col.key]
                        const isVariance = col.key === "variance"
                        const isAchieved = col.key === "achieved_percent"
                        const color = isVariance
                          ? (value >= 0 ? "#16a34a" : "#dc2626")
                          : isAchieved
                          ? (value >= 100 ? "#16a34a" : value >= 80 ? "#d97706" : "#dc2626")
                          : "#1e293b"
                        const display =
                          value === null || value === undefined
                            ? "—"
                            : isAchieved
                            ? `${Number(value).toFixed(1)}%`
                            : typeof value === "number"
                            ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                            : value
                        return (
                          <td key={col.key} style={{ padding: "8px 12px", color, whiteSpace: "nowrap" }}>
                            {isVariance && value > 0 ? `+${display}` : display}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default HistoryDropdown