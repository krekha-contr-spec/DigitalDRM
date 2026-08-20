// DepartmentDetail.jsx
// Shows the chart + summary + history for a SINGLE department — whichever
// one the user clicked on the dashboard grid (PlantDashboard.jsx passes the
// clicked card's name in as `deptName`). The page opens straight into that
// department's KPI chart and data; no other department is fetched or shown.
// The full history table is not shown inline — it lives in a collapsed
// floating dropdown pinned to the bottom-right corner (HistoryDropdown.jsx)
// so it never affects the main page layout.

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "../context/AuthContext"
import RaneLogo from "../assets/Rane_Group_Logo.jpg";
import {
  getProductionTrend, getManpowerTrend, getDespatchTrend, getOVCTrend, getSalesTrend,
  getProductionHistory, getManpowerHistory, getDespatchHistory, getOVCHistory, getSalesHistory,
  getRejectionPPMTrend, getRejectionPPMHistory,
  getProductValueTrend, getProductValueHistory,
} from "../services/api"
import ProductionChart    from "../components/charts/ProductionChart"
import ManpowerChart      from "../components/charts/ManpowerChart"
import DespatchChart      from "../components/charts/DespatchChart"
import OVCChart           from "../components/charts/OVCChart"
import SalesChart         from "../components/charts/SalesChart"
import RejectionPPMChart  from "../components/charts/RejectionPPMChart"
import ProductValueChart  from "../components/charts/ProductValueChart"
import HistoryDropdown    from "../components/HistoryDropdown"

const DEPT_CONFIG = {
  Production: {
    icon: "⚙️", accentColor: "#3b82f6",
    chartTitle: "Production Performance Trend",
    getTrend: (pid, y, m, v) => getProductionTrend(pid, y, m, v),
    getHistory: (pid) => getProductionHistory(pid),
    ChartComponent: ProductionChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"       },
      { key: "month",            label: "Month"      },
      { key: "plan",             label: "Target"     },
      { key: "actual",           label: "Actual"     },
      { key: "variance",         label: "Variance"   },
      { key: "achieved_percent", label: "Achieved %" },
    ],
  },
  Manpower: {
    icon: "👷", accentColor: "#7c3aed",
    chartTitle: "Manpower Performance Trend",
    getTrend: (pid, y, m, v) => getManpowerTrend(pid, y, m, v),
    getHistory: (pid) => getManpowerHistory(pid),
    ChartComponent: ManpowerChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"            },
      { key: "month",            label: "Month"           },
      { key: "plan",             label: "Target"          },
      { key: "actual",           label: "Actual (Present)"},
      { key: "variance",         label: "Variance"        },
      { key: "achieved_percent", label: "Achieved %"      },
    ],
  },
  Despatch: {
    icon: "🚚", accentColor: "#0891b2",
    chartTitle: "Despatch Performance Trend",
    getTrend: (pid, y, m, v) => getDespatchTrend(pid, y, m, v),
    getHistory: (pid) => getDespatchHistory(pid),
    ChartComponent: DespatchChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"        },
      { key: "month",            label: "Month"       },
      { key: "customer_name",    label: "Customer"    },
      { key: "month_plan",       label: "Month Plan"  },
      { key: "mtd_actual",       label: "MTD Actual"  },
      { key: "variance",         label: "Variance"    },
      { key: "achieved_percent", label: "Achieved %"  },
    ],
  },
  "OVC Elements": {
    icon: "📐", accentColor: "#d97706",
    chartTitle: "OVC Elements Performance Trend",
    getTrend: (pid, y, m, v) => getOVCTrend(pid, y, m, v),
    getHistory: (pid) => getOVCHistory(pid),
    ChartComponent: OVCChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"         },
      { key: "month",            label: "Month"        },
      { key: "element_type",     label: "Element Type" },
      { key: "plan",             label: "Target"       },
      { key: "actual",           label: "Actual"       },
      { key: "variance",         label: "Variance"     },
      { key: "achieved_percent", label: "Achieved %"   },
    ],
  },
  Sales: {
    icon: "💰", accentColor: "#16a34a",
    chartTitle: "Sales Performance Trend",
    getTrend: (pid, y, m, v) => getSalesTrend(pid, y, m, v),
    getHistory: (pid) => getSalesHistory(pid),
    ChartComponent: SalesChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"        },
      { key: "month",            label: "Month"       },
      { key: "segment",          label: "Segment"     },
      { key: "month_plan",       label: "Month Plan"  },
      { key: "mtd_actual",       label: "MTD Actual"  },
      { key: "variance",         label: "Variance"    },
      { key: "achieved_percent", label: "Achieved %"  },
    ],
  },
  "Rejection PPM": {
    icon: "🔻", accentColor: "#ef4444",
    chartTitle: "Rejection PPM Trend",
    getTrend: (pid, y, m, v) => getRejectionPPMTrend(pid, y, m, v),
    getHistory: (pid) => getRejectionPPMHistory(pid),
    ChartComponent: RejectionPPMChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"         },
      { key: "month",            label: "Month"        },
      { key: "element_type",     label: "Type"         },
      { key: "plan",             label: "Target (PPM)" },
      { key: "actual",           label: "Actual (PPM)" },
      { key: "variance",         label: "Variance"     },
      { key: "achieved_percent", label: "Achieved %"   },
    ],
  },
  "Product Value": {
    icon: "💎", accentColor: "#8b5cf6",
    chartTitle: "Product Value Performance Trend",
    getTrend: (pid, y, m, v) => getProductValueTrend(pid, y, m, v),
    getHistory: (pid) => getProductValueHistory(pid),
    ChartComponent: ProductValueChart,
    historyKey: "history",
    columns: [
      { key: "date",             label: "Date"          },
      { key: "month",            label: "Month"         },
      { key: "element_type",     label: "Type"          },
      { key: "plan",             label: "Target Value"  },
      { key: "actual",           label: "Actual Value"  },
      { key: "variance",         label: "Variance"      },
      { key: "achieved_percent", label: "Achieved %"    },
    ],
  },
}

