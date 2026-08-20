import { useAuth } from "../context/AuthContext"
import RaneLogo from "../assets/Rane_Group_Logo.jpg";

function Home({ onDashboard, onDataEntry, onManageTeam }) {
  const { user, logout } = useAuth()

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden", background: "#f1f5f9" }}>

      {/* Header */}
      <div style={{ background: "#0f172a", padding: "17px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <img src={RaneLogo} alt="Rane Madras Ltd" style={{ height: "36px", width: "auto", objectFit: "contain" }} />
          <div>
            <p style={{ color: "white", fontWeight: "bold", fontSize: "17px", margin: 0 }}>Rane Madras Ltd - Digital DRM</p>
            <p style={{ color: "#94a3b8", fontSize: "11px", margin: 0 }}>Digital DRM Dashboard</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ background: "#3b82f6", color: "white", fontSize: "12px", padding: "4px 12px", borderRadius: "20px", fontWeight: "600" }}>
            Plant {user.plant_id}
          </span>
          <span style={{ color: "#94a3b8", fontSize: "12px" }}>
            {new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
          </span>
          <button onClick={logout} style={{ background: "#334155", color: "white", border: "none", padding: "6px 12px", borderRadius: "6px", cursor: "pointer", fontSize: "12px" }}>
            Logout
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px" }}>

        {/* Welcome Text */}
        <div style={{ textAlign: "center", marginBottom: "48px" }}>
          <h1 style={{ color: "#0f172a", fontSize: "28px", fontWeight: "800", margin: "0 0 8px 0" }}>
            Welcome, Plant {user.plant_id}! 👋
          </h1>
          <p style={{ color: "#64748b", fontSize: "15px", margin: 0 }}>
            What would you like to do today?
          </p>
        </div>

        {/* Cards */}
        <div style={{ display: "flex", gap: "24px" }}>

          {/* Dashboard Card */}
          <div
            onClick={onDashboard}
            style={{
              background: "white",
              borderRadius: "16px",
              padding: "40px",
              width: "260px",
              textAlign: "center",
              cursor: "pointer",
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
              border: "2px solid transparent",
              transition: "all 0.2s"
            }}
            onMouseEnter={e => e.currentTarget.style.border = "2px solid #3b82f6"}
            onMouseLeave={e => e.currentTarget.style.border = "2px solid transparent"}
          >
            <div style={{ fontSize: "48px", marginBottom: "16px" }}>📊</div>
            <h2 style={{ color: "#0f172a", fontSize: "18px", fontWeight: "700", margin: "0 0 8px 0" }}>
              View Dashboard
            </h2>
            <p style={{ color: "#64748b", fontSize: "13px", margin: "0 0 24px 0", lineHeight: "1.5" }}>
              View your plant performance graphs and trends
            </p>
            <div style={{ background: "#3b82f6", color: "white", padding: "10px 24px", borderRadius: "8px", fontSize: "13px", fontWeight: "600" }}>
              Open Dashboard →
            </div>
          </div>

          {/* Data Entry Card */}
          <div
            onClick={onDataEntry}
            style={{
              background: "white",
              borderRadius: "16px",
              padding: "40px",
              width: "260px",
              textAlign: "center",
              cursor: "pointer",
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
              border: "2px solid transparent",
              transition: "all 0.2s"
            }}
            onMouseEnter={e => e.currentTarget.style.border = "2px solid #16a34a"}
            onMouseLeave={e => e.currentTarget.style.border = "2px solid transparent"}
          >
            <div style={{ fontSize: "48px", marginBottom: "16px" }}>📝</div>
            <h2 style={{ color: "#0f172a", fontSize: "18px", fontWeight: "700", margin: "0 0 8px 0" }}>
              Enter Data
            </h2>
            <p style={{ color: "#64748b", fontSize: "13px", margin: "0 0 24px 0", lineHeight: "1.5" }}>
              Update today's production, manpower and other metrics
            </p>
            <div style={{ background: "#16a34a", color: "white", padding: "10px 24px", borderRadius: "8px", fontSize: "13px", fontWeight: "600" }}>
              Enter Data →
            </div>
          </div>

          {/* Manage Team Card — Plant Head only. A Staff Incharge login
              never receives onManageTeam from App.jsx, so this card
              simply doesn't render for them — no separate role check
              needed here. */}
          {onManageTeam && (
            <div
              onClick={onManageTeam}
              style={{
                background: "white",
                borderRadius: "16px",
                padding: "40px",
                width: "260px",
                textAlign: "center",
                cursor: "pointer",
                boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                border: "2px solid transparent",
                transition: "all 0.2s"
              }}
              onMouseEnter={e => e.currentTarget.style.border = "2px solid #774fbb"}
              onMouseLeave={e => e.currentTarget.style.border = "2px solid transparent"}
            >
              <div style={{ fontSize: "48px", marginBottom: "16px" }}>👥</div>
              <h2 style={{ color: "#0f172a", fontSize: "18px", fontWeight: "700", margin: "0 0 8px 0" }}>
                Manage Team
              </h2>
              <p style={{ color: "#64748b", fontSize: "11.1px", margin: "0 0 24px 0", lineHeight: "1.5" }}>
                Request to add or remove Data Entry Users (needs Admin approval)
              </p>
              <div style={{ background: "#774fbb", color: "white", padding: "10px 24px", borderRadius: "8px", fontSize: "13px", fontWeight: "600" }}>
                Manage Team →
              </div>
            </div>
          )}

        </div>

      </div>

    </div>
  )
}

export default Home