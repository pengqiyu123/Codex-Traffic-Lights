"""Side action buttons for the floating window."""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget

DEFAULT_ACCENT_COLOR = "#FFCC00"
BASE_BUTTON_SIZE = 26
BASE_ICON_INSET = 6
BASE_ICON_EXTENT = 14
BASE_STRIP_WIDTH = 32
BASE_MARGIN_LEFT = 4
BASE_MARGIN_TOP = 12
BASE_MARGIN_RIGHT = 2
BASE_MARGIN_BOTTOM = 12
BASE_SPACING = 6


class PaintedIconButton(QPushButton):
    """Circular button that paints its own vector icon."""

    def __init__(
        self,
        icon_name: str,
        object_name: str,
        checkable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Create a self-painted icon button with QPushButton semantics."""
        super().__init__(parent)
        self._icon_name = icon_name
        self._accent_color = QColor(DEFAULT_ACCENT_COLOR)
        self._scale = 1.0
        self.setObjectName(object_name)
        self.setProperty("icon_name", icon_name)
        self.setCheckable(checkable)
        self.setFixedSize(BASE_BUTTON_SIZE, BASE_BUTTON_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")
        self.setToolTip(_tooltip_for_icon(icon_name))

    @property
    def icon_extent(self) -> float:
        """Return the current square icon drawing extent."""
        return BASE_ICON_EXTENT * self._scale

    def set_accent_color(self, color: str) -> None:
        """Set the active-state icon color."""
        self._accent_color = QColor(color)
        self.update()

    def set_scale(self, scale: float) -> None:
        """Scale button and vector icon dimensions together."""
        self._scale = max(0.5, min(2.0, scale))
        size = round(BASE_BUTTON_SIZE * self._scale)
        self.setFixedSize(size, size)
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint circular background and the configured vector icon."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color, icon_color, border_color = self._colors_for_state()
        circle = QRectF(1, 1, self.width() - 2, self.height() - 2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(circle)
        if border_color is not None:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(border_color, 1))
            painter.drawEllipse(circle.adjusted(0.5, 0.5, -0.5, -0.5))

        painter.setPen(QPen(icon_color, 1.5 * self._scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        inset = BASE_ICON_INSET * self._scale
        _paint_icon(
            painter,
            self._icon_name,
            QRectF(inset, inset, self.icon_extent, self.icon_extent),
            icon_color,
        )

    def _colors_for_state(self) -> tuple[QColor, QColor, QColor | None]:
        """Return background, icon, and optional border colors for current state."""
        if self.isDown():
            return QColor(255, 255, 255, 56), QColor(255, 255, 255, 255), None
        if self.isCheckable() and self.isChecked():
            bg = QColor(self._accent_color)
            bg.setAlphaF(0.15)
            return bg, QColor(self._accent_color), None
        if self.underMouse():
            return (
                QColor(255, 255, 255, 38),
                QColor(255, 255, 255, 230),
                QColor(255, 255, 255, 42),
            )
        return QColor(255, 255, 255, 20), QColor(255, 255, 255, 90), None


class SideButtonsWidget(QWidget):
    """Vertical strip of compact action buttons."""

    notification_toggled = pyqtSignal(bool)
    zoom_in = pyqtSignal()
    zoom_out = pyqtSignal()
    settings_requested = pyqtSignal()
    power_toggled = pyqtSignal(bool)
    sound_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the six PRD-defined side buttons."""
        super().__init__(parent)
        self._scale = 1.0
        self.setFixedWidth(BASE_STRIP_WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            BASE_MARGIN_LEFT,
            BASE_MARGIN_TOP,
            BASE_MARGIN_RIGHT,
            BASE_MARGIN_BOTTOM,
        )
        self._layout.setSpacing(BASE_SPACING)

        self.notification_button = self._make_button("bell", "notification_button", True)
        self.notification_button.hide()
        self.zoom_out_button = self._make_button("minus", "zoom_out_button")
        self.zoom_in_button = self._make_button("plus", "zoom_in_button")
        self.settings_button = self._make_button("gear", "settings_button")
        self.power_button = self._make_button("power", "power_button", True)
        self.sound_button = self._make_button("mute", "sound_button", True)

        for button in [
            self.notification_button,
            self.zoom_out_button,
            self.zoom_in_button,
            self.settings_button,
            self.power_button,
            self.sound_button,
        ]:
            self._layout.addWidget(button)
        self._layout.addStretch(1)

        self.notification_button.toggled.connect(self.notification_toggled)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.settings_button.clicked.connect(self.settings_requested)
        self.power_button.toggled.connect(self.power_toggled)
        self.sound_button.toggled.connect(self.sound_toggled)

    def set_accent_color(self, color: str) -> None:
        """Set the active-state color for all checkable icon buttons."""
        for button in self.findChildren(PaintedIconButton):
            button.set_accent_color(color)

    def set_scale(self, scale: float) -> None:
        """Scale the side strip, button geometry, and layout rhythm."""
        self._scale = max(0.5, min(2.0, scale))
        self.setFixedWidth(round(BASE_STRIP_WIDTH * self._scale))
        self._layout.setContentsMargins(
            round(BASE_MARGIN_LEFT * self._scale),
            round(BASE_MARGIN_TOP * self._scale),
            round(BASE_MARGIN_RIGHT * self._scale),
            round(BASE_MARGIN_BOTTOM * self._scale),
        )
        self._layout.setSpacing(round(BASE_SPACING * self._scale))
        for button in self.findChildren(PaintedIconButton):
            button.set_scale(self._scale)

    def _make_button(
        self,
        icon_name: str,
        object_name: str,
        checkable: bool = False,
    ) -> PaintedIconButton:
        """Create a compact self-painted button."""
        return PaintedIconButton(icon_name, object_name, checkable, self)


def _tooltip_for_icon(icon_name: str) -> str:
    """Return a short tooltip for one icon."""
    labels = {
        "bell": "通知",
        "minus": "缩小",
        "plus": "放大",
        "gear": "展开",
        "power": "电源",
        "mute": "静音",
    }
    return labels[icon_name]


def _paint_icon(painter: QPainter, icon_name: str, rect: QRectF, color: QColor) -> None:
    """Dispatch vector icon painting."""
    if icon_name == "bell":
        _paint_bell(painter, rect)
    elif icon_name == "minus":
        _paint_minus(painter, rect)
    elif icon_name == "plus":
        _paint_plus(painter, rect)
    elif icon_name == "gear":
        _paint_gear(painter, rect)
    elif icon_name == "power":
        _paint_power(painter, rect)
    elif icon_name == "mute":
        _paint_mute(painter, rect, color)


def _paint_bell(painter: QPainter, rect: QRectF) -> None:
    """Paint a small notification bell outline."""
    path = QPainterPath()
    path.moveTo(rect.center().x(), rect.top() + 1)
    path.cubicTo(
        rect.right() - 1,
        rect.top() + 2,
        rect.right() - 1,
        rect.bottom() - 5,
        rect.right() - 2,
        rect.bottom() - 4,
    )
    path.lineTo(rect.left(), rect.bottom() - 4)
    path.cubicTo(
        rect.left() + 1,
        rect.bottom() - 5,
        rect.left() + 1,
        rect.top() + 2,
        rect.center().x(),
        rect.top() + 1,
    )
    painter.drawPath(path)
    painter.drawLine(
        QPointF(rect.left() + 3, rect.bottom() - 3),
        QPointF(rect.right() - 3, rect.bottom() - 3),
    )
    painter.drawEllipse(QPointF(rect.center().x(), rect.bottom() - 1), 1.3, 1.3)


def _paint_minus(painter: QPainter, rect: QRectF) -> None:
    """Paint a minus icon."""
    painter.drawLine(
        QPointF(rect.left() + 2, rect.center().y()),
        QPointF(rect.right() - 2, rect.center().y()),
    )


def _paint_plus(painter: QPainter, rect: QRectF) -> None:
    """Paint a plus icon."""
    _paint_minus(painter, rect)
    painter.drawLine(
        QPointF(rect.center().x(), rect.top() + 2),
        QPointF(rect.center().x(), rect.bottom() - 2),
    )


def _paint_gear(painter: QPainter, rect: QRectF) -> None:
    """Paint a compact gear icon."""
    center = rect.center()
    radius = rect.width() * 0.34
    painter.drawEllipse(center, radius, radius)
    painter.drawEllipse(center, radius * 0.34, radius * 0.34)
    for index in range(8):
        angle = math.radians(index * 45)
        inner = QPointF(
            center.x() + math.cos(angle) * radius,
            center.y() + math.sin(angle) * radius,
        )
        outer = QPointF(
            center.x() + math.cos(angle) * (radius + 2.2),
            center.y() + math.sin(angle) * (radius + 2.2),
        )
        painter.drawLine(inner, outer)


def _paint_power(painter: QPainter, rect: QRectF) -> None:
    """Paint the IEC power symbol."""
    painter.drawLine(
        QPointF(rect.center().x(), rect.top() + 1),
        QPointF(rect.center().x(), rect.top() + 7),
    )
    painter.drawArc(rect.adjusted(2, 3, -2, -1), 35 * 16, 290 * 16)


def _paint_mute(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Paint speaker and slash mute icon."""
    speaker = QPolygonF(
        [
            QPointF(rect.left() + 1, rect.center().y() - 3),
            QPointF(rect.left() + 4, rect.center().y() - 3),
            QPointF(rect.left() + 8, rect.top() + 2),
            QPointF(rect.left() + 8, rect.bottom() - 2),
            QPointF(rect.left() + 4, rect.center().y() + 3),
            QPointF(rect.left() + 1, rect.center().y() + 3),
        ]
    )
    painter.setBrush(color)
    painter.drawPolygon(speaker)
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(
        QPointF(rect.right() - 3, rect.top() + 2),
        QPointF(rect.right() - 1, rect.bottom() - 1),
    )
