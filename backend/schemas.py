from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    patient_code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    age: int | None = Field(default=None, ge=0, le=150)


class VisitCreate(BaseModel):
    clinical_notes: str = ""
    visit_date: str | None = None


class ClinicalPlanInput(BaseModel):
    clinician_assessment: str = ""
    medication: str = ""
    wound_care_plan: str = ""
    follow_up_interval: str = ""
    additional_tests: str = ""
    escalation_required: bool = False
