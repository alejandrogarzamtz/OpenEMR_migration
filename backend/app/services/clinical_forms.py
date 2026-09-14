import json
from typing import Any


SOAP_FIELDS = ("subjective", "objective", "assessment", "plan")

# Exact source-column identifiers from OpenEMR's shipped form_ros table. Historical
# spelling is intentionally retained so imported and newly authored data reconcile.
ROS_FIELDS = tuple("""
weight_change weakness fatigue anorexia fever chills night_sweats insomnia irritability heat_or_cold intolerance
change_in_vision glaucoma_history eye_pain irritation redness excessive_tearing double_vision blind_spots photophobia
hearing_loss discharge pain vertigo tinnitus frequent_colds sore_throat sinus_problems post_nasal_drip nosebleed snoring apnea
breast_mass breast_discharge biopsy abnormal_mammogram cough sputum shortness_of_breath wheezing hemoptsyis asthma copd
chest_pain palpitation syncope pnd doe orthopnea peripheal edema legpain_cramping history_murmur arrythmia heart_problem
dysphagia heartburn bloating belching flatulence nausea vomiting hematemesis gastro_pain food_intolerance hepatitis jaundice
hematochezia changed_bowel diarrhea constipation polyuria polydypsia dysuria hematuria frequency urgency incontinence
renal_stones utis hesitancy dribbling stream nocturia erections ejaculations g p ap lc mearche menopause lmp f_frequency
f_flow f_symptoms abnormal_hair_growth f_hirsutism joint_pain swelling m_redness m_warm m_stiffness muscle m_aches fms
arthritis loc seizures stroke tia n_numbness n_weakness paralysis intellectual_decline memory_problems dementia n_headache
s_cancer psoriasis s_acne s_other s_disease p_diagnosis p_medication depression anxiety social_difficulties thyroid_problems
diabetes abnormal_blood anemia fh_blood_problems bleeding_problems allergies frequent_illness hiv hai_status
""".split())

PHYSICAL_EXAM_LINES = {
    "GENWELL": ("GEN", "Appearance"), "EYECP": ("EYE", "Conjunctiva, pupils"),
    "ENTTM": ("ENT", "TMs/EAMs/EE, external nose"), "ENTNASAL": ("ENT", "Nasal mucosa, septum"),
    "ENTORAL": ("ENT", "Oral mucosa and throat"), "ENTNECK": ("ENT", "Neck"), "ENTTHY": ("ENT", "Thyroid"),
    "CVRRR": ("CV", "Rate and rhythm"), "CVNTOH": ("CV", "Thrills or heaves"), "CVCP": ("CV", "Carotid and pedal pulses"),
    "CVNPE": ("CV", "Peripheral edema"), "CHNSD": ("CHEST", "Skin dimpling or breast nodules"),
    "RECTAB": ("RESP", "Breath sounds"), "REEFF": ("RESP", "Respiratory effort"),
    "GIMASS": ("GI", "Masses or tenderness"), "GIOG": ("GI", "Organomegaly"), "GIHERN": ("GI", "Hernia"),
    "GIRECT": ("GI", "Rectal exam"), "GUTEST": ("GU", "Testicular exam"), "GUPROS": ("GU", "Prostate exam"),
    "GUEG": ("GU", "External genitalia, vaginal mucosa and cervix"), "GUAD": ("GU", "Adnexa"),
    "LYAD": ("LYMPH", "Adenopathy"), "MUSTR": ("MUSC", "Strength"), "MUROM": ("MUSC", "Range of motion"),
    "MUSTAB": ("MUSC", "Stability"), "MUINSP": ("MUSC", "Inspection"), "NEUCN2": ("NEURO", "Cranial nerves 2-12"),
    "NEUREF": ("NEURO", "Reflexes"), "NEUSENS": ("NEURO", "Sensory exam"), "PSYOR": ("PSYCH", "Orientation"),
    "PSYAFF": ("PSYCH", "Affect"), "SKRASH": ("SKIN", "Rash or lesions"), "OTHER": ("OTHER", "Other"),
    "TRTLABS": ("TREATMENT", "Labs"), "TRTXRAY": ("TREATMENT", "X-ray"), "TRTRET": ("TREATMENT", "Return visit"),
}

