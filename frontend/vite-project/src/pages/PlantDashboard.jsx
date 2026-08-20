// PlantDashboard.jsx — Dashboard Summary Grid (View Dashboard page)
// Shows one card per department; clicking a card navigates to DepartmentDetail.

import { useEffect, useState, useCallback, useRef } from "react"
import { useAuth } from "../context/AuthContext"
import {
  getProductionTrend, getManpowerTrend,
  getDespatchTrend, getOVCTrend, getSalesTrend,
  getRejectionPPMTrend, getProductValueTrend,
} from "../services/api"
import DeptSummaryCard from "../components/DeptSummaryCard"
import OVCSummaryCard from "../components/OVCSummaryCard"
import RaneLogo from "../assets/Rane_Group_Logo.jpg";

// Per-department visual identity
// Order matters here — it's the grid fill order. Product Value sits
// right after Despatch so it fills out row 1 (Production, Manpower,
// Despatch, Product Value); OVC Elements comes next and, since it spans
// 2 grid columns, naturally wraps to start row 2, followed by Sales and
// Rejection PPM.
const DEPT_META = {
  Production:      { icon: "⚙️",  accentColor: "#3b82f6", trendType: "plan_actual" },
  Manpower:        { icon: "👷",  accentColor: "#7c3aed", trendType: "plan_actual" },
  Despatch:        { icon: "🚚",  accentColor: "#0891b2", trendType: "month_mtd"   },
  "Product Value": { icon: "💎",  accentColor: "#f7349f", trendType: "plan_actual" },
  "OVC Elements":  { icon: "📐",  accentColor: "#d97706", trendType: "plan_actual" },
  Sales:           { icon: "💰",  accentColor: "#16a34a", trendType: "month_mtd"   },
  "Rejection PPM": { icon: "🔻",  accentColor: "#ef4444", trendType: "plan_actual" },
}


// Format a timestamp as "05 Jul 2026" — date only, no time shown.
function formatLastUpdated(raw) {
  if (!raw) return "—"
  const d = new Date(raw)
  if (isNaN(d)) return raw

  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
}

// Derive status and trend from summary data
function deriveCard(name, apiData, type) {
  const meta    = DEPT_META[name] || { icon: "📊", accentColor: "#64748b", trendType: "plan_actual" }
  const summary = apiData?.summary
  const trend   = apiData?.trend || apiData?.customers || apiData?.segments || apiData?.elements || []

  if (!summary && trend.length === 0) {
    return { name, ...meta, status: "nodata", trend: "none", latestValue: null, latestLabel: "No data", lastUpdated: "—", kpi: null, kpiLabel: "", target: null, targetLabel: "" }
  }

  const isMtd     = meta.trendType === "month_mtd"
  const plan      = isMtd ? (summary?.month_plan_total || 0) : (summary?.plan_total || 0)
  const actual    = isMtd ? (summary?.mtd_actual_total  || 0) : (summary?.actual_total  || 0)
  const achieved  = summary?.achieved_percent || 0

  const status    = achieved >= 100 ? "green" : achieved >= 80 ? "amber" : "red"

  // Trend: compare last two data points
  let trendDir = "stable"
  if (trend.length >= 2) {
    const last  = trend[trend.length - 1]
    const prev  = trend[trend.length - 2]
    const lastA = last.actual  ?? last.mtd_actual  ?? 0
    const prevA = prev.actual  ?? prev.mtd_actual  ?? 0
    if (lastA > prevA)      trendDir = "up"
    else if (lastA < prevA) trendDir = "down"
  }

  const lastPoint   = trend[trend.length - 1]

  // Prefer backend-provided last_updated (real save timestamp, date+time);
  // fall back to the last trend point's date if the backend value is missing.
  const lastUpdatedRaw = apiData?.last_updated || lastPoint?.date_full || lastPoint?.date
  const lastUpdated = formatLastUpdated(lastUpdatedRaw)

  // Show variance from 100% target: e.g. 157.8% → +57.8%, 96.3% → -3.7%
  const variance100 = achieved - 100
  const sign        = variance100 >= 0 ? "+" : ""
  const latestValue = achieved ? `${sign}${variance100.toFixed(1)}%` : null
  const latestLabel = isMtd ? "vs 100% Target (MTD)" : "vs 100% Target"
  const kpi         = actual ? actual.toLocaleString(undefined, { maximumFractionDigits: 0 }) : null
  const kpiLabel    = isMtd ? "MTD actual" : "actual"
  const target      = plan ? plan.toLocaleString(undefined, { maximumFractionDigits: 0 }) : null
  const targetLabel = isMtd ? "MTD target" : "target"

  return { name, ...meta, status, trend: trendDir, latestValue, latestLabel, lastUpdated, kpi, kpiLabel, target, targetLabel }
}

