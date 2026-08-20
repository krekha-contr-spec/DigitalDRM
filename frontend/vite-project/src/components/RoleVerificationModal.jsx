import { useState } from "react"
import { verifyRoleAccess } from "../services/api"
import RaneLogo from "../assets/Rane_Group_Logo.jpg";

const ROLE_OPTIONS = [
  { label: "Select your department role", value: "" },
  { label: "Production",    value: "production"    },
  { label: "Manpower",      value: "manpower"      },
  { label: "Despatch",      value: "despatch"      },
  { label: "OVC Elements",  value: "ovc"           },
  { label: "Sales",         value: "sales"         },
  { label: "Rejection PPM", value: "rejection_ppm" },
  { label: "Product Value", value: "product_value" },
]

function RoleVerificationModal({ plantId, onVerified, onBack }) {
  const [personName, setPersonName] = useState("")
  const [email,      setEmail]      = useState("")
  const [role,       setRole]       = useState("")
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState("")

  const isValid = personName.trim() && email.trim() && role

  const handleVerify = async (e) => {
    e.preventDefault()
    if (!isValid) return
    setError("")
    setLoading(true)

    try {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Verification timed out — check your connection")), 15000)
      )
      const verifyPromise = verifyRoleAccess({
        plant_id:    plantId,
        person_name: personName.trim(),
        email:       email.trim().toLowerCase(),
        role:        role,
      })
      const response = await Promise.race([verifyPromise, timeoutPromise])
      onVerified(response.data.role)
    } catch (err) {
      const detail = err.response?.data?.detail
      let msg
      if (!detail) {
        msg = err.message || "Verification failed. Please check your credentials."
      } else if (typeof detail === "string") {
        msg = detail
      } else if (Array.isArray(detail)) {
        msg = detail.map(d => d.msg || JSON.stringify(d)).join("; ")
      } else {
        msg = JSON.stringify(detail)
      }
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900">

      {/* Card — same width/shape as Login */}
      <div className="bg-white rounded-2xl shadow-2xl overflow-hidden" style={{ width: "420px" }}>

        {/* Top dark banner — identical to Login */}
        <div className="bg-slate-900 px-8 py-6 text-center">
          <div className="flex items-center justify-center mb-3">
            <img
              src={RaneLogo}
              alt="Rane Madras Ltd"
              style={{ height: "48px", width: "auto", objectFit: "contain" }}
            />
          </div>
          <p className="text-white font-bold text-base">Rane Madras Ltd</p>
          <p className="text-blue-400 text-xs mt-0.5">ECD Division</p>
          <div className="border-b border-blue-600 w-10 mx-auto my-3" />
          <h2 className="text-white text-xl font-bold">Digital DRM Dashboard</h2>
          <p className="text-blue-400 text-xs mt-1">Data Entry Login</p>
        </div>

        {/* White form area */}
        <div className="px-8 py-6">
          <p className="text-slate-500 text-sm mb-5 text-center">
            Plant {plantId} — Enter your credentials to continue
          </p>

          {/* Error */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-600 text-xs px-3 py-2 rounded-lg mb-4">
              ⚠️ {error}
            </div>
          )}

          <form onSubmit={handleVerify}>
            {/* Username */}
            <div className="mb-4">
              <label className="text-slate-600 text-xs font-semibold mb-1 block">
                USERNAME
              </label>
              <input
                type="text"
                placeholder="Enter your full name"
                value={personName}
                onChange={e => setPersonName(e.target.value)}
                disabled={loading}
                required
                className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-slate-50 disabled:opacity-70"
              />
            </div>

            {/* Email */}
            <div className="mb-4">
              <label className="text-slate-600 text-xs font-semibold mb-1 block">
                EMAIL ID
              </label>
              <input
                type="email"
                placeholder="Enter your email address"
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={loading}
                required
                className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-slate-50 disabled:opacity-70"
              />
            </div>

            {/* Role */}
            <div className="mb-5">
              <label className="text-slate-600 text-xs font-semibold mb-1 block">
                CHOOSE ROLE
              </label>
              <select
                value={role}
                onChange={e => setRole(e.target.value)}
                disabled={loading}
                required
                className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-slate-50 disabled:opacity-70 bg-white"
                style={{ color: role ? "#0f172a" : "#94a3b8" }}
              >
                {ROLE_OPTIONS.map(opt => (
                  <option
                    key={opt.value}
                    value={opt.value}
                    disabled={opt.value === ""}
                    style={{ color: "#0f172a" }}
                  >
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !isValid}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed mb-2"
            >
              {loading ? "Verifying..." : "Sign In"}
            </button>

            {/* Back */}
            <button
              type="button"
              onClick={onBack}
              disabled={loading}
              className="w-full bg-slate-100 hover:bg-slate-200 text-slate-600 font-semibold py-2.5 rounded-lg text-sm transition-all duration-200 disabled:opacity-50"
            >
              ← Back
            </button>
          </form>

          <p className="text-center text-slate-400 text-xs mt-4">
            RML Digital DRM © 2026
          </p>
        </div>

      </div>
    </div>
  )
}

export default RoleVerificationModal