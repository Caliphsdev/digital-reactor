"""
plants_screen.py — Real-Plant Scientific Twin screen.

V1 includes only three South African plants:
  * Daspoort WWTW
  * Zeekoegat WWTW
  * Phola WWTP

The screen is intentionally labelled as a Scientific Twin: process-realistic
and mass-balance based, but not a live operational replica until field data is
connected and calibration is performed.
"""

from __future__ import annotations

import math

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QDoubleSpinBox, QComboBox, QScrollArea,
    QSizePolicy, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import QFont, QColor, QBrush, QPainter, QPen, QPainterPath, QPolygonF

from core.database import get_session
from core.models import Plant, PlantMonitoringReading
from core.plant_calibration import (
    CALIBRATION_TARGETS,
    calibrate_plant,
    get_calibration_factors,
    get_calibration_summary,
    import_monitoring_file,
)
from simulation.plant_model import (
    BNR_MODES, PlantTwinInputs, PlantTwinOutputs, run_plant_twin,
)
from simulation.generic_model import PFAS_COMPOUND_LIST, PFAS_COMPOUND_CHAIN_TYPE


C_HDR = "#2c3e50"
C_BG = "#f5f6fa"
C_CARD = "#ffffff"
C_BORDER = "#dde1e7"
C_TEXT = "#2c3e50"
C_MUTED = "#636e72"


def _unit_order(unit) -> int:
    return int(getattr(unit, "unit_order", getattr(unit, "order", 0)) or 0)


def _point_order(point) -> int:
    return int(getattr(point, "point_order", getattr(point, "order", 0)) or 0)


def _plant_attr(plant, key: str, fallback=""):
    if isinstance(plant, dict):
        return plant.get(key, fallback)
    return getattr(plant, key, fallback)


def _item(text: str, align=Qt.AlignCenter) -> QTableWidgetItem:
    cell = QTableWidgetItem(text)
    cell.setTextAlignment(align)
    cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return cell


def _default(value, fallback: float = 0.0) -> float:
    return float(value) if value is not None else fallback


class PlantImportWorker(QThread):
    """Background worker for potentially large CSV/Excel monitoring imports."""
    result_ready = Signal(dict)

    def __init__(self, plant_slug: str, path: str, parent=None):
        super().__init__(parent)
        self.plant_slug = plant_slug
        self.path = path

    def run(self) -> None:
        try:
            with get_session() as session:
                result = import_monitoring_file(session, self.plant_slug, self.path)
            self.result_ready.emit({"status": "ok", "result": result})
        except Exception as exc:
            self.result_ready.emit({"status": "error", "message": str(exc)})


class PlantCalibrationWorker(QThread):
    """Background worker for recalculating Daspoort calibration coefficients."""
    result_ready = Signal(dict)

    def __init__(self, plant_slug: str, parent=None):
        super().__init__(parent)
        self.plant_slug = plant_slug

    def run(self) -> None:
        try:
            with get_session() as session:
                result = calibrate_plant(session, self.plant_slug)
            self.result_ready.emit({"status": "ok", "result": result})
        except Exception as exc:
            self.result_ready.emit({"status": "error", "message": str(exc)})


class PlantProcessDiagram(QWidget):
    """Read-only treatment-train visual generated from plant profile data."""

    CATEGORY_STYLES = {
        "preliminary": ("Preliminary", "#eaf2f8", "#2471a3"),
        "primary": ("Primary", "#f4ecf7", "#8e44ad"),
        "anaerobic": ("Anaerobic", "#fdf2e9", "#ca6f1e"),
        "anoxic": ("Anoxic", "#e8f4fd", "#2874a6"),
        "aerobic": ("Aerobic", "#e9f7ef", "#1e8449"),
        "clarification": ("Clarification", "#f8f9fa", "#7f8c8d"),
        "tertiary": ("Tertiary", "#edf7f2", "#138d75"),
        "disinfection": ("Disinfection", "#fff7e6", "#d68910"),
        "pond": ("Pond/wetland", "#e8f8f5", "#148f77"),
        "biofilm": ("Biofilm", "#eef4ff", "#2e86de"),
        "sludge": ("Sludge", "#fdecea", "#c0392b"),
        "other": ("Process", "#f4f6f7", "#566573"),
    }

    TYPE_TO_CATEGORY = {
        "screening": "preliminary",
        "screening_grit": "preliminary",
        "grit": "preliminary",
        "balancing": "preliminary",
        "primary_settling": "primary",
        "anaerobic": "anaerobic",
        "anoxic": "anoxic",
        "aerobic": "aerobic",
        "secondary_clarifier": "clarification",
        "humus_tank": "clarification",
        "tertiary_filtration": "tertiary",
        "disinfection": "disinfection",
        "anaerobic_pond": "pond",
        "reed_bed": "pond",
        "trickling_filter": "biofilm",
        "sludge_handling": "sludge",
        "sludge_drying": "sludge",
    }

    PLANT_NOTES = {
        "daspoort": "Research layer: heritage trickling filters and reported anammox context are shown for scientific interpretation, not live control.",
        "zeekoegat": "Mode-ready BNR profile: A2O/Bardenpho, UCT, Modified UCT, and Johannesburg configurations are represented in the model controls.",
        "phola": "PETRO-style path: pond retention, fixed-film treatment, humus settling, disinfection, reed-bed polishing, and solids drying.",
    }

    def __init__(self, plant, units: list, sampling_points: list, parent=None):
        super().__init__(parent)
        self.plant = plant
        self.units = sorted(units, key=_unit_order)
        self.sampling_points = sorted(sampling_points, key=_point_order)
        self.plant_slug = str(_plant_attr(plant, "slug", "") or "")
        self.plant_name = str(_plant_attr(plant, "name", "Plant") or "Plant")
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def sizeHint(self) -> QSize:
        return QSize(920, 340)

    def resizeEvent(self, event) -> None:
        metrics = self._layout_for_width(max(320, event.size().width()))
        if self.minimumHeight() != metrics["required_height"]:
            self.setMinimumHeight(metrics["required_height"])
        super().resizeEvent(event)

    def ordered_unit_names(self) -> list[str]:
        return [getattr(unit, "name", "") for unit in self.units]

    def ordered_sampling_codes(self) -> list[str]:
        return [getattr(point, "code", "") for point in self.sampling_points]

    @classmethod
    def category_for_unit(cls, unit_type: str) -> str:
        return cls.TYPE_TO_CATEGORY.get(unit_type, "other")

    @classmethod
    def category_label_for_unit(cls, unit_type: str) -> str:
        category = cls.category_for_unit(unit_type)
        return cls.CATEGORY_STYLES[category][0]

    def _layout_for_width(self, width: int) -> dict:
        usable = max(280, width - 32)
        gap = 18
        min_card = 138
        max_card = 178
        columns = max(1, min(len(self.units) or 1, int((usable + gap) / (min_card + gap))))
        card_w = min(max_card, max(min_card, (usable - gap * (columns - 1)) / columns))
        card_h = 78
        row_gap = 76
        rows = max(1, (len(self.units) + columns - 1) // columns)
        top = 72
        categories = []
        for unit in self.units:
            category = self.category_for_unit(getattr(unit, "unit_type", "other") or "other")
            if category not in categories:
                categories.append(category)
        legend_lines = 1
        legend_x = 0
        for category in categories[:8]:
            label = self.CATEGORY_STYLES[category][0]
            chip_w = max(82, len(label) * 6 + 24) + 8
            if legend_x and legend_x + chip_w > usable:
                legend_lines += 1
                legend_x = 0
            legend_x += chip_w
        note_height = 62 if self.plant_slug in self.PLANT_NOTES else 0
        required = int(top + rows * card_h + (rows - 1) * row_gap + 48 + legend_lines * 24 + note_height + 24)
        return {
            "columns": columns,
            "card_w": card_w,
            "card_h": card_h,
            "gap": gap,
            "row_gap": row_gap,
            "top": top,
            "required_height": max(300, required),
        }

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        rect = self.rect().adjusted(16, 14, -16, -14)
        metrics = self._layout_for_width(self.width())
        self._draw_title(painter, rect)

        unit_rects = self._draw_units(painter, rect, metrics)
        self._draw_arrows(painter, unit_rects)
        self._draw_sampling_points(painter, unit_rects)
        self._draw_legend_and_note(painter, rect, unit_rects, metrics)

    def _draw_title(self, painter: QPainter, rect) -> None:
        painter.setPen(QColor(C_TEXT))
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), 22), Qt.AlignLeft | Qt.AlignVCenter, "Visual Process Screen")

        painter.setPen(QColor(C_MUTED))
        sub = QFont()
        sub.setPointSize(8)
        painter.setFont(sub)
        process = str(_plant_attr(self.plant, "process_family", "") or "")
        painter.drawText(
            QRectF(rect.left(), rect.top() + 24, rect.width(), 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{self.plant_name} · {process}",
        )

    def _draw_units(self, painter: QPainter, rect, metrics: dict) -> dict[int, QRectF]:
        unit_rects = {}
        columns = metrics["columns"]
        card_w = metrics["card_w"]
        card_h = metrics["card_h"]
        gap = metrics["gap"]
        row_gap = metrics["row_gap"]
        top = rect.top() + metrics["top"]

        for index, unit in enumerate(self.units):
            row = index // columns
            col = index % columns
            x = rect.left() + col * (card_w + gap)
            y = top + row * (card_h + row_gap)
            box = QRectF(x, y, card_w, card_h)
            unit_rects[_unit_order(unit)] = box
            self._draw_unit_box(painter, unit, box, index + 1)
        return unit_rects

    def _draw_unit_box(self, painter: QPainter, unit, box: QRectF, sequence: int) -> None:
        unit_type = getattr(unit, "unit_type", "other") or "other"
        category = self.category_for_unit(unit_type)
        label, fill, border = self.CATEGORY_STYLES[category]

        painter.setPen(QPen(QColor(border), 1.4))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(box, 7, 7)

        number_rect = QRectF(box.left() + 8, box.top() + 8, 24, 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(border))
        painter.drawRoundedRect(number_rect, 5, 5)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(number_rect, Qt.AlignCenter, str(sequence))

        painter.setPen(QColor(border))
        tag_font = QFont()
        tag_font.setPointSize(7)
        tag_font.setBold(True)
        painter.setFont(tag_font)
        painter.drawText(QRectF(box.left() + 38, box.top() + 8, box.width() - 46, 14), Qt.AlignLeft | Qt.AlignVCenter, label)

        painter.setPen(QColor(C_TEXT))
        name_font = QFont()
        name_font.setPointSize(8)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.drawText(
            QRectF(box.left() + 8, box.top() + 28, box.width() - 16, 38),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            getattr(unit, "name", ""),
        )

    def _draw_arrows(self, painter: QPainter, unit_rects: dict[int, QRectF]) -> None:
        if len(self.units) < 2:
            return
        pen = QPen(QColor("#85929e"), 1.7)
        painter.setPen(pen)
        painter.setBrush(QColor("#85929e"))

        for current, nxt in zip(self.units, self.units[1:]):
            a = unit_rects[_unit_order(current)]
            b = unit_rects[_unit_order(nxt)]
            if abs(a.center().y() - b.center().y()) < 2:
                start = QPointF(a.right() + 2, a.center().y())
                end = QPointF(b.left() - 2, b.center().y())
                painter.drawLine(start, end)
                self._draw_arrow_head(painter, end, "right")
            else:
                mid_y = a.bottom() + 26
                path = QPainterPath(QPointF(a.center().x(), a.bottom() + 2))
                path.lineTo(QPointF(a.center().x(), mid_y))
                path.lineTo(QPointF(b.center().x(), mid_y))
                path.lineTo(QPointF(b.center().x(), b.top() - 2))
                painter.drawPath(path)
                self._draw_arrow_head(painter, QPointF(b.center().x(), b.top() - 2), "down")

    def _draw_arrow_head(self, painter: QPainter, point: QPointF, direction: str) -> None:
        if direction == "right":
            polygon = [
                QPointF(point.x(), point.y()),
                QPointF(point.x() - 7, point.y() - 4),
                QPointF(point.x() - 7, point.y() + 4),
            ]
        else:
            polygon = [
                QPointF(point.x(), point.y()),
                QPointF(point.x() - 4, point.y() - 7),
                QPointF(point.x() + 4, point.y() - 7),
            ]
        painter.drawPolygon(polygon)

    def _draw_sampling_points(self, painter: QPainter, unit_rects: dict[int, QRectF]) -> None:
        offsets: dict[int, int] = {}
        for point in self.sampling_points:
            after_order = int(getattr(point, "after_unit_order", 0) or 0)
            anchor = unit_rects.get(after_order)
            if anchor is None:
                continue
            offset = offsets.get(after_order, 0)
            offsets[after_order] = offset + 1
            code = str(getattr(point, "code", "SP")).split("_")[0]
            name = str(getattr(point, "name", ""))
            badge_w = min(138, max(92, anchor.width() - 14))
            badge = QRectF(
                anchor.center().x() - badge_w / 2,
                anchor.bottom() + 10 + offset * 28,
                badge_w,
                23,
            )
            painter.setPen(QPen(QColor("#566573"), 1))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(badge, 11, 11)
            painter.setPen(QColor("#2c3e50"))
            font = QFont()
            font.setPointSize(7)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(badge.adjusted(6, 0, -6, 0), Qt.AlignCenter, f"{code} · {name}")

    def _draw_legend_and_note(self, painter: QPainter, rect, unit_rects: dict[int, QRectF], metrics: dict) -> None:
        if unit_rects:
            bottom = max(box.bottom() for box in unit_rects.values()) + 48
        else:
            bottom = rect.top() + metrics["top"] + 90

        categories = []
        seen = set()
        for unit in self.units:
            category = self.category_for_unit(getattr(unit, "unit_type", "other") or "other")
            if category not in seen:
                seen.add(category)
                categories.append(category)

        x = rect.left()
        y = bottom
        font = QFont()
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)
        for category in categories[:8]:
            label, fill, border = self.CATEGORY_STYLES[category]
            chip_w = max(82, len(label) * 6 + 24)
            if x + chip_w > rect.right():
                x = rect.left()
                y += 24
            chip = QRectF(x, y, chip_w, 18)
            painter.setPen(QPen(QColor(border), 1))
            painter.setBrush(QColor(fill))
            painter.drawRoundedRect(chip, 8, 8)
            painter.setPen(QColor(border))
            painter.drawText(chip, Qt.AlignCenter, label)
            x += chip_w + 8

        note = self.PLANT_NOTES.get(self.plant_slug)
        if note:
            note_y = y + 30
            note_rect = QRectF(rect.left(), note_y, rect.width(), 42)
            painter.setPen(QPen(QColor("#d6dbdf"), 1))
            painter.setBrush(QColor("#f8f9fa"))
            painter.drawRoundedRect(note_rect, 6, 6)
            painter.setPen(QColor(C_TEXT))
            note_font = QFont()
            note_font.setPointSize(8)
            painter.setFont(note_font)
            painter.drawText(note_rect.adjusted(10, 5, -10, -5), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, note)


