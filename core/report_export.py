"""
report_export.py — Multi-sheet Excel report generator for Digital Reactor.

Pure functions only — no Qt, no database access at call time.
The caller fetches data and passes plain Python objects; this module
writes the workbook and returns the file path.

Sheets produced:
    1. Summary         — experiment metadata + key stats
    2. Daily Readings  — all zone measurements by date
    3. CEC Readings    — concentrations at each sampling point + removal %
    4. Mass Balance    — saved mass balance results
    5. Simulations     — saved what-if scenario runs
"""

from __future__ import annotations

import math
import statistics
from datetime import date as dt_date, datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers,
)
from openpyxl.utils import get_column_letter


# ── Colour palette (matches app theme) ────────────────────────────────────────
_HDR_FILL   = PatternFill("solid", fgColor="2C3E50")   # dark navy
_SUBHDR     = PatternFill("solid", fgColor="2980B9")   # blue
_GOOD_FILL  = PatternFill("solid", fgColor="D5F5E3")   # light green  ≥ 60%
_WARN_FILL  = PatternFill("solid", fgColor="FDEBD0")   # amber  30–60%
_BAD_FILL   = PatternFill("solid", fgColor="FADBD8")   # red   < 30%
_ALT_FILL   = PatternFill("solid", fgColor="F8F9FA")   # light grey alternate row
_WHITE      = PatternFill("solid", fgColor="FFFFFF")

_HDR_FONT   = Font(bold=True, color="ECF0F1", size=11)
_SUBHDR_FNT = Font(bold=True, color="FFFFFF", size=10)
_BOLD       = Font(bold=True)
_SMALL      = Font(size=9)

