// PlantSummaryOverview.jsx
// "Overall Plant Summary" for the President Dashboard — consolidates all
// five plants into one consolidated view: overall KPIs, plant-wise
// comparison/ranking, trend analysis, charts, and executive insights.
// When an individual plant is selected via the Plant filter, the view
// switches to a plant-specific layout: plant-level KPIs, department
// performance cards, department-wise chart, and a department-wise
// performance table — with NO "Plants On Track" / "Plants Needing
// Attention" / "Needing Attention" boxes, since those are multi-plant
// concepts that only make sense in the unfiltered All Plants view.
//
// IMPORTANT: this component uses ONLY the existing report-generation API
// endpoints (generateMonthlyReport / generateQuarterlyReport /
// generateYearlyReport — the exact same ones the per-plant Reports.jsx
// page already calls), plus the /report-save/overall-summary endpoint
// used by the "Generate Report" button. No new SQL or business logic is
// introduced; this is a pure frontend aggregation/visualization layer on
// top of data the backend already computes and returns today.

import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import DeptSummaryCard from "../components/DeptSummaryCard"
import OVCSummaryCard from "../components/OVCSummaryCard"
import {
  getProductionTrend, getManpowerTrend, getDespatchTrend,
  getOVCTrend, getSalesTrend, getRejectionPPMTrend, getProductValueTrend,
} from "../services/api"
import {
  Bar, Line
} from "react-chartjs-2"
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  BarElement, PointElement, LineElement, Tooltip, Legend
} from "chart.js"
import {
  generateMonthlyReport, generateQuarterlyReport, generateYearlyReport,
  generateOverallSummaryReport,
} from "../services/api"
import RaneLogo from "../assets/Rane_Group_Logo.jpg"

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend)

const PLANTS = [
  { id: 2, name: "Plant 2" },
  { id: 3, name: "Plant 3" },
  { id: 4, name: "Plant 4" },
  { id: 5, name: "Plant 5" },
  { id: 6, name: "Plant 6" },
]

// Same department config/keys used by report_save_routes.py's DEPTS and
// by Reports.jsx — kept identical so labels/keys never drift apart.
const DEPTS = [
  { label: "Production",    key: "production" },
  { label: "Manpower",      key: "manpower" },
  { label: "Sales",         key: "sales" },
  { label: "Despatch",      key: "despatch" },
  { label: "Rejection PPM", key: "rejection_ppm" },
  { label: "Product Value", key: "product_value" },
  { label: "OVC Elements",  key: "ovc" },
]

// Same icon/accent per department as PlantDashboard.jsx's DEPT_META —
// duplicated here (rather than imported) since this file's DEPTS uses
// plan/actual/achieved fields only, with no shared module between them.
const DEPT_VISUAL = {
  Production:      { icon: "⚙️", accentColor: "#3b82f6" },
  Manpower:        { icon: "👷", accentColor: "#7c3aed" },
  Sales:           { icon: "💰", accentColor: "#16a34a" },
  "OVC Elements":  { icon: "📐", accentColor: "#d97706" },
  Despatch:        { icon: "🚚", accentColor: "#0891b2" },
  "Rejection PPM": { icon: "🔻", accentColor: "#ef4444" },
  "Product Value": { icon: "💎", accentColor: "#f7349f" },
}

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
]

// Same thresholds used across the rest of the app (DepartmentDetail.jsx,
// PlantDashboard.jsx) — kept consistent so colors/labels never disagree.
const statusOf = achieved => {
  if (achieved === null || achieved === undefined) return "nodata"
  if (achieved >= 100) return "green"
  if (achieved >= 80)  return "amber"
  return "red"
}
const STATUS_COLOR = { green: "#16a34a", amber: "#d97706", red: "#dc2626", nodata: "#94a3b8" }
const STATUS_LABEL = { green: "On Track", amber: "Near Target", red: "Below Target", nodata: "No Data" }

// Standardized Indian-FY quarter labels, used across the Dashboard,
// Reports, Charts, Filters, and PDF/Excel exports. Numbering matches the
// backend's get_quarter_months() (report_service.py) and scheduler.py
// exactly, so a given quarter number always means the same months
// everywhere in the app.
//   Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar
const QUARTER_RANGES = { 1: "Apr-Jun", 2: "Jul-Sep", 3: "Oct-Dec", 4: "Jan-Mar" }
const QUARTER_START_MONTH = { 1: 4, 2: 7, 3: 10, 4: 1 }
function quarterLabel(q) {
  return `Q${q} (${QUARTER_RANGES[q] || ""})`
}
// Fiscal-quarter-of-a-given-month, using the same Q1=Apr-Jun mapping as
// the backend (instead of a plain calendar-quarter Math.ceil(month/3)).
function fiscalQuarterOfMonth(month) {
  if (month >= 4 && month <= 6)  return 1
  if (month >= 7 && month <= 9)  return 2
  if (month >= 10 && month <= 12) return 3
  return 4 // Jan-Mar
}

function periodLabel(periodType, year, month, quarter) {
  if (periodType === "monthly")   return `${MONTH_NAMES[month]} ${year}`
  if (periodType === "quarterly") return `${quarterLabel(quarter)} ${year}`
  return String(year)
}

// Production and Sales are the two primary KPIs surfaced everywhere on
// this dashboard — shown and compared SEPARATELY, never blended into a
// single score (per requirement: no combined Plant Achievement metric).
const PRIMARY_DEPT_KEYS = ["production", "sales"]

/** Aggregates one plant's report_data (dept -> {plan, actual}) into a
 * flat summary the rest of this component consumes. Pure presentation
 * math — mirrors the same plan/actual/variance/achieved% calculations
 * already displayed elsewhere in the app; nothing new is computed
 * server-side and nothing is written back anywhere. */
