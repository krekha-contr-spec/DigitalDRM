import axios from "axios"

// Configurable via VITE_API_BASE_URL (see .env / .env.example) so the
// deployed server IP (or any future host) never has to be hardcoded
// and edited by hand in multiple files — every API call in this app
// goes through this one constant.
export const API = import.meta.env.VITE_API_BASE_URL || "https://digitaldrm.onrender.com"

// Production
export const getProductionTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const queryString = params.toString()
  const url = `${API}/production/trend/${plantId}${queryString ? '?' + queryString : ''}`
  return axios.get(url)
}

export const addProduction = (data) => {
  return axios.post(`${API}/production/entry`, data)
}

export const checkProductionLock = (plantId, date) => {
  return axios.get(`${API}/production/check/${plantId}/${date}`)
}

export const getProductionLatestActual = (plantId) => {
  return axios.get(`${API}/production/latest-actual/${plantId}`)
}

export const getProductionHistory = (plantId) => {
  return axios.get(`${API}/production/history/${plantId}`)
}

// Manpower
export const getManpowerTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const queryString = params.toString()
  const url = `${API}/manpower/trend/${plantId}${queryString ? '?' + queryString : ''}`
  return axios.get(url)
}

export const addManpower = (data) => {
  return axios.post(`${API}/manpower/entry`, data)
}

export const checkManpowerLock = (plantId, date) => {
  return axios.get(`${API}/manpower/check/${plantId}/${date}`)
}

export const getManpowerLatestActual = (plantId) => {
  return axios.get(`${API}/manpower/latest-actual/${plantId}`)
}

export const getManpowerHistory = (plantId) => {
  return axios.get(`${API}/manpower/history/${plantId}`)
}

// Despatch
export const getDespatchTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const queryString = params.toString()
  const url = `${API}/despatch/trend/${plantId}${queryString ? '?' + queryString : ''}`
  return axios.get(url)
}

export const addDespatch = (data) => {
  return axios.post(`${API}/despatch/entry`, data)
}

export const checkDespatchLock = (plantId, date, customerName) => {
  return axios.get(`${API}/despatch/check/${plantId}/${date}`, { params: { customer_name: customerName } })
}

export const getDespatchLatestActual = (plantId) => {
  return axios.get(`${API}/despatch/latest-actual/${plantId}`)
}

export const getDespatchHistory = (plantId, limit = 0) => {
  // limit=0 (default) means "all records" per the backend's own
  // fallback (`if not limit or limit <= 0: return everything`) — needed
  // now that Despatch can have MULTIPLE customer rows per day; the old
  // default of 30 rows could silently cut off some customers'
  // per-customer charts once there's more than ~1 month of a couple of
  // customers' combined history.
  return axios.get(`${API}/despatch/history/${plantId}`, { params: { limit } })
}

// OVC
export const getOVCTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const queryString = params.toString()
  const url = `${API}/ovc/trend/${plantId}${queryString ? '?' + queryString : ''}`
  return axios.get(url)
}

export const addOVC = (data) => {
  return axios.post(`${API}/ovc/entry`, data)
}

export const checkOVCLock = (plantId, date, elementType) => {
  return axios.get(`${API}/ovc/check/${plantId}/${date}`, { params: { element_type: elementType } })
}

export const getOVCLatestActual = (plantId) => {
  return axios.get(`${API}/ovc/latest-actual/${plantId}`)
}

export const getOVCHistory = (plantId) => {
  return axios.get(`${API}/ovc/history/${plantId}`)
}

// Sales
export const getSalesTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const queryString = params.toString()
  const url = `${API}/sales/trend/${plantId}${queryString ? '?' + queryString : ''}`
  return axios.get(url)
}

export const addSales = (data) => {
  return axios.post(`${API}/sales/entry`, data)
}

export const checkSalesLock = (plantId, date, segment) => {
  return axios.get(`${API}/sales/check/${plantId}/${date}`, { params: { segment } })
}

export const getSalesLatestActual = (plantId) => {
  return axios.get(`${API}/sales/latest-actual/${plantId}`)
}

export const getSalesHistory = (plantId, limit = 30) => {
  const params = new URLSearchParams()
  params.append('limit', limit)
  return axios.get(`${API}/sales/history/${plantId}?${params.toString()}`)
}

