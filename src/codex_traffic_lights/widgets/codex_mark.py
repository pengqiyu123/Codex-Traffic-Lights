"""Shared Codex-style cloud terminal mark painter."""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen


def paint_codex_mark(painter: QPainter, rect: QRectF, *, with_shadow: bool = True) -> None:
    """Paint a blue-purple cloud mark with a terminal prompt glyph."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)

    cloud = _cloud_path(rect)
    if with_shadow:
        shadow = QColor(60, 80, 255, 68)
        painter.fillPath(cloud.translated(0, rect.height() * 0.05), shadow)

    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#D7C7FF"))
    gradient.setColorAt(0.45, QColor("#7C8BFF"))
    gradient.setColorAt(1.0, QColor("#2457FF"))
    painter.setPen(QPen(QColor(255, 255, 255, 92), max(1.0, rect.width() * 0.018)))
    painter.setBrush(gradient)
    painter.drawPath(cloud)

    glyph_pen = QPen(QColor(255, 255, 255, 226), max(2.0, rect.width() * 0.075))
    glyph_pen.setCapStyle(Qt.RoundCap)
    glyph_pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(glyph_pen)

    x = rect.left()
    y = rect.top()
    w = rect.width()
    h = rect.height()
    painter.drawLine(
        QPointF(x + w * 0.33, y + h * 0.38),
        QPointF(x + w * 0.44, y + h * 0.55),
    )
    painter.drawLine(
        QPointF(x + w * 0.44, y + h * 0.55),
        QPointF(x + w * 0.33, y + h * 0.72),
    )
    painter.drawLine(
        QPointF(x + w * 0.57, y + h * 0.69),
        QPointF(x + w * 0.73, y + h * 0.69),
    )

    painter.restore()


def paint_codex_title(painter: QPainter, rect: QRectF) -> None:
    """Paint the CODEX wordmark using the app's compact technical typography."""
    painter.save()
    font = QFont("Consolas", max(8, int(rect.height() * 0.58)), QFont.Bold)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
    painter.setFont(font)
    painter.setPen(QPen(QColor("#6A6A70")))
    painter.drawText(rect, Qt.AlignCenter, "CODEX")
    painter.restore()


def _cloud_path(rect: QRectF) -> QPainterPath:
    """Build the rounded cloud silhouette used by the product mark."""
    x = rect.left()
    y = rect.top()
    w = rect.width()
    h = rect.height()
    path = QPainterPath()
    path.moveTo(x + w * 0.24, y + h * 0.73)
    path.cubicTo(x + w * 0.09, y + h * 0.71, x + w * 0.04, y + h * 0.54, x + w * 0.13, y + h * 0.42)
    path.cubicTo(x + w * 0.12, y + h * 0.22, x + w * 0.32, y + h * 0.08, x + w * 0.48, y + h * 0.17)
    path.cubicTo(x + w * 0.61, y + h * 0.06, x + w * 0.83, y + h * 0.15, x + w * 0.84, y + h * 0.35)
    path.cubicTo(x + w * 0.99, y + h * 0.42, x + w * 0.96, y + h * 0.68, x + w * 0.79, y + h * 0.72)
    path.cubicTo(x + w * 0.69, y + h * 0.91, x + w * 0.39, y + h * 0.91, x + w * 0.31, y + h * 0.74)
    path.cubicTo(x + w * 0.29, y + h * 0.74, x + w * 0.26, y + h * 0.74, x + w * 0.24, y + h * 0.73)
    path.closeSubpath()
    return path
