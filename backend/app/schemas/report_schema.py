from pydantic import BaseModel

class ReportRequest(BaseModel):
    plant_id: int
    report_type: str
    year: int
    month: int | None = None
    quarter: int | None = None