const months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
const years  = [2024, 2025, 2026, 2027, 2028]

// Maps every department-name spelling that can arrive here to its
// DEPT_CONFIG key. Two different parts of the app hand this component a
// department name: PlantDashboard's grid (a Plant Head clicking a card)
// sends the DEPT_CONFIG key as-is (e.g. "OVC Elements"), while a Gen ID's
// (Staff Incharge) own department comes straight from their role/access
// mapping in the database — role_access.role, stored as the lowercase
// underscore slug from AdminDashboard's ROLE_OPTIONS (e.g. "ovc",
// "rejection_ppm", "product_value"). Both spellings, and every plant,
// must resolve to the SAME department dynamically — never silently fall
// through to a default department.
const DEPT_ALIASES = {
  production:      "Production",
  manpower:         "Manpower",
  despatch:         "Despatch",
  sales:            "Sales",
  ovc:              "OVC Elements",
  "ovc elements":   "OVC Elements",
  "rejection ppm":  "Rejection PPM",
  "rejection_ppm":  "Rejection PPM",
  "product value":  "Product Value",
  "product_value":  "Product Value",
}

function resolveDeptName(deptName) {
  if (!deptName) return null
  if (DEPT_CONFIG[deptName]) return deptName
  // Normalize both underscore-slugs (role_access.role, e.g.
  // "rejection_ppm") and space-separated names to the same lookup key
  // so a Gen ID from ANY plant/department resolves correctly, dynamically.
  const normalized = deptName.trim().toLowerCase()
  const alias = DEPT_ALIASES[normalized] || DEPT_ALIASES[normalized.replace(/_/g, " ")]
  return alias && DEPT_CONFIG[alias] ? alias : null
}

