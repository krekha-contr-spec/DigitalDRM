// DataEntry.jsx
// Data entry form only — no history table.
// After saving, user stays on this page and sees a success banner.

import { useState, useEffect } from "react"
import { useAuth } from "../context/AuthContext"
import {
  addProduction, addManpower, addDespatch, addOVC, addSales,
  addRejectionPPM, addProductValue,
  getProductionLatestActual, getManpowerLatestActual,
  getOVCLatestActual, getSalesLatestActual,
  getRejectionPPMLatestActual, getProductValueLatestActual, getOVCHistory,
  checkProductionLock, checkManpowerLock, checkDespatchLock, checkOVCLock,
  checkSalesLock, checkRejectionPPMLock, checkProductValueLock,
} from "../services/api"
import RoleVerificationModal from "../components/RoleVerificationModal"
import RaneLogo from "../assets/Rane_Group_Logo.jpg"

// The six OVC categories shown as independent cards. Product Value and
// Rejection PPM are handled by their own dedicated modules/roles and are
// intentionally excluded here.
const OVC_CATEGORIES = [
  "Consumable Cost",
  "Direct Labour Cost",
  "Freight Cost",
  "Plant Overall Overrun",
  "Power Cost",
  "Rejection Cost",
]

const inputStyle = {
  width: "100%",
  padding: "10px 12px",
  border: "1px solid #e2e8f0",
  borderRadius: "8px",
  fontSize: "13px",
  fontFamily: "inherit",
  boxSizing: "border-box",
}

const labelStyle = {
  color: "#64748b",
  fontSize: "12px",
  fontWeight: "600",
  display: "block",
  marginBottom: "8px",
}

const fieldWrap = { marginBottom: "20px" }

const requiredMsgStyle = {
  color: "#dc2626",
  fontSize: "11px",
  fontWeight: "600",
  margin: "6px 0 0 0",
}

