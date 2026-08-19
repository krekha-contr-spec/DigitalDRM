// PendingApprovals.jsx
// Admin Dashboard tab for reviewing Plant Head add/remove-user requests
// without needing to check email — mirrors EmailServicesPanel.jsx's
// props (token, logout) and styling conventions. Talks to the backend's
// GET /approvals and POST /approvals/{id}/approve|reject (see
// app/routes/approval_routes.py) — same admin JWT already used
// everywhere else, no separate token needed.

import { useState, useEffect, useCallback } from "react"
import { API } from "../services/api"

const STATUS_BADGE = {
  pending:  { bg: "#fef3c7", color: "#b45309", label: "Pending" },
  approved: { bg: "#dcfce7", color: "#16a34a", label: "Approved" },
  rejected: { bg: "#fee2e2", color: "#dc2626", label: "Rejected" },
  expired:  { bg: "#f1f5f9", color: "#64748b", label: "Expired" },
}

function formatDate(iso) {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

function PendingApprovals({ token, logout }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState("pending") // "pending" | "approved" | "rejected" | "expired" | "" (all)
  const [actingId, setActingId] = useState(null) // request id currently being approved/rejected, disables its buttons
  const [banner, setBanner] = useState(null) // { type: "success"|"error", text }

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

  const fetchRequests = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const qs = filter ? `?status=${filter}` : ""
      const res = await authFetch(`${API}/approvals${qs}`)
      if (!res.ok) throw new Error("Failed to load approval requests.")
      setRequests(await res.json())
    } catch (err) {
      setError(err.message || "Something went wrong loading approval requests.")
    } finally {
      setLoading(false)
    }
  }, [authFetch, filter])

  useEffect(() => { fetchRequests() }, [fetchRequests])

  const act = async (id, action) => {
    setActingId(id)
    setBanner(null)
    try {
      const res = await authFetch(`${API}/approvals/${id}/${action}`, { method: "POST" })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.message || `Failed to ${action} this request.`)
      setBanner({ type: "success", text: data.message })
      fetchRequests()
    } catch (err) {
      setBanner({ type: "error", text: err.message || `Failed to ${action} this request.` })
    } finally {
      setActingId(null)
    }
  }

  const pendingCount = requests.filter(r => r.status === "pending").length

  return (
    <main className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">User Approval Requests</h2>
          <p className="text-sm text-slate-500 mt-1">
            Add/remove requests submitted by Plant Heads. Each one was also emailed to the configured
            Admin recipient (Email Services &gt; Admin) with its own Approve/Reject link — acting here does the same thing.
          </p>
        </div>
        <button
          onClick={fetchRequests}
          className="text-sm px-3 py-1.5 border border-slate-300 rounded-md hover:bg-slate-50 text-slate-600"
        >
          Refresh
        </button>
      </div>

      {banner && (
        <div
          className="mb-4 px-4 py-2.5 rounded-md text-sm"
          style={{
            background: banner.type === "success" ? "#dcfce7" : "#fee2e2",
            color: banner.type === "success" ? "#16a34a" : "#dc2626",
          }}
        >
          {banner.text}
        </div>
      )}

      {/* Status filter tabs */}
      <div className="flex gap-1 mb-4 border-b border-slate-200">
        {[
          { key: "pending", label: `Pending${pendingCount ? ` (${pendingCount})` : ""}` },
          { key: "approved", label: "Approved" },
          { key: "rejected", label: "Rejected" },
          { key: "expired", label: "Expired" },
          { key: "", label: "All" },
        ].map(tab => (
          <button
            key={tab.key || "all"}
            onClick={() => setFilter(tab.key)}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              filter === tab.key ? "border-blue-600 text-blue-600" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center text-slate-500 py-10">Loading approval requests...</div>
      ) : error ? (
        <div className="text-center text-red-500 py-10">{error}</div>
      ) : requests.length === 0 ? (
        <div className="text-center text-slate-400 py-10 text-sm">No {filter || ""} requests.</div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-2.5">Action</th>
                <th className="text-left px-4 py-2.5">Plant</th>
                <th className="text-left px-4 py-2.5">Details</th>
                <th className="text-left px-4 py-2.5">Requested By</th>
                <th className="text-left px-4 py-2.5">Submitted</th>
                <th className="text-left px-4 py-2.5">Status</th>
                <th className="text-right px-4 py-2.5">Action</th>
              </tr>
            </thead>
            <tbody>
              {requests.map(r => {
                const badge = STATUS_BADGE[r.status] || STATUS_BADGE.pending
                return (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded ${r.action === "add" ? "bg-blue-50 text-blue-600" : "bg-orange-50 text-orange-600"}`}>
                        {r.action === "add" ? "Add User" : "Remove User"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{r.plant_name}</td>
                    <td className="px-4 py-3 text-slate-700">
                      {r.action === "add" ? (
                        <>
                          <div className="font-medium">{r.person_name}</div>
                          <div className="text-xs text-slate-500">{r.email} · {r.role}{r.employee_id ? ` · ${r.employee_id}` : ""}</div>
                        </>
                      ) : (
                        <div className="font-medium">{r.target_label || "(user no longer exists)"}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{r.requested_by_username}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{formatDate(r.created_at)}</td>
                    <td className="px-4 py-3">
                      <span
                        className="text-xs font-semibold px-2 py-0.5 rounded-full"
                        style={{ background: badge.bg, color: badge.color }}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {r.status === "pending" ? (
                        <div className="flex gap-2 justify-end">
                          <button
                            disabled={actingId === r.id}
                            onClick={() => act(r.id, "approve")}
                            className="text-xs px-3 py-1.5 rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                          >
                            {actingId === r.id ? "..." : "Approve"}
                          </button>
                          <button
                            disabled={actingId === r.id}
                            onClick={() => act(r.id, "reject")}
                            className="text-xs px-3 py-1.5 rounded-md bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 disabled:opacity-50"
                          >
                            {actingId === r.id ? "..." : "Reject"}
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">{formatDate(r.decided_at)}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}

export default PendingApprovals