function DepartmentDetail({ deptName, plantId, onBack }) {
  const { user } = useAuth()
  const activePlantId = plantId || user.plant_id

  // The logged-in user's own assigned department, resolved dynamically
  // for whichever plant + department they belong to — NOT hardcoded to
  // any single department. If the incoming name doesn't match any known
  // department (a genuinely unrecognized/misconfigured value), we show a
  // clear message below instead of silently defaulting to Production.
  const resolvedName = resolveDeptName(deptName)
  const cfg = resolvedName ? DEPT_CONFIG[resolvedName] : null

  const [selectedYear,  setSelectedYear]  = useState(new Date().getFullYear())
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1)
  const [selectedView,  setSelectedView]  = useState("daily")

  // Data for THIS department only — the whole point of opening this page
  // is to land straight on the selected department's own chart/summary.
  const [deptData, setDeptData] = useState(null)
  const [history,  setHistory]  = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const fetchData = useCallback(async () => {
    if (!cfg) {
      setLoading(false)
      setError(`No dashboard is configured for department "${deptName}". Please contact your admin to check your Data Entry Users department mapping.`)
      return
    }
    setLoading(true)
    setError("")

    try {
      const [trendRes, historyRes] = await Promise.all([
        cfg.getTrend(activePlantId, selectedYear, selectedMonth, selectedView)
          .then(res => res.data)
          .catch(err => ({ error: err.message })),
        cfg.getHistory(activePlantId)
          .then(res => res?.data?.history || [])
          .catch(() => []),
      ])

      setDeptData(trendRes)
      setHistory(historyRes)

      if (trendRes?.error) {
        setError(`Failed to load ${resolvedName} data: ${trendRes.error}`)
      }
    } catch (err) {
      setError("Failed to load department data. Please try again.")
      console.error(err)
    } finally {
      setLoading(false)
    }
    // cfg is derived from resolvedName/deptName, so re-fetch whenever the
    // selected department, plant, or period changes.
  }, [activePlantId, resolvedName, selectedYear, selectedMonth, selectedView])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const data = deptData || {}
  const summary = data?.summary
  const achieved = summary?.achieved_percent
  const statusColor = achieved >= 100 ? "#16a34a" : achieved >= 80 ? "#d97706" : achieved !== undefined && achieved !== null ? "#dc2626" : "#94a3b8"
  const statusLabel = achieved >= 100 ? "🟢 On Track" : achieved >= 80 ? "🟡 Near Target" : achieved !== undefined && achieved !== null ? "🔴 Below Target" : "⚪ No Data"
  const ChartComponent = cfg?.ChartComponent

  // No department could be resolved for this login — show a clear message
  // instead of ever silently defaulting to Production or any other
  // department's data.
  if (!cfg) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "#f1f5f9", padding: 24, textAlign: "center" }}>
        <h2 style={{ color: "#1e293b", marginBottom: 8 }}>Department not configured</h2>
        <p style={{ color: "#64748b", maxWidth: 420 }}>
          {error || `We couldn't match "${deptName}" to a known department dashboard. Please contact your admin to check your Data Entry Users department mapping.`}
        </p>
        <button onClick={onBack} style={{ marginTop: 20, padding: "10px 20px", borderRadius: 8, border: "none", background: "#1e293b", color: "white", cursor: "pointer" }}>
          Go Back
        </button>
      </div>
    )
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "#f1f5f9" }}>

      {/* Header */}
      <div style={{ background: "linear-gradient(135deg,#1e293b 0%,#0f172a 100%)", padding: "16px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", boxShadow: "0 4px 12px rgba(0,0,0,0.15)", flexWrap: "wrap", gap: "16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <img
            src={RaneLogo}
            alt="Rane Madras Ltd"
            style={{ height: "30px", width: "auto", objectFit: "contain" }}
          />
          <div>
            <h1 style={{ color: "white", fontWeight: "700", fontSize: "16px", margin: "0 0 4px 0" }}>
              {cfg.icon} {resolvedName}
            </h1>
            <p style={{ color: "#cbd5e1", fontSize: "12px", margin: 0 }}>
              Plant {activePlantId} · {cfg.chartTitle}
            </p>
          </div>
        </div>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
            <select
              value={selectedView}
              onChange={e => setSelectedView(e.target.value)}
              style={{ 
                padding: "6px 10px", 
                border: "1px solid #64748b", 
                borderRadius: "6px", 
                fontSize: "12px", 
                color: "#e2e8f0", 
                background: "rgba(148,163,184,0.15)", 
                cursor: "pointer" 
              }}
            >
              <option value="daily" style={{ color: "#0f172a", background: "white" }}>Daily</option>
              <option value="monthly" style={{ color: "#0f172a", background: "white" }}>Monthly</option>
              <option value="yearly" style={{ color: "#0f172a", background: "white" }}>Yearly</option>
            </select>
            <select
              value={selectedYear}
              onChange={e => setSelectedYear(parseInt(e.target.value))}
              style={{ 
                padding: "6px 10px", 
                border: "1px solid #64748b", 
                borderRadius: "6px", 
                fontSize: "12px", 
                color: "#e2e8f0", 
                background: "rgba(148,163,184,0.15)", 
                cursor: "pointer" 
              }}
            >
              {years.map(y => <option key={y} value={y} style={{ color: "#0f172a", background: "white" }}>{y}</option>)}
            </select>
            {selectedView === "daily" && (
              <select
                value={selectedMonth}
                onChange={e => setSelectedMonth(parseInt(e.target.value))}
                style={{ 
                  padding: "6px 10px", 
                  border: "1px solid #64748b", 
                  borderRadius: "6px", 
                  fontSize: "12px", 
                  color: "#e2e8f0", 
                  background: "rgba(148,163,184,0.15)", 
                  cursor: "pointer" 
                }}
              >
                {months.map((m, i) => <option key={i} value={i + 1} style={{ color: "#0f172a", background: "white" }}>{m}</option>)}
              </select>
            )}
          </div>
          <button
            onClick={onBack}
            style={{ background: "rgba(148,163,184,0.2)", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>

      {/* Main Content — the single selected department only */}
      <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto" }}>
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "400px" }}>
            <div style={{ fontSize: "48px", marginBottom: "16px" }}>⏳</div>
            <p style={{ color: "#64748b", fontSize: "16px" }}>Loading {resolvedName} data...</p>
          </div>
        ) : error ? (
          <div style={{ background: "#fee2e2", color: "#dc2626", padding: "16px 20px", borderRadius: "8px", fontSize: "14px", textAlign: "center" }}>
            ⚠️ {error}
          </div>
        ) : (
          <div style={{ background: "white", borderRadius: "12px", boxShadow: "0 2px 8px rgba(0,0,0,0.07)", border: "1px solid #e2e8f0", overflow: "hidden" }}>
            {/* Department Header */}
            <div style={{
              padding: "16px 24px",
              background: `linear-gradient(135deg, ${cfg.accentColor}15 0%, transparent 100%)`,
              borderBottom: `3px solid ${cfg.accentColor}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "12px"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <span style={{ fontSize: "24px" }}>{cfg.icon}</span>
                <div>
                  <h2 style={{ margin: 0, fontSize: "16px", fontWeight: "700", color: "#0f172a" }}>
                    {resolvedName}
                  </h2>
                  <p style={{ margin: 0, fontSize: "11px", color: "#64748b" }}>
                    {cfg.chartTitle}
                  </p>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase", fontWeight: "600" }}>Achievement</div>
                  <div style={{ fontSize: "20px", fontWeight: "800", color: statusColor }}>
                    {achieved !== undefined && achieved !== null ? `${achieved.toFixed(1)}%` : "N/A"}
                  </div>
                </div>
                <div style={{
                  padding: "4px 12px",
                  borderRadius: "20px",
                  background: statusColor === "#16a34a" ? "#dcfce7" : statusColor === "#d97706" ? "#fef3c7" : statusColor === "#dc2626" ? "#fee2e2" : "#f1f5f9",
                  color: statusColor === "#16a34a" ? "#166534" : statusColor === "#d97706" ? "#92400e" : statusColor === "#dc2626" ? "#991b1b" : "#64748b",
                  fontSize: "11px",
                  fontWeight: "600"
                }}>
                  {statusLabel}
                </div>
              </div>
            </div>

            {/* Chart Body */}
            <div style={{ padding: "20px", minHeight: "300px" }}>
              {data?.error ? (
                <div style={{ background: "#fee2e2", color: "#dc2626", padding: "12px 16px", borderRadius: "8px", fontSize: "13px" }}>
                  ⚠️ Failed to load data: {data.error}
                </div>
              ) : (
                <div style={{ minHeight: "280px" }}>
                  <ChartComponent
                    data={data}
                    plantId={activePlantId}
                    selectedYear={selectedYear}
                    selectedMonth={selectedMonth}
                    history={history}
                  />
                </div>
              )}
            </div>

            {/* Quick Stats */}
            {summary && (
              <div style={{
                padding: "12px 24px",
                background: "#f8fafc",
                borderTop: "1px solid #e2e8f0",
                display: "flex",
                gap: "24px",
                flexWrap: "wrap",
                fontSize: "12px"
              }}>
                {(summary.plan_total !== undefined || summary.month_plan_total !== undefined) && (
                  <div>
                    <span style={{ color: "#64748b" }}>Plan: </span>
                    <span style={{ fontWeight: "600", color: "#0f172a" }}>
                      {((summary.plan_total ?? summary.month_plan_total) || 0).toLocaleString()}
                    </span>
                  </div>
                )}
                {(summary.actual_total !== undefined || summary.mtd_actual_total !== undefined) && (
                  <div>
                    <span style={{ color: "#64748b" }}>Actual: </span>
                    <span style={{ fontWeight: "600", color: "#0f172a" }}>
                      {((summary.actual_total ?? summary.mtd_actual_total) || 0).toLocaleString()}
                    </span>
                  </div>
                )}
                {summary.variance !== undefined && (
                  <div>
                    <span style={{ color: "#64748b" }}>Variance: </span>
                    <span style={{ fontWeight: "600", color: summary.variance >= 0 ? "#16a34a" : "#dc2626" }}>
                      {summary.variance >= 0 ? "+" : ""}{summary.variance.toLocaleString()}
                    </span>
                  </div>
                )}
                <div style={{ marginLeft: "auto", color: "#94a3b8", fontSize: "11px" }}>
                  {history.length} history records · use the History button (bottom-right) to view
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Floating History dropdown — collapsed by default, expands in place
          over the page (position: fixed) so it never shifts this layout. */}
      <HistoryDropdown
        deptName={resolvedName}
        accentColor={cfg.accentColor}
        columns={cfg.columns}
        rows={history}
      />
    </div>
  )
}

export default DepartmentDetail