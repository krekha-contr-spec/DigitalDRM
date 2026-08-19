// PresidentDashboard.jsx
// -----------------------
// The President Dashboard's navigation hierarchy is:
//
//   President  ->  Plant  ->  Department  ->  KPI Details
//   (Overall       (that        (Production,    (the same trend charts /
//    Summary)       plant's      Sales,           plan-vs-actual detail
//                   full dept.   Manpower,        Plant Heads and Staff
//                   grid - the   OVC, Despatch,   already see for that
//                   SAME view    Rejection PPM,   department - no
//                   a Plant      Product Value)   separate "President
//                   Head sees)                     version" to maintain)
//
// This reuses PlantDashboard and DepartmentDetail completely unchanged -
// the President sees exactly the same department dashboards/charts
// available to Plant Heads and Staff, just reached by clicking a plant
// from the Overall Summary instead of logging in as that plant. No new
// components, no duplicated data-fetching logic.
import { useState } from "react"
import { useAuth } from "../context/AuthContext"
import PlantSummaryOverview from "./PlantSummaryOverview"
import PlantDashboard from "./PlantDashboard"
import DepartmentDetail from "./DepartmentDetail"
import Reports from "./Reports"

function PresidentDashboard() {
  const { logout } = useAuth()

  // "overview" | "plant" | "dept" | "reports"
  const [view, setView] = useState("overview")
  const [selectedPlantId, setSelectedPlantId] = useState(null)
  const [selectedDept, setSelectedDept] = useState(null)

  // Plant level - the same department card grid a Plant Head sees for
  // their own plant, here shown for whichever plant the President
  // clicked on the Overall Summary.
  if (view === "plant" && selectedPlantId) {
    return (
      <PlantDashboard
        plantId={selectedPlantId}
        isPresident
        onBack={() => { setSelectedPlantId(null); setView("overview") }}
        onReports={plantId => { setSelectedPlantId(plantId); setView("reports") }}
        onDeptClick={deptName => { setSelectedDept(deptName); setView("dept") }}
      />
    )
  }

  // Department level - the same trend charts, plan-vs-actual
  // breakdown, and KPI detail a Plant Head or Staff user sees when they
  // drill into one department. Reached either via the Plant level
  // grid's own department cards, or directly from a Department
  // Performance card on the Overall Summary (skipping the intermediate
  // Plant level entirely) via onDeptDrillDown below.
  if (view === "dept" && selectedPlantId && selectedDept) {
    return (
      <DepartmentDetail
        deptName={selectedDept}
        plantId={selectedPlantId}
        onBack={() => setView("plant")}
      />
    )
  }

  // Reports for a single plant, reached from inside that plant's
  // dashboard (same "Reports" button a Plant Head has).
  if (view === "reports" && selectedPlantId) {
    return (
      <Reports
        plantId={selectedPlantId}
        onBack={() => setView("plant")}
      />
    )
  }

  // President level - the Overall Summary across all plants. Clicking a
  // plant (in the ranking table, the comparison chart, or the plant
  // filter) drills down into that plant's own department dashboard.
  return (
    <PlantSummaryOverview
      onLogout={logout}
      onPlantDrillDown={plantId => { setSelectedPlantId(plantId); setView("plant") }}
      onDeptDrillDown={(plantId, deptName) => {
        setSelectedPlantId(plantId)
        setSelectedDept(deptName)
        setView("dept")
      }}
    />
  )
}

export default PresidentDashboard