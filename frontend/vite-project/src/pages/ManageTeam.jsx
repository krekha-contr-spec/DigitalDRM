// ManageTeam.jsx
// Plant Head's screen for requesting Data Entry User add/remove
// changes. Every submit here creates a pending UserApprovalRequest and
// emails the configured Admin recipient — nothing here touches
// role_access directly (see app/routes/role_access_routes.py's
// /plant-head/request-add and /request-remove/{id}, and
// app/services/approval_service.py for the full workflow).

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "../context/AuthContext"
import RaneLogo from "../assets/Rane_Group_Logo.jpg";
import { API } from "../services/api"

const ROLE_OPTIONS = [
  { value: "production", label: "Production" },
  { value: "manpower", label: "Manpower" },
  { value: "ovc", label: "OVC" },
  { value: "despatch", label: "Despatch" },
  { value: "sales", label: "Sales" },
  { value: "rejection_ppm", label: "Rejection PPM" },
  { value: "product_value", label: "Product Value" },
]

const ROLE_LABELS = Object.fromEntries(ROLE_OPTIONS.map(o => [o.value, o.label]))

const STATUS_BADGE = {
  pending:  { bg: "#fef3c7", color: "#b45309", label: "Pending Admin Approval" },
  approved: { bg: "#dcfce7", color: "#16a34a", label: "Approved" },
  rejected: { bg: "#fee2e2", color: "#dc2626", label: "Rejected" },
  expired:  { bg: "#f1f5f9", color: "#64748b", label: "Expired" },
}

function formatDate(iso) {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
}