class PlantProcessOverview(QWidget):
    """Large animated plant process overview with clear scientific lanes."""

    CATEGORY_STYLES = PlantProcessDiagram.CATEGORY_STYLES
    TYPE_TO_CATEGORY = PlantProcessDiagram.TYPE_TO_CATEGORY
    PLANT_NOTES = {
        "daspoort": (
            "Daspoort note: heritage trickling filters/anammox are drawn as dashed "
            "research context, not as the normal mainline BNR hydraulic path."
        ),
        "zeekoegat": (
            "Zeekoegat note: BNR mode changes the scientific assumption set; the "
            "visual mode badge follows the current model control."
        ),
        "phola": (
            "Phola note: pond retention, fixed-film treatment, humus settling, "
            "reed-bed polishing, and sludge drying are shown as distinct process paths."
        ),
    }
    TIMER_MS = 66
    FLOW_SPEED = 0.018

    def __init__(self, plant, units: list, sampling_points: list, parent=None):
        super().__init__(parent)
        self.plant = plant
        self.units = sorted(units, key=_unit_order)
        self.sampling_points = sorted(sampling_points, key=_point_order)
        self.plant_slug = str(_plant_attr(plant, "slug", "") or "")
        self.plant_name = str(_plant_attr(plant, "name", "Plant") or "Plant")
        self.process_family = str(_plant_attr(plant, "process_family", "") or "")
        self._inputs: PlantTwinInputs | None = None
        self._outputs: PlantTwinOutputs | None = None
        self._bnr_mode = "A2O / 3-stage Bardenpho"
        self._flow_phase = 0.0
        self._geo: dict | None = None

        self.setMinimumHeight(560)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.TIMER_MS)

    def sizeHint(self) -> QSize:
        return QSize(1020, 600)

    def ordered_unit_names(self) -> list[str]:
        return [getattr(unit, "name", "") for unit in self.units]

    def ordered_sampling_codes(self) -> list[str]:
        return [getattr(point, "code", "") for point in self.sampling_points]

    @classmethod
    def category_for_unit(cls, unit_type: str) -> str:
        return cls.TYPE_TO_CATEGORY.get(unit_type, "other")

    @classmethod
    def category_label_for_unit(cls, unit_type: str) -> str:
        category = cls.category_for_unit(unit_type)
        return cls.CATEGORY_STYLES[category][0]

    def set_bnr_mode(self, mode: str) -> None:
        self._bnr_mode = mode or self._bnr_mode
        self.update()

    def set_results(self, inputs: PlantTwinInputs, outputs: PlantTwinOutputs) -> None:
        self._inputs = inputs
        self._outputs = outputs
        self._bnr_mode = inputs.bnr_mode
        self.update()

    def animation_active(self) -> bool:
        return self._timer.isActive()

    def pfas_fate_summary(self) -> str:
        if not self._outputs:
            return "PFAS fate: waiting for model run. Transfer only, not destruction."
        return (
            f"PFAS fate: effluent {self._outputs.pfas_effluent_g_day:.3f} g/d · "
            f"sludge/solids {self._outputs.pfas_sludge_g_day:.3f} g/d · "
            f"unresolved {self._outputs.pfas_unresolved_g_day:.3f} g/d. "
            "Transfer only, not destruction."
        )

    def resizeEvent(self, event) -> None:
        self._geo = None
        metrics = self._layout_for_width(max(340, event.size().width()))
        if self.minimumHeight() != metrics["required_height"]:
            self.setMinimumHeight(metrics["required_height"])
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(self.TIMER_MS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        self._flow_phase = (self._flow_phase + self.FLOW_SPEED) % 1.0
        self.update()

    def _main_units(self) -> list:
        main = []
        for unit in self.units:
            unit_type = getattr(unit, "unit_type", "") or ""
            if self._is_sludge_unit(unit):
                continue
            if self._is_context_unit(unit):
                continue
            main.append(unit)
        return main

    def _sludge_units(self) -> list:
        return [unit for unit in self.units if self._is_sludge_unit(unit)]

    def _context_units(self) -> list:
        return [unit for unit in self.units if self._is_context_unit(unit)]

    def _is_sludge_unit(self, unit) -> bool:
        return self.category_for_unit(getattr(unit, "unit_type", "") or "") == "sludge"

    def _is_context_unit(self, unit) -> bool:
        return self.plant_slug == "daspoort" and getattr(unit, "unit_type", "") == "trickling_filter"

    def _layout_for_width(self, width: int) -> dict:
        narrow = width < 760
        main = self._main_units()
        sludge = self._sludge_units()
        context = self._context_units()
        if narrow:
            card_w = max(230, min(360, width - 96))
            card_h = 74
            step_y = 104
            required = 118 + len(main) * step_y + (len(sludge) + len(context)) * 92 + 190
            return {
                "mode": "narrow",
                "layout_type": "phola_vertical" if self.plant_slug == "phola" else "bnr_vertical",
                "card_w": card_w,
                "card_h": card_h,
                "required_height": max(620, int(required)),
                "columns": 1,
            }

        if self.plant_slug == "phola":
            required = 960
            layout_type = "pond_biofilm_wetland"
        else:
            required = 960 if self.plant_slug == "daspoort" else 930
            layout_type = "bnr_lanes"
        return {
            "mode": "wide",
            "layout_type": layout_type,
            "card_w": 148,
            "card_h": 84,
            "required_height": required,
            "columns": 6,
        }

    def _build_geometry(self, width: int, height: int) -> dict:
        metrics = self._layout_for_width(width)
        rect = self.rect().adjusted(18, 16, -18, -16)
        if metrics["mode"] == "narrow":
            return self._build_narrow_geometry(rect, metrics)
        if self.plant_slug == "phola":
            return self._build_phola_geometry(rect, metrics)
        return self._build_bnr_geometry(rect, metrics)

    def _build_narrow_geometry(self, rect, metrics: dict) -> dict:
        unit_rects = {}
        lanes = []
        x = rect.center().x() - metrics["card_w"] / 2
        y = rect.top() + 104
        for unit in self._main_units():
            box = QRectF(x, y, metrics["card_w"], metrics["card_h"])
            unit_rects[_unit_order(unit)] = box
            lanes.append((self.category_label_for_unit(getattr(unit, "unit_type", "")), QRectF(rect.left(), y - 10, rect.width(), metrics["card_h"] + 20)))
            y += 104
        for unit in self._sludge_units() + self._context_units():
            box = QRectF(x, y, metrics["card_w"], metrics["card_h"])
            unit_rects[_unit_order(unit)] = box
            y += 92
        return {"metrics": metrics, "rect": rect, "unit_rects": unit_rects, "lanes": lanes}

    def _build_bnr_geometry(self, rect, metrics: dict) -> dict:
        unit_rects = {}
        lane_h = 122
        lanes = [
            ("Preliminary / primary", QRectF(rect.left(), rect.top() + 112, rect.width(), lane_h)),
            ("Biological BNR zones", QRectF(rect.left(), rect.top() + 274, rect.width(), lane_h)),
            ("Clarification / polishing", QRectF(rect.left(), rect.top() + 436, rect.width(), lane_h)),
            ("Sludge + PFAS solids path", QRectF(rect.left(), rect.top() + 598, rect.width(), lane_h)),
        ]
        if self.plant_slug == "daspoort":
            lanes.append(("Research context only", QRectF(rect.left(), rect.top() + 692, rect.width(), 72)))

        lane_groups = {
            "pre": [u for u in self._main_units() if self.category_for_unit(getattr(u, "unit_type", "")) in {"preliminary", "primary"}],
            "bio": [u for u in self._main_units() if self.category_for_unit(getattr(u, "unit_type", "")) in {"anaerobic", "anoxic", "aerobic"}],
            "polish": [u for u in self._main_units() if self.category_for_unit(getattr(u, "unit_type", "")) in {"clarification", "tertiary", "disinfection"}],
            "sludge": self._sludge_units(),
            "context": self._context_units(),
        }
        lane_rects = {
            "pre": lanes[0][1],
            "bio": lanes[1][1],
            "polish": lanes[2][1],
            "sludge": lanes[3][1],
            "context": lanes[4][1] if len(lanes) > 4 else lanes[3][1],
        }

        main_units = self._main_units()
        process_rect = rect.adjusted(24, 0, -24, 0)
        card_w = self._ordered_card_width(process_rect.width(), len(main_units))
        card_h = metrics["card_h"]
        x_by_order = self._ordered_x_positions(main_units, process_rect, card_w)

        for key in ("pre", "bio", "polish"):
            lane = lane_rects[key]
            y = self._unit_y_in_lane(lane, card_h)
            for unit in lane_groups[key]:
                x = x_by_order.get(_unit_order(unit), process_rect.left())
                unit_rects[_unit_order(unit)] = QRectF(x, y, card_w, card_h)

        clarifier = next((u for u in main_units if getattr(u, "unit_type", "") == "secondary_clarifier"), None)
        sludge_w = min(220, max(card_w + 28, 176))
        sludge_h = card_h
        sludge_lane = lane_rects["sludge"]
        sludge_anchor = unit_rects.get(_unit_order(clarifier)) if clarifier else None
        for index, unit in enumerate(lane_groups["sludge"]):
            center_x = sludge_anchor.center().x() if sludge_anchor else process_rect.center().x()
            x = self._clamp(center_x - sludge_w / 2 + index * (sludge_w + 18), process_rect.left(), process_rect.right() - sludge_w)
            y = self._unit_y_in_lane(sludge_lane, sludge_h)
            unit_rects[_unit_order(unit)] = QRectF(x, y, sludge_w, sludge_h)

        context_lane = lane_rects["context"]
        source = next((u for u in main_units if getattr(u, "unit_type", "") == "primary_settling"), None)
        source_box = unit_rects.get(_unit_order(source)) if source else None
        context_w = min(224, max(card_w + 36, 184))
        context_h = 58 if self.plant_slug == "daspoort" else card_h
        for index, unit in enumerate(lane_groups["context"]):
            center_x = source_box.center().x() if source_box else process_rect.center().x()
            context_min_x = process_rect.left()
            if self._is_context_unit(unit):
                context_min_x = max(context_min_x, context_lane.left() + 220)
            x = self._clamp(
                center_x - context_w / 2 + 64 + index * (context_w + 18),
                context_min_x,
                process_rect.right() - context_w,
            )
            y = self._unit_y_in_lane(context_lane, context_h)
            unit_rects[_unit_order(unit)] = QRectF(x, y, context_w, context_h)
        return {"metrics": metrics, "rect": rect, "unit_rects": unit_rects, "lanes": lanes}

    def _build_phola_geometry(self, rect, metrics: dict) -> dict:
        unit_rects = {}
        lane_h = 122
        lanes = [
            ("Preliminary treatment", QRectF(rect.left(), rect.top() + 112, rect.width(), lane_h)),
            ("Anaerobic pond retention", QRectF(rect.left(), rect.top() + 274, rect.width(), lane_h)),
            ("Biofilm + humus settling", QRectF(rect.left(), rect.top() + 436, rect.width(), lane_h)),
            ("Disinfection / reed-bed polishing", QRectF(rect.left(), rect.top() + 598, rect.width(), lane_h)),
            ("Sludge drying path", QRectF(rect.left(), rect.top() + 692, rect.width(), 72)),
        ]
        lane_groups = {
            "pre": [u for u in self._main_units() if self.category_for_unit(getattr(u, "unit_type", "")) == "preliminary"],
            "pond": [u for u in self._main_units() if getattr(u, "unit_type", "") == "anaerobic_pond"],
            "biofilm": [u for u in self._main_units() if getattr(u, "unit_type", "") in {"trickling_filter", "humus_tank"}],
            "polish": [u for u in self._main_units() if getattr(u, "unit_type", "") in {"disinfection", "reed_bed"}],
            "sludge": self._sludge_units(),
        }
        lane_rects = {"pre": lanes[0][1], "pond": lanes[1][1], "biofilm": lanes[2][1], "polish": lanes[3][1], "sludge": lanes[4][1]}

        main_units = self._main_units()
        process_rect = rect.adjusted(24, 0, -24, 0)
        card_w = self._ordered_card_width(process_rect.width(), len(main_units))
        card_h = metrics["card_h"]
        x_by_order = self._ordered_x_positions(main_units, process_rect, card_w)
        for key in ("pre", "pond", "biofilm", "polish"):
            lane = lane_rects[key]
            y = self._unit_y_in_lane(lane, card_h)
            for unit in lane_groups[key]:
                x = x_by_order.get(_unit_order(unit), process_rect.left())
                unit_rects[_unit_order(unit)] = QRectF(x, y, card_w, card_h)

        pond = next((u for u in main_units if getattr(u, "unit_type", "") == "anaerobic_pond"), None)
        pond_box = unit_rects.get(_unit_order(pond)) if pond else None
        sludge_w = min(210, max(card_w + 24, 168))
        sludge_h = 58
        for unit in lane_groups["sludge"]:
            center_x = pond_box.center().x() if pond_box else process_rect.center().x()
            x = self._clamp(center_x - sludge_w / 2, process_rect.left(), process_rect.right() - sludge_w)
            y = self._unit_y_in_lane(lane_rects["sludge"], sludge_h)
            unit_rects[_unit_order(unit)] = QRectF(x, y, sludge_w, sludge_h)
        return {"metrics": metrics, "rect": rect, "unit_rects": unit_rects, "lanes": lanes}

    def _ordered_card_width(self, process_width: float, count: int) -> float:
        if count <= 1:
            return min(166, max(128, process_width))
        minimum_gap = 14
        width = (process_width - minimum_gap * (count - 1)) / count
        return min(166, max(108, width))

    def _ordered_x_positions(self, units: list, process_rect: QRectF, card_w: float) -> dict[int, float]:
        if not units:
            return {}
        if len(units) == 1:
            return {_unit_order(units[0]): process_rect.center().x() - card_w / 2}
        step = (process_rect.width() - card_w) / (len(units) - 1)
        positions = {}
        for index, unit in enumerate(units):
            x = process_rect.left() + index * step
            positions[_unit_order(unit)] = self._clamp(x, process_rect.left(), process_rect.right() - card_w)
        return positions

    def _unit_y_in_lane(self, lane: QRectF, card_h: float) -> float:
        if lane.height() >= card_h + 38:
            return lane.top() + 32
        return lane.center().y() - card_h / 2

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        if high < low:
            return low
        return max(low, min(high, value))

    def _place_units_in_lane(self, unit_rects: dict, units: list, lane: QRectF, card_w: float, card_h: float) -> None:
        if not units:
            return
        count = len(units)
        gap = min(46, max(22, (lane.width() - count * card_w) / max(1, count + 1)))
        total = count * card_w + (count - 1) * gap
        x = lane.left() + max(20, (lane.width() - total) / 2)
        y = lane.center().y() - card_h / 2
        for unit in units:
            unit_rects[_unit_order(unit)] = QRectF(x, y, card_w, card_h)
            x += card_w + gap

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), QColor("#f4f7f9"))
        self._draw_background_grid(painter)

        self._geo = self._build_geometry(self.width(), self.height())
        self._draw_header(painter, self._geo)
        self._draw_lanes(painter, self._geo)
        paths = self._draw_main_flow(painter, self._geo)
        sludge_paths = self._draw_secondary_paths(painter, self._geo)
        self._draw_particles(painter, paths, QColor("#3498db"), radius=4.2)
        self._draw_particles(painter, sludge_paths, QColor("#c0392b"), radius=3.8, offset=0.35)
        self._draw_units(painter, self._geo)
        self._draw_sampling_points(painter, self._geo)
        self._draw_overlays(painter, self._geo)
        self._draw_note(painter, self._geo)
        painter.end()

    def _draw_background_grid(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(220, 228, 234, 150), 0.5))
        for x in range(0, self.width(), 52):
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        for y in range(0, self.height(), 52):
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))

    def _draw_header(self, painter: QPainter, geo: dict) -> None:
        rect = geo["rect"]
        painter.setPen(QColor(C_TEXT))
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), rect.top(), rect.width() * 0.62, 28), Qt.AlignLeft | Qt.AlignVCenter, self.plant_name)

        sub_font = QFont()
        sub_font.setPointSize(9)
        painter.setFont(sub_font)
        painter.setPen(QColor(C_MUTED))
        painter.drawText(
            QRectF(rect.left(), rect.top() + 30, rect.width() * 0.72, 34),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            f"{self.process_family} · animated Scientific Twin overview",
        )

        badge = QRectF(rect.right() - 290, rect.top(), 290, 30)
        painter.setPen(QPen(QColor("#8e44ad"), 1))
        painter.setBrush(QColor("#f4ecf7"))
        painter.drawRoundedRect(badge, 6, 6)
        painter.setPen(QColor("#6c3483"))
        badge_font = QFont()
        badge_font.setPointSize(8)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        if self.plant_slug == "zeekoegat":
            badge_text = f"BNR mode: {self._bnr_mode}"
        else:
            badge_text = "Scientific Twin: explanatory, not SCADA"
        painter.drawText(badge.adjusted(8, 0, -8, 0), Qt.AlignCenter, badge_text)

    def _draw_lanes(self, painter: QPainter, geo: dict) -> None:
        lane_font = QFont()
        lane_font.setPointSize(8)
        lane_font.setBold(True)
        painter.setFont(lane_font)
        for label, lane in geo["lanes"]:
            painter.setPen(QPen(QColor("#d6dbdf"), 1))
            painter.setBrush(QColor(255, 255, 255, 168))
            painter.drawRoundedRect(lane, 8, 8)
            label_rect = QRectF(lane.left() + 8, lane.top() + 6, 170, 18)
            painter.setPen(QColor("#566573"))
            painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, label)

    def _draw_units(self, painter: QPainter, geo: dict) -> None:
        for unit in self.units:
            box = geo["unit_rects"].get(_unit_order(unit))
            if not box:
                continue
            self._draw_unit_box(painter, unit, box)

    def _draw_unit_box(self, painter: QPainter, unit, box: QRectF) -> None:
        unit_type = getattr(unit, "unit_type", "other") or "other"
        category = self.category_for_unit(unit_type)
        label, fill, border = self.CATEGORY_STYLES[category]
        is_context = self._is_context_unit(unit)

        painter.setPen(QPen(QColor(border), 1.5, Qt.DashLine if is_context else Qt.SolidLine))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(box, 8, 8)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(border))
        tag = QRectF(box.left() + 8, box.top() + 8, min(88, box.width() - 16), 18)
        painter.drawRoundedRect(tag, 6, 6)
        painter.setPen(QColor("#ffffff"))
        tag_font = QFont()
        tag_font.setPointSize(7)
        tag_font.setBold(True)
        painter.setFont(tag_font)
        painter.drawText(tag, Qt.AlignCenter, label)

        painter.setPen(QColor(C_TEXT))
        name_font = QFont()
        name_font.setPointSize(8)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.drawText(
            QRectF(box.left() + 9, box.top() + 32, box.width() - 18, box.height() - 38),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            getattr(unit, "name", ""),
        )
        self._draw_unit_activity(painter, unit, box)

    def _draw_unit_activity(self, painter: QPainter, unit, box: QRectF) -> None:
        category = self.category_for_unit(getattr(unit, "unit_type", "") or "")
        painter.save()
        painter.setClipRect(box.adjusted(2, 2, -2, -2))
        if category in {"anaerobic", "anoxic", "aerobic", "biofilm"}:
            color = QColor("#5dade2" if category == "aerobic" else "#7dcea0")
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 90))
            for i in range(5):
                t = (self._flow_phase + i * 0.19) % 1.0
                x = box.left() + 20 + (box.width() - 40) * ((i * 0.37) % 1.0)
                y = box.bottom() - 12 - t * (box.height() - 34)
                r = 2.2 + 1.5 * math.sin((self._flow_phase + i) * math.tau)
                painter.drawEllipse(QPointF(x, y), max(1.4, r), max(1.4, r))
        elif category == "pond":
            painter.setPen(QPen(QColor("#148f77"), 1.1))
            for i in range(3):
                y = box.top() + 46 + i * 9
                path = QPainterPath(QPointF(box.left() + 12, y))
                for x_i in range(0, int(box.width() - 24), 18):
                    x = box.left() + 12 + x_i
                    wave = math.sin(self._flow_phase * math.tau + x_i * 0.35 + i) * 3
                    path.lineTo(QPointF(x, y + wave))
                painter.drawPath(path)
        painter.restore()

    def _draw_main_flow(self, painter: QPainter, geo: dict) -> list[QPainterPath]:
        paths = []
        main = self._main_units()
        for current, nxt in zip(main, main[1:]):
            a = geo["unit_rects"].get(_unit_order(current))
            b = geo["unit_rects"].get(_unit_order(nxt))
            if not a or not b:
                continue
            path = self._path_between(a, b)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 210), 5.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#2471a3"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            self._draw_arrowhead(painter, path, QColor("#2471a3"))
            paths.append(path)
        return paths

    def _draw_secondary_paths(self, painter: QPainter, geo: dict) -> list[QPainterPath]:
        paths = []
        unit_rects = geo["unit_rects"]
        clarifiers = [u for u in self.units if getattr(u, "unit_type", "") in {"secondary_clarifier", "humus_tank", "anaerobic_pond"}]
        sludge_units = self._sludge_units()

        if sludge_units and clarifiers:
            source = unit_rects.get(_unit_order(clarifiers[-1]))
            target = unit_rects.get(_unit_order(sludge_units[0]))
            if source and target:
                path = self._path_between(source, target, vertical_bias=28)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 210), 5.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(path)
                painter.setPen(QPen(QColor("#c0392b"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(path)
                self._draw_arrowhead(painter, path, QColor("#c0392b"))
                label_w = 150
                label_x = target.right() + 10
                if label_x + label_w > geo["rect"].right():
                    label_x = target.left() - label_w - 10
                label_rect = QRectF(label_x, target.top() + 7, label_w, 22)
                self._draw_path_label(painter, path, "Sludge-bound PFAS", label_rect=label_rect)
                paths.append(path)

        if self.plant_slug in {"daspoort", "zeekoegat"}:
            anoxic = next((u for u in self.units if getattr(u, "unit_type", "") == "anoxic"), None)
            secondary = next((u for u in self.units if getattr(u, "unit_type", "") == "secondary_clarifier"), None)
            if anoxic and secondary:
                a = unit_rects.get(_unit_order(secondary))
                b = unit_rects.get(_unit_order(anoxic))
                if a and b:
                    path = QPainterPath(QPointF(a.center().x(), a.bottom()))
                    y = max(a.bottom(), b.bottom()) + 38
                    path.lineTo(QPointF(a.center().x(), y))
                    path.lineTo(QPointF(b.center().x(), y))
                    path.lineTo(QPointF(b.center().x(), b.bottom() + 4))
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(QColor(255, 255, 255, 210), 4.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    painter.drawPath(path)
                    painter.setPen(QPen(QColor("#16a085"), 1.8, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
                    painter.drawPath(path)
                    self._draw_arrowhead(painter, path, QColor("#16a085"))
                    self._draw_path_label(painter, path, "RAS / nitrate recycle")

        for context in self._context_units():
            target = unit_rects.get(_unit_order(context))
            source_unit = next((u for u in self.units if getattr(u, "unit_type", "") == "primary_settling"), None)
            source = unit_rects.get(_unit_order(source_unit)) if source_unit else None
            if target:
                if self._is_context_unit(context):
                    x0 = max(geo["rect"].left() + 12, target.left() - 38)
                    path = QPainterPath(QPointF(x0, target.center().y()))
                    path.lineTo(QPointF(target.left() - 8, target.center().y()))
                elif source:
                    path = self._path_between(source, target, vertical_bias=18)
                else:
                    continue
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 210), 4.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(path)
                painter.setPen(QPen(QColor("#8e44ad"), 1.8, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(path)
                self._draw_arrowhead(painter, path, QColor("#8e44ad"))
        return paths

    def _path_between(self, a: QRectF, b: QRectF, vertical_bias: float = 0.0) -> QPainterPath:
        start = QPointF(a.right(), a.center().y())
        end = QPointF(b.left(), b.center().y())
        if b.center().x() < a.center().x() or abs(a.center().y() - b.center().y()) > 46:
            start = QPointF(a.center().x(), a.bottom())
            end = QPointF(b.center().x(), b.top())
            mid_y = (start.y() + end.y()) / 2 + vertical_bias
            path = QPainterPath(start)
            path.lineTo(QPointF(start.x(), mid_y))
            path.lineTo(QPointF(end.x(), mid_y))
            path.lineTo(end)
            return path
        mid_x = (start.x() + end.x()) / 2
        path = QPainterPath(start)
        path.cubicTo(QPointF(mid_x, start.y()), QPointF(mid_x, end.y()), end)
        return path

    def _draw_arrowhead(self, painter: QPainter, path: QPainterPath, color: QColor) -> None:
        end = path.pointAtPercent(1.0)
        before = path.pointAtPercent(0.965)
        angle = math.atan2(end.y() - before.y(), end.x() - before.x())
        size = 9
        pts = QPolygonF([
            end,
            QPointF(end.x() - size * math.cos(angle - 0.45), end.y() - size * math.sin(angle - 0.45)),
            QPointF(end.x() - size * math.cos(angle + 0.45), end.y() - size * math.sin(angle + 0.45)),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(pts)

    def _draw_path_label(self, painter: QPainter, path: QPainterPath, text: str, label_rect: QRectF | None = None) -> None:
        if label_rect is None:
            pos = path.pointAtPercent(0.52)
            label = QRectF(pos.x() - 64, pos.y() - 12, 128, 20)
        else:
            label = label_rect
        painter.setPen(QPen(QColor("#d6dbdf"), 1))
        painter.setBrush(QColor(255, 255, 255, 218))
        painter.drawRoundedRect(label, 7, 7)
        painter.setPen(QColor(C_TEXT))
        font = QFont()
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(label, Qt.AlignCenter, text)

    def _draw_particles(self, painter: QPainter, paths: list[QPainterPath], color: QColor, radius: float, offset: float = 0.0) -> None:
        painter.setPen(Qt.NoPen)
        for path_i, path in enumerate(paths):
            for i in range(3):
                t = (self._flow_phase + offset + i * 0.29 + path_i * 0.11) % 1.0
                pos = path.pointAtPercent(t)
                alpha = 225 - i * 45
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
                painter.drawEllipse(pos, radius - i * 0.55, radius - i * 0.55)

    def _draw_sampling_points(self, painter: QPainter, geo: dict) -> None:
        unit_rects = geo["unit_rects"]
        pulse = 1.0 + 0.12 * math.sin(self._flow_phase * math.tau)
        offsets: dict[int, int] = {}
        for point in self.sampling_points:
            after_order = int(getattr(point, "after_unit_order", 0) or 0)
            anchor = unit_rects.get(after_order)
            if not anchor:
                continue
            offset = offsets.get(after_order, 0)
            offsets[after_order] = offset + 1
            code = str(getattr(point, "code", "SP")).split("_")[0]
            name = str(getattr(point, "name", ""))
            x = anchor.center().x()
            y = anchor.top() - 17 - offset * 26
            r = 9.5 * pulse
            painter.setPen(QPen(QColor("#c0392b"), 1.5))
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.drawEllipse(QPointF(x, y), r, r)
            painter.setPen(QColor("#c0392b"))
            sp_font = QFont()
            sp_font.setPointSize(7)
            sp_font.setBold(True)
            painter.setFont(sp_font)
            painter.drawText(QRectF(x - 20, y - 22, 40, 12), Qt.AlignCenter, code)
            label = QRectF(x - 58, y + 11, 116, 18)
            painter.setPen(QPen(QColor("#d6dbdf"), 1))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(label, 7, 7)
            painter.setPen(QColor(C_TEXT))
            painter.drawText(label.adjusted(4, 0, -4, 0), Qt.AlignCenter, name)

    def _draw_overlays(self, painter: QPainter, geo: dict) -> None:
        rect = geo["rect"]
        cards = []
        if self._inputs:
            cards.extend([
                ("Flow", f"{self._inputs.flow_mld:.2f} ML/d"),
                ("HRT", f"{self._inputs.hrt_hours:.1f} h"),
                ("SRT/ret.", f"{self._inputs.srt_days:.1f} d" if self._inputs.srt_days else f"{self._inputs.hrt_hours:.1f} h"),
                ("MLSS", f"{self._inputs.mlss_mgl:.0f} mg/L"),
            ])
        if self._outputs:
            cards.extend([
                ("COD", f"{self._outputs.cod_removal_pct:.1f}%"),
                ("NH4", f"{self._outputs.nh4_removal_pct:.1f}%"),
                ("PFAS", f"{self._outputs.pfas_removal_pct:.2f}% transfer"),
            ])
        else:
            cards.append(("Model", "waiting for run"))

        visible_cards = cards[:7]
        if visible_cards:
            gap = 8
            min_card_w = 88
            per_row = max(1, min(len(visible_cards), int((rect.width() + gap) / (min_card_w + gap))))
            card_w = min(112, (rect.width() - gap * (per_row - 1)) / per_row)
            total_w = per_row * card_w + (per_row - 1) * gap
            x0 = rect.right() - total_w
            y0 = rect.top() + 68
            for index, (title, value) in enumerate(visible_cards):
                row = index // per_row
                col = index % per_row
                x = x0 + col * (card_w + gap)
                y = y0 + row * 42
                self._draw_metric_card(painter, QRectF(x, y, card_w, 36), title, value)

        if self._outputs:
            fate = self.pfas_fate_summary()
            footer_top = self._footer_top(geo)
            footer_w = min(rect.width(), 860)
            conf = QRectF(rect.left(), footer_top, footer_w, 32)
            painter.setPen(QPen(QColor("#d6dbdf"), 1))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(conf, 8, 8)
            painter.setPen(QColor(C_TEXT))
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(conf.adjusted(10, 0, -10, 0), Qt.AlignLeft | Qt.AlignVCenter, self._outputs.confidence_label)

            card = QRectF(rect.left(), footer_top + 40, footer_w, 58)
            painter.setPen(QPen(QColor("#f5b7b1"), 1))
            painter.setBrush(QColor("#fdecea"))
            painter.drawRoundedRect(card, 8, 8)
            painter.setPen(QColor("#922b21"))
            painter.drawText(card.adjusted(10, 6, -10, -6), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, fate)

    def _draw_metric_card(self, painter: QPainter, box: QRectF, title: str, value: str) -> None:
        painter.setPen(QPen(QColor("#d6dbdf"), 1))
        painter.setBrush(QColor(255, 255, 255, 232))
        painter.drawRoundedRect(box, 7, 7)
        painter.setPen(QColor(C_MUTED))
        title_font = QFont()
        title_font.setPointSize(7)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(box.left() + 8, box.top() + 5, box.width() - 16, 12), Qt.AlignLeft | Qt.AlignVCenter, title)
        painter.setPen(QColor(C_TEXT))
        value_font = QFont()
        value_font.setPointSize(8)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.drawText(QRectF(box.left() + 8, box.top() + 20, box.width() - 16, 16), Qt.AlignLeft | Qt.AlignVCenter, value)

    def _draw_note(self, painter: QPainter, geo: dict) -> None:
        note = self.PLANT_NOTES.get(self.plant_slug)
        if not note:
            return
        rect = geo["rect"]
        note_top = self._footer_top(geo) + (108 if self._outputs else 0)
        note_box = QRectF(rect.left(), note_top, min(rect.width(), 860), 40)
        painter.setPen(QPen(QColor("#d6dbdf"), 1))
        painter.setBrush(QColor(255, 255, 255, 226))
        painter.drawRoundedRect(note_box, 7, 7)
        painter.setPen(QColor(C_TEXT))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(note_box.adjusted(9, 4, -9, -4), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, note)

    def _footer_top(self, geo: dict) -> float:
        bottoms = [lane.bottom() for _, lane in geo.get("lanes", [])]
        bottoms.extend(box.bottom() for box in geo.get("unit_rects", {}).values())
        content_bottom = max(bottoms) if bottoms else geo["rect"].top() + 120
        return content_bottom + 18


PlantProcessDiagram = PlantProcessOverview


class PlantsScreen(QWidget):
    """Container with one tab/page for each real South African plant."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setStyleSheet(f"background:{C_BG};")

        root.addWidget(self._build_header())
        root.addWidget(self._build_info_strip())

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {C_BORDER};
                background: {C_CARD};
            }}
            QTabBar::tab {{
                background: #ecf0f1;
                color: {C_MUTED};
                padding: 8px 18px;
                border: 1px solid {C_BORDER};
                border-bottom: none;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {C_CARD};
                color: {C_TEXT};
                font-weight: 600;
            }}
        """)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.addWidget(self._tabs)
        root.addWidget(content, stretch=1)

        self._load_tabs()

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background:{C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa6s.industry", color="#ecf0f1").pixmap(QSize(18, 18)))
        row.addWidget(icon)

        title = QLabel("Real Plant Scientific Twins")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#ecf0f1;")
        row.addWidget(title)
        row.addStretch()

        refresh_btn = QPushButton("  Refresh")
        refresh_btn.setIcon(qta.icon("fa6s.rotate-left", color="#ecf0f1"))
        refresh_btn.setIconSize(QSize(13, 13))
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton { background:#3d5166; color:#ecf0f1; border:none;
                border-radius:4px; padding:0 14px; font-size:11px; }
            QPushButton:hover { background:#3498db; }
        """)
        refresh_btn.clicked.connect(self._load_tabs)
        row.addWidget(refresh_btn)
        return bar

    def _build_info_strip(self) -> QWidget:
        strip = QWidget()
        strip.setFixedHeight(34)
        strip.setStyleSheet("background:#eaf2f8; border-bottom:1px solid #c5d8ea;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(qta.icon("fa6s.circle-info", color="#2c6fa6").pixmap(QSize(13, 13)))
        row.addWidget(icon)

        label = QLabel(
            "Scientific Twin mode: process-realistic and mass-balance based; "
            "not a live plant replica until field data is connected."
        )
        label.setStyleSheet("color:#1f3a5f; font-size:11px; font-weight:600;")
        row.addWidget(label)
        row.addStretch()
        return strip

    def _load_tabs(self) -> None:
        """Reload plant profiles from the database and rebuild tabs."""
        if self._tabs is None:
            return
        self._tabs.clear()

        with get_session() as session:
            plants = (
                session.query(Plant)
                .filter(Plant.slug.in_(["daspoort", "zeekoegat", "phola"]))
                .order_by(Plant.name)
                .all()
            )
            # Force relationship loading before the session closes.
            plant_payloads = []
            for plant in plants:
                plant_payloads.append({
                    "plant": plant,
                    "units": list(plant.units),
                    "sampling_points": list(plant.sampling_points),
                })

        order = {"daspoort": 0, "zeekoegat": 1, "phola": 2}
        plant_payloads.sort(key=lambda p: order.get(p["plant"].slug, 99))

        if not plant_payloads:
            self._tabs.addTab(_EmptyPlantsMessage(), "No plants")
            return

        for payload in plant_payloads:
            self._tabs.addTab(
                PlantDetailPanel(payload["plant"], payload["units"], payload["sampling_points"]),
                payload["plant"].name.split(" Wastewater")[0].split(" Waste ")[0],
            )


class _EmptyPlantsMessage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel("No plant profiles found. Restart the app to run database seeding.")
        label.setStyleSheet(f"color:{C_MUTED}; font-size:13px;")
        layout.addWidget(label)


class PlantDetailPanel(QWidget):
    """One plant page: profile, process train, inputs, and simulation output."""

    def __init__(self, plant: Plant, units: list, sampling_points: list, parent=None):
        super().__init__(parent)
        self.plant = plant
        self.units = units
        self.sampling_points = sampling_points
        self._inputs: dict[str, QDoubleSpinBox] = {}
        self._result_labels: dict[str, QLabel] = {}
        self._calibration_factors: dict[str, float] = {}
        self._calibration_table = None
        self._calibration_status = None
        self._import_btn = None
        self._calibrate_btn = None
        self._import_worker = None
        self._calibration_worker = None
        self._overview = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._run)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        body.setStyleSheet(f"background:{C_CARD};")
        root = QVBoxLayout(body)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)

        root.addLayout(self._build_profile_row())
        if self.plant.slug == "daspoort":
            root.addWidget(self._panel("Daspoort Data Import & Calibration", self._build_calibration_tools()))

        self._overview = PlantProcessOverview(self.plant, self.units, self.sampling_points)
        root.addWidget(self._panel(
            "Animated Plant Process Overview",
            self._overview,
        ))

        tables_row = QHBoxLayout()
        tables_row.setSpacing(10)
        tables_row.addWidget(self._panel("Process Train", self._build_units_table()), stretch=2)
        tables_row.addWidget(self._panel("Sampling Map", self._build_sampling_table()), stretch=1)
        root.addLayout(tables_row)

        sim_row = QHBoxLayout()
        sim_row.setSpacing(10)
        sim_row.addWidget(self._panel("Scientific Twin Inputs", self._build_inputs()), stretch=1)
        sim_row.addWidget(self._panel("Predicted Fate", self._build_outputs()), stretch=1)
        root.addLayout(sim_row)

        root.addWidget(self._panel("Unit-by-Unit Prediction", self._build_unit_results_table()))

        scroll.setWidget(body)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._refresh_calibration_state()
        QTimer.singleShot(0, self._run)

    def _build_profile_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._profile_card(
            "Plant",
            self.plant.name,
            f"{self.plant.municipality or 'Unknown municipality'} · {self.plant.province or 'Unknown province'}",
            "#2471a3",
        ))
        row.addWidget(self._profile_card(
            "Process",
            self.plant.process_family,
            f"Capacity: {_default(self.plant.capacity_mld):.1f} ML/d",
            "#1e8449",
        ))
        row.addWidget(self._profile_card(
            "Confidence",
            "Scientific Twin",
            "Literature/default assumptions until calibrated",
            "#8e44ad",
        ))
        return row

    def _build_calibration_tools(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._calibration_status = QLabel("Loading calibration status...")
        self._calibration_status.setWordWrap(True)
        self._calibration_status.setStyleSheet(
            f"color:{C_TEXT}; font-size:10px; font-weight:600;"
        )
        top.addWidget(self._calibration_status, stretch=1)

        self._import_btn = QPushButton("  Import CSV/Excel")
        self._import_btn.setIcon(qta.icon("fa6s.file-import", color="#ffffff"))
        self._import_btn.setFixedHeight(32)
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setStyleSheet("""
            QPushButton { background:#2471a3; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 12px; }
            QPushButton:hover { background:#2980b9; }
            QPushButton:disabled { background:#aab7b8; color:#ecf0f1; }
        """)
        self._import_btn.clicked.connect(self._on_import_monitoring)
        top.addWidget(self._import_btn)

        self._calibrate_btn = QPushButton("  Calibrate")
        self._calibrate_btn.setIcon(qta.icon("fa6s.sliders", color="#ffffff"))
        self._calibrate_btn.setFixedHeight(32)
        self._calibrate_btn.setCursor(Qt.PointingHandCursor)
        self._calibrate_btn.setStyleSheet("""
            QPushButton { background:#8e44ad; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 12px; }
            QPushButton:hover { background:#9b59b6; }
            QPushButton:disabled { background:#aab7b8; color:#ecf0f1; }
        """)
        self._calibrate_btn.clicked.connect(self._on_calibrate)
        top.addWidget(self._calibrate_btn)
        layout.addLayout(top)

        hint = QLabel(
            "Expected columns: date, sampling_point, flow_mld, COD, NH4, TN, TP, "
            "pH, temperature, DO, MLSS, SRT, HRT, cec_name, concentration_ugl, "
            "detection_limit, below_detection. SP1/influent and SP4/effluent pairs drive calibration."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{C_MUTED}; font-size:10px;")
        layout.addWidget(hint)

        self._calibration_table = QTableWidget(len(CALIBRATION_TARGETS), 6)
        self._calibration_table.setHorizontalHeaderLabels([
            "Target", "Multiplier", "Samples", "RMSE", "MAE", "R2",
        ])
        self._style_table(self._calibration_table)
        self._calibration_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._calibration_table.setFixedHeight(190)
        layout.addWidget(self._calibration_table)
        return w

    def _refresh_calibration_state(self) -> None:
        if self.plant.slug != "daspoort":
            return
        try:
            with get_session() as session:
                rows_count = (
                    session.query(PlantMonitoringReading)
                    .filter_by(plant_id=self.plant.id)
                    .count()
                )
                summary = get_calibration_summary(session, self.plant.id)
                self._calibration_factors = get_calibration_factors(session, self.plant.id)
        except Exception as exc:
            if self._calibration_status:
                self._calibration_status.setText(f"Calibration unavailable: {exc}")
            self._calibration_factors = {}
            return

        calibrated = len(self._calibration_factors)
        if self._calibration_status:
            self._calibration_status.setText(
                f"Imported monitoring rows: {rows_count}  |  "
                f"Calibrated targets: {calibrated}/5"
            )

        if not self._calibration_table:
            return
        by_target = {row.target: row for row in summary}
        for row_i, target in enumerate(CALIBRATION_TARGETS):
            cal = by_target.get(target)
            values = [
                target.upper(),
                f"{cal.multiplier:.3f}" if cal else "—",
                str(cal.n_samples) if cal else "0",
                f"{cal.rmse_pct:.2f}%" if cal and cal.rmse_pct is not None else "—",
                f"{cal.mean_abs_error_pct:.2f}%" if cal and cal.mean_abs_error_pct is not None else "—",
                f"{cal.r2:.3f}" if cal and cal.r2 is not None else "—",
            ]
            for col, text in enumerate(values):
                self._calibration_table.setItem(row_i, col, _item(text))
            self._calibration_table.setRowHeight(row_i, 28)

    def _on_import_monitoring(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Daspoort Monitoring Data",
            "",
            "Data files (*.csv *.xlsx *.xls);;CSV files (*.csv);;Excel files (*.xlsx *.xls)",
        )
        if not path:
            return
        self._set_calibration_busy(True, "Importing Daspoort monitoring data...")
        self._import_worker = PlantImportWorker(self.plant.slug, path, self)
        self._import_worker.result_ready.connect(self._on_import_finished)
        self._import_worker.finished.connect(self._import_worker.deleteLater)
        self._import_worker.start()

    def _on_import_finished(self, payload: dict) -> None:
        self._import_worker = None
        self._set_calibration_busy(False)
        if payload.get("status") != "ok":
            QMessageBox.critical(self, "Import Failed", payload.get("message", "Unknown error"))
            self._refresh_calibration_state()
            return

        result = payload["result"]
        self._refresh_calibration_state()
        self._run()
        warning_text = ""
        if result["warnings"]:
            warning_text = "\n\nWarnings:\n" + "\n".join(result["warnings"])
        QMessageBox.information(
            self,
            "Import Complete",
            f"Imported {result['imported']} new row(s).\n"
            f"Updated {result['updated']} existing row(s).\n"
            f"Skipped {result['skipped']} row(s)."
            f"{warning_text}",
        )

    def _on_calibrate(self) -> None:
        self._set_calibration_busy(True, "Calibrating Daspoort coefficients...")
        self._calibration_worker = PlantCalibrationWorker(self.plant.slug, self)
        self._calibration_worker.result_ready.connect(self._on_calibration_finished)
        self._calibration_worker.finished.connect(self._calibration_worker.deleteLater)
        self._calibration_worker.start()

    def _on_calibration_finished(self, payload: dict) -> None:
        self._calibration_worker = None
        self._set_calibration_busy(False)
        if payload.get("status") != "ok":
            QMessageBox.critical(self, "Calibration Failed", payload.get("message", "Unknown error"))
            self._refresh_calibration_state()
            return

        result = payload["result"]
        self._refresh_calibration_state()
        self._run()
        targets = result.get("targets", {})
        if targets:
            detail = ", ".join(f"{target.upper()} n={data['n_samples']}" for target, data in targets.items())
        else:
            detail = "No complete SP1-to-SP4 pairs were available yet."
        QMessageBox.information(
            self,
            "Calibration Complete",
            f"Daspoort calibration updated.\n\n{detail}",
        )

    def _set_calibration_busy(self, busy: bool, message: str | None = None) -> None:
        if self._import_btn:
            self._import_btn.setEnabled(not busy)
            self._import_btn.setText("  Importing..." if busy and message and "Import" in message else "  Import CSV/Excel")
        if self._calibrate_btn:
            self._calibrate_btn.setEnabled(not busy)
            self._calibrate_btn.setText("  Calibrating..." if busy and message and "Calibrat" in message else "  Calibrate")
        if busy and self._calibration_status and message:
            self._calibration_status.setText(message)

    def _profile_card(self, title: str, value: str, sub: str, color: str) -> QWidget:
        card = QWidget()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumHeight(88)
        card.setStyleSheet(f"""
            QWidget {{ background:#ffffff; border:1px solid {C_BORDER}; border-radius:6px; }}
            QLabel {{ border:none; background:transparent; }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        t = QLabel(title)
        t.setStyleSheet(f"color:{C_MUTED}; font-size:10px; font-weight:600;")
        v = QLabel(value)
        v.setWordWrap(True)
        v.setStyleSheet(f"color:{color}; font-size:13px; font-weight:700;")
        s = QLabel(sub)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{C_MUTED}; font-size:10px;")
        layout.addWidget(t)
        layout.addWidget(v)
        layout.addWidget(s)
        layout.addStretch()
        return card

    def _build_units_table(self) -> QTableWidget:
        table = QTableWidget(len(self.units), 5)
        table.setHorizontalHeaderLabels(["#", "Unit", "Type", "HRT", "Scientific role"])
        self._style_table(table)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.setMinimumHeight(240)

        for row, unit in enumerate(self.units):
            table.setItem(row, 0, _item(str(unit.unit_order)))
            table.setItem(row, 1, _item(unit.name, Qt.AlignLeft | Qt.AlignVCenter))
            table.setItem(row, 2, _item(unit.unit_type))
            hrt = f"{unit.hrt_hours:.1f} h" if unit.hrt_hours else "—"
            table.setItem(row, 3, _item(hrt))
            table.setItem(row, 4, _item(unit.hydraulic_role or unit.notes or "", Qt.AlignLeft | Qt.AlignVCenter))
            table.setRowHeight(row, 30)
        return table

    def _build_sampling_table(self) -> QTableWidget:
        table = QTableWidget(len(self.sampling_points), 4)
        table.setHorizontalHeaderLabels(["Code", "Location", "After", "Purpose"])
        self._style_table(table)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.setMinimumHeight(240)

        for row, point in enumerate(self.sampling_points):
            table.setItem(row, 0, _item(point.code))
            table.setItem(row, 1, _item(point.name, Qt.AlignLeft | Qt.AlignVCenter))
            table.setItem(row, 2, _item(str(point.after_unit_order or "—")))
            table.setItem(row, 3, _item(point.description or "", Qt.AlignLeft | Qt.AlignVCenter))
            table.setRowHeight(row, 36)
        return table

    def _build_inputs(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)

        defs = [
            ("flow_mld", "Flow", "ML/d", 0.1, 120.0, _default(self.plant.default_flow_mld, _default(self.plant.capacity_mld, 1.0)), 2),
            ("hrt_hours", "HRT", "h", 1.0, 120.0, _default(self.plant.default_hrt_hours, 12.0), 1),
            ("srt_days", "SRT", "d", 0.0, 80.0, _default(self.plant.default_srt_days, 0.0), 1),
            ("mlss_mgl", "MLSS", "mg/L", 100.0, 10000.0, _default(self.plant.default_mlss_mgl, 3000.0), 0),
            ("do_mgl", "DO", "mg/L", 0.0, 6.0, _default(self.plant.default_do_mgl, 1.5), 2),
            ("temp_c", "Temp", "deg C", 5.0, 35.0, _default(self.plant.default_temp_c, 22.0), 1),
            ("ph", "pH", "", 5.0, 9.5, _default(self.plant.default_ph, 7.5), 2),
            ("recycle_ratio", "Recycle", "", 0.0, 8.0, _default(self.plant.default_recycle_ratio, 0.0), 2),
            ("organic_loading", "Org. load", "kg BOD/m3/d", 0.0, 2.0, _default(self.plant.default_organic_loading, 0.0), 3),
            ("nitrogen_loading", "N load", "g TKN/m2/d", 0.0, 5.0, _default(self.plant.default_nitrogen_loading, 0.0), 2),
            ("inf_cod_mgl", "Influent COD", "mg/L", 1.0, 2000.0, 450.0 if self.plant.slug == "phola" else 350.0, 1),
            ("inf_nh4_mgl", "Influent NH4", "mg/L", 0.1, 200.0, 45.0, 2),
            ("inf_tn_mgl", "Influent TN", "mg/L", 0.1, 250.0, 70.0, 2),
            ("inf_tp_mgl", "Influent TP", "mg/L", 0.1, 60.0, 8.0, 2),
            ("inf_pfas_ugl", "Influent PFAS", "ug/L", 0.0, 1000.0, 50.0, 3),
        ]

        for i, (key, label, unit, mn, mx, val, dec) in enumerate(defs):
            r = i // 2
            c = (i % 2) * 2
            lbl = QLabel(f"{label} {f'({unit})' if unit else ''}")
            lbl.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:600;")
            spin = QDoubleSpinBox()
            spin.setRange(mn, mx)
            spin.setDecimals(dec)
            spin.setValue(val)
            spin.setFixedHeight(28)
            spin.setStyleSheet(self._spin_style())
            spin.valueChanged.connect(lambda _: self._debounce.start())
            self._inputs[key] = spin
            grid.addWidget(lbl, r, c)
            grid.addWidget(spin, r, c + 1)

        layout.addLayout(grid)

        # ── PFAS compound + chain type ─────────────────────────────────────────
        compound_row = QHBoxLayout()
        compound_row.setSpacing(6)
        compound_lbl = QLabel("PFAS compound")
        compound_lbl.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:600;")
        self._pfas_compound = QComboBox()
        for label, _ in PFAS_COMPOUND_LIST:
            self._pfas_compound.addItem(label)
        self._pfas_compound.setStyleSheet(self._combo_style())
        self._pfas_compound.currentIndexChanged.connect(self._on_pfas_compound_changed)
        compound_row.addWidget(compound_lbl)
        compound_row.addWidget(self._pfas_compound, stretch=1)
        layout.addLayout(compound_row)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        pfas_lbl = QLabel("Chain type")
        pfas_lbl.setStyleSheet(f"color:{C_MUTED}; font-size:10px;")
        self._pfas_type = QComboBox()
        self._pfas_type.addItems(["short-chain", "long-chain"])
        self._pfas_type.setStyleSheet(self._combo_style())
        self._pfas_type.currentIndexChanged.connect(lambda _: self._debounce.start())
        controls.addWidget(pfas_lbl)
        controls.addWidget(self._pfas_type)

        bnr_lbl = QLabel("BNR mode")
        bnr_lbl.setStyleSheet(f"color:{C_TEXT}; font-size:10px; font-weight:600;")
        self._bnr_mode = QComboBox()
        self._bnr_mode.addItems(BNR_MODES)
        self._bnr_mode.setStyleSheet(self._combo_style())
        self._bnr_mode.currentIndexChanged.connect(self._on_bnr_mode_changed)
        # Phola uses pond/trickling filter — BNR mode not applicable
        if self.plant.slug == "phola":
            self._bnr_mode.setEnabled(False)
        controls.addWidget(bnr_lbl)
        controls.addWidget(self._bnr_mode, stretch=1)
        layout.addLayout(controls)

        # ── Load Latest Data button ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        load_btn = QPushButton("  Load Latest Monitoring Data")
        load_btn.setIcon(qta.icon("fa6s.database", color="#ffffff"))
        load_btn.setFixedHeight(30)
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.setToolTip("Pre-fill inputs from the most recently imported SP1 monitoring row")
        load_btn.setStyleSheet("""
            QPushButton { background:#16a085; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 10px; }
            QPushButton:hover { background:#1abc9c; }
        """)
        load_btn.clicked.connect(self._load_monitoring_data)
        btn_row.addWidget(load_btn, stretch=1)

        run_btn = QPushButton("  Run Scientific Twin")
        run_btn.setIcon(qta.icon("fa6s.play", color="#ffffff"))
        run_btn.setFixedHeight(30)
        run_btn.setCursor(Qt.PointingHandCursor)
        run_btn.setStyleSheet("""
            QPushButton { background:#8e44ad; color:#fff; border:none;
                border-radius:4px; font-size:10px; font-weight:600; padding:0 10px; }
            QPushButton:hover { background:#9b59b6; }
        """)
        run_btn.clicked.connect(self._run)
        btn_row.addWidget(run_btn, stretch=1)
        layout.addLayout(btn_row)
        return w

    def _on_bnr_mode_changed(self, _index=None) -> None:
        if self._overview:
            self._overview.set_bnr_mode(self._bnr_mode.currentText())
        self._debounce.start()

    def _on_pfas_compound_changed(self, index: int) -> None:
        """Auto-set chain type when a specific compound is chosen."""
        key = PFAS_COMPOUND_LIST[index][1]
        if key in PFAS_COMPOUND_CHAIN_TYPE:
            self._pfas_type.setCurrentText(PFAS_COMPOUND_CHAIN_TYPE[key])
        self._debounce.start()

    def _load_monitoring_data(self) -> None:
        """Pre-fill inputs from the most recently imported SP1 monitoring row."""
        try:
            with get_session() as session:
                # Most recent conventional (non-CEC) influent row for this plant
                latest = (
                    session.query(PlantMonitoringReading)
                    .filter_by(plant_id=self.plant.id, sampling_point_code="SP1_influent")
                    .filter(PlantMonitoringReading.cec_name.is_(None))
                    .order_by(PlantMonitoringReading.sampling_date.desc())
                    .first()
                )

            if not latest:
                QMessageBox.information(
                    self, "No Monitoring Data",
                    "No imported monitoring data found for this plant.\n"
                    "Use the Import button to load a CSV or Excel file first."
                )
                return

            field_map = {
                "flow_mld":       latest.flow_mld,
                "hrt_hours":      latest.hrt_hours,
                "srt_days":       latest.srt_days,
                "mlss_mgl":       latest.mlss_mgl,
                "do_mgl":         latest.do_mgl,
                "temp_c":         latest.temperature_c,
                "ph":             latest.ph,
                "recycle_ratio":  latest.recycle_ratio,
                "inf_cod_mgl":    latest.cod_mgl,
                "inf_nh4_mgl":    latest.nh4_mgl,
                "inf_tn_mgl":     latest.tn_mgl,
                "inf_tp_mgl":     latest.tp_mgl,
            }
            filled = []
            for key, value in field_map.items():
                if value is not None and key in self._inputs:
                    spin = self._inputs[key]
                    clamped = max(spin.minimum(), min(spin.maximum(), float(value)))
                    spin.setValue(clamped)
                    filled.append(key.replace("_", " "))

            if filled:
                self._debounce.start()

        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _build_outputs(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)
        for i, (key, title, color) in enumerate([
            ("cod", "COD", "#2471a3"),
            ("nh4", "NH4", "#8e44ad"),
            ("tn", "TN", "#138d75"),
            ("tp", "TP", "#1e8449"),
            ("pfas", "PFAS", "#c0392b"),
            ("fm", "F:M", "#d68910"),
        ]):
            kpi_grid.addWidget(self._kpi(key, title, color), i // 3, i % 3)
        layout.addLayout(kpi_grid)

        self._eff_table = QTableWidget(5, 4)
        self._eff_table.setHorizontalHeaderLabels(["Parameter", "Influent", "Effluent", "Removal"])
        self._style_table(self._eff_table)
        self._eff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._eff_table.setFixedHeight(190)
        layout.addWidget(self._eff_table)

        self._mass_table = QTableWidget(4, 2)
        self._mass_table.setHorizontalHeaderLabels(["PFAS fate", "g/day"])
        self._style_table(self._mass_table)
        self._mass_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._mass_table.setFixedHeight(150)
        layout.addWidget(self._mass_table)

        self._confidence = QLabel("Scientific Twin")
        self._confidence.setWordWrap(True)
        self._confidence.setStyleSheet("""
            background:#f8f9fa; border:1px solid #dde1e7; border-radius:6px;
            padding:8px 10px; color:#2c3e50; font-size:10px; font-weight:600;
        """)
        layout.addWidget(self._confidence)

        self._warnings = QLabel("")
        self._warnings.setWordWrap(True)
        self._warnings.setVisible(False)
        self._warnings.setStyleSheet("""
            background:#fef9e7; border:1px solid #f9ca24; border-radius:6px;
            padding:8px 10px; color:#7d6608; font-size:10px; font-weight:600;
        """)
        layout.addWidget(self._warnings)
        return w

    def _kpi(self, key: str, title: str, color: str) -> QWidget:
        box = QWidget()
        box.setMinimumHeight(68)
        box.setStyleSheet(f"""
            QWidget {{ background:{QColor(color).lighter(190).name()};
                border:1px solid {color}; border-radius:6px; }}
            QLabel {{ border:none; background:transparent; }}
        """)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 6)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{color}; font-size:10px; font-weight:600;")
        val = QLabel("—")
        val.setAlignment(Qt.AlignCenter)
        val.setStyleSheet(f"color:{color}; font-size:17px; font-weight:800;")
        v.addWidget(t)
        v.addWidget(val)
        self._result_labels[key] = val
        return box

    def _build_unit_results_table(self) -> QTableWidget:
        self._unit_results = QTableWidget(0, 7)
        self._unit_results.setHorizontalHeaderLabels([
            "Unit", "Type", "COD", "NH4", "TN", "TP", "PFAS / note",
        ])
        self._style_table(self._unit_results)
        self._unit_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._unit_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in range(2, 6):
            self._unit_results.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._unit_results.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self._unit_results.setMinimumHeight(210)
        return self._unit_results

    def _run(self) -> None:
        inputs = PlantTwinInputs(
            plant_slug=self.plant.slug,
            flow_mld=self._inputs["flow_mld"].value(),
            hrt_hours=self._inputs["hrt_hours"].value(),
            srt_days=self._inputs["srt_days"].value(),
            mlss_mgl=self._inputs["mlss_mgl"].value(),
            do_mgl=self._inputs["do_mgl"].value(),
            temp_c=self._inputs["temp_c"].value(),
            ph=self._inputs["ph"].value(),
            recycle_ratio=self._inputs["recycle_ratio"].value(),
            organic_loading=self._inputs["organic_loading"].value(),
            nitrogen_loading=self._inputs["nitrogen_loading"].value(),
            inf_cod_mgl=self._inputs["inf_cod_mgl"].value(),
            inf_nh4_mgl=self._inputs["inf_nh4_mgl"].value(),
            inf_tn_mgl=self._inputs["inf_tn_mgl"].value(),
            inf_tp_mgl=self._inputs["inf_tp_mgl"].value(),
            inf_pfas_ugl=self._inputs["inf_pfas_ugl"].value(),
            pfas_type=self._pfas_type.currentText(),
            pfas_compound=PFAS_COMPOUND_LIST[self._pfas_compound.currentIndex()][1],
            bnr_mode=self._bnr_mode.currentText(),
            calibration_factors=self._calibration_factors,
        )
        outputs = run_plant_twin(inputs)
        if self._overview:
            self._overview.set_results(inputs, outputs)
        self._update_results(inputs, outputs)

    def _update_results(self, inputs: PlantTwinInputs, outputs: PlantTwinOutputs) -> None:
        self._result_labels["cod"].setText(f"{outputs.cod_removal_pct:.1f}%")
        self._result_labels["nh4"].setText(f"{outputs.nh4_removal_pct:.1f}%")
        self._result_labels["tn"].setText(f"{outputs.tn_removal_pct:.1f}%")
        self._result_labels["tp"].setText(f"{outputs.tp_removal_pct:.1f}%")
        self._result_labels["pfas"].setText(f"{outputs.pfas_removal_pct:.2f}%")
        self._result_labels["fm"].setText(f"{outputs.fm_ratio:.3f}")

        eff_rows = [
            ("COD", f"{inputs.inf_cod_mgl:.1f} mg/L", f"{outputs.eff_cod_mgl:.2f} mg/L", f"{outputs.cod_removal_pct:.1f}%"),
            ("NH4", f"{inputs.inf_nh4_mgl:.2f} mg/L", f"{outputs.eff_nh4_mgl:.2f} mg/L", f"{outputs.nh4_removal_pct:.1f}%"),
            ("TN", f"{inputs.inf_tn_mgl:.2f} mg/L", f"{outputs.eff_tn_mgl:.2f} mg/L", f"{outputs.tn_removal_pct:.1f}%"),
            ("TP", f"{inputs.inf_tp_mgl:.2f} mg/L", f"{outputs.eff_tp_mgl:.2f} mg/L", f"{outputs.tp_removal_pct:.1f}%"),
            ("PFAS", f"{inputs.inf_pfas_ugl:.3f} ug/L", f"{outputs.eff_pfas_ugl:.3f} ug/L", f"{outputs.pfas_removal_pct:.2f}%"),
        ]
        for r, row in enumerate(eff_rows):
            for c, text in enumerate(row):
                cell = _item(text)
                if c == 3:
                    cell.setForeground(QBrush(QColor("#1e8449" if row[0] != "PFAS" and float(text.rstrip("%")) >= 60 else "#c0392b" if row[0] == "PFAS" else "#d68910")))
                self._eff_table.setItem(r, c, cell)
            self._eff_table.setRowHeight(r, 30)

        mass_rows = [
            ("PFAS in", outputs.pfas_in_g_day),
            ("To effluent", outputs.pfas_effluent_g_day),
            ("To sludge/solids", outputs.pfas_sludge_g_day),
            ("Unresolved", outputs.pfas_unresolved_g_day),
        ]
        for r, (label, value) in enumerate(mass_rows):
            self._mass_table.setItem(r, 0, _item(label, Qt.AlignLeft | Qt.AlignVCenter))
            self._mass_table.setItem(r, 1, _item(f"{value:.4f}"))
            self._mass_table.setRowHeight(r, 28)

        self._confidence.setText(
            f"{outputs.confidence_label}  |  COD load: {outputs.cod_load_kg_day:.1f} kg/day  |  "
            f"PFAS Kd: {outputs.kd_used:.3g} L/kg. PFAS removal is adsorption/solids capture, not biodegradation."
        )

        if outputs.warnings:
            self._warnings.setText("  ".join(outputs.warnings))
            self._warnings.setVisible(True)
        else:
            self._warnings.setVisible(False)

        self._unit_results.setRowCount(len(outputs.unit_results))
        for r, unit in enumerate(outputs.unit_results):
            values = [
                unit.unit_name,
                unit.unit_type,
                f"{unit.cod_mgl:.2f}",
                f"{unit.nh4_mgl:.2f}",
                f"{unit.tn_mgl:.2f}",
                f"{unit.tp_mgl:.2f}",
                f"{unit.pfas_ugl:.3f} ug/L  ·  {unit.note}",
            ]
            for c, text in enumerate(values):
                align = Qt.AlignLeft | Qt.AlignVCenter if c in (0, 6) else Qt.AlignCenter
                self._unit_results.setItem(r, c, _item(text, align))
            self._unit_results.setRowHeight(r, 32)

    def _panel(self, title: str, widget: QWidget) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet(f"background:#ffffff; border:1px solid {C_BORDER};")
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet(f"background:{C_HDR}; border:none;")
        row = QHBoxLayout(hdr)
        row.setContentsMargins(12, 0, 12, 0)
        label = QLabel(title)
        label.setStyleSheet("color:#ecf0f1; font-size:10px; font-weight:600; border:none;")
        row.addWidget(label)
        layout.addWidget(hdr)
        layout.addWidget(widget)
        return outer

    @staticmethod
    def _style_table(table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.setStyleSheet("""
            QTableWidget { background:#fff; border:1px solid #dde1e7;
                border-radius:6px; font-size:10px; alternate-background-color:#f8f9fa; }
            QHeaderView::section { background:#2c3e50; color:#ecf0f1;
                font-weight:bold; font-size:10px; padding:6px; border:none; }
            QTableWidget::item { padding:4px 7px; }
        """)

    @staticmethod
    def _spin_style() -> str:
        return """
            QDoubleSpinBox { border:1px solid #ced4da; border-radius:4px;
                padding:2px 6px; font-size:10px; background:#fff; color:#2c3e50; }
            QDoubleSpinBox:focus { border-color:#2980b9; }
        """

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox { border:1px solid #ced4da; border-radius:4px;
                padding:3px 8px; font-size:10px; background:#fff; color:#2c3e50; }
            QComboBox:disabled { color:#95a5a6; background:#f8f9fa; }
        """
