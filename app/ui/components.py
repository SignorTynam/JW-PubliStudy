from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def section_card(
    title: str = "",
    description: str = "",
    parent: QWidget | None = None,
    object_name: str = "SectionCard",
) -> tuple[QFrame, QVBoxLayout, QLabel, QLabel]:
    card = QFrame(parent)
    card.setObjectName(object_name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)

    title_label = QLabel(title)
    title_label.setObjectName("SectionTitle")
    title_label.setWordWrap(True)
    description_label = QLabel(description)
    description_label.setObjectName("SectionDescription")
    description_label.setWordWrap(True)

    layout.addWidget(title_label)
    if description:
        layout.addWidget(description_label)
    return card, layout, title_label, description_label


def metric_card(parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout, QLabel, QLabel]:
    card = QFrame(parent)
    card.setObjectName("MetricCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(8)

    value = QLabel()
    value.setObjectName("MetricValue")
    label = QLabel()
    label.setObjectName("MetricLabel")
    label.setWordWrap(True)
    layout.addWidget(value)
    layout.addWidget(label)
    return card, layout, value, label


def info_row(label: QLabel, value: QLabel) -> QFrame:
    row = QFrame()
    row.setObjectName("InfoRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(12)
    label.setObjectName("FieldLabel")
    value.setObjectName("DetailMeta")
    value.setWordWrap(True)
    layout.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)
    layout.addWidget(value, 1)
    return row


def status_badge(parent: QWidget | None = None) -> QLabel:
    label = QLabel(parent)
    label.setObjectName("StatusBadge")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setProperty("status", "neutral")
    return label