function ManageTeam({ onBack }) {
  const { user, token, logout } = useAuth()

  const [users, setUsers] = useState([])
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [banner, setBanner] = useState(null)

  const [showAddForm, setShowAddForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [removingId, setRemovingId] = useState(null)
  const [form, setForm] = useState({ role: "", person_name: "", email: "", employee_id: "" })

  const authFetch = useCallback(async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` },
    })
    if (response.status === 401) {
      logout()
      throw new Error("Your session has expired. Please log in again.")
    }
    return response
  }, [token, logout])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [usersRes, requestsRes] = await Promise.all([
        authFetch(`${API}/role-access/plant-head/my-users`),
        authFetch(`${API}/role-access/plant-head/my-requests`),
      ])
      if (!usersRes.ok) throw new Error("Failed to load your team.")
      if (!requestsRes.ok) throw new Error("Failed to load your requests.")
      setUsers(await usersRes.json())
      setRequests(await requestsRes.json())
    } catch (err) {
      setError(err.message || "Something went wrong.")
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => { fetchAll() }, [fetchAll])

  const submitAdd = async (e) => {
    e.preventDefault()
    if (!form.role || !form.person_name.trim() || !form.email.trim()) {
      setBanner({ type: "error", text: "Department, Name, and Email are required." })
      return
    }
    setSubmitting(true)
    setBanner(null)
    try {
      const res = await authFetch(`${API}/role-access/plant-head/request-add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: form.role,
          person_name: form.person_name.trim(),
          email: form.email.trim(),
          employee_id: form.employee_id.trim() || null,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || "Failed to submit request.")
      setBanner({ type: "success", text: data.message })
      setForm({ role: "", person_name: "", email: "", employee_id: "" })
      setShowAddForm(false)
      fetchAll()
    } catch (err) {
      setBanner({ type: "error", text: err.message })
    } finally {
      setSubmitting(false)
    }
  }

  const requestRemove = async (userId) => {
    setRemovingId(userId)
    setBanner(null)
    try {
      const res = await authFetch(`${API}/role-access/plant-head/request-remove/${userId}`, { method: "POST" })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || "Failed to submit request.")
      setBanner({ type: "success", text: data.message })
      fetchAll()
    } catch (err) {
      setBanner({ type: "error", text: err.message })
    } finally {
      setRemovingId(null)
    }
  }

  // Has a pending remove-request already been submitted for this user?
  // Used to disable the button and avoid the same person being
  // submitted for removal twice while the first is still pending.
  const pendingRemovalUserIds = new Set(
    requests.filter(r => r.action === "remove" && r.status === "pending").map(r => r.target_user_id)
  )

  return (
    <div style={{ minHeight: "100vh", background: "#f1f5f9" }}>
      <div style={{ background: "#0f172a", padding: "17px 32px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <img src={RaneLogo} alt="Rane Madras Ltd" style={{ height: "36px", width: "auto", objectFit: "contain" }} />
          <div>
            <p style={{ color: "white", fontWeight: "bold", fontSize: "17px", margin: 0 }}>Manage Team</p>
            <p style={{ color: "#94a3b8", fontSize: "11px", margin: 0 }}>Plant {user.plant_id} — Data Entry Users</p>
          </div>
        </div>
        <button onClick={onBack} style={{ background: "#334155", color: "white", border: "none", padding: "8px 16px", borderRadius: "6px", cursor: "pointer", fontSize: "13px" }}>
          ← Back
        </button>
      </div>

      <div className="max-w-5xl mx-auto p-6">
        <div className="bg-blue-50 border border-blue-200 text-blue-700 text-sm rounded-md px-4 py-3 mb-5">
          Adding or removing a Data Entry User needs Admin approval — a request is emailed to the Admin the moment you submit it below, and takes effect only once approved. Removing a user marks them Inactive; nothing is ever deleted.
        </div>

        {banner && (
          <div
            className="mb-4 px-4 py-2.5 rounded-md text-sm"
            style={{ background: banner.type === "success" ? "#dcfce7" : "#fee2e2", color: banner.type === "success" ? "#16a34a" : "#dc2626" }}
          >
            {banner.text}
          </div>
        )}

        {loading ? (
          <div className="text-center text-slate-500 py-10">Loading...</div>
        ) : error ? (
          <div className="text-center text-red-500 py-10">{error}</div>
        ) : (
          <>
            {/* Current team */}
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden mb-6">
              <div className="flex justify-between items-center px-4 py-3 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-800">Your Team</h3>
                <button
                  onClick={() => setShowAddForm(s => !s)}
                  className="text-xs px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700"
                >
                  {showAddForm ? "Cancel" : "+ Request Add User"}
                </button>
              </div>

              {showAddForm && (
                <form onSubmit={submitAdd} className="px-4 py-4 border-b border-slate-100 bg-slate-50 grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Department</label>
                    <select
                      value={form.role}
                      onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                      className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                    >
                      <option value="">Select department...</option>
                      {ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Employee ID (optional)</label>
                    <input
                      value={form.employee_id}
                      onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}
                      className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Name</label>
                    <input
                      value={form.person_name}
                      onChange={e => setForm(f => ({ ...f, person_name: e.target.value }))}
                      className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Email</label>
                    <input
                      type="email"
                      value={form.email}
                      onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                      className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="col-span-2 flex justify-end">
                    <button
                      type="submit"
                      disabled={submitting}
                      className="text-xs px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {submitting ? "Submitting..." : "Submit for Admin Approval"}
                    </button>
                  </div>
                </form>
              )}

              {users.length === 0 ? (
                <div className="text-center text-slate-400 py-8 text-sm">No Data Entry Users yet for your plant.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                    <tr>
                      <th className="text-left px-4 py-2">Department</th>
                      <th className="text-left px-4 py-2">Name</th>
                      <th className="text-left px-4 py-2">Email</th>
                      <th className="text-left px-4 py-2">Status</th>
                      <th className="text-right px-4 py-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => (
                      <tr key={u.id} className="border-t border-slate-100">
                        <td className="px-4 py-2.5 text-slate-700">{ROLE_LABELS[u.role] || u.role}</td>
                        <td className="px-4 py-2.5 text-slate-700">{u.person_name}</td>
                        <td className="px-4 py-2.5 text-slate-500">{u.email}</td>
                        <td className="px-4 py-2.5">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${u.is_active ? "bg-green-50 text-green-600" : "bg-slate-100 text-slate-500"}`}>
                            {u.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {u.is_active ? (
                            pendingRemovalUserIds.has(u.id) ? (
                              <span className="text-xs text-amber-600">Removal pending approval</span>
                            ) : (
                              <button
                                disabled={removingId === u.id}
                                onClick={() => requestRemove(u.id)}
                                className="text-xs px-3 py-1.5 rounded-md bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 disabled:opacity-50"
                              >
                                {removingId === u.id ? "..." : "Request Remove"}
                              </button>
                            )
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Request history */}
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-800">Your Requests</h3>
              </div>
              {requests.length === 0 ? (
                <div className="text-center text-slate-400 py-8 text-sm">No requests submitted yet.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                    <tr>
                      <th className="text-left px-4 py-2">Action</th>
                      <th className="text-left px-4 py-2">Details</th>
                      <th className="text-left px-4 py-2">Submitted</th>
                      <th className="text-left px-4 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {requests.map(r => {
                      const badge = STATUS_BADGE[r.status] || STATUS_BADGE.pending
                      return (
                        <tr key={r.id} className="border-t border-slate-100">
                          <td className="px-4 py-2.5">
                            <span className={`text-xs font-semibold px-2 py-0.5 rounded ${r.action === "add" ? "bg-blue-50 text-blue-600" : "bg-orange-50 text-orange-600"}`}>
                              {r.action === "add" ? "Add" : "Remove"}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-slate-700">
                            {r.action === "add" ? `${r.person_name} (${ROLE_LABELS[r.role] || r.role})` : (r.target_label || "—")}
                          </td>
                          <td className="px-4 py-2.5 text-slate-500 text-xs">{formatDate(r.created_at)}</td>
                          <td className="px-4 py-2.5">
                            <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: badge.bg, color: badge.color }}>
                              {badge.label}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default ManageTeam