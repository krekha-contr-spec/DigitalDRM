import { useState, useEffect, useRef } from "react"
import RaneLogo from "../assets/Rane_Group_Logo.jpg"
import { API } from "../services/api"

const API_BASE = API

// Same department slugs used by role_access.role / reminder_service.py /
// report_save_routes.py, so a Staff Incharge recipient set here lines up
// with the rest of the app without any extra mapping.
const DEPARTMENT_OPTIONS = [
  { value: "production", label: "Production" },
  { value: "manpower", label: "Manpower" },
  { value: "ovc", label: "OVC" },
  { value: "despatch", label: "Despatch" },
  { value: "sales", label: "Sales" },
  { value: "rejection_ppm", label: "Rejection PPM" },
  { value: "product_value", label: "Product Value" },
]

const RECIPIENT_TYPE_OPTIONS = [
  { value: "staff_incharge", label: "Staff Incharge", needsDepartment: true },
  { value: "plant_head", label: "Plant Head", needsDepartment: false },
  { value: "president", label: "President", needsDepartment: false },
  { value: "admin", label: "Admin (User Approval Notifications)", needsDepartment: false },
  { value: "daily_report_recipient", label: "Daily Report Recipient (Staff Incharge)", needsDepartment: false },
  { value: "overall_summary_recipient", label: "Overall Summary Recipient (President Dashboard)", needsDepartment: false },
]

const typeLabel = (value) => RECIPIENT_TYPE_OPTIONS.find((t) => t.value === value)?.label || value
const deptLabel = (value) => DEPARTMENT_OPTIONS.find((d) => d.value === value)?.label || value

// Sentinel used (instead of null) to lock the Plant field to "All Plants"
// when adding a recipient from the global/all-plants section header.
const GLOBAL_LOCK = "global"

// "2 minutes ago" / "just now" style formatting for the Excel sync
// status bar. Same helper as AdminDashboard.jsx's Data Entry Users tab.
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

