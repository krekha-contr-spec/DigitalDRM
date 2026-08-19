import { useState, useEffect, useRef } from "react";
import RaneLogo from "../assets/Rane_Group_Logo.jpg";
import {
  generateMonthlyReport,
  generateQuarterlyReport,
  generateYearlyReport,
  generateOverallSummaryReport,
  saveReportToServer,
} from "../services/api";

// ── Constants ────────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const TARGET_SAVE_DIR = "D:\\c103191-Data\\DigitalDRM\\Reports";

// All plants in the system
const ALL_PLANTS = [1, 2, 3, 4, 5];

// Standardized Indian-FY quarter labels
const QUARTER_RANGES = { 1: "Apr-Jun", 2: "Jul-Sep", 3: "Oct-Dec", 4: "Jan-Mar" };
function quarterLabel(q) {
  return `Q${q} (${QUARTER_RANGES[q] || ""})`;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function buildFilename(plantId, reportType, month, quarter, year) {
  if (reportType === "overall-summary") return `Overall_Summary_${MONTH_NAMES[month]}_${year}.pdf`;
  const plant = `Plant${String(plantId).padStart(2, "0")}`;
  const type = reportType.charAt(0).toUpperCase() + reportType.slice(1);
  if (reportType === "yearly") return `${plant}_Yearly_${year}.pdf`;
  if (reportType === "quarterly") return `${plant}_Quarterly_Q${quarter}_${year}.pdf`;
  return `${plant}_Monthly_${MONTH_NAMES[month]}_${year}.pdf`;
}

/** Build individual plant report section HTML */
function buildPlantReportSection(plantId, reportType, month, quarter, year, data) {
  const period =
    reportType === "yearly" ? String(year) :
    reportType === "quarterly" ? `${quarterLabel(quarter)} ${year}` :
    `${MONTH_NAMES[month]} ${year}`;

  const depts = [
    ["Production", data.production],
    ["Manpower", data.manpower],
    ["Sales", data.sales],
    ["OVC Elements", data.ovc],
    ["Despatch", data.despatch],
    ["Rejection PPM", data.rejection_ppm],
    ["Product Value", data.product_value],
  ].filter(([, d]) => d);

  // Calculate totals for plant achievement
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

  const plantAchieved = totalPlan > 0 ? ((totalActual / totalPlan) * 100) : 0;

  // Build department rows
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

  return `
    <!-- Plant ${plantId} Section -->
    <div style="page-break-inside:avoid;margin-bottom:40px;padding-bottom:32px;border-bottom:2px solid #e2e8f0">
      <h2 style="font-size:18px;margin:0 0 4px;color:#0f172a">Plant ${plantId}</h2>
      <p style="color:#64748b;font-size:12px;margin:0 0 16px">Department-wise Performance Summary</p>
      
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px">
        <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:12px;border-radius:6px">
          <p style="font-size:11px;color:#64748b;margin:0 0 4px;text-transform:uppercase;font-weight:600">Overall Achievement</p>
          <p style="font-size:18px;font-weight:700;margin:0;color:${plantAchieved >= 100 ? '#16a34a' : plantAchieved >= 80 ? '#d97706' : '#dc2626'}">${plantAchieved.toFixed(1)}%</p>
        </div>
        <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:12px;border-radius:6px">
          <p style="font-size:11px;color:#64748b;margin:0 0 4px;text-transform:uppercase;font-weight:600">On Track</p>
          <p style="font-size:18px;font-weight:700;margin:0;color:#16a34a">${onTrack}</p>
        </div>
        <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:12px;border-radius:6px">
          <p style="font-size:11px;color:#64748b;margin:0 0 4px;text-transform:uppercase;font-weight:600">Departments</p>
          <p style="font-size:18px;font-weight:700;margin:0;color:#d97706">${depts.length}</p>
        </div>
        <div style="background:#fef2f2;border-left:4px solid #ef4444;padding:12px;border-radius:6px">
          <p style="font-size:11px;color:#64748b;margin:0 0 4px;text-transform:uppercase;font-weight:600">Needs Attention</p>
          <p style="font-size:18px;font-weight:700;margin:0;color:#dc2626">${needsAttention}</p>
        </div>
      </div>

      <div style="background:white;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0">
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="background:#f8fafc;border-bottom:1px solid #e2e8f0">
              <th style="padding:12px 14px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Department</th>
              <th style="padding:12px 14px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Plan</th>
              <th style="padding:12px 14px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Actual</th>
              <th style="padding:12px 14px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Variance</th>
              <th style="padding:12px 14px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Achieved %</th>
              <th style="padding:12px 14px;text-align:center;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Status</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

/** Build Overall Summary Report HTML with all plants (separate department-wise details per plant) */
function buildOverallSummaryHTML(reportType, month, quarter, year, allPlantsData) {
  const period =
    reportType === "yearly" ? String(year) :
    reportType === "quarterly" ? `${quarterLabel(quarter)} ${year}` :
    `${MONTH_NAMES[month]} ${year}`;

  const generatedAt = new Date().toLocaleString("en-GB");

  // Build individual plant sections with department-wise breakdown
  const plantSections = Object.entries(allPlantsData)
    .sort(([a], [b]) => parseInt(a) - parseInt(b))
    .map(([plantId, data]) => {
      if (!data) return "";

      const depts = [
        ["Production", data.production],
        ["Manpower", data.manpower],
        ["Sales", data.sales],
        ["OVC Elements", data.ovc],
        ["Despatch", data.despatch],
        ["Rejection PPM", data.rejection_ppm],
        ["Product Value", data.product_value],
      ].filter(([, d]) => d);

      let totalPlan = 0, totalActual = 0, onTrack = 0, needsAttention = 0;
      depts.forEach(([, d]) => {
        const plan = d.plan || 0;
        const actual = d.actual || 0;
        if (plan > 0 || actual > 0) {
          totalPlan += plan;
          totalActual += actual;
          const pct = plan ? (actual / plan * 100) : 0;
          if (pct >= 100) onTrack++;
          else if (pct < 80) needsAttention++;
        }
      });

      const plantAchieved = totalPlan > 0 ? ((totalActual / totalPlan) * 100) : 0;

      // Build department rows
      const rows = depts.map(([name, d]) => {
        const plan = d.plan || 0;
        const actual = d.actual || 0;
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

      return `
        <!-- Plant ${plantId} Page -->
        <div style="page-break-after:always;padding-bottom:40px">
          <h2 style="font-size:20px;margin:0 0 4px 0;color:#0f172a;font-weight:700">Plant ${plantId}</h2>
          <p style="color:#64748b;font-size:12px;margin:0 0 20px 0">Department-wise Performance Report</p>
          
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px">
            <div style="background:#f0f9ff;border-left:4px solid #3b82f6;padding:14px;border-radius:6px">
              <p style="font-size:10px;color:#64748b;margin:0 0 4px 0;text-transform:uppercase;font-weight:600">Overall Achievement</p>
              <p style="font-size:18px;font-weight:700;margin:0;color:${plantAchieved >= 100 ? '#16a34a' : plantAchieved >= 80 ? '#d97706' : '#dc2626'}">${plantAchieved.toFixed(1)}%</p>
            </div>
            <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:14px;border-radius:6px">
              <p style="font-size:10px;color:#64748b;margin:0 0 4px 0;text-transform:uppercase;font-weight:600">On Track</p>
              <p style="font-size:18px;font-weight:700;margin:0;color:#16a34a">${onTrack}/${depts.length}</p>
            </div>
            <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:14px;border-radius:6px">
              <p style="font-size:10px;color:#64748b;margin:0 0 4px 0;text-transform:uppercase;font-weight:600">Near Target</p>
              <p style="font-size:18px;font-weight:700;margin:0;color:#d97706">${depts.filter(([, d]) => {
                const p = d.plan || 0;
                const a = d.actual || 0;
                const pct = p ? (a / p * 100) : 0;
                return pct >= 80 && pct < 100;
              }).length}</p>
            </div>
            <div style="background:#fef2f2;border-left:4px solid #ef4444;padding:14px;border-radius:6px">
              <p style="font-size:10px;color:#64748b;margin:0 0 4px 0;text-transform:uppercase;font-weight:600">Below Target</p>
              <p style="font-size:18px;font-weight:700;margin:0;color:#dc2626">${needsAttention}</p>
            </div>
          </div>

          <div style="background:white;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0">
            <table style="width:100%;border-collapse:collapse">
              <thead>
                <tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0">
                  <th style="padding:12px 14px;text-align:left;font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600">Department</th>
                  <th style="padding:12px 14px;text-align:right;font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600">Plan</th>
                  <th style="padding:12px 14px;text-align:right;font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600">Actual</th>
                  <th style="padding:12px 14px;text-align:right;font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600">Variance</th>
                  <th style="padding:12px 14px;text-align:right;font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600">Achieved %</th>
                  <th style="padding:12px 14px;text-align:center;font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600">Status</th>
                </tr>
              </thead>
              <tbody>
                ${rows}
              </tbody>
            </table>
          </div>
        </div>
      `;
    })
    .join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>DRM Overall Summary Report - ${period}</title>
<style>
  body{font-family:Arial,sans-serif;font-size:13px;color:#0f172a;margin:0;padding:24px;background:#ffffff}
  h1{font-size:22px;margin:0 0 4px;font-weight:700}
  .sub{color:#64748b;font-size:12px;margin:0 0 20px}
  .meta{display:flex;gap:28px;margin-bottom:32px;padding:16px 20px;
        background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;page-break-after:avoid}
  .mi{display:flex;flex-direction:column}
  .mi label{font-size:10px;color:#64748b;text-transform:uppercase;
            font-weight:600;margin-bottom:4px}
  .mi span{font-size:14px;font-weight:700;color:#0f172a}
  h2{font-size:20px;margin:0 0 4px 0;color:#0f172a;font-weight:700;page-break-before:avoid}
  table{width:100%;border-collapse:collapse}
  th{background:#f8fafc;padding:12px 14px;text-align:left;font-size:11px;
     color:#64748b;text-transform:uppercase;border-bottom:2px solid #e2e8f0;font-weight:600}
  td{padding:10px 14px;border-bottom:1px solid #e2e8f0;font-size:13px}
  tr:last-child td{border-bottom:1px solid #e2e8f0}
  .footer{margin-top:40px;padding:24px;border-top:2px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center;background:#f8fafc;border-radius:8px}
  @media print{
    @page{size:A4;margin:14mm 12mm}
    body{padding:0;margin:0}
    .meta{page-break-after:avoid}
  }
</style>
</head>
<body>
  <h1>Digital DRM — Overall Summary Report</h1>
  <p class="sub">Rane Madras Ltd · Multi-Plant Performance</p>
  <div class="meta">
    <div class="mi"><label>Report Type</label><span>Overall Summary</span></div>
    <div class="mi"><label>Period</label><span>${period}</span></div>
    <div class="mi"><label>Plants Covered</label><span>5 Plants</span></div>
    <div class="mi"><label>Generated</label><span>${generatedAt}</span></div>
  </div>
  
  ${plantSections}
  
  <div class="footer">
    <p style="margin:0;font-weight:600">Report Structure</p>
    <p style="margin:8px 0 0 0">This report displays each of the 5 plants separately with complete department-wise achievement metrics. Each plant shows its individual performance across Production, Manpower, Sales, OVC Elements, Despatch, Rejection PPM, and Product Value. No aggregation across plants is performed.</p>
    <p style="margin:12px 0 0 0;color:#cbd5e1;font-size:10px">Generated by Digital DRM System • Rane Group • ${generatedAt}</p>
  </div>
</body>
</html>`;
}

/** Build a clean, print-ready HTML string from report data (single plant). */
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

  <div class="footer">
    <p>This report was automatically generated by the Digital DRM system. Data is current as of the report generation date and time.</p>
  </div>
</body>
</html>`;
}

// ── Main Component ──────────────────────────────────────────────────────────

function Reports({ plantId, onBack }) {
  const [reportType, setReportType] = useState("monthly");
  const [month, setMonth] = useState(new Date().getMonth());
  const [quarter, setQuarter] = useState(1);
  const [year, setYear] = useState(new Date().getFullYear());
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState({ type: "", text: "" });
  const [showPopup, setShowPopup] = useState(false);
  const reportContentRef = useRef(null);

  const isOverallSummary = reportType === "overall-summary";

  // Generate report on button click
  const handleGenerateReport = async () => {
    setLoading(true);
    setSaveMsg({ type: "", text: "" });

    try {
      let response;

      if (isOverallSummary) {
        // Overall Summary - fetch data for all plants
        const allPlantsData = {};
        for (const pid of ALL_PLANTS) {
          let plantReport;
          if (reportType === "overall-summary") {
            plantReport = await generateMonthlyReport(pid, month, year);
          }
          allPlantsData[pid] = plantReport;
        }
        response = allPlantsData;
      } else {
        // Single plant report
        if (reportType === "monthly") {
          response = await generateMonthlyReport(plantId, month, year);
        } else if (reportType === "quarterly") {
          response = await generateQuarterlyReport(plantId, quarter, year);
        } else if (reportType === "yearly") {
          response = await generateYearlyReport(plantId, year);
        }
      }

      setReport(response);
      setLoading(false);
    } catch (error) {
      console.error("Error generating report:", error);
      setLoading(false);
    }
  };

  const handleSaveReport = async () => {
    if (!report) return;

    setSaving(true);
    try {
      let html;
      let filename;

      if (isOverallSummary) {
        html = buildOverallSummaryHTML(reportType, month, quarter, year, report);
        filename = buildFilename(null, reportType, month, quarter, year);
      } else {
        html = buildReportHTML(plantId, reportType, month, quarter, year, report);
        filename = buildFilename(plantId, reportType, month, quarter, year);
      }

      await saveReportToServer(filename, html, TARGET_SAVE_DIR);
      setSaveMsg({ type: "success", text: `Report saved as ${filename}` });
      setShowPopup(true);
      setTimeout(() => setShowPopup(false), 4000);
    } catch (error) {
      console.error("Save error:", error);
      setSaveMsg({ type: "error", text: "Failed to save report. Please try again." });
    } finally {
      setSaving(false);
    }
  };

  const calculateVariance = (plan, actual) => (actual - plan).toFixed(2);
  const calculateAchievement = (plan, actual) => plan ? ((actual / plan * 100).toFixed(2) + "%") : "N/A";

  return (
    <div style={{ display: "flex", height: "100vh", background: "#f8fafc" }}>
      {/* Sidebar */}
      <div style={{ width: "280px", background: "white", borderRight: "1px solid #e2e8f0", padding: "24px", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "24px" }}>
          <button
            onClick={onBack}
            style={{
              background: "none",
              border: "none",
              fontSize: "20px",
              cursor: "pointer",
              padding: "4px",
            }}
          >
            ←
          </button>
          <h2 style={{ margin: "0", fontSize: "18px", fontWeight: "700" }}>Reports</h2>
        </div>

        {/* Report Type */}
        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "600", marginBottom: "8px", fontSize: "13px", color: "#0f172a" }}>Report Type</label>
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px",
              borderRadius: "6px",
              border: "1px solid #e2e8f0",
              fontSize: "13px",
            }}
          >
            <option value="monthly">Monthly Report</option>
            <option value="quarterly">Quarterly Report</option>
            <option value="yearly">Yearly Report</option>
            <option value="overall-summary">Overall Summary (All Plants)</option>
          </select>
        </div>

        {/* Month Selector */}
        {reportType === "monthly" && (
          <div style={{ marginBottom: "20px" }}>
            <label style={{ display: "block", fontWeight: "600", marginBottom: "8px", fontSize: "13px", color: "#0f172a" }}>Month</label>
            <select
              value={month}
              onChange={(e) => setMonth(parseInt(e.target.value))}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: "6px",
                border: "1px solid #e2e8f0",
                fontSize: "13px",
              }}
            >
              {MONTH_NAMES.slice(1).map((m, i) => (
                <option key={i} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Quarter Selector */}
        {reportType === "quarterly" && (
          <div style={{ marginBottom: "20px" }}>
            <label style={{ display: "block", fontWeight: "600", marginBottom: "8px", fontSize: "13px", color: "#0f172a" }}>Quarter</label>
            <select
              value={quarter}
              onChange={(e) => setQuarter(parseInt(e.target.value))}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: "6px",
                border: "1px solid #e2e8f0",
                fontSize: "13px",
              }}
            >
              <option value={1}>Q1 (Apr-Jun)</option>
              <option value={2}>Q2 (Jul-Sep)</option>
              <option value={3}>Q3 (Oct-Dec)</option>
              <option value={4}>Q4 (Jan-Mar)</option>
            </select>
          </div>
        )}

        {/* Year Selector */}
        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontWeight: "600", marginBottom: "8px", fontSize: "13px", color: "#0f172a" }}>Year</label>
          <select
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
            style={{
              width: "100%",
              padding: "8px 12px",
              borderRadius: "6px",
              border: "1px solid #e2e8f0",
              fontSize: "13px",
            }}
          >
            {[2023, 2024, 2025, 2026].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        {/* Info Box */}
        {isOverallSummary && (
          <div style={{
            background: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: "8px",
            padding: "12px",
            fontSize: "12px",
            color: "#1e40af",
            marginBottom: "20px",
          }}>
            <p style={{ margin: "0 0 6px 0", fontWeight: "600" }}>📋 Overall Summary</p>
            <p style={{ margin: 0 }}>Shows all 5 plants separately with department-wise achievement. Each plant displays independently without aggregation.</p>
          </div>
        )}

        {/* Generate Button */}
        <button
          onClick={handleGenerateReport}
          disabled={loading}
          style={{
            width: "100%",
            padding: "10px",
            background: "#3b82f6",
            color: "white",
            border: "none",
            borderRadius: "6px",
            fontWeight: "600",
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.7 : 1,
            fontSize: "13px",
            marginBottom: "12px",
          }}
        >
          {loading ? "⏳ Generating..." : "Generate Report"}
        </button>

        {/* Save Button */}
        {report && (
          <button
            onClick={handleSaveReport}
            disabled={saving}
            style={{
              width: "100%",
              padding: "10px",
              background: "#16a34a",
              color: "white",
              border: "none",
              borderRadius: "6px",
              fontWeight: "600",
              cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.7 : 1,
              fontSize: "13px",
            }}
          >
            {saving ? "💾 Saving..." : "💾 Save Report"}
          </button>
        )}
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Print Toolbar */}
        {report && (
          <div style={{
            background: "white",
            borderBottom: "1px solid #e2e8f0",
            padding: "12px 20px",
            display: "flex",
            gap: "12px",
            alignItems: "center",
            justifyContent: "flex-end",
          }}>
            <button
              onClick={() => window.print()}
              style={{
                padding: "8px 16px",
                background: "#f3f4f6",
                border: "1px solid #d1d5db",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: "500",
              }}
            >
              🖨️ Print
            </button>
          </div>
        )}

        {/* Report Content */}
        <div ref={reportContentRef} style={{ flex: 1, overflow: "auto", padding: "20px" }}>
          {report ? (
            <div style={{
              background: "white",
              borderRadius: "8px",
              padding: "32px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
              minHeight: "100%",
            }}>
              {isOverallSummary ? (
                // Overall Summary View - Separate plants with department details
                <>
                  <h1 style={{ fontSize: "24px", margin: "0 0 8px 0", fontWeight: "700" }}>Digital DRM — Overall Summary Report</h1>
                  <p style={{ color: "#64748b", fontSize: "13px", margin: "0 0 24px 0" }}>Rane Madras Ltd · Multi-Plant Performance</p>
                  
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px", marginBottom: "32px" }}>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Report Type</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>Overall Summary</p>
                    </div>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Period</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>{MONTH_NAMES[month]} {year}</p>
                    </div>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Plants Covered</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>5 Plants</p>
                    </div>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Generated</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>{new Date().toLocaleDateString()}</p>
                    </div>
                  </div>

                  {/* Plant Sections - Each with Department Details */}
                  {Object.entries(report)
                    .sort(([a], [b]) => parseInt(a) - parseInt(b))
                    .map(([pid, data]) => {
                      if (!data) return null;

                      const depts = [
                        ["Production", data.production],
                        ["Manpower", data.manpower],
                        ["Sales", data.sales],
                        ["OVC Elements", data.ovc],
                        ["Despatch", data.despatch],
                        ["Rejection PPM", data.rejection_ppm],
                        ["Product Value", data.product_value],
                      ].filter(([, d]) => d);

                      let totalPlan = 0, totalActual = 0, onTrack = 0;
                      depts.forEach(([, d]) => {
                        const plan = d.plan || 0;
                        const actual = d.actual || 0;
                        if (plan > 0 || actual > 0) {
                          totalPlan += plan;
                          totalActual += actual;
                          const pct = plan ? (actual / plan * 100) : 0;
                          if (pct >= 100) onTrack++;
                        }
                      });

                      const plantAchieved = totalPlan > 0 ? ((totalActual / totalPlan) * 100) : 0;
                      const needsAttention = depts.filter(([, d]) => {
                        const p = d.plan || 0;
                        const a = d.actual || 0;
                        return p > 0 && (a / p * 100) < 80;
                      }).length;
                      const nearTarget = depts.filter(([, d]) => {
                        const p = d.plan || 0;
                        const a = d.actual || 0;
                        const pct = p ? (a / p * 100) : 0;
                        return pct >= 80 && pct < 100;
                      }).length;

                      return (
                        <div key={pid} style={{ marginBottom: "48px", paddingBottom: "32px", borderBottom: "2px solid #e2e8f0" }}>
                          <h2 style={{ fontSize: "20px", margin: "0 0 4px 0", color: "#0f172a", fontWeight: "700" }}>Plant {pid}</h2>
                          <p style={{ color: "#64748b", fontSize: "12px", margin: "0 0 16px 0" }}>Department-wise Performance Report</p>

                          {/* KPI Cards */}
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px", marginBottom: "24px" }}>
                            <div style={{ background: "#f0f9ff", borderLeft: "4px solid #3b82f6", borderRadius: "6px", padding: "12px" }}>
                              <p style={{ fontSize: "10px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Overall Achievement</p>
                              <p style={{ fontSize: "18px", fontWeight: "700", margin: 0, color: plantAchieved >= 100 ? "#16a34a" : plantAchieved >= 80 ? "#d97706" : "#dc2626" }}>{plantAchieved.toFixed(1)}%</p>
                            </div>
                            <div style={{ background: "#f0fdf4", borderLeft: "4px solid #22c55e", borderRadius: "6px", padding: "12px" }}>
                              <p style={{ fontSize: "10px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>On Track</p>
                              <p style={{ fontSize: "18px", fontWeight: "700", margin: 0, color: "#16a34a" }}>{onTrack}/{depts.length}</p>
                            </div>
                            <div style={{ background: "#fffbeb", borderLeft: "4px solid #f59e0b", borderRadius: "6px", padding: "12px" }}>
                              <p style={{ fontSize: "10px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Near Target</p>
                              <p style={{ fontSize: "18px", fontWeight: "700", margin: 0, color: "#d97706" }}>{nearTarget}</p>
                            </div>
                            <div style={{ background: "#fef2f2", borderLeft: "4px solid #ef4444", borderRadius: "6px", padding: "12px" }}>
                              <p style={{ fontSize: "10px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Below Target</p>
                              <p style={{ fontSize: "18px", fontWeight: "700", margin: 0, color: "#dc2626" }}>{needsAttention}</p>
                            </div>
                          </div>

                          {/* Department Table */}
                          <div style={{ background: "white", borderRadius: "8px", overflow: "hidden", border: "1px solid #e2e8f0" }}>
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                              <thead>
                                <tr style={{ background: "#f8fafc", borderBottom: "2px solid #e2e8f0" }}>
                                  {["Department", "Plan", "Actual", "Variance", "Achieved %", "Status"].map((h, i) => (
                                    <th key={h} style={{ padding: "12px 14px", textAlign: i === 0 ? "left" : "right", fontWeight: "600", color: "#64748b", fontSize: "11px", textTransform: "uppercase" }}>{h}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {depts.map(([metric, d]) => {
                                  const plan = d.plan || 0;
                                  const actual = d.actual || 0;
                                  const variance = actual - plan;
                                  const achievement = plan ? ((actual / plan * 100).toFixed(2) + "%") : "N/A";
                                  const pctNum = plan ? (actual / plan * 100) : 0;
                                  let status = "No Data";
                                  if (plan > 0 || actual > 0) {
                                    if (pctNum >= 100) status = "On Track";
                                    else if (pctNum >= 80) status = "Near Target";
                                    else if (pctNum > 0) status = "Below Target";
                                  }
                                  const statusColor = status === "On Track" ? "#16a34a" : status === "Near Target" ? "#d97706" : status === "Below Target" ? "#dc2626" : "#94a3b8";

                                  return (
                                    <tr key={metric} style={{ borderBottom: "1px solid #e2e8f0" }}>
                                      <td style={{ padding: "12px 14px", fontSize: "13px", color: "#0f172a", fontWeight: "500" }}>{metric}</td>
                                      <td style={{ padding: "12px 14px", fontSize: "13px", color: "#0f172a", textAlign: "right" }}>{plan.toFixed(2)}</td>
                                      <td style={{ padding: "12px 14px", fontSize: "13px", color: "#0f172a", textAlign: "right", fontWeight: "600" }}>{actual.toFixed(2)}</td>
                                      <td style={{ padding: "12px 14px", fontSize: "13px", textAlign: "right", fontWeight: "600", color: variance >= 0 ? "#16a34a" : "#dc2626" }}>{variance >= 0 ? "+" : ""}{variance.toFixed(2)}</td>
                                      <td style={{ padding: "12px 14px", fontSize: "13px", textAlign: "right", fontWeight: "600", color: "#0f172a" }}>{achievement}</td>
                                      <td style={{ padding: "12px 14px", fontSize: "12px", textAlign: "center", fontWeight: "600", color: statusColor }}>{status}</td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    })}

                  {/* Footer */}
                  <div style={{ marginTop: "40px", padding: "24px", borderTop: "2px solid #e2e8f0", background: "#f8fafc", borderRadius: "8px", fontSize: "12px", color: "#94a3b8", textAlign: "center" }}>
                    <p style={{ margin: "0 0 8px 0", fontWeight: "600", color: "#0f172a" }}>Report Structure</p>
                    <p style={{ margin: 0 }}>This report displays each of the 5 plants separately with complete department-wise achievement metrics. Each plant shows its individual performance across Production, Manpower, Sales, OVC Elements, Despatch, Rejection PPM, and Product Value. No aggregation across plants is performed.</p>
                  </div>
                </>
              ) : (
                // Single Plant Report View
                <>
                  <h1 style={{ fontSize: "22px", margin: "0 0 4px 0", fontWeight: "700" }}>Digital DRM — {reportType.charAt(0).toUpperCase() + reportType.slice(1)} Report</h1>
                  <p style={{ color: "#64748b", fontSize: "13px", margin: "0 0 20px 0" }}>Rane Madras Ltd · Plant {plantId}</p>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px", marginBottom: "24px" }}>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Plant</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>{plantId}</p>
                    </div>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Report Type</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>{reportType.charAt(0).toUpperCase() + reportType.slice(1)}</p>
                    </div>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Period</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>
                        {reportType === "yearly" ? year : reportType === "quarterly" ? quarterLabel(quarter) + " " + year : MONTH_NAMES[month] + " " + year}
                      </p>
                    </div>
                    <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "14px" }}>
                      <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Generated</p>
                      <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>{new Date().toLocaleDateString()}</p>
                    </div>
                  </div>

                  <div style={{ background: "#f0f9ff", border: "1px solid #bfdbfe", borderRadius: "8px", padding: "16px", marginBottom: "24px" }}>
                    <p style={{ fontSize: "13px", fontWeight: "600", margin: "0 0 8px 0", color: "#1e40af" }}>📊 Executive Summary</p>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
                      <div>
                        <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Departments</p>
                        <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>
                          {[
                            ["Production", report.production],
                            ["Manpower", report.manpower],
                            ["Sales", report.sales],
                            ["OVC Elements", report.ovc],
                            ["Despatch", report.despatch],
                            report.rejection_ppm && ["Rejection PPM", report.rejection_ppm],
                            report.product_value && ["Product Value", report.product_value],
                          ].filter(Boolean).length}
                        </p>
                      </div>
                      <div>
                        <p style={{ fontSize: "11px", color: "#64748b", margin: "0 0 4px 0", textTransform: "uppercase", fontWeight: "600" }}>Overall Achieved</p>
                        <p style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#0f172a" }}>
                          {(() => {
                            let total = 0, count = 0;
                            [
                              ["Production", report.production],
                              ["Manpower", report.manpower],
                              ["Sales", report.sales],
                              ["OVC Elements", report.ovc],
                              ["Despatch", report.despatch],
                              report.rejection_ppm && ["Rejection PPM", report.rejection_ppm],
                              report.product_value && ["Product Value", report.product_value],
                            ].filter(Boolean).forEach(([, d]) => {
                              const plan = d.plan || 0;
                              const actual = d.actual || 0;
                              if (plan > 0) {
                                total += (actual / plan) * 100;
                                count++;
                              }
                            });
                            return count > 0 ? (total / count).toFixed(1) + "%" : "N/A";
                          })()}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div style={{ background: "white", borderRadius: "8px", overflow: "hidden", border: "1px solid #e2e8f0" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                          {["Metric", "Plan", "Actual", "Variance", "Achieved %", "Status"].map((h, i) => (
                            <th key={h} style={{ padding: "12px 16px", textAlign: i === 0 ? "left" : "right", fontWeight: "600", color: "#64748b", fontSize: "12px", textTransform: "uppercase" }}>{h}</th>
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
                </>
              )}

              {saveMsg.type === "error" && (
                <div style={{
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
                <div style={{ marginTop: "24px", padding: "14px 18px", borderRadius: "10px", background: "#eff6ff", border: "1px solid #bfdbfe", color: "#1d4ed8", fontSize: "13px" }}>
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
        <div style={{
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
        }}>
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

// ── Helper components ─────────────────────────────────────────────────────

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