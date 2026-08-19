import { useState } from "react"
import { loginUser, adLoginUser } from "../services/api"
import { useAuth } from "../context/AuthContext"

function Login() {
  // "local" = existing username/app-password login.
  // "ad"    = Windows/Active Directory login (all plants), using a
  //           company GEN ID + Windows/Domain password. The person is
  //           mapped to their Plant/Department/Role automatically —
  //           see ad_auth_service.resolve_plant_department_role().
  const [mode, setMode] = useState("local")
  const [username, setUsername] = useState("")
  const [genId, setGenId] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false);
  const { login } = useAuth()

  const handleModeChange = (nextMode) => {
    setMode(nextMode)
    setError("")
    setPassword("")
  }

  const handleLogin = async () => {
    setLoading(true)
    setError("")

    try {
      const response = await loginUser({ username, password })
      const data = response.data

      login(
        {
          username: data.username,
          role: data.role,
          plant_id: data.plant_id,
        },
        data.access_token
      )
    } catch {
      // Generic on purpose — never reveal whether the username exists.
      setError("Invalid username or password!")
    }

    setLoading(false)
  }

  const handleAdLogin = async () => {
    setLoading(true)
    setError("")

    try {
      const response = await adLoginUser({ gen_id: genId, password })
      const data = response.data

      login(
        {
          username: data.username,
          role: data.role,
          plant_id: data.plant_id,
          department: data.department,
          person_name: data.person_name,
        },
        data.access_token
      )
    } catch {
      // Generic on purpose — never reveal whether the GEN ID is valid,
      // whether AD accepted the password, or whether the person simply
      // isn't provisioned for any plant/department. Same message either way.
      setError("Invalid username or password!")
    }

    setLoading(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 px-4 py-6">

      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">

        {/* Header */}
        <div className="bg-slate-900 px-8 py-6 text-center">

          <div className="flex justify-center mb-4">
            <img
              src="/src/assets/Rane_Group_Logo.jpg"
             
              style={{
                height: "55px",
                width: "auto",
                objectFit: "contain"
              }}
            />
          </div>

          <h2 className="text-white text-xl font-bold">
            Rane Madras Ltd
          </h2>

          <p className="text-slate-400 text-sm mt-1">
            ECD Division
          </p>

          <div className="w-16 h-px bg-blue-500 mx-auto my-4"></div>

          <h3 className="text-white text-lg font-semibold">
            Digital DRM Dashboard
          </h3>

          <p className="text-slate-400 text-xs mt-1">
            Daily Review Meeting
          </p>

        </div>

        {/* Login Form */}
        <div className="px-8 py-6">

          <p className="text-slate-500 text-sm mb-5 text-center">
            Sign in to continue
          </p>

          {/* Local vs Windows/AD mode toggle */}
          <div className="flex bg-slate-100 rounded-lg p-1 mb-5 text-sm">
            <button
              type="button"
              onClick={() => handleModeChange("local")}
              className={`flex-1 py-2 rounded-md font-medium transition-colors duration-150 ${
                mode === "local" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => handleModeChange("ad")}
              className={`flex-1 py-2 rounded-md font-medium transition-colors duration-150 ${
                mode === "ad" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Windows / AD Login
            </button>
          </div>

          {mode === "local" ? (
          <div className="mb-4">
            <label className="text-slate-600 text-xs font-semibold block mb-1">
              USERNAME
            </label>

            <input
              type="text"
              placeholder="Enter username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
          ) : (
          <div className="mb-4">
            <label className="text-slate-600 text-xs font-semibold block mb-1">
              GEN ID
            </label>

            <input
              type="text"
              placeholder="Enter your company GEN ID"
              value={genId}
              onChange={(e) => setGenId(e.target.value)}
              className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
            <p className="text-slate-400 text-xs mt-1">Sign in with your Windows/Domain credentials.</p>
          </div>
          )}

        <div className="mb-4">
  <label className="text-slate-600 text-xs font-semibold block mb-1">
    PASSWORD
  </label>

  <div className="relative">
    <input
      type={showPassword ? "text" : "password"}
      placeholder="Enter password"
      value={password}
      onChange={(e) => setPassword(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && (mode === "local" ? handleLogin() : handleAdLogin())}
      className="w-full px-4 py-3 pr-12 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
    />

    <button
      type="button"
      onClick={() => setShowPassword(!showPassword)}
      className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-500 hover:text-slate-700 focus:outline-none"
      tabIndex={-1}
    >
      {showPassword ? (
        // Eye Slash
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="w-5 h-5"
        >
          <path d="M3.53 2.47a.75.75 0 10-1.06 1.06l18 18a.75.75 0 101.06-1.06l-2.2-2.2A12.6 12.6 0 0022.5 12S18.75 4.5 12 4.5c-1.58 0-3.04.34-4.37.92L3.53 2.47zm7.94 7.94a2.25 2.25 0 013.12 3.12l-3.12-3.12z"/>
          <path d="M5.74 7.68A13.9 13.9 0 001.5 12s3.75 7.5 10.5 7.5c1.95 0 3.73-.43 5.29-1.17l-2.07-2.07a3.75 3.75 0 01-5.01-5.01L5.74 7.68z"/>
        </svg>
      ) : (
        // Eye
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="w-5 h-5"
        >
          <path d="M12 5.25c-6.75 0-10.5 6.75-10.5 6.75S5.25 18.75 12 18.75 22.5 12 22.5 12 18.75 5.25 12 5.25zm0 11.25A4.5 4.5 0 1112 7.5a4.5 4.5 0 010 9z"/>
          <path d="M12 9a3 3 0 100 6 3 3 0 000-6z"/>
        </svg>
      )}
    </button>
  </div>
</div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-600 text-xs px-3 py-2 rounded-lg mb-4">
              {error}
            </div>
          )}

          <button
            onClick={mode === "local" ? handleLogin : handleAdLogin}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg text-sm transition-all duration-200 disabled:opacity-50"
          >
            {loading ? "Signing In..." : "Sign In"}
          </button>

          <p className="text-center text-slate-400 text-xs mt-5">
            RML Digital DRM © 2026
          </p>

        </div>

      </div>
    </div>
  )
}

export default Login