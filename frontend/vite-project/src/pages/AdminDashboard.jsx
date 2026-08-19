import { useState, useEffect } from "react"
import { useAuth } from "../context/AuthContext"
import RaneLogo from "../assets/Rane_Group_Logo.jpg"
import EmailServicesPanel from "./EmailServicesPanel"
import PendingApprovals from "./PendingApprovals"
import { API } from "../services/api"

// Valid department/role options. `value` must match the slug format
// already stored in role_access.role (lowercase, underscores) so nothing
// else in the app (verification, matching, imports) needs to change.
const ROLE_OPTIONS = [
  { value: "production", label: "Production" },
  { value: "manpower", label: "Manpower" },
  { value: "ovc", label: "OVC" },
  { value: "despatch", label: "Despatch" },
  { value: "sales", label: "Sales" },
  { value: "rejection_ppm", label: "Rejection PPM" },
  { value: "product_value", label: "Product Value" },
]

// "2 minutes ago" / "just now" style formatting for the Excel sync
// status bar. Falls back to a locale timestamp for anything over a day.
function formatSyncTime(isoString) {
  if (!isoString) return "never"
  const then = new Date(isoString)
  if (Number.isNaN(then.getTime())) return "never"
  const seconds = Math.round((Date.now() - then.getTime()) / 1000)
  if (seconds < 5) return "just now"
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return then.toLocaleString()
}

