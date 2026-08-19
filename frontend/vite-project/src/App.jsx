import { useAuth } from "./context/AuthContext"
import { useState } from "react"
import Login              from "./pages/Login"
import Home               from "./pages/Home"
import PlantDashboard     from "./pages/PlantDashboard"
import DepartmentDetail   from "./pages/DepartmentDetail"
import PresidentDashboard from "./pages/PresidentDashboard"
import DataEntry          from "./pages/DataEntry"
import Reports            from "./pages/Reports"
import ManageTeam         from "./pages/ManageTeam"

import AdminDashboard from "./pages/AdminDashboard"

function App() {
  const { user } = useAuth()
  const [view,                  setView]                  = useState("home")
  const [reportsPlantId,        setReportsPlantId]        = useState(null)
  const [selectedDept,          setSelectedDept]          = useState(null)
  const [dashboardRefreshToken, setDashboardRefreshToken] = useState(0)

  if (!user) return <Login />

  if (user.role === "admin") {
    return <AdminDashboard />
  }

  if (user.role === "president") {
    return <PresidentDashboard />
  }

  if (user.role === "plant") {
    if (view === "home") {
      return (
        <Home
          onDashboard={() => setView("dashboard")}
          onDataEntry={() => setView("entry")}
          onManageTeam={() => setView("manage-team")}
        />
      )
    }

    if (view === "manage-team") {
      return <ManageTeam onBack={() => setView("home")} />
    }

    if (view === "dashboard") {
      return (
        <PlantDashboard
          onBack={() => setView("home")}
          onReports={plantId => { setReportsPlantId(plantId); setView("reports") }}
          onDeptClick={deptName => { setSelectedDept(deptName); setView("dept-detail") }}
          refreshToken={dashboardRefreshToken}
        />
      )
    }

    if (view === "dept-detail" && selectedDept) {
      return (
        <DepartmentDetail
          deptName={selectedDept}
          plantId={user.plant_id}
          onBack={() => setView("dashboard")}
        />
      )
    }

    if (view === "reports") {
      return (
        <Reports
          plantId={reportsPlantId || user.plant_id}
          onBack={() => setView("dashboard")}
        />
      )
    }

    if (view === "entry") {
      return (
        <DataEntry
          onBack={() => setView("home")}
          onDataSaved={() => setDashboardRefreshToken(t => t + 1)}
        />
      )
    }
  }

  // Staff Incharge — AD-authenticated to exactly one plant + one
  // department (see ad_auth_service.resolve_plant_department_role()).
  // Unlike "plant" (Plant Head — full plant access), a Staff Incharge
  // never sees the full department grid or any other department's
  // data: "View My Department" goes straight to their own
  // DepartmentDetail, and Data Entry still self-verifies against Data
  // Entry Users the same way it already does for shared plant logins.
  if (user.role === "staff") {
    if (view === "dept-detail") {
      return (
        <DepartmentDetail
          deptName={user.department}
          plantId={user.plant_id}
          onBack={() => setView("home")}
        />
      )
    }

    if (view === "entry") {
      return (
        <DataEntry
          onBack={() => setView("home")}
          onDataSaved={() => setDashboardRefreshToken(t => t + 1)}
        />
      )
    }

    return (
      <Home
        onDashboard={() => setView("dept-detail")}
        onDataEntry={() => setView("entry")}
      />
    )
  }

 return (
  <div className="bg-red-500 text-white p-10 text-3xl">
    TEST TAILWIND
  </div>
)
}

export default App