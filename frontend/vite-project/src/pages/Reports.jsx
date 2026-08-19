import { useState, useEffect, useRef } from "react";
import RaneLogo from "../assets/Rane_Group_Logo.jpg";
import {
  generateMonthlyReport,
  generateQuarterlyReport,
  generateYearlyReport,
  saveReportToServer,
} from "../services/api";

// ── Constants ────────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const TARGET_SAVE_DIR = "D:\\c103191-Data\\DigitalDRM\\Reports";

// Standardized Indian-FY quarter labels
const QUARTER_RANGES = { 1: "Apr-Jun", 2: "Jul-Sep", 3: "Oct-Dec", 4: "Jan-Mar" };
function quarterLabel(q) {
  return `Q${q} (${QUARTER_RANGES[q] || ""})`;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function buildFilename(plantId, reportType, month, quarter, year) {
  const plant = `Plant${String(plantId).padStart(2, "0")}`;
  const type = reportType.charAt(0).toUpperCase() + reportType.slice(1);
  if (reportType === "yearly") return `${plant}_Yearly_${year}.pdf`;
  if (reportType === "quarterly") return `${plant}_Quarterly_Q${quarter}_${year}.pdf`;
  return `${plant}_Monthly_${MONTH_NAMES[month]}_${year}.pdf`;
}

/** Build a clean, print-ready HTML string from report data. */
function buildReportHTML(plantId, reportType, month, quarter, year, data) {
  const period =
    reportType === "yearly" ? String(year) :
    reportType === "quarterly" ? `${quarterLabel(quarter)} ${year}` :
    `${MONTH_NAMES[month]} ${year}`;

  const generatedAt = new Date().toLocaleString("en-GB");

  const depts = [
    ["Production", data.production],
    ["Manpower", data.manpower],
    ["Sales", data.sales],
    ["OVC Elements", data.ovc],
    ["Despatch", data.despatch],
    ["Rejection PPM", data.rejection_ppm],
    ["Product Value", data.product_value],
  ].filter(([, d]) => d);

  // Calculate totals for overall achievement
  let totalPlan = 0;
  let totalActual = 0;
  let onTrack = 0;
  let needsAttention = 0;

  depts.forEach(([name, d]) => {
    const plan = (d.plan || 0);
    const actual = (d.actual || 0);
    if (plan > 0 || actual > 0) {
      totalPlan += plan;
      totalActual += actual;
      const pct = plan ? (actual / plan * 100) : 0;
      if (pct >= 100) onTrack++;
      else if (pct < 80 && plan > 0) needsAttention++;
    }
  });

  const overallAchieved = totalPlan > 0 ? ((totalActual / totalPlan) * 100) : 0;

  // Build department rows with accurate achievement percentage
  const rows = depts.map(([name, d]) => {
    const plan = (d.plan || 0);
    const actual = (d.actual || 0);
    const variance = actual - plan;
    const pct = plan ? ((actual / plan * 100).toFixed(2)) : "N/A";
    const pctDisplay = typeof pct === 'string' ? pct : pct + '%';
    const color = variance >= 0 ? "#16a34a" : "#dc2626";
    const sign = variance >= 0 ? "+" : "";
    
    let status = "No Data";
    if (plan > 0 || actual > 0) {
      const pctNum = typeof pct === 'string' ? 0 : parseFloat(pct);
      if (pctNum >= 100) status = "On Track";
      else if (pctNum >= 80) status = "Near Target";
      else if (pctNum > 0) status = "Below Target";
    }
    
    return `<tr>
      <td>${name}</td>
      <td style="text-align:right">${plan.toFixed(2)}</td>
      <td style="text-align:right;font-weight:600">${actual.toFixed(2)}</td>
      <td style="text-align:right;color:${color};font-weight:600">${sign}${variance.toFixed(2)}</td>
      <td style="text-align:right;font-weight:600">${pctDisplay}</td>
      <td style="text-align:center;font-weight:600;color:${status === 'On Track' ? '#16a34a' : status === 'Near Target' ? '#d97706' : '#dc2626'}">${status}</td>
    </tr>`;
  }).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>DRM Report Plant ${plantId} - ${period}</title>
<style>
  body{font-family:Arial,sans-serif;font-size:13px;color:#0f172a;margin:0;padding:24px}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:#64748b;font-size:12px;margin:0 0 20px}
  .meta{display:flex;gap:28px;margin-bottom:24px;padding:12px 16px;
        background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0}
  .mi label{display:block;font-size:10px;color:#64748b;text-transform:uppercase;
             font-weight:600;margin-bottom:2px}
  .mi span{font-size:14px;font-weight:700}
  .summary-box{background:#f0f9ff;border-left:4px solid #3b82f6;padding:16px 20px;border-radius:6px;margin:20px 0}
  .summary-box p{font-size:12px;color:#1e293b;line-height:1.6;margin:0}
  .summary-stats{display:flex;gap:30px;margin-top:10px}
  .summary-stats .stat{display:flex;align-items:center;gap:8px}
  .summary-stats .stat .label{font-size:11px;color:#64748b}
  .summary-stats .stat .value{font-size:16px;font-weight:700;color:#0f172a}
  .summary-stats .stat .value.green{color:#16a34a}
  .summary-stats .stat .value.yellow{color:#f59e0b}
  .summary-stats .stat .value.red{color:#dc2626}
  table{width:100%;border-collapse:collapse;margin-top:12px}
  th{background:#f1f5f9;padding:10px 14px;text-align:left;font-size:11px;
     color:#64748b;text-transform:uppercase;border-bottom:2px solid #e2e8f0}
  td{padding:10px 14px;border-bottom:1px solid #f1f5f9}
  tr:last-child td{border-bottom:none}
  .footer{margin-top:32px;font-size:11px;color:#94a3b8}
  @media print{@page{size:A4;margin:14mm 12mm}body{padding:0}}
</style>
</head>
<body>
  <h1>Digital DRM — ${data.report_type || reportType} Report</h1>
  <p class="sub">Rane Madras Ltd · Plant ${plantId}</p>
  <div class="meta">
    <div class="mi"><label>Plant</label><span>${plantId}</span></div>
    <div class="mi"><label>Report Type</label><span>${data.report_type || reportType}</span></div>
    <div class="mi"><label>Period</label><span>${period}</span></div>
    <div class="mi"><label>Generated</label><span>${generatedAt}</span></div>
  </div>
  
  <!-- Executive Summary -->
  <div class="summary-box">
    <p style="font-weight:600;font-size:13px;margin-bottom:6px">📊 Executive Summary</p>
    <p>This ${reportType} report covers Plant ${plantId} for ${period}, consolidating ${depts.length} department(s). 
    Overall achievement against plan stood at <strong>${overallAchieved.toFixed(1)}%</strong>, with 
    <strong>${onTrack}</strong> department(s) on track and <strong>${needsAttention}</strong> department(s) needing attention.</p>
    <div class="summary-stats">
      <div class="stat"><span class="label">Departments</span><span class="value">${depts.length}</span></div>
      <div class="stat"><span class="label">Overall Achieved</span><span class="value ${overallAchieved >= 100 ? 'green' : overallAchieved >= 80 ? 'yellow' : 'red'}">${overallAchieved.toFixed(1)}%</span></div>
      <div class="stat"><span class="label">On Track</span><span class="value green">${onTrack}</span></div>
      <div class="stat"><span class="label">Needs Attention</span><span class="value red">${needsAttention}</span></div>
    </div>
  </div>
  
  <table>
    <thead><tr>
      <th>Department</th>
      <th style="text-align:right">Plan</th>
      <th style="text-align:right">Actual</th>
      <th style="text-align:right">Variance</th>
      <th style="text-align:right">Achieved %</th>
      <th style="text-align:center">Status</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <p class="footer">Generated by DigitalDRM · ${generatedAt}</p>
</body>
</html>`;
}

/**
 * Save HTML content as a PDF-named file.
 */
async function saveFile(filename, htmlContent) {
  const blob = new Blob([htmlContent], { type: "text/html;charset=utf-8" });

  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        startIn: "downloads",
        types: [{
          description: "HTML Report (print to PDF)",
          accept: { "text/html": [".html"] },
        }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return { method: "picker", name: handle.name };
    } catch (err) {
      if (err.name === "AbortError") throw err;
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.replace(".pdf", ".html");
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return { method: "download", name: a.download };
}

// ── Storage key for auto-report tracking ─────────────────────────────────────
function autoReportKey(plantId, year, month) {
  return `drm_auto_report_${plantId}_${year}_${month}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

function Reports({ plantId, onBack }) {
  const [reportType, setReportType] = useState("monthly");
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [quarter, setQuarter] = useState(1);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saveMsg, setSaveMsg] = useState({ text: "", type: "" });
  const [autoMsg, setAutoMsg] = useState("");
  const [showPopup, setShowPopup] = useState(false);
  const autoRan = useRef(false);

  const months = [
    { value: 1, label: "January" }, { value: 2, label: "February" },
    { value: 3, label: "March" }, { value: 4, label: "April" },
    { value: 5, label: "May" }, { value: 6, label: "June" },
    { value: 7, label: "July" }, { value: 8, label: "August" },
    { value: 9, label: "September" }, { value: 10, label: "October" },
    { value: 11, label: "November" }, { value: 12, label: "December" },
  ];

  const quarters = [
    { value: 1, label: quarterLabel(1) }, { value: 2, label: quarterLabel(2) },
    { value: 3, label: quarterLabel(3) }, { value: 4, label: quarterLabel(4) },
  ];

  // ── Auto-monthly report on 1st of month ─────────────────────────────────
  useEffect(() => {
    if (autoRan.current) return;
    autoRan.current = true;

    const today = new Date();
    const day = today.getDate();
    if (day !== 1) return;

    const prevMonth = today.getMonth() === 0 ? 12 : today.getMonth();
    const prevYear = today.getMonth() === 0 ? today.getFullYear() - 1 : today.getFullYear();

    const key = autoReportKey(plantId, prevYear, prevMonth);
    if (localStorage.getItem(key)) return;

    setAutoMsg(`⏳ Auto-generating ${MONTH_NAMES[prevMonth]} ${prevYear} report…`);

    generateMonthlyReport(plantId, prevYear, prevMonth)
      .then(async (res) => {
        const data = res.data;
        try {
          const saveRes = await saveReportToServer({
            plant_id: plantId,
            report_type: data.report_type,
            year: prevYear,
            month: prevMonth,
            quarter: null,
            report_data: data,
          });
          localStorage.setItem(key, new Date().toISOString());
          setAutoMsg(`✅ Auto-report saved: D:\\c103191-Data\\DigitalDRM\\Reports\\${saveRes.data.filename}`);
        } catch {
          setAutoMsg("⚠️ Auto-report could not be saved to server.");
        }
      })
      .catch((err) => {
        console.error("Auto-report failed:", err);
        setAutoMsg("⚠️ Auto-report generation failed. You can generate it manually.");
      });
  }, [plantId]);

  // ── Generate + auto-save to backend ──────────────────────────────────────
  const generateReport = async () => {
    setLoading(true);
    setError("");
    setSaveMsg({ text: "", type: "" });
    try {
      let response;
      if (reportType === "monthly") response = await generateMonthlyReport(plantId, year, month);
      else if (reportType === "quarterly") response = await generateQuarterlyReport(plantId, year, quarter);
      else response = await generateYearlyReport(plantId, year);

      const data = response.data;
      setReport(data);
      setLoading(false);

      setSaving(true);
      try {
        const saveRes = await saveReportToServer({
          plant_id: plantId,
          report_type: data.report_type,
          year,
          month: reportType === "monthly" ? month : null,
          quarter: reportType === "quarterly" ? quarter : null,
          report_data: data,
        });
        setSaveMsg({ type: "ok", text: `Report saved successfully.` });
        setShowPopup(true);
        setTimeout(() => setShowPopup(false), 3000);
      } catch (saveErr) {
        const detail = saveErr?.response?.data?.message || saveErr?.message || "Unknown error";
        setSaveMsg({ type: "error", text: `⚠️ Could not save to server: ${detail}` });
      } finally {
        setSaving(false);
      }

    } catch (err) {
      setError("Failed to generate report. Please try again.");
      console.error(err);
      setLoading(false);
    }
  };

  // Calculate achievement percentage (not deviation)
  const calculateAchievement = (plan, actual) => {
    if (!plan || plan === 0) return "N/A";
    const achieved = (actual / plan) * 100;
    return `${achieved.toFixed(2)}%`;
  };

  // Calculate variance
  const calculateVariance = (plan, actual) => (actual || 0) - (plan || 0);

  // Calculate percentage deviation from target (for display)
  const calculateDeviation = (plan, actual) => {
    if (!plan || plan === 0) return "N/A";
    const achieved = (actual / plan) * 100;
    const deviation = achieved - 100;
    const sign = deviation >= 0 ? "+" : "";
    return `${sign}${deviation.toFixed(2)}%`;
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden", background: "#f1f5f9" }}>

      <style>{`
        @media print {
          @page { size: A4; margin: 14mm 12mm; }
          body  { background: white !important; }
          .drm-no-print   { display: none !important; }
          .drm-print-area {
            position: fixed !important; inset: 0 !important;
            overflow: visible !important; padding: 20px !important;
            background: white !important;
          }
          .drm-print-area * { box-shadow: none !important; }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(40px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>

      {/* Header */}
      <div className="drm-no-print" style={{ background: "#0f172a", padding: "12px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <img src={RaneLogo} alt="Rane Madras Ltd" style={{ height: "30px", width: "auto", objectFit: "contain" }} />
          <div>
            <p style={{ color: "white", fontWeight: "bold", fontSize: "14px", margin: 0 }}>Rane Madras Ltd</p>
            <p style={{ color: "#94a3b8", fontSize: "11px", margin: 0 }}>Digital DRM — Reports</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ background: "#3b82f6", color: "white", fontSize: "12px", padding: "4px 12px", borderRadius: "20px", fontWeight: "600" }}>
            Plant {plantId}
          </span>
          <button onClick={onBack} style={{ background: "#334155", color: "white", border: "none", padding: "6px 12px", borderRadius: "6px", cursor: "pointer", fontSize: "12px" }}>
            ← Back to Dashboard
          </button>
        </div>
      </div>

      {/* Auto-report banner */}
      {autoMsg && (
        <div className="drm-no-print" style={{
          padding: "10px 32px", fontSize: "12px", fontWeight: "500",
          background: autoMsg.startsWith("✅") ? "#dcfce7" : autoMsg.startsWith("⏳") ? "#eff6ff" : "#fef3c7",
          color: autoMsg.startsWith("✅") ? "#166534" : autoMsg.startsWith("⏳") ? "#1e40af" : "#92400e",
          borderBottom: "1px solid #e2e8f0",
        }}>
          {autoMsg}
        </div>
      )}

      {/* Main */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0 }}>

        {/* Left panel */}
        <div className="drm-no-print" style={{ width: "300px", background: "white", borderRight: "1px solid #e2e8f0", padding: "24px", overflowY: "auto", flexShrink: 0 }}>
          <h3 style={{ color: "#0f172a", fontSize: "15px", fontWeight: "700", margin: "0 0 4px 0" }}>Generate Report</h3>

          <div style={{ marginBottom: "20px" }}>
            <label style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", display: "block", marginBottom: "8px" }}>Report Type</label>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {["monthly", "quarterly", "yearly"].map(type => (
                <button key={type} onClick={() => setReportType(type)} style={{
                  padding: "10px 12px", borderRadius: "8px", cursor: "pointer", fontWeight: "600",
                  fontSize: "13px", transition: "all 0.2s",
                  border: reportType === type ? "2px solid #3b82f6" : "1px solid #e2e8f0",
                  background: reportType === type ? "#eff6ff" : "white",
                  color: reportType === type ? "#3b82f6" : "#64748b",
                }}>
                  {type.charAt(0).toUpperCase() + type.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <label style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", display: "block", marginBottom: "8px" }}>Year</label>
            <input type="number" value={year} onChange={e => setYear(Number(e.target.value))}
              style={{ width: "100%", padding: "10px 12px", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: "13px", fontFamily: "inherit", boxSizing: "border-box" }} />
          </div>

          {reportType === "monthly" && (
            <div style={{ marginBottom: "20px" }}>
              <label style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", display: "block", marginBottom: "8px" }}>Month</label>
              <select value={month} onChange={e => setMonth(Number(e.target.value))}
                style={{ width: "100%", padding: "10px 12px", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: "13px", fontFamily: "inherit" }}>
                {months.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>
          )}

          {reportType === "quarterly" && (
            <div style={{ marginBottom: "20px" }}>
              <label style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", display: "block", marginBottom: "8px" }}>Quarter</label>
              <select value={quarter} onChange={e => setQuarter(Number(e.target.value))}
                style={{ width: "100%", padding: "10px 12px", border: "1px solid #e2e8f0", borderRadius: "8px", fontSize: "13px", fontFamily: "inherit" }}>
                {quarters.map(q => <option key={q.value} value={q.value}>{q.label}</option>)}
              </select>
            </div>
          )}

          <button onClick={generateReport} disabled={loading || saving} style={{
            width: "100%", padding: "12px", border: "none", borderRadius: "8px",
            fontWeight: "600", fontSize: "13px",
            background: (loading || saving) ? "#cbd5e1" : "#3b82f6",
            color: "white", cursor: (loading || saving) ? "not-allowed" : "pointer",
          }}>
            {loading ? "Generating…" : saving ? "Saving…" : "Generate Report"}
          </button>

          {error && (
            <div style={{ marginTop: "12px", padding: "10px 12px", background: "#fee2e2", border: "1px solid #fecaca", borderRadius: "8px", color: "#dc2626", fontSize: "12px" }}>
              {error}
            </div>
          )}

          <div style={{ marginTop: "16px", padding: "10px 12px", background: "#eff6ff", borderRadius: "8px", border: "1px solid #bfdbfe" }}>
            <p style={{ margin: 0, fontSize: "11px", color: "#1d4ed8", lineHeight: 1.5 }}>
              📁 Reports are automatically saved to:<br />
              <strong>D:\Digitalization_DigitalDRM2.o\DigitalDRM\Reports</strong>
            </p>
          </div>
        </div>

        {/* Right panel — report display */}
        <div className="drm-print-area" style={{ flex: 1, padding: "24px", overflowY: "auto" }}>
          {report ? (
            <div>
              <div style={{ marginBottom: "24px" }}>
                <h2 style={{ color: "#0f172a", fontSize: "20px", fontWeight: "700", margin: "0 0 4px 0" }}>
                  {report.report_type} Report — Plant {plantId}
                </h2>
                <p style={{ color: "#64748b", fontSize: "13px", margin: "0 0 4px 0" }}>
                  {report.report_type === "Monthly" && `${MONTH_NAMES[report.month]} ${report.year}`}
                  {report.report_type === "Quarterly" && `${quarterLabel(report.quarter)} ${report.year}`}
                  {report.report_type === "Yearly" && `Year ${report.year}`}
                </p>
                <p style={{ color: "#94a3b8", fontSize: "12px", margin: 0 }}>
                  File: <strong style={{ color: "#475569" }}>{buildFilename(plantId, reportType, month, quarter, year)}</strong>
                </p>
              </div>

              {/* Metric cards - show Achievement % (not deviation) */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px", marginBottom: "24px" }}>
                {[
                  ["Production", report.production],
                  ["Manpower", report.manpower],
                  ["Sales", report.sales],
                  ["OVC Elements", report.ovc],
                  ["Despatch", report.despatch],
                  report.rejection_ppm && ["Rejection PPM", report.rejection_ppm],
                  report.product_value && ["Product Value", report.product_value],
                ].filter(Boolean).map(([title, d]) => (
                  <ReportCard key={title} title={title}
                    plan={d.plan} actual={d.actual}
                    variance={calculateVariance(d.plan, d.actual)}
                    percentage={calculateAchievement(d.plan, d.actual)} 
                    deviation={calculateDeviation(d.plan, d.actual)}/>
                ))}
              </div>

              {/* Summary table with correct Achievement % */}
              <div>
                <h3 style={{ color: "#0f172a", fontSize: "15px", fontWeight: "700", margin: "0 0 12px 0" }}>Summary</h3>
                <div style={{ background: "white", borderRadius: "12px", overflow: "hidden", border: "1px solid #e2e8f0" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                        {["Metric", "Plan", "Actual", "Variance", "Achieved %", "Status"].map((h, i) => (
                          <th key={h} style={{ padding: "12px 16px", textAlign: i === 0 ? "left" : "right", fontWeight: "600", color: "#64748b", fontSize: "12px" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ["Production", report.production],
                        ["Manpower", report.manpower],
                        ["Sales", report.sales],
                        ["OVC Elements", report.ovc],
                        ["Despatch", report.despatch],
                        report.rejection_ppm && ["Rejection PPM", report.rejection_ppm],
                        report.product_value && ["Product Value", report.product_value],
                      ].filter(Boolean).map(([metric, d]) => {
                        const plan = d.plan || 0;
                        const actual = d.actual || 0;
                        const variance = calculateVariance(plan, actual);
                        const achievement = calculateAchievement(plan, actual);
                        const pctNum = plan ? (actual / plan * 100) : 0;
                        let status = "No Data";
                        if (plan > 0 || actual > 0) {
                          if (pctNum >= 100) status = "On Track";
                          else if (pctNum >= 80) status = "Near Target";
                          else if (pctNum > 0) status = "Below Target";
                        }
                        return (
                          <TableRow key={metric} metric={metric}
                            plan={plan} actual={actual}
                            variance={variance}
                            achievement={achievement}
                            status={status} />
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {saveMsg.type === "error" && (
                <div className="drm-no-print" style={{
                  marginTop: "24px",
                  padding: "14px",
                  background: "#fee2e2",
                  border: "1px solid #fecaca",
                  borderRadius: "10px",
                  color: "#dc2626",
                  fontSize: "13px",
                }}>
                  {saveMsg.text}
                </div>
              )}
              {saving && (
                <div className="drm-no-print" style={{ marginTop: "24px", padding: "14px 18px", borderRadius: "10px", background: "#eff6ff", border: "1px solid #bfdbfe", color: "#1d4ed8", fontSize: "13px" }}>
                  ⏳ Saving report to server…
                </div>
              )}

            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "#94a3b8" }}>
              <div style={{ fontSize: "48px", marginBottom: "12px" }}>📊</div>
              <p style={{ fontSize: "15px", fontWeight: "600", margin: "0 0 4px 0" }}>No report generated yet</p>
              <p style={{ fontSize: "13px", margin: 0 }}>Select options and click "Generate Report"</p>
            </div>
          )}
        </div>

      </div>

      {/* Success Popup */}
      {showPopup && (
        <div
          style={{
            position: "fixed",
            top: "30px",
            right: "30px",
            background: "#ffffff",
            border: "1px solid #16a34a",
            borderLeft: "5px solid #16a34a",
            borderRadius: "10px",
            padding: "16px 20px",
            boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
            zIndex: 9999,
            minWidth: "320px",
            animation: "slideIn 0.3s ease",
          }}
        >
          <div style={{ fontWeight: "600", color: "#166534", fontSize: "15px", marginBottom: "4px" }}>
            Report Saved ✅
          </div>
          <div style={{ color: "#475569", fontSize: "13px" }}>
            The report has been successfully saved to the Reports folder.
          </div>
        </div>
      )}

    </div>
  );
}

// ── Helper components ─────────────────────────────────────────────────────────

function ReportCard({ title, plan, actual, variance, percentage, deviation }) {
  const pos = (variance || 0) >= 0;
  const pctNum = plan ? (actual / plan * 100) : 0;
  let status = "No Data";
  if (plan > 0 || actual > 0) {
    if (pctNum >= 100) status = "On Track";
    else if (pctNum >= 80) status = "Near Target";
    else if (pctNum > 0) status = "Below Target";
  }
  const statusColor = status === "On Track" ? "#16a34a" : status === "Near Target" ? "#d97706" : status === "Below Target" ? "#dc2626" : "#94a3b8";
  
  return (
    <div style={{ background: "white", borderRadius: "12px", padding: "16px", border: "1px solid #e2e8f0" }}>
      <h4 style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", margin: "0 0 12px 0", textTransform: "uppercase" }}>{title}</h4>
      <div style={{ display: "grid", gap: "10px" }}>
        <div><p style={{ color: "#94a3b8", fontSize: "11px", margin: "0 0 2px 0" }}>PLAN</p>
          <p style={{ color: "#0f172a", fontSize: "16px", fontWeight: "700", margin: 0 }}>{(plan || 0).toFixed(2)}</p></div>
        <div><p style={{ color: "#94a3b8", fontSize: "11px", margin: "0 0 2px 0" }}>ACTUAL</p>
          <p style={{ color: "#0f172a", fontSize: "16px", fontWeight: "700", margin: 0 }}>{(actual || 0).toFixed(2)}</p></div>
        <div><p style={{ color: "#94a3b8", fontSize: "11px", margin: "0 0 2px 0" }}>VARIANCE</p>
          <p style={{ color: pos ? "#16a34a" : "#dc2626", fontSize: "15px", fontWeight: "700", margin: 0 }}>{pos ? "+" : ""}{(variance || 0).toFixed(2)}</p></div>
        <div style={{ background: pos ? "#dcfce7" : "#fee2e2", padding: "6px 10px", borderRadius: "6px", textAlign: "center" }}>
          <p style={{ color: pos ? "#166534" : "#991b1b", fontSize: "13px", fontWeight: "700", margin: 0 }}>{percentage}</p>
        </div>
        <div style={{ textAlign: "center", marginTop: "4px" }}>
          <span style={{ 
            padding: "2px 10px", 
            borderRadius: "12px", 
            fontSize: "11px", 
            fontWeight: "600",
            background: status === "On Track" ? "#dcfce7" : status === "Near Target" ? "#fef3c7" : status === "Below Target" ? "#fee2e2" : "#f1f5f9",
            color: statusColor
          }}>
            {status}
          </span>
        </div>
      </div>
    </div>
  );
}

function TableRow({ metric, plan, actual, variance, achievement, status }) {
  const pos = (variance || 0) >= 0;
  const statusColor = status === "On Track" ? "#16a34a" : status === "Near Target" ? "#d97706" : status === "Below Target" ? "#dc2626" : "#94a3b8";
  
  return (
    <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
      <td style={{ padding: "12px 16px", fontSize: "13px", color: "#0f172a", fontWeight: "500" }}>{metric}</td>
      <td style={{ padding: "12px 16px", fontSize: "13px", color: "#0f172a", textAlign: "right" }}>{(plan || 0).toFixed(2)}</td>
      <td style={{ padding: "12px 16px", fontSize: "13px", color: "#0f172a", textAlign: "right", fontWeight: "600" }}>{(actual || 0).toFixed(2)}</td>
      <td style={{ padding: "12px 16px", fontSize: "13px", textAlign: "right", fontWeight: "600", color: pos ? "#16a34a" : "#dc2626" }}>{pos ? "+" : ""}{(variance || 0).toFixed(2)}</td>
      <td style={{ padding: "12px 16px", fontSize: "13px", textAlign: "right", fontWeight: "600", color: "#0f172a" }}>{achievement}</td>
      <td style={{ padding: "12px 16px", fontSize: "12px", textAlign: "center", fontWeight: "600", color: statusColor }}>
        {status}
      </td>
    </tr>
  );
}

export default Reports;