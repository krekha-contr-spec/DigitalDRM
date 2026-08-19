import { useState } from "react"

function MonthSelector({ selectedDate, onDateChange }) {
  const [showPicker, setShowPicker] = useState(false)

  const months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ]

  const currentYear = new Date().getFullYear()
  const years = [currentYear - 1, currentYear, currentYear + 1]

  const handleMonthChange = (month, year) => {
    const newDate = new Date(year, month, 1)
    onDateChange(newDate)
    setShowPicker(false)
  }

  const [month, year] = [selectedDate.getMonth(), selectedDate.getFullYear()]

  return (
    <div style={{ position: "relative" }}>
      {/* Month Display Button */}
      <button
        onClick={() => setShowPicker(!showPicker)}
        style={{
          padding: "10px 16px",
          background: "#3b82f6",
          color: "white",
          border: "none",
          borderRadius: "8px",
          fontWeight: "600",
          fontSize: "13px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          transition: "all 0.2s"
        }}
      >
        📅 {months[month]} {year}
        <span style={{ fontSize: "11px" }}>▼</span>
      </button>

      {/* Month Picker Dropdown */}
      {showPicker && (
        <div style={{
          position: "absolute",
          top: "100%",
          left: 0,
          marginTop: "8px",
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: "12px",
          boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
          zIndex: 1000,
          minWidth: "320px",
          padding: "16px"
        }}>
          {/* Year Selection */}
          <div style={{ marginBottom: "16px" }}>
            <p style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", margin: "0 0 8px 0" }}>
              YEAR
            </p>
            <div style={{ display: "flex", gap: "8px" }}>
              {years.map(y => (
                <button
                  key={y}
                  onClick={() => handleMonthChange(month, y)}
                  style={{
                    flex: 1,
                    padding: "8px",
                    border: year === y ? "2px solid #3b82f6" : "1px solid #e2e8f0",
                    background: year === y ? "#eff6ff" : "white",
                    color: year === y ? "#3b82f6" : "#64748b",
                    borderRadius: "6px",
                    fontWeight: year === y ? "600" : "500",
                    fontSize: "13px",
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                >
                  {y}
                </button>
              ))}
            </div>
          </div>

          {/* Month Selection Grid */}
          <div>
            <p style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", margin: "0 0 8px 0" }}>
              MONTH
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
              {months.map((m, index) => (
                <button
                  key={index}
                  onClick={() => handleMonthChange(index, year)}
                  style={{
                    padding: "10px",
                    border: month === index && year === year ? "2px solid #3b82f6" : "1px solid #e2e8f0",
                    background: month === index && year === year ? "#eff6ff" : "white",
                    color: month === index && year === year ? "#3b82f6" : "#64748b",
                    borderRadius: "6px",
                    fontWeight: month === index && year === year ? "600" : "500",
                    fontSize: "12px",
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                >
                  {m.substring(0, 3)}
                </button>
              ))}
            </div>
          </div>

          {/* Quick Select Options */}
          <div style={{ marginTop: "16px", paddingTop: "12px", borderTop: "1px solid #e2e8f0" }}>
            <p style={{ color: "#64748b", fontSize: "12px", fontWeight: "600", margin: "0 0 8px 0" }}>
              QUICK SELECT
            </p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <button
                onClick={() => onDateChange(new Date())}
                style={{
                  padding: "6px 12px",
                  background: "#f1f5f9",
                  border: "1px solid #cbd5e1",
                  borderRadius: "4px",
                  fontSize: "12px",
                  cursor: "pointer",
                  fontWeight: "500"
                }}
              >
                This Month
              </button>
              <button
                onClick={() => {
                  const lastMonth = new Date()
                  lastMonth.setMonth(lastMonth.getMonth() - 1)
                  onDateChange(lastMonth)
                }}
                style={{
                  padding: "6px 12px",
                  background: "#f1f5f9",
                  border: "1px solid #cbd5e1",
                  borderRadius: "4px",
                  fontSize: "12px",
                  cursor: "pointer",
                  fontWeight: "500"
                }}
              >
                Last Month
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MonthSelector