function DataEntry({ onBack, onDataSaved }) {
  const { user } = useAuth()
  const [verifiedRole, setVerifiedRole] = useState(null)
  const [formData,     setFormData]     = useState({})
  const [submitting,   setSubmitting]   = useState(false)
  const [error,        setError]        = useState("")
  const [success,      setSuccess]      = useState("")

  // Per-field "This field is required" messages for the main (non-OVC)
  // form. Populated on submit attempt / cleared as soon as the person
  // fixes the field. Submission is blocked entirely while any required
  // field is empty — nothing is sent to the backend, and therefore
  // nothing gets locked, until every mandatory field has a value.
  const [fieldErrors, setFieldErrors] = useState({})

  // Which fields are mandatory for each role. Date is always required
  // (it already has a default value, so it's effectively always filled,
  // but is included for completeness/clarity).
  const REQUIRED_FIELDS = {
    production:    ["date", "plan", "actual"],
    manpower:      ["date", "plan", "actual"],
    despatch:      ["date", "customer_name", "month_plan", "mtd_actual"],
    rejection_ppm: ["date", "plan", "actual"],
    product_value: ["date", "plan", "actual"],
    sales:         ["date", "segment", "month_plan", "mtd_actual"],
  }

  // A value counts as "missing" if it's null/undefined, an empty string,
  // or (after whitespace-trimming) an empty text field. Numeric 0 is a
  // valid, deliberately-entered value and must NOT be treated as missing.
  const isEmpty = v => v === null || v === undefined || (typeof v === "string" && v.trim() === "")

  const validateForm = () => {
    const required = REQUIRED_FIELDS[verifiedRole] || []
    const errors = {}
    required.forEach(field => {
      if (isEmpty(formData[field])) errors[field] = "This field is required"
    })
    return errors
  }


  // Date-wise KPI lock: once a record exists for this plant + date (+
  // customer/segment/element for departments that have one), the record is
  // permanently locked — the form goes read-only and Save is disabled.
  const [locked,       setLocked]       = useState(false)
  const [lockMessage,  setLockMessage]  = useState("")
  const [checkingLock, setCheckingLock] = useState(false)

  const runLockCheck = async () => {
    if (!verifiedRole || verifiedRole === "ovc") return
    const plantId = user.plant_id
    const entryDate = formData.date || new Date().toISOString().split("T")[0]

    // Departments with a sub-key need that value filled in before we can
    // meaningfully check for a duplicate.
    const subKeyReady =
      verifiedRole === "despatch" ? !!formData.customer_name :
      verifiedRole === "sales"    ? !!formData.segment        :
      true

    if (!subKeyReady) {
      setLocked(false)
      setLockMessage("")
      return
    }

    setCheckingLock(true)
    try {
      let res
      if      (verifiedRole === "production")    res = await checkProductionLock(plantId, entryDate)
      else if (verifiedRole === "manpower")      res = await checkManpowerLock(plantId, entryDate)
      else if (verifiedRole === "despatch")      res = await checkDespatchLock(plantId, entryDate, formData.customer_name)
      else if (verifiedRole === "ovc")           res = await checkOVCLock(plantId, entryDate, formData.element_type)
      else if (verifiedRole === "sales")         res = await checkSalesLock(plantId, entryDate, formData.segment)
      else if (verifiedRole === "rejection_ppm") res = await checkRejectionPPMLock(plantId, entryDate)
      else if (verifiedRole === "product_value") res = await checkProductValueLock(plantId, entryDate)

      setLocked(!!res?.data?.locked)
      setLockMessage(res?.data?.locked ? res.data.message : "")
    } catch (err) {
      // Don't block the user optimistically on a network hiccup — the
      // backend still enforces the lock authoritatively on save.
      setLocked(false)
      setLockMessage("")
      console.error("Lock check failed", err)
    } finally {
      setCheckingLock(false)
    }
  }

  // Re-check whenever the date (or the relevant sub-key field) changes
  useEffect(() => {
    if (!verifiedRole || verifiedRole === "ovc") return
    const timer = setTimeout(() => { runLockCheck() }, 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifiedRole, user.plant_id, formData.date, formData.customer_name, formData.element_type, formData.segment])

  // Prefill Target (Plan) from previous record; Actual always starts empty.
  //
  // DESPATCH IS EXCLUDED FROM THIS PREFILL — Despatch allows MULTIPLE
  // customers per plant+date (BMW, HMI, etc.), each locked
  // independently. Prefilling customer_name with whoever was entered
  // LAST would immediately trigger the lock-check for that customer on
  // page load (see the lock-check effect below), showing "🔒 Locked —
  // Already Submitted" before the user has touched anything — which
  // looks exactly like the whole date is locked, even though only that
  // one customer is. Prefilling month_plan from the last customer's
  // record would also be factually wrong once a different customer is
  // typed in (each customer has their own independent plan). So for
  // Despatch, customer_name and month_plan both start blank/untouched —
  // the user must actively choose which customer they're entering.
  useEffect(() => {
    if (!verifiedRole || verifiedRole === "ovc" || verifiedRole === "despatch") return
    const plantId = user.plant_id
    const today = new Date().toISOString().split("T")[0]

    const loadPrevious = async () => {
      try {
        let latestRes
        if      (verifiedRole === "production")    latestRes = await getProductionLatestActual(plantId)
        else if (verifiedRole === "manpower")      latestRes = await getManpowerLatestActual(plantId)
        else if (verifiedRole === "sales")         latestRes = await getSalesLatestActual(plantId)
        else if (verifiedRole === "rejection_ppm") latestRes = await getRejectionPPMLatestActual(plantId)
        else if (verifiedRole === "product_value") latestRes = await getProductValueLatestActual(plantId)

        const latest = latestRes?.data || {}
        setFormData(prev => ({
          ...prev,
          date:          today,
          plan:          latest.plan       !== undefined ? latest.plan       : null,
          actual:        null,   // always empty
          month_plan:    latest.month_plan !== undefined ? latest.month_plan : null,
          mtd_actual:    null,   // always empty
          element_type:  latest.element_type  || "",
          segment:       latest.segment       || "",
        }))
      } catch (err) {
        console.error("Failed to load previous data", err)
      }
    }

    loadPrevious()
  }, [verifiedRole, user.plant_id])

  // Despatch's own, much simpler load-on-entry: just stamp today's date
  // and leave customer_name/month_plan/mtd_actual blank, per the note
  // above. No "previous record" fetch at all — every customer starts
  // from a clean slate.
  useEffect(() => {
    if (verifiedRole !== "despatch") return
    const today = new Date().toISOString().split("T")[0]
    setFormData(prev => ({
      ...prev,
      date: today,
      customer_name: "",
      month_plan: null,
      mtd_actual: null,
    }))
  }, [verifiedRole, user.plant_id])

  // ------------------------------------------------------------------
  // OVC: six independent categories, each its own card with its own
  // Target / Actual / Save & Lock. Submitting one never touches the
  // others. The OVC section is "complete" only once all six are locked
  // (i.e. already submitted) for the selected date.
  // ------------------------------------------------------------------
  const emptyOvcRow = () => ({
    plan: null, actual: null, locked: false, lockMessage: "",
    submitting: false, checkingLock: false, error: "", success: "",
    fieldErrors: {},   // { plan: "This field is required", actual: "..." }
  })
  const [ovcDate, setOvcDate] = useState(new Date().toISOString().split("T")[0])
  const [ovcRows, setOvcRows] = useState(() => {
    const init = {}
    OVC_CATEGORIES.forEach(cat => { init[cat] = emptyOvcRow() })
    return init
  })

  const patchOvcRow = (category, patch) => {
    setOvcRows(prev => ({ ...prev, [category]: { ...prev[category], ...patch } }))
  }

  const checkOneOvcLock = async (category, entryDate) => {
    patchOvcRow(category, { checkingLock: true })
    try {
      const res = await checkOVCLock(user.plant_id, entryDate, category)
      patchOvcRow(category, {
        checkingLock: false,
        locked: !!res?.data?.locked,
        lockMessage: res?.data?.locked ? res.data.message : "",
      })
    } catch (err) {
      console.error("OVC lock check failed", category, err)
      patchOvcRow(category, { checkingLock: false, locked: false, lockMessage: "" })
    }
  }

  // Prefill each category's Target from its most recent history entry,
  // and check today's lock state for each category independently.
  useEffect(() => {
    if (verifiedRole !== "ovc") return
    const plantId = user.plant_id

    const init = async () => {
      let latestByCategory = {}
      try {
        const res = await getOVCHistory(plantId)
        const history = res?.data?.history || []
        // history is ordered most-recent-first; keep the first plan seen per category
        for (const rec of history) {
          if (!(rec.element_type in latestByCategory)) {
            latestByCategory[rec.element_type] = rec.plan
          }
        }
      } catch (err) {
        console.error("Failed to load OVC history for prefill", err)
      }

      setOvcRows(prev => {
        const next = { ...prev }
        OVC_CATEGORIES.forEach(cat => {
          next[cat] = {
            ...emptyOvcRow(),
            plan: latestByCategory[cat] !== undefined ? latestByCategory[cat] : null,
          }
        })
        return next
      })

      OVC_CATEGORIES.forEach(cat => { checkOneOvcLock(cat, ovcDate) })
    }

    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifiedRole, user.plant_id])

  // Re-check locks for every category whenever the OVC date changes
  useEffect(() => {
    if (verifiedRole !== "ovc") return
    OVC_CATEGORIES.forEach(cat => { checkOneOvcLock(cat, ovcDate) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verifiedRole, ovcDate])

  const handleOvcFieldChange = (category, field, value) => {
    patchOvcRow(category, {
      [field]: value === "" ? null : parseFloat(value),
      fieldErrors: { ...(ovcRows[category]?.fieldErrors || {}), [field]: undefined },
    })
  }

  const handleOvcSave = async (category) => {
    const row = ovcRows[category]
    if (!row || row.locked) return

    // Both Target and Actual are mandatory. Block submission entirely —
    // and therefore never call the backend or lock this category — until
    // both are filled in. 0 is a valid entered value; only null/blank
    // counts as missing.
    const rowErrors = {}
    if (row.plan === null || row.plan === undefined)   rowErrors.plan   = "This field is required"
    if (row.actual === null || row.actual === undefined) rowErrors.actual = "This field is required"
    if (Object.keys(rowErrors).length > 0) {
      patchOvcRow(category, { fieldErrors: rowErrors, error: "", success: "" })
      return
    }

    patchOvcRow(category, { submitting: true, error: "", success: "", fieldErrors: {} })
    try {
      await addOVC({
        plant_id: user.plant_id,
        date: ovcDate,
        element_type: category,
        plan: row.plan,
        actual: row.actual,
      })
      patchOvcRow(category, {
        submitting: false,
        success: `✅ ${category} saved and locked for ${ovcDate}!`,
        locked: true,
        lockMessage: "Data already submitted and locked.",
      })
      if (onDataSaved) onDataSaved()
      setTimeout(() => patchOvcRow(category, { success: "" }), 5000)
    } catch (err) {
      if (err.response?.status === 409) {
        patchOvcRow(category, {
          submitting: false,
          locked: true,
          lockMessage: err.response.data?.detail || "Data already submitted and locked.",
        })
      } else {
        patchOvcRow(category, {
          submitting: false,
          error: err.response?.data?.detail || "Failed to save data. Please try again.",
        })
      }
      console.error(err)
    }
  }

  const ovcAllLocked = OVC_CATEGORIES.every(cat => ovcRows[cat]?.locked)

  if (!verifiedRole) {
    return (
      <RoleVerificationModal
        plantId={user.plant_id}
        onVerified={role => setVerifiedRole(role)}
        onBack={onBack}
      />
    )
  }

  const handleInputChange = e => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value === "" ? null : parseFloat(value) }))
    setFieldErrors(prev => ({ ...prev, [name]: undefined }))
  }
  const handleTextChange = e => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setFieldErrors(prev => ({ ...prev, [name]: undefined }))
  }
  const handleDateChange = e => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setFieldErrors(prev => ({ ...prev, [name]: undefined }))
  }

  const handleSubmit = async e => {
    e.preventDefault()
    if (locked) return  // extra client-side guard; backend enforces this authoritatively
    setError("")
    setSuccess("")

    // Mandatory-field check: if anything required is missing, show
    // "This field is required" under each empty field and stop — no
    // request is sent to the backend, so nothing gets locked for a
    // partially-completed entry.
    const errors = validateForm()
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      setError("Please fill in all required fields before submitting.")
      return
    }
    setFieldErrors({})

    setSubmitting(true)
    try {
      const data = {
        plant_id:      user.plant_id,
        date:          formData.date || new Date().toISOString().split("T")[0],
        plan:          formData.plan,
        actual:        formData.actual,
        month_plan:    formData.month_plan,
        mtd_actual:    formData.mtd_actual,
        element_type:  formData.element_type,
        customer_name: formData.customer_name,
        segment:       formData.segment,
      }

      if      (verifiedRole === "production")    await addProduction(data)
      else if (verifiedRole === "manpower")      await addManpower(data)
      else if (verifiedRole === "despatch")      await addDespatch(data)
      else if (verifiedRole === "ovc")           await addOVC(data)
      else if (verifiedRole === "rejection_ppm") await addRejectionPPM({ ...data, element_type: "Rejection PPM" })
      else if (verifiedRole === "product_value") await addProductValue({ ...data, element_type: "Product Value" })
      else if (verifiedRole === "sales")         await addSales(data)

      setSuccess(`✅ ${verifiedRole.toUpperCase()} data saved successfully for ${data.date}!`)
      setFormData(prev => ({ ...prev, actual: null, mtd_actual: null }))
      if (onDataSaved) onDataSaved()
      setTimeout(() => setSuccess(""), 5000)
      // The record now exists for this date — lock the form immediately.
      runLockCheck()
    } catch (err) {
      if (err.response?.status === 409) {
        // Backend confirms this date+KPI type is already locked (e.g. a
        // race with another submission). Reflect the same lock state.
        setLocked(true)
        setLockMessage(err.response.data?.detail || "Data already submitted and locked.")
      } else {
        setError(err.response?.data?.detail || "Failed to save data. Please try again.")
      }
      console.error(err)
    } finally {
      setSubmitting(false)
    }
  }

  const roleLabel = verifiedRole?.charAt(0).toUpperCase() + verifiedRole?.slice(1).replace(/_/g, " ")

  // Shared helpers so every mandatory field in the main form gets the
  // same red-border + "This field is required" treatment consistently.
  const fieldStyle = name => fieldErrors[name] ? { ...inputStyle, borderColor: "#dc2626" } : inputStyle
  const FieldError = ({ name }) => fieldErrors[name] ? <p style={requiredMsgStyle}>{fieldErrors[name]}</p> : null

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "#f1f5f9" }}>

      {/* Header */}
      <div style={{ background: "linear-gradient(135deg,#1e293b 0%,#0f172a 100%)", padding: "16px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", boxShadow: "0 4px 12px rgba(0,0,0,0.15)", flexWrap: "wrap", gap: "16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flex: "1 1 auto", minWidth: "280px" }}>
          <img
            src={RaneLogo}
            alt="Rane Madras Ltd"
            style={{ height: "30px", width: "auto", objectFit: "contain" }}
          />
          <div>
            <h1 style={{ color: "white", fontWeight: "700", fontSize: "16px", margin: "0 0 4px 0" }}>Rane Madras Ltd - Data Entry</h1>
            <p style={{ color: "#cbd5e1", fontSize: "12px", margin: 0 }}>
              Plant {user.plant_id} · {roleLabel} Data Management
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <span style={{ background: "#10b981", color: "white", fontSize: "12px", padding: "6px 12px", borderRadius: "20px", fontWeight: "600", whiteSpace: "nowrap" }}>
            ✅ {verifiedRole?.toUpperCase()}
          </span>
          <button
            onClick={() => { setVerifiedRole(null); setFormData({}); setFieldErrors({}); setError(""); setSuccess("") }}
            style={{ background: "#6366f1", color: "white", border: "none", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
            title="Switch to a different role"
          >
            🔄 Change Role
          </button>
          <button
            onClick={onBack}
            style={{ background: "rgba(148,163,184,0.2)", border: "1px solid #64748b", color: "#e2e8f0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", fontWeight: "600" }}
          >
            ← Back
          </button>
        </div>
      </div>

      {/* Form */}
      <div style={{ flex: 1, padding: "32px", overflowY: "auto" }}>
        <div style={{ maxWidth: verifiedRole === "ovc" ? "1000px" : "560px", margin: "0 auto" }}>
          {verifiedRole === "ovc" ? (
            <div style={{ background: "white", borderRadius: "12px", padding: "40px", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}>
              <h2 style={{ color: "#0f172a", fontSize: "18px", fontWeight: "700", margin: "0 0 6px 0" }}>
                OVC Data Entry
              </h2>
              <p style={{ color: "#64748b", fontSize: "12px", margin: "0 0 20px 0" }}>
                📝 Enter Target and Actual for each category and Save & Lock it independently. Target is prefilled from the most recent submission.
              </p>

              <div style={fieldWrap}>
                <label style={labelStyle}>Date</label>
                <input
                  type="date"
                  value={ovcDate}
                  onChange={e => setOvcDate(e.target.value)}
                  style={{ ...inputStyle, maxWidth: "220px" }}
                />
              </div>

              <div style={{
                background: ovcAllLocked ? "#dcfce7" : "#eff6ff",
                border: `1px solid ${ovcAllLocked ? "#86efac" : "#bfdbfe"}`,
                color: ovcAllLocked ? "#166534" : "#1e40af",
                padding: "10px 14px",
                borderRadius: "8px",
                marginBottom: "20px",
                fontSize: "13px",
                fontWeight: "600",
              }}>
                {ovcAllLocked
                  ? "✅ OVC section complete — all 6 categories submitted and locked for this date."
                  : `📋 ${OVC_CATEGORIES.filter(c => ovcRows[c]?.locked).length} of ${OVC_CATEGORIES.length} categories submitted for this date.`}
              </div>

              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: "16px",
              }}>
                {OVC_CATEGORIES.map(category => {
                  const row = ovcRows[category] || emptyOvcRow()
                  return (
                    <div key={category} style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: "10px",
                      padding: "18px",
                      background: row.locked ? "#f8fafc" : "white",
                    }}>
                      <h3 style={{ fontSize: "14px", fontWeight: "700", color: "#0f172a", margin: "0 0 12px 0" }}>
                        {category}
                      </h3>

                      {row.error && (
                        <div style={{ background: "#fee2e2", border: "1px solid #fecaca", color: "#dc2626", padding: "8px 10px", borderRadius: "6px", marginBottom: "10px", fontSize: "12px" }}>
                          {row.error}
                        </div>
                      )}
                      {row.success && (
                        <div style={{ background: "#dcfce7", border: "1px solid #86efac", color: "#166534", padding: "8px 10px", borderRadius: "6px", marginBottom: "10px", fontSize: "12px" }}>
                          {row.success}
                        </div>
                      )}
                      {row.locked && !row.success && (
                        <div style={{ background: "#fef3c7", border: "1px solid #fcd34d", color: "#92400e", padding: "8px 10px", borderRadius: "6px", marginBottom: "10px", fontSize: "12px", fontWeight: "600" }}>
                          🔒 {row.lockMessage || "Data already submitted and locked."}
                        </div>
                      )}

                      <fieldset disabled={row.locked} style={{ border: "none", padding: 0, margin: 0 }}>
                        <div style={{ marginBottom: "12px" }}>
                          <label style={labelStyle}>Target</label>
                          <input
                            type="number"
                            placeholder="Enter target"
                            value={row.plan ?? ""}
                            onChange={e => handleOvcFieldChange(category, "plan", e.target.value)}
                            step="0.01"
                            style={row.fieldErrors?.plan ? { ...inputStyle, borderColor: "#dc2626" } : inputStyle}
                          />
                          {row.fieldErrors?.plan && (
                            <p style={requiredMsgStyle}>{row.fieldErrors.plan}</p>
                          )}
                        </div>
                        <div style={{ marginBottom: "12px" }}>
                          <label style={labelStyle}>Actual</label>
                          <input
                            type="number"
                            placeholder="Enter actual"
                            value={row.actual ?? ""}
                            onChange={e => handleOvcFieldChange(category, "actual", e.target.value)}
                            step="0.01"
                            style={row.fieldErrors?.actual ? { ...inputStyle, borderColor: "#dc2626" } : inputStyle}
                          />
                          {row.fieldErrors?.actual && (
                            <p style={requiredMsgStyle}>{row.fieldErrors.actual}</p>
                          )}
                        </div>

                        <button
                          type="button"
                          onClick={() => handleOvcSave(category)}
                          disabled={row.submitting || row.locked || row.checkingLock}
                          title={row.locked ? row.lockMessage : undefined}
                          style={{
                            width: "100%",
                            padding: "10px",
                            background: (row.submitting || row.locked) ? "#cbd5e1" : "#3b82f6",
                            color: "white",
                            border: "none",
                            borderRadius: "8px",
                            fontWeight: "600",
                            fontSize: "12px",
                            cursor: (row.submitting || row.locked) ? "not-allowed" : "pointer",
                          }}
                        >
                          {row.locked ? "🔒 Locked" : row.submitting ? "Saving..." : "💾 Save & Lock"}
                        </button>
                      </fieldset>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
          <div style={{ background: "white", borderRadius: "12px", padding: "40px", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}>

            {error && (
              <div style={{ background: "#fee2e2", border: "1px solid #fecaca", color: "#dc2626", padding: "12px 16px", borderRadius: "8px", marginBottom: "20px", fontSize: "13px" }}>
                {error}
              </div>
            )}
            {success && (
              <div style={{ background: "#dcfce7", border: "1px solid #86efac", color: "#166534", padding: "12px 16px", borderRadius: "8px", marginBottom: "20px", fontSize: "13px" }}>
                {success}
              </div>
            )}
            {locked && (
              <div style={{ background: "#fef3c7", border: "1px solid #fcd34d", color: "#92400e", padding: "12px 16px", borderRadius: "8px", marginBottom: "20px", fontSize: "13px", fontWeight: "600" }}>
                🔒 {lockMessage || "Data already submitted and locked."}
              </div>
            )}

            <h2 style={{ color: "#0f172a", fontSize: "18px", fontWeight: "700", margin: "0 0 6px 0" }}>
              {roleLabel} Data Entry
            </h2>
            <p style={{ color: "#64748b", fontSize: "12px", margin: "0 0 28px 0" }}>
              📝 Target (Plan) is prefilled from the previous record. Enter today's Actual value.
            </p>

            <form onSubmit={handleSubmit}>
              {/* Date */}
              <div style={fieldWrap}>
                <label style={labelStyle}>Date</label>
                <input
                  type="date"
                  name="date"
                  value={formData.date || new Date().toISOString().split("T")[0]}
                  onChange={handleDateChange}
                  style={fieldStyle("date")}
                />
                <FieldError name="date" />
              </div>

              {/* DESPATCH — Customer Name is deliberately OUTSIDE the
                  locked-disabled fieldset below: locking is per
                  (plant, date, customer), not per date, so the user
                  must always be able to change the customer name to
                  move on to a different customer (BMW locked doesn't
                  mean HMI is locked) even while THIS customer's own
                  Month Plan / MTD Actual fields are locked. */}
              {verifiedRole === "despatch" && (
                <div style={fieldWrap}>
                  <label style={labelStyle}>Customer Name</label>
                  <input type="text" name="customer_name" placeholder="Enter customer name" value={formData.customer_name || ""} onChange={handleTextChange} style={fieldStyle("customer_name")} />
                  <FieldError name="customer_name" />
                </div>
              )}

              <fieldset disabled={locked} style={{ border: "none", padding: 0, margin: 0 }}>

              {/* PRODUCTION */}
              {verifiedRole === "production" && (
                <>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Target Production</label>
                    <input type="number" name="plan" placeholder="Enter target production" value={formData.plan ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("plan")} />
                    <FieldError name="plan" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Actual Production</label>
                    <input type="number" name="actual" placeholder="Enter actual production" value={formData.actual ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("actual")} />
                    <FieldError name="actual" />
                  </div>
                </>
              )}

              {/* MANPOWER */}
              {verifiedRole === "manpower" && (
                <>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Target MP Present</label>
                    <input type="number" name="plan" placeholder="Enter target MP" value={formData.plan ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("plan")} />
                    <FieldError name="plan" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Actual MP Present</label>
                    <input type="number" name="actual" placeholder="Enter actual MP" value={formData.actual ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("actual")} />
                    <FieldError name="actual" />
                  </div>
                </>
              )}

              {/* DESPATCH — Month Plan / MTD Actual only; Customer Name
                  lives outside the fieldset above so it stays editable
                  even when this customer's own entry is locked. */}
              {verifiedRole === "despatch" && (
                <>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Month Plan</label>
                    <input type="number" name="month_plan" placeholder="Enter month plan" value={formData.month_plan ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("month_plan")} />
                    <FieldError name="month_plan" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>MTD Actual</label>
                    <input type="number" name="mtd_actual" placeholder="Enter MTD actual" value={formData.mtd_actual ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("mtd_actual")} />
                    <FieldError name="mtd_actual" />
                  </div>
                </>
              )}

              {/* REJECTION PPM */}
              {verifiedRole === "rejection_ppm" && (
                <>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Target PPM</label>
                    <input type="number" name="plan" placeholder="Enter target PPM" value={formData.plan ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("plan")} />
                    <FieldError name="plan" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Actual PPM</label>
                    <input type="number" name="actual" placeholder="Enter actual PPM" value={formData.actual ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("actual")} />
                    <FieldError name="actual" />
                  </div>
                </>
              )}

              {/* PRODUCT VALUE */}
              {verifiedRole === "product_value" && (
                <>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Target Value</label>
                    <input type="number" name="plan" placeholder="Enter target value" value={formData.plan ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("plan")} />
                    <FieldError name="plan" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Actual Value</label>
                    <input type="number" name="actual" placeholder="Enter actual value" value={formData.actual ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("actual")} />
                    <FieldError name="actual" />
                  </div>
                </>
              )}

              {/* SALES */}
              {verifiedRole === "sales" && (
                <>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Segment</label>
                    <input type="text" name="segment" placeholder="Enter sales segment" value={formData.segment || ""} onChange={handleTextChange} style={fieldStyle("segment")} />
                    <FieldError name="segment" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>Month Plan</label>
                    <input type="number" name="month_plan" placeholder="Enter month plan" value={formData.month_plan ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("month_plan")} />
                    <FieldError name="month_plan" />
                  </div>
                  <div style={fieldWrap}>
                    <label style={labelStyle}>MTD Actual</label>
                    <input type="number" name="mtd_actual" placeholder="Enter MTD actual" value={formData.mtd_actual ?? ""} onChange={handleInputChange} step="0.01" style={fieldStyle("mtd_actual")} />
                    <FieldError name="mtd_actual" />
                  </div>
                </>
              )}

              <button
                type="submit"
                disabled={submitting || locked || checkingLock}
                title={locked ? lockMessage : undefined}
                style={{
                  width: "100%",
                  padding: "12px",
                  background: (submitting || locked) ? "#cbd5e1" : "#3b82f6",
                  color: "white",
                  border: "none",
                  borderRadius: "8px",
                  fontWeight: "600",
                  fontSize: "13px",
                  cursor: (submitting || locked) ? "not-allowed" : "pointer",
                  marginTop: "20px",
                }}
              >
                {locked ? "🔒 Locked — Already Submitted" : submitting ? "Saving..." : "💾 Save Data"}
              </button>
              </fieldset>
            </form>
          </div>
          )}
        </div>
      </div>

    </div>
  )
}

export default DataEntry