_THIN = Side(style="thin", color="DDE1E7")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=False)
_WRAP   = Alignment(horizontal="left",   vertical="top",    wrap_text=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _header_row(ws, row: int, values: list[str], fill=None) -> None:
    fill = fill or _HDR_FILL
    font = _HDR_FONT if fill is _HDR_FILL else _SUBHDR_FNT
    for col, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.fill = fill
        cell.font = font
        cell.alignment = _CENTER
        cell.border = _BORDER


def _data_row(ws, row: int, values: list[Any], alt: bool = False) -> None:
    fill = _ALT_FILL if alt else _WHITE
    for col, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.fill = fill
        cell.alignment = _CENTER
        cell.border = _BORDER
        cell.font = _SMALL


def _removal_fill(pct: float | None) -> PatternFill:
    if pct is None:
        return _WHITE
    if pct >= 60:
        return _GOOD_FILL
    if pct >= 30:
        return _WARN_FILL
    return _BAD_FILL


def _auto_width(ws, min_w: int = 8, max_w: int = 40) -> None:
    for col in ws.columns:
        best = min_w
        for cell in col:
            try:
                best = max(best, len(str(cell.value or "")) + 2)
            except Exception:
                pass
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(best, max_w)


def _safe_pct(a, b) -> float | None:
    """(a - b) / a × 100, guarded against None and zero."""
    try:
        if a and a > 0 and b is not None:
            return round((a - b) / a * 100, 2)
    except Exception:
        pass
    return None


def _fmt_date(d) -> str:
    if d is None:
        return ""
    return str(d)[:10]


def _mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    v = [x for x in values if x is not None]
    if not v:
        return None, None
    m = statistics.mean(v)
    s = statistics.stdev(v) if len(v) > 1 else 0.0
    return round(m, 2), round(s, 2)


# ── Sheet 1 — Summary ──────────────────────────────────────────────────────────

def _sheet_summary(wb, exp_data: dict, stats: dict) -> None:
    ws = wb.create_sheet("Summary")
    ws.sheet_view.showGridLines = False

    # Title banner
    ws.merge_cells("A1:E1")
    ws["A1"].value = "Digital Reactor — Experiment Report"
    ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws["A1"].fill = _HDR_FILL
    ws["A1"].alignment = _CENTER
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:E2")
    ws["A2"].value = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws["A2"].font = Font(italic=True, size=9, color="7F8C8D")
    ws["A2"].alignment = _CENTER

    # Experiment metadata
    meta = [
        ("Experiment name",    exp_data.get("name", "—")),
        ("Start date",         _fmt_date(exp_data.get("start_date"))),
        ("End date",           _fmt_date(exp_data.get("end_date")) or "Running"),
        ("CECs spiked",        exp_data.get("cec_spiked") or "—"),
        ("Spike concentration",f"{exp_data.get('spike_conc', '—')} µg/L" if exp_data.get("spike_conc") else "—"),
        ("Description",        exp_data.get("description") or "—"),
    ]
    r = 4
    ws.cell(r, 1, "Experiment Metadata").font = Font(bold=True, size=11)
    r += 1
    _header_row(ws, r, ["Field", "Value"], fill=_SUBHDR)
    r += 1
    for key, val in meta:
        ws.cell(r, 1, key).font = _BOLD
        ws.cell(r, 2, val)
        r += 1

    # Stats summary
    r += 1
    ws.cell(r, 1, "Key Statistics").font = Font(bold=True, size=11)
    r += 1
    _header_row(ws, r, ["Metric", "Mean", "Std Dev", "N"], fill=_SUBHDR)
    r += 1
    for label, key in [
        ("PFAS Overall Removal %",  "pfas"),
        ("COD Removal %",           "cod"),
        ("NH₄ Removal %",           "nh4"),
    ]:
        vals = stats.get(key, [])
        m, s = _mean_sd(vals)
        _data_row(ws, r, [label, f"{m:.1f}" if m is not None else "—",
                          f"{s:.1f}" if s is not None else "—", len(vals)])
        # colour the mean cell
        cell = ws.cell(r, 2)
        if m is not None:
            cell.fill = _removal_fill(m)
        r += 1

    _auto_width(ws)
    ws.column_dimensions["B"].width = 40


# ── Sheet 2 — Daily Readings ───────────────────────────────────────────────────

_DAILY_COLS = [
    "Date", "Zone",
    "DO (mg/L)", "pH", "Temp (°C)", "COD (mg/L)",
    "NH₄-N (mg/L)", "NO₃-N (mg/L)", "SO₄ (mg/L)", "PO₄-P (mg/L)",
    "MLSS (mg/L)", "VSS (mg/L)", "TN (mg/L)", "TP (mg/L)",
    "ORP (mV)", "Turbidity (NTU)", "OUR (mg/L/h)", "Notes",
]


def _sheet_daily(wb, readings: list[dict]) -> None:
    ws = wb.create_sheet("Daily Readings")
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    _header_row(ws, 1, _DAILY_COLS)
    ws.row_dimensions[1].height = 22

    for i, r in enumerate(readings):
        alt = (i % 2 == 1)
        row_vals = [
            _fmt_date(r.get("reading_date")),
            r.get("zone", ""),
            r.get("do_mgl"),    r.get("ph"),        r.get("temperature_c"),
            r.get("cod_mgl"),   r.get("nh4_mgl"),   r.get("no3_mgl"),
            r.get("so4_mgl"),   r.get("po4_mgl"),   r.get("mlss_mgl"),
            r.get("vss_mgl"),   r.get("tn_mgl"),    r.get("tp_mgl"),
            r.get("orp_mv"),    r.get("turbidity_ntu"), r.get("our_mgl_h"),
            r.get("notes", ""),
        ]
        _data_row(ws, i + 2, row_vals, alt=alt)

    _auto_width(ws)


# ── Sheet 3 — CEC Readings ─────────────────────────────────────────────────────

_CEC_COLS = [
    "Date", "CEC Name", "Type", "Method",
    "SP1 Influent (µg/L)", "SP2 Primary Settling (µg/L)",
    "SP3 Clarifier (µg/L)", "SP4 Effluent (µg/L)",
    "Stage 1→2 Removal %", "Stage 2→3 Removal %",
    "Stage 3→4 Removal %", "Overall Removal %",
]


def _sheet_cec(wb, cec_groups: list[dict]) -> None:
    """
    cec_groups: list of dicts, each with keys:
        date, cec_name, cec_type, method,
        sp1, sp2, sp3, sp4   (float or None)
    """
    ws = wb.create_sheet("CEC Readings")
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    _header_row(ws, 1, _CEC_COLS)
    ws.row_dimensions[1].height = 22

    for i, g in enumerate(cec_groups):
        sp1, sp2, sp3, sp4 = g.get("sp1"), g.get("sp2"), g.get("sp3"), g.get("sp4")
        r12 = _safe_pct(sp1, sp2)
        r23 = _safe_pct(sp2, sp3)
        r34 = _safe_pct(sp3, sp4)
        rov = _safe_pct(sp1, sp4)
        alt = (i % 2 == 1)

        row_vals = [
            _fmt_date(g.get("date")),
            g.get("cec_name", ""), g.get("cec_type", ""), g.get("method", ""),
            sp1, sp2, sp3, sp4,
            f"{r12:.1f}%" if r12 is not None else "—",
            f"{r23:.1f}%" if r23 is not None else "—",
            f"{r34:.1f}%" if r34 is not None else "—",
            f"{rov:.1f}%" if rov is not None else "—",
        ]
        row_num = i + 2
        _data_row(ws, row_num, row_vals, alt=alt)

        # Colour-code the overall removal cell
        overall_cell = ws.cell(row_num, 12)
        if rov is not None:
            overall_cell.fill = _removal_fill(rov)
            overall_cell.font = Font(bold=True, size=9)

    _auto_width(ws)


# ── Sheet 4 — Mass Balance ─────────────────────────────────────────────────────

_MB_COLS = [
    "Date", "CEC",
    "Mass In (µg/day)", "Mass Effluent (µg/day)",
    "Mass Sludge (µg/day)", "Mass Transformed (µg/day)",
    "Removal %", "Q_eff (mL/day)",
]


def _sheet_mass_balance(wb, results: list[dict]) -> None:
    ws = wb.create_sheet("Mass Balance")
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    _header_row(ws, 1, _MB_COLS)
    ws.row_dimensions[1].height = 22

    for i, r in enumerate(results):
        pct = r.get("removal_pct")
        alt = (i % 2 == 1)
        _data_row(ws, i + 2, [
            _fmt_date(r.get("calculation_date")),
            r.get("cec_name", ""),
            r.get("mass_in_mgday"),
            r.get("mass_eff_mgday"),
            r.get("mass_sludge_mgday"),
            r.get("mass_transformed"),
            f"{pct:.1f}%" if pct is not None else "—",
            r.get("q_eff_mlday"),
        ], alt=alt)
        pct_cell = ws.cell(i + 2, 7)
        if pct is not None:
            pct_cell.fill = _removal_fill(pct)
            pct_cell.font = Font(bold=True, size=9)

    _auto_width(ws)


# ── Sheet 5 — Simulations ─────────────────────────────────────────────────────

_SIM_COLS = [
    "Date/Time", "Model",
    "Flow (mL/h)", "DO (mg/L)", "SRT (d)", "RAS ratio",
    "Temp (°C)", "pH", "Inf COD (mg/L)", "Inf NH₄ (mg/L)",
    "Inf PFAS (µg/L)", "PFAS type",
    "Pred COD %", "Pred NH₄ %", "Pred TP %", "Pred PFAS %",
]


def _sheet_simulations(wb, runs: list[dict]) -> None:
    ws = wb.create_sheet("Simulations")
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    _header_row(ws, 1, _SIM_COLS)
    ws.row_dimensions[1].height = 22

    for i, r in enumerate(runs):
        alt = (i % 2 == 1)
        _data_row(ws, i + 2, [
            str(r.get("run_date", ""))[:16],
            r.get("model_type", ""),
            r.get("flow_rate_mlh"),   r.get("do_mgl"),
            r.get("srt_days"),        r.get("ras_ratio"),
            r.get("temp_c"),          r.get("ph"),
            r.get("inf_cod"),         r.get("inf_nh4"),
            r.get("inf_pfas"),        r.get("pfas_type", ""),
            f"{r['pred_cod_removal']:.1f}%"  if r.get("pred_cod_removal")  is not None else "—",
            f"{r['pred_nh4_removal']:.1f}%"  if r.get("pred_nh4_removal")  is not None else "—",
            f"{r['pred_tp_removal']:.1f}%"   if r.get("pred_tp_removal")   is not None else "—",
            f"{r['pred_pfas_removal']:.1f}%" if r.get("pred_pfas_removal") is not None else "—",
        ], alt=alt)

    _auto_width(ws)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_experiment_report(
    filepath: str,
    exp_data: dict,
    daily_readings: list[dict],
    cec_groups: list[dict],
    mass_balance_results: list[dict],
    simulation_runs: list[dict],
) -> str:
    """
    Write a multi-sheet Excel workbook and return the file path.

    Args:
        filepath:             Absolute path for the .xlsx file.
        exp_data:             Experiment metadata dict (from Experiment ORM row).
        daily_readings:       List of dicts from DailyReading rows.
        cec_groups:           List of dicts — one per (date, cec_name) pair with
                              sp1/sp2/sp3/sp4 concentration values.
        mass_balance_results: List of dicts from MassBalanceResult rows.
        simulation_runs:      List of dicts from SimulationRun rows.

    Returns:
        The filepath that was written.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)   # remove default blank sheet

    # Compute removal stats from CEC groups for the summary sheet
    pfas_removals = [_safe_pct(g["sp1"], g["sp4"]) for g in cec_groups if g["sp1"]]
    cod_removals  = [r["removal_pct"] for r in mass_balance_results if r.get("removal_pct") is not None]

    stats = {
        "pfas": [x for x in pfas_removals if x is not None],
        "cod":  cod_removals,
        "nh4":  [],   # not yet tracked in mass balance rows
    }

    _sheet_summary(wb, exp_data, stats)
    _sheet_daily(wb, daily_readings)
    _sheet_cec(wb, cec_groups)
    _sheet_mass_balance(wb, mass_balance_results)
    _sheet_simulations(wb, simulation_runs)

    wb.save(filepath)
    return filepath