function AdminDashboard() {
  const { logout, token } = useAuth()
  const [mode, setMode] = useState("users") // "users" | "email" | "approvals"
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Wraps fetch so that if the session token is missing/expired, we log
  // the user out and send them back to the login screen instead of
  // leaving them stuck on a page that will 401 forever. Every call below
  // goes through this instead of calling fetch() directly.
  const authFetch = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`,
      },
    })

    if (response.status === 401) {
      logout()
      throw new Error("Your session has expired. Please log in again.")
    }

    return response
  }
  
  // Form states for adding/editing user
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [isPlantLocked, setIsPlantLocked] = useState(false)
  const [formData, setFormData] = useState({
    plant_id: "",
    role: "",
    person_name: "",
    email: "",
    employee_id: "",
    is_active: true
  })

  // Excel import states
  const [downloading, setDownloading] = useState(false)

  // Excel <-> Database sync status (Data Entry Users). Backed by
  // GET/POST /admin/sync — see admin_routes.py and app/scheduler.py.
  const [syncStatus, setSyncStatus] = useState(null)
  const [syncing, setSyncing] = useState(false)

  const fetchSyncStatus = async () => {
    try {
      const response = await authFetch(`${API}/admin/sync-status`)
      if (!response.ok) return
      setSyncStatus(await response.json())
    } catch {
      // Non-critical — the status bar just won't render if this fails.
    }
  }

  const handleSyncNow = async () => {
    setSyncing(true)
    try {
      const response = await authFetch(`${API}/admin/sync`, { method: "POST" })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Sync failed")
      await Promise.all([fetchUsers(), fetchSyncStatus()])
    } catch (err) {
      alert(err.message)
    } finally {
      setSyncing(false)
    }
  }

  const fetchUsers = async () => {
    try {
      const response = await authFetch(`${API}/role-access/list`)
      if (!response.ok) throw new Error("Failed to fetch users")
      const data = await response.json()
      setUsers(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
    fetchSyncStatus()
  }, [])

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value
    }))
  }

  const handleOpenForm = (user = null, lockedPlantId = null) => {
    if (user) {
      setEditingUser(user)
      setFormData({
        plant_id: user.plant_id,
        role: user.role,
        person_name: user.person_name,
        email: user.email,
        employee_id: user.employee_id || "",
        is_active: user.is_active
      })
      setIsPlantLocked(false)
    } else {
      setEditingUser(null)
      setFormData({
        plant_id: lockedPlantId !== null ? lockedPlantId : "",
        role: "",
        person_name: "",
        email: "",
        employee_id: "",
        is_active: true
      })
      setIsPlantLocked(lockedPlantId !== null)
    }
    setIsFormOpen(true)
  }

  const handleSaveUser = async (e) => {
    e.preventDefault()
    try {
      const payload = {
        ...formData,
        plant_id: parseInt(formData.plant_id, 10),
      }
      const url = editingUser 
        ? `${API}/role-access/user/${editingUser.id}` 
        : `${API}/role-access/user`
      
      const response = await authFetch(url, {
        method: editingUser ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || "Failed to save user")
      }

      const saved = await response.json()
      await fetchUsers()
      fetchSyncStatus()
      setIsFormOpen(false)
      if (saved.excel_sync_warning) alert(saved.excel_sync_warning)
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDeleteUser = async (id) => {
    if (!window.confirm("Are you sure you want to delete this user?")) return
    try {
      const response = await authFetch(`${API}/role-access/user/${id}`, {
        method: "DELETE"
      })
      if (!response.ok) throw new Error("Failed to delete user")
      const result = await response.json()
      await fetchUsers()
      fetchSyncStatus()
      if (result.excel_sync_warning) alert(result.excel_sync_warning)
    } catch (err) {
      alert(err.message)
    }
  }

  const handleToggleStatus = async (id, currentStatus) => {
    try {
      const response = await authFetch(`${API}/role-access/user/${id}/status?is_active=${!currentStatus}`, {
        method: "PATCH"
      })
      if (!response.ok) throw new Error("Failed to update status")
      const result = await response.json()
      await fetchUsers()
      fetchSyncStatus()
      if (result.excel_sync_warning) alert(result.excel_sync_warning)
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDownloadExcel = async () => {
    setDownloading(true)
    try {
      const response = await authFetch(`${API}/role-access/export`)
      if (!response.ok) throw new Error("Failed to export users")

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "data_entry_users.xlsx"
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert(err.message)
    } finally {
      setDownloading(false)
    }
  }


  // Group users by plant_id
  const groupedUsers = users.reduce((groups, user) => {
    const plantId = user.plant_id || 'Unassigned'
    if (!groups[plantId]) {
      groups[plantId] = []
    }
    groups[plantId].push(user)
    return groups
  }, {})

  // Get unique plant IDs sorted
  const plantIds = Object.keys(groupedUsers).sort((a, b) => {
    if (a === 'Unassigned') return 1
    if (b === 'Unassigned') return -1
    return parseInt(a) - parseInt(b)
  })

  // Color palette for plant sections
  const plantColors = [
    'border-blue-200 bg-blue-50',
    'border-green-200 bg-green-50',
    'border-purple-200 bg-purple-50',
    'border-orange-200 bg-orange-50',
    'border-pink-200 bg-pink-50',
    'border-teal-200 bg-teal-50',
    'border-indigo-200 bg-indigo-50',
    'border-rose-200 bg-rose-50',
  ]

  const getPlantColor = (index) => {
    return plantColors[index % plantColors.length]
  }

  if (mode === "users" && loading) return <div className="p-8 text-center text-slate-500">Loading Admin Dashboard...</div>
  if (mode === "users" && error) return <div className="p-8 text-center text-red-500">{error}</div>

  return (
    <div className="min-h-screen bg-slate-50">
      
      {/* Header with Company Branding - Reduced Logo Size */}
      <header className="bg-slate-900 px-6 py-3 flex justify-between items-center text-white shadow-lg">
        <div className="flex items-center gap-3">
          {/* Small Logo - Same style as Home component */}
          <img 
            src={RaneLogo} 
            alt="Rane Madras Ltd" 
            style={{ height: "45px", width: "auto", objectFit: "contain" }}
          />
          <div>
            <h1 className="text-base font-bold tracking-tight">Rane Madras Ltd</h1>
            <p className="text-[15px] text-slate-400 tracking-wide">Admin Dashboard</p>
          </div>
        </div>
        <button 
          onClick={logout} 
          className="bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded text-xs transition-colors duration-200 flex items-center gap-1.5 border border-slate-700"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Logout
        </button>
      </header>

      {/* Mode Tabs */}
      <div className="bg-white border-b border-slate-200 px-6">
        <div className="max-w-7xl mx-auto flex gap-1">
          <button
            onClick={() => setMode("users")}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors duration-150 ${
              mode === "users"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Data Entry Users
          </button>
          <button
            onClick={() => setMode("email")}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors duration-150 ${
              mode === "email"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Email Services
          </button>
          <button
            onClick={() => setMode("approvals")}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors duration-150 ${
              mode === "approvals"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Approvals
          </button>
        </div>
      </div>

      {mode === "email" ? (
        <EmailServicesPanel token={token} logout={logout} />
      ) : mode === "approvals" ? (
        <PendingApprovals token={token} logout={logout} />
      ) : (
      <>
      <main className="p-6 max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">User Management</h2>
            <p className="text-sm text-slate-500">Manage users across all plants</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleSyncNow}
              disabled={syncing}
              className="bg-slate-600 hover:bg-slate-700 text-white px-4 py-2 rounded text-sm transition-colors duration-200 flex items-center gap-2 shadow-sm disabled:opacity-50"
              title="Re-read users.xlsx from disk and apply any changes made directly in Excel"
            >
              <svg className={`w-4 h-4 ${syncing ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {syncing ? "Syncing..." : "Sync from Excel"}
            </button>
            <button 
              onClick={() => handleOpenForm()} 
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm transition-colors duration-200 flex items-center gap-2 shadow-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add User
            </button>
            <button
              onClick={handleDownloadExcel}
              disabled={downloading}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded text-sm transition-colors duration-200 flex items-center gap-2 shadow-sm disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              {downloading ? "Downloading..." : "Download Excel"}
            </button>
          </div>
        </div>

        {/* Excel <-> Database sync status. The Dashboard->Excel direction
            is always instant (every add/edit/delete/status-toggle above
            rewrites users.xlsx immediately); this bar reflects the
            Excel->Dashboard direction, which also runs automatically
            every couple of minutes in the background (see
            app/scheduler.py) — "Sync from Excel" above just runs it now
            instead of waiting. */}
        {syncStatus && (
          <div className="mb-4 -mt-2 text-xs text-slate-500 flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${syncStatus.file_exists ? "bg-emerald-500" : "bg-amber-500"}`} />
              {syncStatus.file_exists
                ? <>users.xlsx last edited {formatSyncTime(syncStatus.file_modified)}</>
                : <>users.xlsx not found on the server yet</>}
            </span>
            {syncStatus.last_synced && (
              <span>· last synced into the database {formatSyncTime(syncStatus.last_synced)}</span>
            )}
            {syncStatus.last_error && (
              <span className="text-red-500">· last sync attempt failed: {syncStatus.last_error}</span>
            )}
          </div>
        )}

        {/* Plant Sections */}
        <div className="space-y-6">
          {plantIds.map((plantId, plantIndex) => (
            <div key={plantId} className={`border-l-4 rounded-lg shadow-sm overflow-hidden ${getPlantColor(plantIndex)}`}>
              {/* Plant Header - Custom Font for Plant ID */}
              <div className="bg-white/90 backdrop-blur-sm px-6 py-3 border-b border-slate-200 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Plant</span>
                  <span className="text-2xl font-bold text-slate-800 tracking-tight" style={{ fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif" }}>
                    {plantId}
                  </span>
                  <span className="text-sm font-normal text-slate-500 bg-slate-100 px-2.5 py-0.5 rounded-full">
                    {groupedUsers[plantId].length} users
                  </span>
                </div>
                <button 
                  onClick={() => handleOpenForm(null, plantId !== "Unassigned" ? plantId : null)}
                  className="text-xs bg-white hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded border border-slate-300 transition-colors duration-200 flex items-center gap-1"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add User
                </button>
              </div>

              {/* Users Table for this Plant */}
              <div className="bg-white overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-sm text-slate-600">
                      <th className="p-4 font-semibold">Role</th>
                      <th className="p-4 font-semibold">Name</th>
                      <th className="p-4 font-semibold">Email</th>
                      <th className="p-4 font-semibold">Emp ID</th>
                      <th className="p-4 font-semibold">Status</th>
                      <th className="p-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedUsers[plantId].map((u) => (
                      <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50/70 transition-colors duration-150">
                        <td className="p-4 text-sm text-slate-800">
                          <span className="bg-slate-100 px-2 py-1 rounded text-xs font-mono">
                            {u.role}
                          </span>
                        </td>
                        <td className="p-4 text-sm text-slate-800 font-medium">{u.person_name}</td>
                        <td className="p-4 text-sm text-slate-600">{u.email}</td>
                        <td className="p-4 text-sm text-slate-600">{u.employee_id || "-"}</td>
                        <td className="p-4 text-sm">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${u.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                            {u.is_active ? "● Active" : "● Inactive"}
                          </span>
                        </td>
                        <td className="p-4 text-sm text-right">
                          <div className="flex justify-end gap-2">
                            <button 
                              onClick={() => handleToggleStatus(u.id, u.is_active)} 
                              className="p-1.5 rounded hover:bg-slate-100 transition-colors duration-200 text-slate-500 hover:text-slate-800" 
                              title={u.is_active ? "Deactivate" : "Activate"}
                            >
                              {u.is_active ? "⛔" : "✅"}
                            </button>
                            <button 
                              onClick={() => handleOpenForm(u)} 
                              className="px-3 py-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors duration-200 text-sm"
                            >
                              Edit
                            </button>
                            <button 
                              onClick={() => handleDeleteUser(u.id)} 
                              className="px-3 py-1 text-red-600 hover:text-red-800 hover:bg-red-50 rounded transition-colors duration-200 text-sm"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {users.length === 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center">
              <svg className="w-16 h-16 mx-auto text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              <h3 className="text-lg font-medium text-slate-700 mb-2">No users found</h3>
              <p className="text-slate-500">Import from Excel or add manually to get started.</p>
            </div>
          )}
        </div>
      </main>

      {/* Modal Form */}
      {isFormOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 transform transition-all">
            <div className="flex items-center gap-3 mb-6">
              <img 
                src={RaneLogo} 
                alt="Rane Madras Ltd" 
                style={{ height: "28px", width: "auto", objectFit: "contain" }}
              />
              <div>
                <h3 className="text-xl font-bold text-slate-800">{editingUser ? "Edit User" : "Add New User"}</h3>
                <p className="text-xs text-slate-500">Rane Madras Ltd • User Management</p>
              </div>
            </div>
            <form onSubmit={handleSaveUser}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Plant ID *</label>
                  <input 
                    type="number" 
                    name="plant_id" 
                    value={formData.plant_id} 
                    onChange={handleInputChange} 
                    required 
                    readOnly={isPlantLocked}
                    className={`w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none ${isPlantLocked ? "bg-slate-100 text-slate-500 cursor-not-allowed" : ""}`}
                  />
                  {isPlantLocked && (
                    <p className="text-xs text-slate-400 mt-1">Locked to this plant's section.</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Role (Department) *</label>
                  <select
                    name="role"
                    value={formData.role}
                    onChange={handleInputChange}
                    required
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none bg-white"
                  >
                    <option value="">Select role...</option>
                    {ROLE_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                    {/* Preserve an existing record's role even if it isn't
                        one of the standard options above, so editing it
                        doesn't silently blank out or change its value. */}
                    {formData.role && !ROLE_OPTIONS.some(opt => opt.value === formData.role) && (
                      <option value={formData.role}>{formData.role}</option>
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Name *</label>
                  <input 
                    type="text" 
                    name="person_name" 
                    value={formData.person_name} 
                    onChange={handleInputChange} 
                    required 
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none" 
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Email *</label>
                  <input 
                    type="email" 
                    name="email" 
                    value={formData.email} 
                    onChange={handleInputChange} 
                    required 
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none" 
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Employee ID</label>
                  <input 
                    type="text" 
                    name="employee_id" 
                    value={formData.employee_id} 
                    onChange={handleInputChange} 
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none" 
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input 
                    type="checkbox" 
                    id="is_active" 
                    name="is_active" 
                    checked={formData.is_active} 
                    onChange={handleInputChange} 
                    className="h-4 w-4 text-blue-600 border-slate-300 rounded focus:ring-2 focus:ring-blue-500" 
                  />
                  <label htmlFor="is_active" className="text-sm text-slate-700">Active User</label>
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <button 
                  type="button" 
                  onClick={() => setIsFormOpen(false)} 
                  className="px-4 py-2 text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors duration-200"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="px-4 py-2 text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors duration-200 shadow-sm"
                >
                  {editingUser ? "Update User" : "Save User"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      </>
      )}
    </div>
  )
}

export default AdminDashboard