function summarizePlant(plantId, plantName, reportData) {
  const rows = DEPTS.map(({ label, key }) => {
    const d = reportData?.[key]
    if (!d) return { label, key, plan: 0, actual: 0, achieved: null, hasData: false }
    const plan   = d.plan   || 0
    const actual = d.actual || 0
    const achieved = plan > 0 ? (actual / plan) * 100 : null
    return { label, key, plan, actual, variance: actual - plan, achieved, hasData: true }
  })

  const withData   = rows.filter(r => r.hasData)
  const totalPlan   = withData.reduce((s, r) => s + r.plan, 0)
  const totalActual = withData.reduce((s, r) => s + r.actual, 0)
  const overallAchieved = totalPlan > 0 ? (totalActual / totalPlan) * 100 : null

  // Production and Sales, kept fully separate — each with its own
  // plan/actual/achieved%. Nothing here is combined into one score;
  // that's used only for the department-level drill-down cards/chart
  // for a single selected plant.
  const production = rows.find(r => r.key === "production")
  const sales      = rows.find(r => r.key === "sales")

  return {
    plantId, plantName, rows,
    totalPlan, totalActual,
    overallAchieved,
    departmentsWithData: withData.length,
    onTrackCount: withData.filter(r => statusOf(r.achieved) === "green").length,
    attentionCount: withData.filter(r => statusOf(r.achieved) === "red").length,
    // Primary KPIs — Production and Sales, always separate:
    productionPlan: production?.plan ?? 0,
    productionActual: production?.actual ?? 0,
    productionAchieved: production?.achieved ?? null,
    salesPlan: sales?.plan ?? 0,
    salesActual: sales?.actual ?? 0,
    salesAchieved: sales?.achieved ?? null,
  }
}

function KpiCard({ label, value, sub, color, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "white", borderRadius: "12px", padding: "16px 18px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0",
        borderTop: `3px solid ${color || "#3b82f6"}`,
        cursor: onClick ? "pointer" : "default",
        transition: onClick ? "transform 0.15s, box-shadow 0.15s" : undefined,
      }}
      onMouseEnter={onClick ? e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 6px 16px rgba(0,0,0,0.1)" } : undefined}
      onMouseLeave={onClick ? e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.06)" } : undefined}
    >
      <p style={{ color: "#64748b", fontSize: "11px", fontWeight: 600, margin: "0 0 6px 0", textTransform: "uppercase", letterSpacing: "0.03em" }}>
        {label}
      </p>
      <p style={{ color: "#0f172a", fontSize: "24px", fontWeight: 700, margin: 0 }}>
        {value}
      </p>
      {sub && <p style={{ color: "#94a3b8", fontSize: "11px", margin: "4px 0 0 0" }}>{sub}</p>}
    </div>
  )
}