FORM_DEFINITIONS = {
    "soap": {"title": "SOAP note", "kind": "narrative", "fields": [{"key": key, "label": key.title(), "type": "text", "required": False} for key in SOAP_FIELDS]},
    "ros": {"title": "Review of systems", "kind": "review-of-systems", "values": ["positive", "negative", "not-assessed"], "fields": [{"key": key, "label": key.replace("_", " ").title(), "type": "tri-state", "source_key": key} for key in ROS_FIELDS]},
    "physical_exam": {"title": "Physical examination", "kind": "exam-findings", "values": ["normal", "abnormal", "not-examined"], "lines": [{"line_id": key, "system": system, "label": label} for key, (system, label) in PHYSICAL_EXAM_LINES.items()]},
    "clinic_note": {"title": "Clinical note", "kind": "narrative", "fields": [{"key": "note", "label": "Note", "type": "text", "required": True}]},
    "custom": {"title": "Custom form", "kind": "custom-json"},
}


class ClinicalFormValidationError(ValueError):
    pass


def _text(value: Any, field: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ClinicalFormValidationError(f"{field} must be text")
    value = value.strip()
    if required and not value:
        raise ClinicalFormValidationError(f"{field} is required")
    if len(value) > 20_000:
        raise ClinicalFormValidationError(f"{field} exceeds 20000 characters")
    return value


def validate_clinical_form_content(form_type: str, content: dict[str, Any]) -> dict[str, Any]:
    if form_type == "soap":
        unknown = set(content) - set(SOAP_FIELDS)
        if unknown:
            raise ClinicalFormValidationError(f"Unknown SOAP fields: {', '.join(sorted(unknown))}")
        normalized = {key: _text(value, key) for key, value in content.items()}
        if not any(normalized.values()):
            raise ClinicalFormValidationError("SOAP note requires at least one populated section")
        return normalized
    if form_type == "ros":
        unknown = set(content) - set(ROS_FIELDS)
        if unknown:
            raise ClinicalFormValidationError(f"Unknown review-of-systems fields: {', '.join(sorted(unknown))}")
        if not content:
            raise ClinicalFormValidationError("Review of systems requires at least one response")
        allowed = {"positive", "negative", "not-assessed"}
        normalized = {}
        for key, value in content.items():
            if value not in allowed:
                raise ClinicalFormValidationError(f"{key} must be positive, negative, or not-assessed")
            normalized[key] = value
        return normalized
    if form_type == "physical_exam":
        if set(content) != {"findings"} or not isinstance(content.get("findings"), list):
            raise ClinicalFormValidationError("Physical examination content must contain a findings list")
        findings, seen = [], set()
        for index, finding in enumerate(content["findings"]):
            if not isinstance(finding, dict):
                raise ClinicalFormValidationError(f"findings[{index}] must be an object")
            unknown = set(finding) - {"line_id", "status", "diagnosis", "comments"}
            if unknown:
                raise ClinicalFormValidationError(f"Unknown physical-exam fields: {', '.join(sorted(unknown))}")
            line_id = finding.get("line_id")
            if line_id not in PHYSICAL_EXAM_LINES:
                raise ClinicalFormValidationError(f"Unknown physical-exam line: {line_id}")
            if line_id in seen:
                raise ClinicalFormValidationError(f"Duplicate physical-exam line: {line_id}")
            seen.add(line_id)
            status = finding.get("status")
            if status not in {"normal", "abnormal", "not-examined"}:
                raise ClinicalFormValidationError(f"{line_id} has an invalid status")
            findings.append({"line_id": line_id, "status": status, "diagnosis": _text(finding.get("diagnosis", ""), f"{line_id}.diagnosis"), "comments": _text(finding.get("comments", ""), f"{line_id}.comments")})
        if not findings:
            raise ClinicalFormValidationError("Physical examination requires at least one finding")
        return {"findings": findings}
    if form_type == "clinic_note":
        if set(content) != {"note"}:
            raise ClinicalFormValidationError("Clinical note requires only the note field")
        return {"note": _text(content["note"], "note", required=True)}
    if len(json.dumps(content, default=str)) > 1_000_000:
        raise ClinicalFormValidationError("Custom form content exceeds 1 MB")
    return content