function EmailServicesPanel({ token, logout }) {
  const [recipients, setRecipients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Form states for adding/editing a recipient — mirrors Data Entry
  // Users' isFormOpen / editingUser / isPlantLocked / formData pattern.
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editingRecipient, setEditingRecipient] = useState(null)
  const [isPlantLocked, setIsPlantLocked] = useState(false)
  const [formData, setFormData] = useState({
    plant_id: "",
    recipient_type: "staff_incharge",
    department: "",
    name: "",
    email: "",
    is_active: true,
  })

  // Excel export state — mirrors Data Entry Users' `downloading` state.
  const [downloading, setDownloading] = useState(false)
  // Excel import state + hidden file input (Data Entry Users has no
  // Import button in its UI yet, so this introduces the pattern fresh).
  const [importing, setImporting] = useState(false)
  const fileInputRef = useRef(null)

  // Excel <-> Database sync status. Backed by GET/POST
  // /admin/email-recipients/sync-status and /sync — mirrors the Data
  // Entry Users tab's sync bar.
  const [syncStatus, setSyncStatus] = useState(null)
  const [syncing, setSyncing] = useState(false)

  // Wraps fetch so that if the session token is missing/expired, we log
  // the user out instead of leaving them stuck on a page that will 401
  // forever — identical pattern to the Data Entry Users tab.
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

  const fetchRecipients = async () => {
    try {
      const response = await authFetch(`${API_BASE}/admin/email-recipients`)
      if (!response.ok) throw new Error("Failed to fetch email recipients")
      const data = await response.json()
      setRecipients(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchSyncStatus = async () => {
    try {
      const response = await authFetch(`${API_BASE}/admin/email-recipients/sync-status`)
      if (!response.ok) return
      setSyncStatus(await response.json())
    } catch {
      // Non-critical — the status bar just won't render if this fails.
    }
  }

  const handleSyncNow = async () => {
    setSyncing(true)
    try {
      const response = await authFetch(`${API_BASE}/admin/email-recipients/sync`, { method: "POST" })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Sync failed")
      await Promise.all([fetchRecipients(), fetchSyncStatus()])
    } catch (err) {
      alert(err.message)
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    fetchRecipients()
    fetchSyncStatus()
  }, [])

  const selectedTypeMeta = RECIPIENT_TYPE_OPTIONS.find((t) => t.value === formData.recipient_type)

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }))
  }

  // lockedPlantId: a real plant id (number/string) to lock the Plant
  // field to that plant, GLOBAL_LOCK to lock it to "All Plants" (blank),
  // or null for a completely free-entry Add Recipient (top toolbar).
  const handleOpenForm = (recipient = null, lockedPlantId = null) => {
    if (recipient) {
      setEditingRecipient(recipient)
      setFormData({
        plant_id: recipient.plant_id ?? "",
        recipient_type: recipient.recipient_type,
        department: recipient.department || "",
        name: recipient.name || "",
        email: recipient.email,
        is_active: recipient.is_active,
      })
      setIsPlantLocked(false)
    } else {
      setEditingRecipient(null)
      setFormData({
        plant_id: lockedPlantId !== null && lockedPlantId !== GLOBAL_LOCK ? lockedPlantId : "",
        recipient_type: "staff_incharge",
        department: "",
        name: "",
        email: "",
        is_active: true,
      })
      setIsPlantLocked(lockedPlantId !== null)
    }
    setIsFormOpen(true)
  }

  const handleSave = async (e) => {
    e.preventDefault()
    try {
      const typeMeta = RECIPIENT_TYPE_OPTIONS.find((t) => t.value === formData.recipient_type)
      const payload = {
        recipient_type: formData.recipient_type,
        department: typeMeta?.needsDepartment ? formData.department : null,
        plant_id: formData.plant_id === "" ? null : parseInt(formData.plant_id, 10),
        name: formData.name || null,
        email: formData.email,
        is_active: formData.is_active,
      }

      const url = editingRecipient
        ? `${API_BASE}/admin/email-recipients/${editingRecipient.id}`
        : `${API_BASE}/admin/email-recipients`

      const response = await authFetch(url, {
        method: editingRecipient ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || "Failed to save email recipient")
      }

      await fetchRecipients()
      fetchSyncStatus()
      setIsFormOpen(false)
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this recipient?")) return
    try {
      const response = await authFetch(`${API_BASE}/admin/email-recipients/${id}`, {
        method: "DELETE",
      })
      if (!response.ok) throw new Error("Failed to delete email recipient")
      await fetchRecipients()
      fetchSyncStatus()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleToggleStatus = async (id, currentStatus) => {
    try {
      const response = await authFetch(
        `${API_BASE}/admin/email-recipients/${id}/status?is_active=${!currentStatus}`,
        { method: "PATCH" }
      )
      if (!response.ok) throw new Error("Failed to update status")
      await fetchRecipients()
      fetchSyncStatus()
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDownloadExcel = async () => {
    setDownloading(true)
    try {
      const response = await authFetch(`${API_BASE}/admin/email-recipients/export`)
      if (!response.ok) throw new Error("Failed to export email recipients")

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "email_services_recipients.xlsx"
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

  const handleImportClick = () => {
    fileInputRef.current?.click()
  }

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0]
    // Reset the input immediately so selecting the same file again later
    // still fires onChange.
    e.target.value = ""
    if (!file) return

    setImporting(true)
    try {
      const body = new FormData()
      body.append("file", file)

      const response = await authFetch(`${API_BASE}/admin/email-recipients/import`, {
        method: "POST",
        body,
      })

      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || "Import failed")

      await fetchRecipients()
      fetchSyncStatus()

      const errorNote = result.errors?.length
        ? `\n\n${result.errors.length} row(s) skipped:\n${result.errors.slice(0, 10).join("\n")}${result.errors.length > 10 ? "\n…" : ""}`
        : ""
      alert(
        `Import complete.\nCreated: ${result.created}  Updated: ${result.updated}  ` +
        `Unchanged: ${result.unchanged}  Skipped: ${result.skipped}` +
        errorNote
      )
    } catch (err) {
      alert(err.message)
    } finally {
      setImporting(false)
    }
  }


  // fallback bucket), mirroring Data Entry Users' groupedUsers/'Unassigned'.
  const groupedRecipients = recipients.reduce((groups, r) => {
    const plantId = r.plant_id === null || r.plant_id === undefined ? "All Plants" : r.plant_id
    if (!groups[plantId]) {
      groups[plantId] = []
    }
    groups[plantId].push(r)
    return groups
  }, {})

  // Get unique plant keys sorted, with "All Plants" always last.
  const plantIds = Object.keys(groupedRecipients).sort((a, b) => {
    if (a === "All Plants") return 1
    if (b === "All Plants") return -1
    return parseInt(a) - parseInt(b)
  })

  // Identical color palette to Data Entry Users so both pages feel like
  // one consistent system.
  const plantColors = [
    "border-blue-200 bg-blue-50",
    "border-green-200 bg-green-50",
    "border-purple-200 bg-purple-50",
    "border-orange-200 bg-orange-50",
    "border-pink-200 bg-pink-50",
    "border-teal-200 bg-teal-50",
    "border-indigo-200 bg-indigo-50",
    "border-rose-200 bg-rose-50",
  ]

  const getPlantColor = (index) => plantColors[index % plantColors.length]

  if (loading) return <div className="p-8 text-center text-slate-500">Loading Email Services...</div>
  if (error) return <div className="p-8 text-center text-red-500">{error}</div>

  return (
    <>
      <main className="p-6 max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">Email Services</h2>
            <p className="text-sm text-slate-500">Manage automated email recipients across all plants</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleSyncNow}
              disabled={syncing}
              className="bg-slate-600 hover:bg-slate-700 text-white px-4 py-2 rounded text-sm transition-colors duration-200 flex items-center gap-2 shadow-sm disabled:opacity-50"
              title="Re-read email_users.xlsx from disk and apply any changes made directly in Excel"
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
              Add Recipient
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={handleImportFile}
              className="hidden"
            />
            <button
              onClick={handleImportClick}
              disabled={importing}
              className="bg-white hover:bg-slate-50 text-slate-700 px-4 py-2 rounded text-sm transition-colors duration-200 flex items-center gap-2 shadow-sm border border-slate-300 disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M12 12v9m0-9l-3 3m3-3l3 3" />
              </svg>
              {importing ? "Importing..." : "Import"}
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

        {/* Excel <-> Database sync status — mirrors the Data Entry
            Users tab's bar. Dashboard->Excel is instant (every
            add/edit/delete/status-toggle rewrites email_users.xlsx
            immediately); Excel->Dashboard also runs automatically every
            couple of minutes in the background (see app/scheduler.py) —
            "Sync from Excel" above just runs it now instead of waiting. */}
        {syncStatus && (
          <div className="mb-4 -mt-2 text-xs text-slate-500 flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${syncStatus.file_exists ? "bg-emerald-500" : "bg-amber-500"}`} />
              {syncStatus.file_exists
                ? <>email_users.xlsx last edited {formatSyncTime(syncStatus.file_modified)}</>
                : <>email_users.xlsx not found on the server yet</>}
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
              {/* Plant Header */}
              <div className="bg-white/90 backdrop-blur-sm px-6 py-3 border-b border-slate-200 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                    {plantId === "All Plants" ? "Global Default" : "Plant"}
                  </span>
                  <span className="text-2xl font-bold text-slate-800 tracking-tight" style={{ fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif" }}>
                    {plantId}
                  </span>
                  <span className="text-sm font-normal text-slate-500 bg-slate-100 px-2.5 py-0.5 rounded-full">
                    {groupedRecipients[plantId].length} recipient(s)
                  </span>
                </div>
                <button
                  onClick={() => handleOpenForm(null, plantId !== "All Plants" ? plantId : GLOBAL_LOCK)}
                  className="text-xs bg-white hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded border border-slate-300 transition-colors duration-200 flex items-center gap-1"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add Recipient
                </button>
              </div>

              {/* Recipients Table for this Plant */}
              <div className="bg-white overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-sm text-slate-600">
                      <th className="p-4 font-semibold">Type</th>
                      <th className="p-4 font-semibold">Department</th>
                      <th className="p-4 font-semibold">Name</th>
                      <th className="p-4 font-semibold">Email</th>
                      <th className="p-4 font-semibold">Status</th>
                      <th className="p-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedRecipients[plantId].map((r) => (
                      <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/70 transition-colors duration-150">
                        <td className="p-4 text-sm text-slate-800">
                          <span className="bg-slate-100 px-2 py-1 rounded text-xs font-mono">
                            {typeLabel(r.recipient_type)}
                          </span>
                        </td>
                        <td className="p-4 text-sm text-slate-600">{r.department ? deptLabel(r.department) : "-"}</td>
                        <td className="p-4 text-sm text-slate-800 font-medium">{r.name || "-"}</td>
                        <td className="p-4 text-sm text-slate-600">{r.email}</td>
                        <td className="p-4 text-sm">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${r.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                            {r.is_active ? "● Active" : "● Inactive"}
                          </span>
                        </td>
                        <td className="p-4 text-sm text-right">
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => handleToggleStatus(r.id, r.is_active)}
                              className="p-1.5 rounded hover:bg-slate-100 transition-colors duration-200 text-slate-500 hover:text-slate-800"
                              title={r.is_active ? "Deactivate" : "Activate"}
                            >
                              {r.is_active ? "⛔" : "✅"}
                            </button>
                            <button
                              onClick={() => handleOpenForm(r)}
                              className="px-3 py-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors duration-200 text-sm"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(r.id)}
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

          {recipients.length === 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center">
              <svg className="w-16 h-16 mx-auto text-slate-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <h3 className="text-lg font-medium text-slate-700 mb-2">No email recipients found</h3>
              <p className="text-slate-500">Add a Staff Incharge, Plant Head, or President recipient to get started.</p>
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
                <h3 className="text-xl font-bold text-slate-800">{editingRecipient ? "Edit Recipient" : "Add New Recipient"}</h3>
                <p className="text-xs text-slate-500">Rane Madras Ltd • Email Services</p>
              </div>
            </div>
            <form onSubmit={handleSave}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Plant ID</label>
                  <input
                    type="number"
                    name="plant_id"
                    value={formData.plant_id}
                    onChange={handleInputChange}
                    readOnly={isPlantLocked}
                    placeholder="Leave blank for All Plants (global default)"
                    className={`w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none ${isPlantLocked ? "bg-slate-100 text-slate-500 cursor-not-allowed" : ""}`}
                  />
                  {isPlantLocked ? (
                    <p className="text-xs text-slate-400 mt-1">Locked to this plant's section.</p>
                  ) : (
                    <p className="text-xs text-slate-400 mt-1">
                      Leave blank to apply to all plants unless a plant-specific entry exists.
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Recipient Type *</label>
                  <select
                    name="recipient_type"
                    value={formData.recipient_type}
                    onChange={handleInputChange}
                    required
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none bg-white"
                  >
                    {RECIPIENT_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>

                {selectedTypeMeta?.needsDepartment && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Department *</label>
                    <select
                      name="department"
                      value={formData.department}
                      onChange={handleInputChange}
                      required
                      className="w-full border border-slate-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition outline-none bg-white"
                    >
                      <option value="">Select department...</option>
                      {DEPARTMENT_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                      {/* Preserve an existing record's department even if it
                          isn't one of the standard options above, so editing
                          it doesn't silently blank out or change its value. */}
                      {formData.department && !DEPARTMENT_OPTIONS.some(opt => opt.value === formData.department) && (
                        <option value={formData.department}>{formData.department}</option>
                      )}
                    </select>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
                  <input
                    type="text"
                    name="name"
                    value={formData.name}
                    onChange={handleInputChange}
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

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_active_email"
                    name="is_active"
                    checked={formData.is_active}
                    onChange={handleInputChange}
                    className="h-4 w-4 text-blue-600 border-slate-300 rounded focus:ring-2 focus:ring-blue-500"
                  />
                  <label htmlFor="is_active_email" className="text-sm text-slate-700">Active Recipient</label>
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
                  {editingRecipient ? "Update Recipient" : "Save Recipient"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}

export default EmailServicesPanel