const HEADER_STYLE = {
  background: "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
  padding: "16px 32px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexShrink: 0,
  boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
  flexWrap: "wrap",
  gap: "16px",
}

function PlantDashboard({ plantId, onBack, isPresident, onReports, onDeptClick, refreshToken }) {
  const { user, logout } = useAuth()
  const activePlantId = plantId || user.plant_id

  const [selectedYear]  = useState(new Date().getFullYear())
  const [selectedMonth] = useState(new Date().getMonth() + 1)

  const [dataMap,      setDataMap]      = useState({})
  const [loading,      setLoading]      = useState(false)
  const [error,        setError]        = useState("")
  const [lastRefresh,  setLastRefresh]  = useState(new Date())

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [prod, mp, desp, ovc, sales, rejPPM, prodVal] = await Promise.all([
        getProductionTrend(activePlantId, selectedYear, selectedMonth, "daily"),
        getManpowerTrend(activePlantId, selectedYear, selectedMonth, "daily"),
        getDespatchTrend(activePlantId, selectedYear, selectedMonth, "daily"),
        getOVCTrend(activePlantId, selectedYear, selectedMonth, "daily"),
        getSalesTrend(activePlantId, selectedYear, selectedMonth, "daily"),
        getRejectionPPMTrend(activePlantId, selectedYear, selectedMonth, "daily"),
        getProductValueTrend(activePlantId, selectedYear, selectedMonth, "daily"),
      ])
      setDataMap({
        Production:      prod.data,
        Manpower:        mp.data,
        Despatch:        desp.data,
        "OVC Elements":  ovc.data,
        Sales:           sales.data,
        "Rejection PPM": rejPPM.data,
        "Product Value": prodVal.data,
      })
      setLastRefresh(new Date())
    } catch (err) {
      setError(err.message || "Failed to load data")
    } finally {
      setLoading(false)
    }
  }, [activePlantId, selectedYear, selectedMonth])

  useEffect(() => { fetchData() }, [fetchData, refreshToken])

  // ── Auto-refresh every 30 seconds ────────────────────────────────────────
  const REFRESH_INTERVAL_MS = 30_000
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL_MS / 1000)
  const countdownRef = useRef(REFRESH_INTERVAL_MS / 1000)

  useEffect(() => {
    countdownRef.current = REFRESH_INTERVAL_MS / 1000
    setCountdown(REFRESH_INTERVAL_MS / 1000)

    const refreshTimer = setInterval(() => {
      fetchData()
      countdownRef.current = REFRESH_INTERVAL_MS / 1000
      setCountdown(REFRESH_INTERVAL_MS / 1000)
    }, REFRESH_INTERVAL_MS)

    const tickTimer = setInterval(() => {
      countdownRef.current -= 1
      setCountdown(countdownRef.current)
    }, 1000)

    return () => {
      clearInterval(refreshTimer)
      clearInterval(tickTimer)
    }
  }, [fetchData])

  let cards = Object.entries(DEPT_META).map(([name]) =>
    deriveCard(name, dataMap[name], DEPT_META[name].trendType)
  )

  // President view: Production and Sales are the two primary KPIs and
  // get top billing in the grid — same cards, same data, just reordered
  // so the CEO's two most important numbers are the first thing seen.
  if (isPresident) {
    const primaryNames = ["Production", "Sales"]
    cards = [
      ...primaryNames.map(n => cards.find(c => c.name === n)).filter(Boolean),
      ...cards.filter(c => !primaryNames.includes(c.name)),
    ]
  }

  const onTrack  = cards.filter(c => c.status === "green").length
  const atRisk   = cards.filter(c => c.status === "amber").length
  const critical = cards.filter(c => c.status === "red").length

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "#f1f5f9" }}>

      {/* Header */}
      <div style={HEADER_STYLE}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flex: "1 1 auto", minWidth: "280px" }}>
          <img
            src={RaneLogo}
            alt="Rane Madras Ltd"
            style={{ height: "30px", width: "auto", objectFit: "contain" }}
          />
          <div>
            <h1 style={{ color: "white", fontWeight: "700", fontSize: "16px", margin: "0 0 4px 0" }}>
              Rane Madras Ltd - Digital DRM
            </h1>
            <p style={{ color: "#cbd5e1", fontSize: "12px", margin: 0 }}>
              Plant {activePlantId} • Dashboard Overview
            </p>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <span style={{ background: "rgba(59,130,246,0.2)", border: "1px solid #3b82f6", color: "#93c5fd", fontSize: "11px", padding: "6px 10px", borderRadius: "6px", fontWeight: "600", whiteSpace: "nowrap" }}>
            🕐 {lastRefresh.toLocaleTimeString()} · next in {countdown}s
          </span>
          <button
            onClick={() => onReports(activePlantId)}
            style={{ background: "#7c3aed", color: "white", border: "none", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
          >
            📊 Reports
          </button>
          {isPresident && (
            <button
              onClick={onBack}
              style={{ background: "rgba(148,163,184,0.2)", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
            >
              ← Back
            </button>
          )}
          {!isPresident && (
            <button
              onClick={onBack}
              style={{ background: "rgba(148,163,184,0.2)", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
            >
              ← Home
            </button>
          )}
          <button
            onClick={logout}
            style={{ background: "rgba(148,163,184,0.2)", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
          >
            Logout
          </button>
        </div>
      </div>

      {/* Page Title Bar */}
      <div style={{ background: "white", borderBottom: "1px solid #e2e8f0", padding: "16px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "20px", fontWeight: "800", color: "#0f172a" }}>
            Plant Performance Dashboard
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#64748b" }}>
            {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "long", year: "numeric" })} · Click any department to drill down
          </p>
        </div>

        {/* Summary pills */}
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <span style={{ background: "#dcfce7", color: "#16a34a", fontSize: "12px", fontWeight: "700", padding: "4px 12px", borderRadius: "20px" }}>
            🟢 {onTrack} On Track
          </span>
          <span style={{ background: "#fef3c7", color: "#d97706", fontSize: "12px", fontWeight: "700", padding: "4px 12px", borderRadius: "20px" }}>
            🟡 {atRisk} Near Target
          </span>
          <span style={{ background: "#fee2e2", color: "#dc2626", fontSize: "12px", fontWeight: "700", padding: "4px 12px", borderRadius: "20px" }}>
            🔴 {critical} Below Target
          </span>
        </div>
      </div>

      {error && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "12px 32px", borderBottom: "1px solid #fecaca", fontSize: "13px", fontWeight: "500" }}>
          ⚠️ {error}
        </div>
      )}

      {/* Responsive grid styles */}
      <style>{`
        .drm-dashboard-grid {
          grid-template-columns: repeat(4, 1fr);
        }
        @media (max-width: 1100px) {
          .drm-dashboard-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
        @media (max-width: 600px) {
          .drm-dashboard-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      {/* Card Grid */}
      <div style={{ flex: 1, padding: "20px 24px", overflowY: "auto" }}>
        {loading && Object.keys(dataMap).length === 0 ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "300px" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "40px", marginBottom: "16px" }}>⏳</div>
              <p style={{ color: "#64748b", fontSize: "15px" }}>Loading department data…</p>
            </div>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "18px",
            width: "100%",
          }}
            className="drm-dashboard-grid"
          >
            {cards.map(card => (
              card.name === "OVC Elements" ? (
                <div key={card.name} style={{ gridColumn: "span 2" }}>
                  <OVCSummaryCard
                    dept={card}
                    ovcData={dataMap["OVC Elements"]}
                    onClick={() => onDeptClick(card.name)}
                    wide
                  />
                </div>
              ) : (
                <DeptSummaryCard
                  key={card.name}
                  dept={card}
                  onClick={() => onDeptClick(card.name)}
                  deemphasizeVariance={isPresident}
                  primary={isPresident && (card.name === "Production" || card.name === "Sales")}
                />
              )
            ))}
          </div>
        )}
      </div>

    </div>
  )
}

export default PlantDashboard