// Primary KPI card for Production / Sales — the President's two most
// important numbers, given the most visual weight on the page. Shows
// Target vs Actual explicitly plus a progress bar, so "are we hitting
// the target" is answerable at a glance without doing any math.
function PrimaryKpiCard({ icon, title, subtitle, target, actual, achieved, accentColor }) {
  const status = statusOf(achieved)
  const pct = achieved !== null ? Math.min(achieved, 100) : 0
  // Cap display at 100%: only the excess is shown above that (e.g.
  // 120% -> "+20%"); at or under 100% shows the plain percentage.
  const achievedLabel = achieved === null ? "N/A"
    : achieved > 100 ? `+${(achieved - 100).toFixed(1)}%`
    : `${achieved.toFixed(1)}%`

  return (
    <div style={{
      background: "white", borderRadius: "14px", padding: "20px 22px",
      boxShadow: "0 2px 10px rgba(0,0,0,0.07)", border: "1px solid #e2e8f0",
      borderLeft: `5px solid ${accentColor}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "20px" }}>{icon}</span>
          <span style={{ fontSize: "15px", fontWeight: 800, color: "#0f172a" }}>{title}</span>
        </div>
        <span style={{
          background: `${STATUS_COLOR[status]}18`, color: STATUS_COLOR[status],
          fontSize: "11px", fontWeight: 700, padding: "3px 10px", borderRadius: "20px",
        }}>
          {STATUS_LABEL[status]}
        </span>
      </div>
      <p style={{ margin: "0 0 14px 0", fontSize: "11px", color: "#94a3b8" }}>{subtitle}</p>

      {/* Actual vs Target — the two highlighted numbers. */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: "18px", marginBottom: "12px" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "2px" }}>
            Actual
          </div>
          <div style={{ fontSize: "30px", fontWeight: 800, lineHeight: 1.1, color: accentColor }}>
            {Math.round(actual).toLocaleString()}
          </div>
        </div>
        <div style={{ fontSize: "20px", color: "#cbd5e1", fontWeight: 300, paddingBottom: "2px" }}>/</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "2px" }}>
            Target
          </div>
          <div style={{ fontSize: "30px", fontWeight: 800, lineHeight: 1.1, color: "#475569" }}>
            {Math.round(target).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ height: "8px", borderRadius: "4px", background: "#f1f5f9", overflow: "hidden", marginBottom: "8px" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: STATUS_COLOR[status], borderRadius: "4px", transition: "width 0.4s" }} />
      </div>

      {/* % Achieved — secondary info, bottom-right corner. */}
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <span style={{ display: "flex", alignItems: "baseline", gap: "4px" }}>
          <span style={{ fontSize: "13px", fontWeight: 700, color: STATUS_COLOR[status] }}>{achievedLabel}</span>
          <span style={{ fontSize: "10px", color: "#94a3b8" }}>% Achieved</span>
        </span>
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  return (
    <span style={{
      background: `${STATUS_COLOR[status]}18`, color: STATUS_COLOR[status],
      fontSize: "11px", fontWeight: 700, padding: "3px 10px", borderRadius: "999px",
      whiteSpace: "nowrap",
    }}>
      ● {STATUS_LABEL[status]}
    </span>
  )
}

function PlantSummaryOverview({ onBack, onLogout, onPlantDrillDown, onDeptDrillDown }) {
  const today = new Date()

  const [periodType, setPeriodType] = useState("monthly")   // monthly | quarterly | yearly
  const [year,        setYear]      = useState(today.getFullYear())
  const [month,       setMonth]     = useState(today.getMonth() + 1)
  const [quarter,     setQuarter]   = useState(fiscalQuarterOfMonth(today.getMonth() + 1))
  const [plantFilter, setPlantFilter] = useState("all")    // "all" or a specific plant id

  const [plantSummaries, setPlantSummaries] = useState([])   // one per plant
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState("")

  // "Generate Report" button state — exports exactly the currently
  // filtered Overall Summary (see overallKpis/visibleSummaries below),
  // saves it to the DigitalDRM/Reports folder, and emails it to
  // r.keerthana-contr@ranegroup.com.
  const [generating, setGenerating] = useState(false)
  const [reportMessage, setReportMessage] = useState(null) // { type: "success"|"error", text }

  // Trend history (for the "monthly/quarterly/yearly trend analysis"
  // requirement): re-uses the SAME endpoints across the last several
  // periods so we get a time series without touching the backend at all.
  const [trendSeries, setTrendSeries] = useState([])
  const [trendLoading, setTrendLoading] = useState(true)

  const fetchAllPlants = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const calls = PLANTS.map(p => {
        if (periodType === "monthly")   return generateMonthlyReport(p.id, year, month)
        if (periodType === "quarterly") return generateQuarterlyReport(p.id, year, quarter)
        return generateYearlyReport(p.id, year)
      })
      const results = await Promise.all(calls)
      const summaries = results.map((res, i) =>
        summarizePlant(PLANTS[i].id, PLANTS[i].name, res.data)
      )
      setPlantSummaries(summaries)
    } catch (err) {
      console.error("Overall Plant Summary fetch failed", err)
      setError("Could not load plant data. Please try again.")
    } finally {
      setLoading(false)
    }
  }, [periodType, year, month, quarter])

  // Builds a short trailing trend (last 6 months / 4 quarters / 3 years)
  // for whichever period type is selected, per plant, using the exact
  // same report-generation calls — just repeated for prior periods.
  const fetchTrend = useCallback(async () => {
    setTrendLoading(true)
    try {
      const periods = []
      if (periodType === "monthly") {
        for (let i = 5; i >= 0; i--) {
          const d = new Date(year, month - 1 - i, 1)
          periods.push({ year: d.getFullYear(), month: d.getMonth() + 1, label: MONTH_NAMES[d.getMonth() + 1].slice(0, 3) })
        }
      } else if (periodType === "quarterly") {
        for (let i = 3; i >= 0; i--) {
          let q = quarter - i, y = year
          while (q <= 0) { q += 4; y -= 1 }
          periods.push({ year: y, quarter: q, label: `Q${q} (${QUARTER_RANGES[q]}) '${String(y).slice(2)}` })
        }
      } else {
        for (let i = 2; i >= 0; i--) {
          periods.push({ year: year - i, label: String(year - i) })
        }
      }

      const seriesPerPeriod = await Promise.all(
        periods.map(async p => {
          const calls = PLANTS.map(pl => {
            if (periodType === "monthly")   return generateMonthlyReport(pl.id, p.year, p.month)
            if (periodType === "quarterly") return generateQuarterlyReport(pl.id, p.year, p.quarter)
            return generateYearlyReport(pl.id, p.year)
          })
          const results = await Promise.all(calls)
          const summaries = results.map((res, i) => summarizePlant(PLANTS[i].id, PLANTS[i].name, res.data))
          // Respect the Plant filter here too, so the trend chart reflects
          // the same scope (all plants, or just the selected plant) as the
          // rest of the Overall Summary.
          const scoped = plantFilter === "all"
            ? summaries
            : summaries.filter(s => String(s.plantId) === String(plantFilter))
          // Production and Sales trend lines, kept separate — no blended
          // "overall" figure (per requirement: never aggregate the two).
          const productionPlan   = scoped.reduce((s, x) => s + x.productionPlan, 0)
          const productionActual = scoped.reduce((s, x) => s + x.productionActual, 0)
          const salesPlan   = scoped.reduce((s, x) => s + x.salesPlan, 0)
          const salesActual = scoped.reduce((s, x) => s + x.salesActual, 0)
          const production = productionPlan > 0 ? (productionActual / productionPlan) * 100 : null
          const sales      = salesPlan > 0 ? (salesActual / salesPlan) * 100 : null
          return { label: p.label, production, sales, summaries }
        })
      )
      setTrendSeries(seriesPerPeriod)
    } catch (err) {
      console.error("Trend fetch failed", err)
    } finally {
      setTrendLoading(false)
    }
  }, [periodType, year, month, quarter, plantFilter])

  useEffect(() => { fetchAllPlants() }, [fetchAllPlants])

  // ── Real-time monitoring: auto-refresh every 60s ──────────────────────
  // Lighter interval than the plant-level dashboard's 30s (this view
  // fans out to every plant at once, so it's a heavier fetch), but the
  // same "always current, no manual refresh needed" experience.
  const REFRESH_INTERVAL_MS = 60_000
  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL_MS / 1000)
  const countdownRef = useRef(REFRESH_INTERVAL_MS / 1000)

  useEffect(() => {
    countdownRef.current = REFRESH_INTERVAL_MS / 1000
    setCountdown(REFRESH_INTERVAL_MS / 1000)

    const refreshTimer = setInterval(() => {
      fetchAllPlants()
      setLastRefresh(new Date())
      countdownRef.current = REFRESH_INTERVAL_MS / 1000
      setCountdown(countdownRef.current)
    }, REFRESH_INTERVAL_MS)

    const tickTimer = setInterval(() => {
      countdownRef.current -= 1
      setCountdown(countdownRef.current)
    }, 1000)

    return () => {
      clearInterval(refreshTimer)
      clearInterval(tickTimer)
    }
  }, [fetchAllPlants])
  useEffect(() => { fetchTrend() }, [fetchTrend])

  const visibleSummaries = useMemo(() => {
    if (plantFilter === "all") return plantSummaries
    return plantSummaries.filter(s => String(s.plantId) === String(plantFilter))
  }, [plantSummaries, plantFilter])

  // Get the selected plant data for department-specific views
  const selectedPlant = useMemo(() => {
    if (plantFilter === "all" || visibleSummaries.length === 0) return null
    return visibleSummaries[0]
  }, [plantFilter, visibleSummaries])

  // Per-department trend, fetched only when a single plant is selected
  // (this is what feeds the "Department Performance" cards' trend
  // arrow — the same trend data the full drill-down dashboard shows).
  // Not fetched in the "All Plants" view since that grid isn't shown
  // there and fetching 7 trend series x 6 plants on every load would be
  // wasteful.
  //
  // Deliberately uses TODAY's year/month here, not the page's selected
  // Period filter (year/month above) — the drill-down dashboard
  // (PlantDashboard.jsx) always shows the trend arrow for the current
  // month regardless of what's being viewed elsewhere, and for Sales/
  // Despatch specifically the "trend" data is actually a segment/
  // customer breakdown for that month rather than a daily series — an
  // older or sparser filtered period can easily have fewer than the 2
  // entries needed to compare, showing "No trend" even though the
  // drill-down (always on the current month) has enough to show one.
  // Matching that same current-month basis here keeps the two views
  // consistent instead of the summary card being at the mercy of
  // whatever historical period the President happens to be filtering by.
  const [deptTrendMap, setDeptTrendMap] = useState({})

  useEffect(() => {
    if (!selectedPlant) { setDeptTrendMap({}); return }

    let cancelled = false
    const trendYear = today.getFullYear()
    const trendMonth = today.getMonth() + 1
    ;(async () => {
      try {
        const [prod, mp, desp, ovc, sales, rejPPM, prodVal] = await Promise.all([
          getProductionTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
          getManpowerTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
          getDespatchTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
          getOVCTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
          getSalesTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
          getRejectionPPMTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
          getProductValueTrend(selectedPlant.plantId, trendYear, trendMonth, "daily"),
        ])
        if (cancelled) return
        setDeptTrendMap({
          Production:      prod.data,
          Manpower:        mp.data,
          Despatch:        desp.data,
          "OVC Elements":  ovc.data,
          Sales:           sales.data,
          "Rejection PPM": rejPPM.data,
          "Product Value": prodVal.data,
        })
      } catch {
        if (!cancelled) setDeptTrendMap({})
      }
    })()

    return () => { cancelled = true }
  }, [selectedPlant])

  // Same "compare last two data points" trend direction PlantDashboard.jsx
  // uses, so a department's trend arrow means the same thing everywhere.
  function trendDirectionFor(deptLabel) {
    const apiData = deptTrendMap[deptLabel]
    const trend = apiData?.trend || apiData?.customers || apiData?.segments || apiData?.elements || []
    if (trend.length < 2) return "none"
    const last = trend[trend.length - 1]
    const prev = trend[trend.length - 2]
    const lastA = last.actual ?? last.mtd_actual ?? 0
    const prevA = prev.actual ?? prev.mtd_actual ?? 0
    if (lastA > prevA) return "up"
    if (lastA < prevA) return "down"
    return "stable"
  }

  function lastUpdatedFor(deptLabel) {
    const apiData = deptTrendMap[deptLabel]
    const trend = apiData?.trend || apiData?.customers || apiData?.segments || apiData?.elements || []
    const lastPoint = trend[trend.length - 1]
    const raw = apiData?.last_updated || lastPoint?.date_full || lastPoint?.date
    if (!raw) return null
    const d = new Date(raw)
    if (isNaN(d)) return raw
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
  }

  // Overall KPIs and charts respect the Plant filter — when a specific
  // plant is selected, "Overall" means that plant only, so every
  // visualization on this page (and the exported report) always
  // matches what the President is actually looking at.
  //
  // Production and Sales are tracked as two fully separate primary
  // KPIs throughout — no blended "Plant Achievement" score is computed
  // or displayed anywhere on this page (per requirement).
  const overallKpis = useMemo(() => {
    if (plantFilter !== "all" && selectedPlant) {
      return {
        productionPlan: selectedPlant.productionPlan,
        productionActual: selectedPlant.productionActual,
        productionAchieved: selectedPlant.productionAchieved,
        salesPlan: selectedPlant.salesPlan,
        salesActual: selectedPlant.salesActual,
        salesAchieved: selectedPlant.salesAchieved,
        departmentsWithData: selectedPlant.departmentsWithData,
        onTrackCount: selectedPlant.onTrackCount,
        attentionCount: selectedPlant.attentionCount,
        isPlantView: true
      }
    }

    // All plants view — Production and Sales summed independently.
    const productionPlan   = visibleSummaries.reduce((s, p) => s + p.productionPlan, 0)
    const productionActual = visibleSummaries.reduce((s, p) => s + p.productionActual, 0)
    const salesPlan   = visibleSummaries.reduce((s, p) => s + p.salesPlan, 0)
    const salesActual = visibleSummaries.reduce((s, p) => s + p.salesActual, 0)
    return {
      productionPlan, productionActual,
      productionAchieved: productionPlan > 0 ? (productionActual / productionPlan) * 100 : null,
      salesPlan, salesActual,
      salesAchieved: salesPlan > 0 ? (salesActual / salesPlan) * 100 : null,
      productionOnTrackPlants: visibleSummaries.filter(p => statusOf(p.productionAchieved) === "green").length,
      productionAttentionPlants: visibleSummaries.filter(p => statusOf(p.productionAchieved) === "red").length,
      salesOnTrackPlants: visibleSummaries.filter(p => statusOf(p.salesAchieved) === "green").length,
      salesAttentionPlants: visibleSummaries.filter(p => statusOf(p.salesAchieved) === "red").length,
      isPlantView: false
    }
  }, [visibleSummaries, plantFilter, selectedPlant])

  // Leading plant per KPI — reported separately, Production and Sales
  // are never combined to pick a single "winner".
  const rankedByProduction = useMemo(() => (
    [...visibleSummaries].filter(p => p.productionAchieved !== null).sort((a, b) => b.productionAchieved - a.productionAchieved)
  ), [visibleSummaries])
  const rankedBySales = useMemo(() => (
    [...visibleSummaries].filter(p => p.salesAchieved !== null).sort((a, b) => b.salesAchieved - a.salesAchieved)
  ), [visibleSummaries])
  const leadingProductionPlant = rankedByProduction[0]
  const leadingSalesPlant = rankedBySales[0]

  // Grouped bar chart — Production and Sales as two separate series per
  // plant, side by side. Never averaged into one bar.
  const barData = {
    labels: visibleSummaries.map(p => p.plantName),
    datasets: [
      {
        label: "Production Achieved %",
        data: visibleSummaries.map(p => p.productionAchieved !== null ? Math.round(p.productionAchieved * 10) / 10 : 0),
        backgroundColor: "#3b82f6",
        borderRadius: 6,
      },
      {
        label: "Sales Achieved %",
        data: visibleSummaries.map(p => p.salesAchieved !== null ? Math.round(p.salesAchieved * 10) / 10 : 0),
        backgroundColor: "#16a34a",
        borderRadius: 6,
      },
    ],
  }

  const trendLineData = {
    labels: trendSeries.map(t => t.label),
    datasets: [
      {
        label: plantFilter === "all" ? "Company-wide Production Achieved %" : `${selectedPlant?.plantName || "Plant"} Production Achieved %`,
        data: trendSeries.map(t => t.production !== null ? Math.round(t.production * 10) / 10 : null),
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59,130,246,0.08)",
        pointRadius: 4, pointBackgroundColor: "#3b82f6",
        tension: 0.35, borderWidth: 2.5, fill: true, spanGaps: true,
      },
      {
        label: plantFilter === "all" ? "Company-wide Sales Achieved %" : `${selectedPlant?.plantName || "Plant"} Sales Achieved %`,
        data: trendSeries.map(t => t.sales !== null ? Math.round(t.sales * 10) / 10 : null),
        borderColor: "#16a34a",
        backgroundColor: "rgba(22,163,74,0.08)",
        pointRadius: 4, pointBackgroundColor: "#16a34a",
        tension: 0.35, borderWidth: 2.5, fill: true, spanGaps: true,
      },
    ],
  }

  const chartOptions = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: true, position: "bottom", labels: { usePointStyle: true, pointStyle: "rect", boxWidth: 10 } } },
    scales: {
      y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { callback: v => `${v}%` } },
      x: { grid: { display: false } },
    },
  }
  const lineOptions = {
    ...chartOptions,
    plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle" } } },
  }

  // Exports EXACTLY what's currently on screen: visibleSummaries already
  // reflects the Plant / Period Type / Year / Month-Quarter filters, and
  // overallKpis is derived from that same filtered set — so the payload
  // sent to the backend always matches the applied filters. The PDF/
  // Excel export format still expects one Plan/Actual/Achieved% total
  // per plant, so Production+Sales are summed ONLY for that export
  // payload — this is a report-format detail, not something shown
  // anywhere in this dashboard's UI.
  const handleGenerateReport = async () => {
    setGenerating(true)
    setReportMessage(null)
    try {
      // Build payload with only fields the backend expects
      const payload = {
        period_type: periodType,
        year: year,
        month: periodType === "monthly" ? month : null,
        quarter: periodType === "quarterly" ? quarter : null,
        plant_filter: String(plantFilter),
        plants: visibleSummaries.map(p => {
          const totalPlan = p.productionPlan + p.salesPlan
          const totalActual = p.productionActual + p.salesActual
          return {
            plant_id: p.plantId,
            plant_name: p.plantName,
            total_plan: totalPlan,
            total_actual: totalActual,
            overall_achieved: totalPlan > 0 ? (totalActual / totalPlan) * 100 : null,
            departments_with_data: p.departmentsWithData,
            on_track_count: p.onTrackCount,
            total_departments: DEPTS.length,
          }
        }),
        overall_achieved: (() => {
          const totalPlan = overallKpis.productionPlan + overallKpis.salesPlan
          const totalActual = overallKpis.productionActual + overallKpis.salesActual
          return totalPlan > 0 ? (totalActual / totalPlan) * 100 : null
        })(),
      }

      // All Plants view only: send plant-level on-track/attention counts
      // so the backend's unfiltered "Overall Summary" layout can render
      // its "Plants On Track" / "Plants Needing Attention" cards.
      if (!overallKpis.isPlantView) {
        payload.on_track_plants = overallKpis.productionOnTrackPlants
        payload.attention_plants = overallKpis.productionAttentionPlants
      }

      // Single-plant view only: send department-level detail so the
      // backend's plant-specific layout can render Department-wise
      // Performance. No "Needing Attention" figure is sent as its own
      // KPI here — that box is intentionally All-Plants-only.
      if (overallKpis.isPlantView && selectedPlant) {
        payload.department_details = selectedPlant.rows.map(dept => ({
          label: dept.label,
          plan: dept.plan,
          actual: dept.actual,
          achieved: dept.achieved,
          status: statusOf(dept.achieved)
        }))
      }

      const res = await generateOverallSummaryReport(payload)
      setReportMessage({
        type: "success",
        text: `✅ Report generated and saved as "${res.data.filename}", and emailed to ${res.data.emailed_to}.`,
      })
    } catch (err) {
      console.error("Generate Report failed", err)
      setReportMessage({
        type: "error",
        text: err.response?.data?.message || "Failed to generate the report. Please try again.",
      })
    } finally {
      setGenerating(false)
      setTimeout(() => setReportMessage(null), 8000)
    }
  }

  // Render department-specific KPI cards for plant view — the SAME
  // DeptSummaryCard component used in the full President -> Plant ->
  // Department drill-down, so the look is consistent everywhere. Values
  // highlighted (Actual/Target big, % Achieved capped + secondary,
  // bottom-right) via DeptSummaryCard's deemphasizeVariance prop.
  // Trend/last-updated aren't available from this page's data (no
  // historical trend fetch here — that's what the chart below this
  // grid is for), so they degrade gracefully to "No trend"/"—".
  const renderDepartmentKPIs = () => {
    if (!selectedPlant) return null

    return (
      <div style={{ marginBottom: "20px" }}>
        <h3 style={{ fontSize: "14px", fontWeight: 700, color: "#0f172a", margin: "0 0 12px 0" }}>
          Department Performance - {selectedPlant.plantName}
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px" }}>
          {selectedPlant.rows.map(dept => {
            const status = statusOf(dept.achieved)
            const visual = DEPT_VISUAL[dept.label] || { icon: "📊", accentColor: "#64748b" }
            const variance100 = dept.achieved !== null ? dept.achieved - 100 : null
            const latestValue = variance100 !== null ? `${variance100 >= 0 ? "+" : ""}${variance100.toFixed(1)}%` : null

            const card = {
              name: dept.label,
              icon: visual.icon,
              accentColor: visual.accentColor,
              status,
              trend: trendDirectionFor(dept.label),
              latestValue,
              latestLabel: "vs 100% Target",
              lastUpdated: lastUpdatedFor(dept.label),
              kpi: dept.hasData ? Math.round(dept.actual).toLocaleString() : null,
              kpiLabel: "actual",
              target: dept.hasData ? Math.round(dept.plan).toLocaleString() : null,
              targetLabel: "target",
            }

            return (
              dept.label === "OVC Elements" ? (
                <OVCSummaryCard
                  key={dept.key}
                  dept={card}
                  ovcData={deptTrendMap["OVC Elements"]}
                  onClick={() => {
                    if (onDeptDrillDown) onDeptDrillDown(selectedPlant.plantId, dept.label)
                    else if (onPlantDrillDown) onPlantDrillDown(selectedPlant.plantId)
                  }}
                />
              ) : (
                <DeptSummaryCard
                  key={dept.key}
                  dept={card}
                  deemphasizeVariance
                  onClick={() => {
                    // Straight to that department's own graph/detail view,
                    // skipping the intermediate Plant-level grid — falls
                    // back to plant drill-down only if the direct path
                    // isn't wired up by the caller.
                    if (onDeptDrillDown) onDeptDrillDown(selectedPlant.plantId, dept.label)
                    else if (onPlantDrillDown) onPlantDrillDown(selectedPlant.plantId)
                  }}
                />
              )
            )
          })}
        </div>
      </div>
    )
  }

  // Render department-wise performance chart for plant view
  const renderDepartmentTrend = () => {
    if (!selectedPlant) return null

    const deptLabels = selectedPlant.rows.map(d => d.label)
    const deptAchieved = selectedPlant.rows.map(d => d.achieved !== null ? Math.round(d.achieved * 10) / 10 : 0)

    const deptBarData = {
      labels: deptLabels,
      datasets: [{
        label: "Achieved %",
        data: deptAchieved,
        backgroundColor: selectedPlant.rows.map(d => STATUS_COLOR[statusOf(d.achieved)]),
        borderRadius: 6,
      }],
    }

    return (
      <div style={{ background: "white", borderRadius: "12px", padding: "18px 20px", marginBottom: "20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0" }}>
        <h3 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>
          Department-wise Performance - {selectedPlant.plantName}
        </h3>
        <div style={{ height: "240px" }}>
          <Bar data={deptBarData} options={chartOptions} />
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f1f5f9" }}>

      {/* Header */}
      <div style={{ background: "linear-gradient(135deg,#1e293b 0%,#0f172a 100%)", padding: "16px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <img src={RaneLogo} alt="Rane Madras Ltd" style={{ height: "30px", width: "auto", objectFit: "contain" }} />
          <div>
            <h1 style={{ color: "white", fontWeight: 700, fontSize: "16px", margin: "0 0 2px 0" }}>
              {plantFilter === "all" ? "Overall Plant Summary" : `${selectedPlant?.plantName || "Plant"} Dashboard`}
            </h1>
            <p style={{ color: "#cbd5e1", fontSize: "12px", margin: 0 }}>
              {plantFilter === "all" ? "Consolidated view across all 5 plants" : `Plant-specific view for ${selectedPlant?.plantName || `Plant ${plantFilter}`}`} · {periodLabel(periodType, year, month, quarter)}
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ background: "rgba(59,130,246,0.2)", border: "1px solid #3b82f6", color: "#93c5fd", fontSize: "11px", padding: "6px 10px", borderRadius: "6px", fontWeight: 600, whiteSpace: "nowrap" }}>
            🕐 {lastRefresh.toLocaleTimeString()} · next in {countdown}s
          </span>
          {onBack && (
            <button
              onClick={onBack}
              style={{ background: "rgba(148,163,184,0.2)", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: 600 }}
            >
              ← Back
            </button>
          )}
          {onLogout && (
            <button
              onClick={onLogout}
              style={{ background: "#334155", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: 600 }}
            >
              Logout
            </button>
          )}
        </div>
      </div>

      <div style={{ padding: "24px 32px", maxWidth: "1280px", margin: "0 auto" }}>

        {/* Filters */}
        <div style={{ background: "white", borderRadius: "12px", padding: "16px 20px", marginBottom: "20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0", display: "flex", flexWrap: "wrap", gap: "16px", alignItems: "flex-end" }}>

          <div>
            <label style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "#64748b", marginBottom: "5px" }}>PERIOD TYPE</label>
            <select value={periodType} onChange={e => setPeriodType(e.target.value)} style={selectStyle}>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "#64748b", marginBottom: "5px" }}>YEAR</label>
            <select value={year} onChange={e => setYear(parseInt(e.target.value, 10))} style={selectStyle}>
              {[today.getFullYear(), today.getFullYear() - 1, today.getFullYear() - 2].map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          {periodType === "monthly" && (
            <div>
              <label style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "#64748b", marginBottom: "5px" }}>MONTH</label>
              <select value={month} onChange={e => setMonth(parseInt(e.target.value, 10))} style={selectStyle}>
                {MONTH_NAMES.slice(1).map((m, i) => (
                  <option key={m} value={i + 1}>{m}</option>
                ))}
              </select>
            </div>
          )}

          {periodType === "quarterly" && (
            <div>
              <label style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "#64748b", marginBottom: "5px" }}>QUARTER</label>
              <select value={quarter} onChange={e => setQuarter(parseInt(e.target.value, 10))} style={selectStyle}>
                {[1, 2, 3, 4].map(q => <option key={q} value={q}>{quarterLabel(q)}</option>)}
              </select>
            </div>
          )}

          <div>
            <label style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "#64748b", marginBottom: "5px" }}>PLANT FILTER</label>
            <select value={plantFilter} onChange={e => setPlantFilter(e.target.value)} style={selectStyle}>
              <option value="all">All Plants</option>
              {PLANTS.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          <div style={{ marginLeft: "auto" }}>
            <button
              onClick={handleGenerateReport}
              disabled={generating || loading}
              style={{
                background: generating ? "#93c5fd" : "#2563eb",
                color: "white",
                border: "none",
                padding: "9px 18px",
                borderRadius: "8px",
                fontSize: "13px",
                fontWeight: 700,
                cursor: generating || loading ? "not-allowed" : "pointer",
                boxShadow: "0 1px 3px rgba(0,0,0,0.15)",
              }}
              title="Exports exactly this filtered Overall Summary, saves it to DigitalDRM/Reports, and emails it to r.keerthana-contr@ranegroup.com"
            >
              {generating ? "Generating…" : "📄 Generate Report"}
            </button>
          </div>

        </div>

        {reportMessage && (
          <div style={{
            background: reportMessage.type === "success" ? "#dcfce7" : "#fee2e2",
            border: `1px solid ${reportMessage.type === "success" ? "#86efac" : "#fecaca"}`,
            color: reportMessage.type === "success" ? "#166534" : "#dc2626",
            padding: "12px 16px", borderRadius: "8px", marginBottom: "20px", fontSize: "13px",
          }}>
            {reportMessage.text}
          </div>
        )}

        {error && (
          <div style={{ background: "#fee2e2", border: "1px solid #fecaca", color: "#dc2626", padding: "12px 16px", borderRadius: "8px", marginBottom: "20px", fontSize: "13px" }}>
            ⚠️ {error}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", color: "#94a3b8", padding: "60px 20px" }}>Loading data…</div>
        ) : (
          <>
            {/* Primary KPIs — Production and Sales, always shown and
                compared SEPARATELY. No combined "Plant Achievement"
                score anywhere on this dashboard. */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "14px", marginBottom: "14px" }}>
              <PrimaryKpiCard
                icon="⚙️"
                title="Production"
                subtitle={plantFilter === "all" ? `Across ${visibleSummaries.length} plants` : selectedPlant?.plantName || ""}
                target={overallKpis.productionPlan}
                actual={overallKpis.productionActual}
                achieved={overallKpis.productionAchieved}
                accentColor="#3b82f6"
              />
              <PrimaryKpiCard
                icon="💰"
                title="Sales"
                subtitle={plantFilter === "all" ? `Across ${visibleSummaries.length} plants` : selectedPlant?.plantName || ""}
                target={overallKpis.salesPlan}
                actual={overallKpis.salesActual}
                achieved={overallKpis.salesAchieved}
                accentColor="#16a34a"
              />
            </div>

            {/* Secondary KPI cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px", marginBottom: "20px" }}>
              {plantFilter === "all" ? (
                <>
                  <KpiCard label="Production — Plants On Track" value={overallKpis.productionOnTrackPlants} color="#16a34a" sub="Achieved ≥ 100% of plan" />
                  <KpiCard label="Sales — Plants On Track" value={overallKpis.salesOnTrackPlants} color="#16a34a" sub="Achieved ≥ 100% of plan" />
                  <KpiCard label="Leading Plant — Production" value={leadingProductionPlant ? leadingProductionPlant.plantName : "—"} color="#3b82f6" sub={leadingProductionPlant ? `${leadingProductionPlant.productionAchieved.toFixed(1)}%` : ""} />
                  <KpiCard label="Leading Plant — Sales" value={leadingSalesPlant ? leadingSalesPlant.plantName : "—"} color="#16a34a" sub={leadingSalesPlant ? `${leadingSalesPlant.salesAchieved.toFixed(1)}%` : ""} />
                </>
              ) : (
                // Single Plant view - show department-level KPIs only.
                <>
                  <KpiCard
                    label="Departments Reporting"
                    value={`${overallKpis.departmentsWithData}/${DEPTS.length}`}
                    color="#3b82f6"
                    sub={`${overallKpis.onTrackCount} on track`}
                  />
                  <KpiCard
                    label="View Full Plant Dashboard"
                    value="→"
                    color="#8b5cf6"
                    sub="All departments, same as Plant Head view"
                    onClick={() => onPlantDrillDown && onPlantDrillDown(selectedPlant.plantId)}
                  />
                </>
              )}
            </div>

            {/* Executive insights */}
            <div style={{ background: "white", borderRadius: "12px", padding: "18px 20px", marginBottom: "20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0" }}>
              <h3 style={{ margin: "0 0 8px 0", fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>📌 Executive Insights</h3>
              <p style={{ margin: 0, fontSize: "13px", color: "#334155", lineHeight: 1.6 }}>
                {overallKpis.productionAchieved !== null || overallKpis.salesAchieved !== null ? (
                  <>
                    {plantFilter === "all" ? "Company-wide" : `${selectedPlant?.plantName || "Plant"}`} performance for {periodLabel(periodType, year, month, quarter)}:{" "}
                    Production is at{" "}
                    <strong style={{ color: STATUS_COLOR[statusOf(overallKpis.productionAchieved)] }}>
                      {overallKpis.productionAchieved !== null ? `${overallKpis.productionAchieved.toFixed(1)}%` : "N/A"}
                    </strong>{" "}
                    of plan, Sales is at{" "}
                    <strong style={{ color: STATUS_COLOR[statusOf(overallKpis.salesAchieved)] }}>
                      {overallKpis.salesAchieved !== null ? `${overallKpis.salesAchieved.toFixed(1)}%` : "N/A"}
                    </strong>{" "}
                    of plan.
                    {plantFilter === "all" ? (
                      <>
                        {" "}{leadingProductionPlant && <><strong>{leadingProductionPlant.plantName}</strong> leads on Production ({leadingProductionPlant.productionAchieved.toFixed(1)}%).{" "}</>}
                        {leadingSalesPlant && <><strong>{leadingSalesPlant.plantName}</strong> leads on Sales ({leadingSalesPlant.salesAchieved.toFixed(1)}%).</>}
                      </>
                    ) : (
                      <>
                        {" "}The plant has {selectedPlant?.onTrackCount || 0} departments on track out of {DEPTS.length} total.
                        {selectedPlant?.attentionCount > 0 && (
                          <> A few departments are below target and may warrant a closer review.</>
                        )}
                      </>
                    )}
                  </>
                ) : "No data available for this period yet."}
              </p>
            </div>

            {/* Department-specific KPIs for plant view */}
            {plantFilter !== "all" && renderDepartmentKPIs()}

            {/* Department-wise performance chart for plant view */}
            {plantFilter !== "all" && renderDepartmentTrend()}

            {/* Charts - conditionally render based on view */}
            {plantFilter === "all" ? (
              // All Plants view - show plant comparison and trend
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "20px" }}>
                <div style={{ background: "white", borderRadius: "12px", padding: "18px 20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0" }}>
                  <h3 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>Plant-wise Comparison</h3>
                  <div style={{ height: "260px" }}>
                    <Bar data={barData} options={chartOptions} />
                  </div>
                </div>
                <div style={{ background: "white", borderRadius: "12px", padding: "18px 20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0" }}>
                  <h3 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>
                    Trend Analysis {trendLoading && <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 400 }}>(loading…)</span>}
                  </h3>
                  <div style={{ height: "260px" }}>
                    <Line data={trendLineData} options={lineOptions} />
                  </div>
                </div>
              </div>
            ) : (
              // Single Plant view - show only trend
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "16px", marginBottom: "20px" }}>
                <div style={{ background: "white", borderRadius: "12px", padding: "18px 20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0" }}>
                  <h3 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>
                    Trend Analysis - {selectedPlant?.plantName} {trendLoading && <span style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 400 }}>(loading…)</span>}
                  </h3>
                  <div style={{ height: "260px" }}>
                    <Line data={trendLineData} options={lineOptions} />
                  </div>
                </div>
              </div>
            )}

            {/* Plant-wise comparison table — Production and Sales shown
                as two fully independent columns-groups, each with its
                own status. No combined rank/score. Click a row to open
                that plant's full department dashboard. */}
            {plantFilter === "all" && (
              <div style={{ background: "white", borderRadius: "12px", padding: "18px 20px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)", border: "1px solid #e2e8f0" }}>
                <h3 style={{ margin: "0 0 14px 0", fontSize: "14px", fontWeight: 700, color: "#0f172a" }}>
                  Plant-wise Comparison <span style={{ fontWeight: 400, color: "#94a3b8", fontSize: "12px" }}>— click a plant to drill down</span>
                </h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                    <thead>
                      <tr style={{ background: "#f8fafc", borderBottom: "2px solid #e2e8f0" }}>
                        <th style={{ ...thStyle, textAlign: "left" }}>Plant</th>
                        <th style={thStyle} colSpan={2}>Production</th>
                        <th style={thStyle} colSpan={2}>Sales</th>
                        <th style={thStyle}></th>
                      </tr>
                      <tr style={{ background: "#f8fafc", borderBottom: "2px solid #e2e8f0" }}>
                        <th style={thStyle}></th>
                        <th style={{ ...thStyle, fontWeight: 400 }}>Actual / Target</th>
                        <th style={{ ...thStyle, fontWeight: 400 }}>Achieved %</th>
                        <th style={{ ...thStyle, fontWeight: 400 }}>Actual / Target</th>
                        <th style={{ ...thStyle, fontWeight: 400 }}>Achieved %</th>
                        <th style={thStyle}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleSummaries.map(p => {
                        const prodStatus = statusOf(p.productionAchieved)
                        const salesStatus = statusOf(p.salesAchieved)
                        return (
                          <tr
                            key={p.plantId}
                            onClick={() => onPlantDrillDown && onPlantDrillDown(p.plantId)}
                            style={{ borderBottom: "1px solid #f1f5f9", cursor: onPlantDrillDown ? "pointer" : "default" }}
                            onMouseEnter={e => { if (onPlantDrillDown) e.currentTarget.style.background = "#f8fafc" }}
                            onMouseLeave={e => { e.currentTarget.style.background = "transparent" }}
                          >
                            <td style={{ ...tdStyle, textAlign: "left", fontWeight: 600, color: "#0f172a" }}>{p.plantName}</td>
                            <td style={tdStyle}>{Math.round(p.productionActual).toLocaleString()} / {Math.round(p.productionPlan).toLocaleString()}</td>
                            <td style={{ ...tdStyle, fontWeight: 700, color: STATUS_COLOR[prodStatus] }}>
                              {p.productionAchieved !== null ? `${p.productionAchieved.toFixed(1)}%` : "N/A"}
                            </td>
                            <td style={tdStyle}>{Math.round(p.salesActual).toLocaleString()} / {Math.round(p.salesPlan).toLocaleString()}</td>
                            <td style={{ ...tdStyle, fontWeight: 700, color: STATUS_COLOR[salesStatus] }}>
                              {p.salesAchieved !== null ? `${p.salesAchieved.toFixed(1)}%` : "N/A"}
                            </td>
                            <td style={{ ...tdStyle, color: "#3b82f6", fontWeight: 600, whiteSpace: "nowrap" }}>
                              {onPlantDrillDown ? "View →" : ""}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

const selectStyle = {
  padding: "8px 12px", borderRadius: "8px", border: "1px solid #cbd5e1",
  fontSize: "13px", color: "#0f172a", background: "white", minWidth: "130px",
}
const thStyle = { padding: "10px 12px", textAlign: "center", fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.03em" }
const tdStyle = { padding: "10px 12px", textAlign: "center", color: "#334155" }

export default PlantSummaryOverview