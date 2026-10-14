"""A stand-in screen: says what it will be and shows a live line from the frames, so the shell is
visibly wired up before the real screens exist."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from evolution_simulator.session import Frame
from evolution_simulator.viewer.registry import ViewerContext


class Placeholder(QWidget):
    def __init__(
        self,
        context: ViewerContext,
        title: str,
        task: str,
        live: Callable[[Frame], str] | None = None,
    ) -> None:
        super().__init__()
        self.live = QLabel("waiting for the first frame")
        heading = QLabel(f"<b>{title}</b><br>to be built in {task}")
        layout = QVBoxLayout(self)
        for label in (heading, self.live) if live is not None else (heading,):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label)
        self._line = live
        if live is not None:
            context.controller.frame_received.connect(self._on_frame)
            if context.controller.frame is not None:
                self._on_frame(context.controller.frame)

    def _on_frame(self, frame: Frame) -> None:
        assert self._line is not None
        self.live.setText(self._line(frame))
