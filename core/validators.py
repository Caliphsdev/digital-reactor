"""
validators.py — Shared scientific/data-quality validation rules.

These checks run before database writes in entry screens.
They do not mutate data; they only return issues that the UI can
block or override with a documented QA reason.
"""

from dataclasses import dataclass


@dataclass
class ValidationIssue:
    """Single validation issue emitted by shared validators."""
    severity: str          # "error" | "warning"
    scope: str             # e.g. "zone:aeration", "flow", "cec"
    message: str


def summarize_issues(issues: list[ValidationIssue], max_items: int = 10) -> str:
    """Build a compact, user-facing summary for dialog prompts."""
    if not issues:
        return ""
    lines: list[str] = []
    for issue in issues[:max_items]:
        level = "ERROR" if issue.severity == "error" else "WARN"
        lines.append(f"- [{level}] {issue.message}")
    if len(issues) > max_items:
        lines.append(f"- ... and {len(issues) - max_items} more")
    return "\n".join(lines)


def validate_daily_payload(
    zone_values: dict[str, dict[str, float | None]],
    flow_values: dict[str, float | None],
) -> list[ValidationIssue]:
    """Validate daily zone + flow payload before save."""
    issues: list[ValidationIssue] = []

    q_in = flow_values.get("q_in_mlh")
    q_was = flow_values.get("q_was_mlh")
    q_ps = flow_values.get("q_psludge_mlh")
    ras = flow_values.get("ras_ratio")

    if q_in is None or q_in <= 0:
        issues.append(ValidationIssue("error", "flow", "Influent flow (Q_in) must be greater than 0 mL/h."))
    if q_in is not None and q_was is not None and q_ps is not None and (q_was + q_ps) >= q_in:
        issues.append(ValidationIssue("error", "flow", "Q_WAS + Q_Psludge is greater than or equal to Q_in, which makes Q_eff non-physical."))
    if q_in is not None and not (250.0 <= q_in <= 390.0):
        issues.append(ValidationIssue("warning", "flow", "Influent flow is outside the design envelope (250-390 mL/h around 320 mL/h setpoint)."))
    if ras is not None and not (0.5 <= ras <= 2.0):
        issues.append(ValidationIssue("warning", "flow", "RAS ratio is outside the typical operating range (0.5-2.0)."))

    for zone, values in zone_values.items():
        do = values.get("do_mgl")
        ph = values.get("ph")
        temp = values.get("temperature_c")
        cod = values.get("cod_mgl")
        nh4 = values.get("nh4_mgl")
        mlss = values.get("mlss_mgl")

        scope = f"zone:{zone}"
        if ph is not None and not (6.0 <= ph <= 9.0):
            issues.append(ValidationIssue("warning", scope, f"{zone}: pH is outside expected biological range (6.0-9.0)."))
        if temp is not None and not (15.0 <= temp <= 30.0):
            issues.append(ValidationIssue("warning", scope, f"{zone}: temperature is outside expected range (15-30 C)."))

        if zone == "primary_settling":
            if do is not None and do > 1.5:
                issues.append(ValidationIssue("warning", scope, "Primary settling DO is unusually high (>1.5 mg/L)."))
        elif zone == "aeration":
            if do is not None and not (1.0 <= do <= 4.0):
                issues.append(ValidationIssue("warning", scope, "Aeration DO should usually be within 1.0-4.0 mg/L."))
            if mlss is not None and not (1000.0 <= mlss <= 5000.0):
                issues.append(ValidationIssue("warning", scope, "Aeration MLSS is outside typical operating band (1000-5000 mg/L)."))
        elif zone == "clarifier":
            if mlss is not None and mlss > 1200.0:
                issues.append(ValidationIssue("warning", scope, "Clarifier MLSS is high (>1200 mg/L), possible solids carryover."))
        elif zone == "effluent":
            if cod is not None and cod > 250.0:
                issues.append(ValidationIssue("warning", scope, "Effluent COD exceeds 250 mg/L."))
            if nh4 is not None and nh4 > 50.0:
                issues.append(ValidationIssue("warning", scope, "Effluent NH4 exceeds 50 mg/L."))

    return issues


def validate_cec_payload(
    sampling_values: dict[str, dict[str, float | bool | None]],
) -> list[ValidationIssue]:
    """Validate CEC concentration payload before save."""
    issues: list[ValidationIssue] = []

    def _effective_conc(rec: dict[str, float | bool | None]) -> float | None:
        bdl = bool(rec.get("below_detection"))
        conc = rec.get("concentration")
        dl = rec.get("detection_limit")
        if bdl:
            if dl is None or dl <= 0:
                return None
            return float(dl) / 2.0
        if conc is None or conc <= 0:
            return None
        return float(conc)

    any_present = False
    for sp, rec in sampling_values.items():
        bdl = bool(rec.get("below_detection"))
        dl = rec.get("detection_limit")
        conc = rec.get("concentration")
        if bdl and (dl is None or dl <= 0):
            issues.append(ValidationIssue("error", "cec", f"{sp}: Below-detection is checked but detection limit is missing."))
        if (not bdl) and conc is not None and conc > 0:
            any_present = True
        if bdl and dl is not None and dl > 0:
            any_present = True

    if not any_present:
        issues.append(ValidationIssue("error", "cec", "No usable CEC concentrations were entered for this record."))

    sp1 = _effective_conc(sampling_values.get("SP1_influent", {}))
    sp4 = _effective_conc(sampling_values.get("SP4_effluent", {}))

    if sp1 is None:
        issues.append(ValidationIssue("error", "cec", "SP1 influent concentration is required to compute removal."))
    if sp1 is not None and sp4 is not None and sp4 > sp1:
        issues.append(ValidationIssue("warning", "cec", "SP4 effluent concentration is higher than SP1 influent (negative apparent removal)."))

    return issues