// Rejection PPM
export const getRejectionPPMTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const qs = params.toString()
  return axios.get(`${API}/rejection-ppm/trend/${plantId}${qs ? '?' + qs : ''}`)
}

export const addRejectionPPM = (data) =>
  axios.post(`${API}/rejection-ppm/entry`, data)

export const checkRejectionPPMLock = (plantId, date) =>
  axios.get(`${API}/rejection-ppm/check/${plantId}/${date}`)

export const getRejectionPPMLatestActual = (plantId) =>
  axios.get(`${API}/rejection-ppm/latest-actual/${plantId}`)

export const getRejectionPPMHistory = (plantId, limit = 30) => {
  const params = new URLSearchParams()
  params.append('limit', limit)
  return axios.get(`${API}/rejection-ppm/history/${plantId}?${params.toString()}`)
}

// Product Value
export const getProductValueTrend = (plantId, year = null, month = null, view = "daily") => {
  const params = new URLSearchParams()
  if (year !== null) params.append('year', year)
  if (month !== null) params.append('month', month)
  params.append('view', view)
  const qs = params.toString()
  return axios.get(`${API}/product-value/trend/${plantId}${qs ? '?' + qs : ''}`)
}

export const addProductValue = (data) =>
  axios.post(`${API}/product-value/entry`, data)

export const checkProductValueLock = (plantId, date) =>
  axios.get(`${API}/product-value/check/${plantId}/${date}`)

export const getProductValueLatestActual = (plantId) =>
  axios.get(`${API}/product-value/latest-actual/${plantId}`)

export const getProductValueHistory = (plantId) =>
  axios.get(`${API}/product-value/history/${plantId}`)

// Monthly trend (full year, month-by-month) for charts
export const getSalesMonthlyTrend = (plantId, year) =>
  axios.get(`${API}/sales/monthly-trend/${plantId}?year=${year}`)

export const getDespatchMonthlyTrend = (plantId, year) =>
  axios.get(`${API}/despatch/monthly-trend/${plantId}?year=${year}`)

export const getRejectionPPMMonthlyTrend = (plantId, year) =>
  axios.get(`${API}/rejection-ppm/monthly-trend/${plantId}?year=${year}`)

export const getProductValueMonthlyTrend = (plantId, year) =>
  axios.get(`${API}/product-value/monthly-trend/${plantId}?year=${year}`)

// Report auto-save — calls backend to write PDF to D:\C102641-Data\DigitalDRM\Reports\
export const saveReportToServer = (data) =>
  axios.post(`${API}/report-save/save`, data)

// President Dashboard "Generate Report" — exports exactly the currently
// filtered Overall Summary, saves it to the DigitalDRM/Reports folder on
// the server, and emails it to r.keerthana-contr@ranegroup.com.
export const generateOverallSummaryReport = (data) =>
  axios.post(`${API}/report-save/overall-summary`, data)

// Auth
export const loginUser = (data) => {
  return axios.post(`${API}/auth/login`, data)
}

// Windows/AD login (Plant 5) — GEN ID + Windows/Domain password,
// authenticated via Rane's AD Login API (SOP ISM_L01).
export const adLoginUser = (data) => {
  return axios.post(`${API}/auth/ad-login`, data)
}

// Roles
export const getRoles = (plantId) => {
  return axios.get(`${API}/roles/${plantId}`)
}

export const verifyRoleAccess = (data) => {
  return axios.post(`${API}/role-access/verify`, {
    plant_id:    data.plant_id,
    person_name: data.person_name,
    email:       data.email,
    role:        data.role,
  })
}

// Reports
export const generateMonthlyReport = (plantId, year, month) => {
  return axios.post(`${API}/reports/monthly`, {
    plant_id: plantId,
    year: year,
    month: month,
    report_type: "monthly"
  })
}

export const generateQuarterlyReport = (plantId, year, quarter) => {
  return axios.post(`${API}/reports/quarterly`, {
    plant_id: plantId,
    year: year,
    quarter: quarter,
    report_type: "quarterly"
  })
}

export const generateYearlyReport = (plantId, year) => {
  return axios.post(`${API}/reports/yearly`, {
    plant_id: plantId,
    year: year,
    report_type: "yearly"
  })
}
