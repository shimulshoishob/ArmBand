"""BioWave Fruit Catcher — an EMG-controlled training game.

Load the same Random Forest model used by the mouse controller, connect the
streaming device over serial (or the built-in simulator), and map gestures
whose names include "left" / "right" to basket movement.
"""

import os
import sys
import time
import random

import joblib
import numpy as np
import serial.tools.list_ports
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app_theme import apply_dark_theme, themed_button_style, themed_label_style
from mouse import (
    DEFAULT_ACCESS_KEY, WIFI_STREAM_PORT, ControlProtocol, DeviceInfo,
    InferenceWorker, KeepaliveWorker, SerialWorker, WirelessStreamWorker,
    get_local_ip_for_target,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TRAINED_MODEL_DIR = os.path.join(PROJECT_ROOT, "trained_model")


class FruitCatcherCanvas(QWidget):
    """Paints a self-contained neon fruit-catching scene without image assets."""

    direction_pressed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(390)
        self.setFocusPolicy(Qt.StrongFocus)
        self.basket_x = 0.5
        self.fruits = []
        self.score = 0
        self.missed = 0
        self.running = False

    def reset_game(self):
        self.basket_x = 0.5
        self.fruits = []
        self.score = 0
        self.missed = 0
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_A):
            self.direction_pressed.emit("left")
        elif event.key() in (Qt.Key_Right, Qt.Key_D):
            self.direction_pressed.emit("right")
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = self.rect()
        width, height = max(1, area.width()), max(1, area.height())

        # Night-sky gradient, horizon glow, and ground.
        painter.fillRect(area, QColor("#07101D"))
        for i in range(10):
            alpha = max(0, 48 - i * 4)
            painter.setPen(QPen(QColor(34, 211, 238, alpha), 1))
            y = int(height * 0.67 + i * height * 0.035)
            painter.drawLine(0, y, width, y)
        painter.setBrush(QBrush(QColor("#0C2434")))
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, int(height * 0.77), width, int(height * 0.23))

        # Stylised tree that drops the fruit.
        painter.setBrush(QBrush(QColor("#4C1D95")))
        painter.drawRoundedRect(int(width * 0.08), int(height * 0.20), int(width * 0.07), int(height * 0.60), 10, 10)
        painter.setBrush(QBrush(QColor("#0E7490")))
        for x, y, radius in ((0.10, 0.16, 0.12), (0.21, 0.13, 0.14), (0.31, 0.20, 0.13), (0.17, 0.28, 0.15)):
            painter.drawEllipse(int(width * (x - radius / 2)), int(height * (y - radius / 2)), int(width * radius), int(height * radius))

        # Falling fruits.
        fruit_colors = ("#FB7185", "#FBBF24", "#A3E635")
        for fruit in self.fruits:
            x = int(fruit["x"] * width)
            y = int(fruit["y"] * height)
            painter.setBrush(QBrush(QColor(fruit_colors[fruit["kind"] % len(fruit_colors)])))
            painter.setPen(QPen(QColor("#F8FAFC"), 1))
            painter.drawEllipse(x - 13, y - 13, 26, 26)
            painter.setPen(QPen(QColor("#5EEAD4"), 2))
            painter.drawLine(x, y - 13, x + 5, y - 21)

        # Basket / catch zone.
        basket_w = max(82, int(width * 0.14))
        basket_h = 42
        basket_x = int(self.basket_x * width - basket_w / 2)
        basket_y = int(height * 0.79)
        painter.setBrush(QBrush(QColor("#1E3A8A")))
        painter.setPen(QPen(QColor("#67E8F9"), 3))
        painter.drawRoundedRect(basket_x, basket_y, basket_w, basket_h, 9, 9)
        painter.setPen(QPen(QColor("#C084FC"), 3))
        painter.drawArc(basket_x + int(basket_w * 0.2), basket_y - 18, int(basket_w * 0.6), 28, 0, 180 * 16)

        painter.setFont(QFont("Helvetica Neue", 13, QFont.Bold))
        painter.setPen(QColor("#67E8F9"))
        painter.drawText(16, 28, "CATCH THE SIGNAL")
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(16, 54, f"SCORE  {self.score:03d}     MISSED  {self.missed:02d}")


class FruitCatcherGame(QMainWindow):
    """Game window that converts EMG classifier labels into basket movement."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BioWave — Fruit Catcher")
        self.resize(1100, 760)
        self.setMinimumSize(760, 600)

        self.model_loaded = False
        self.connected = False
        self.running = False
        self.worker = None
        self.keepalive_worker = None
        self.current_wireless_device = None
        self.discovered_devices = []
        self.inference_worker = InferenceWorker(500)
        self.inference_worker.prediction_ready.connect(self.on_prediction)
        self.inference_worker.start()
        self.num_channels = 4
        self.window_samples = 100
        self.stride_samples = 25
        self.sample_count = 0
        self.data_buffer = None
        self.baseline = None
        self.current_direction = ""
        self.last_tick = time.monotonic()
        self.last_spawn = 0.0

        self.build_ui()
        self.refresh_ports()

        self.game_timer = QTimer(self)
        self.game_timer.setTimerType(Qt.PreciseTimer)
        self.game_timer.setInterval(16)
        self.game_timer.timeout.connect(self.game_tick)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #16102B, stop:0.55 #112B4A, stop:1 #0B192B); "
            "border: 1px solid #7C3AED; border-radius: 14px; } QFrame QLabel { background: transparent; border: none; }"
        )
        h = QVBoxLayout(header)
        h.setContentsMargins(18, 12, 18, 12)
        title = QLabel("FRUIT CATCHER  //  EMG TRAINING MODE")
        title.setStyleSheet("font-size: 21px; font-weight: 800; letter-spacing: 1px; color: #F8FAFC;")
        note = QLabel("Move the basket with your LEFT and RIGHT gestures. Keyboard A/D or arrow keys also work for testing.")
        note.setStyleSheet("font-size: 11px; color: #67E8F9;")
        h.addWidget(title)
        h.addWidget(note)
        layout.addWidget(header)

        setup = QFrame()
        setup.setStyleSheet("QFrame { background: #111F35; border: 1px solid #29415F; border-radius: 10px; }")
        setup_layout = QHBoxLayout(setup)
        setup_layout.setContentsMargins(12, 10, 12, 10)
        setup_layout.addWidget(QLabel("MODEL"))
        self.model_label = QLabel("No model loaded")
        self.model_label.setStyleSheet(themed_label_style("muted"))
        setup_layout.addWidget(self.model_label, 1)
        browse = QPushButton("Load RF Model")
        browse.setStyleSheet(themed_button_style("accent"))
        browse.clicked.connect(self.load_model)
        setup_layout.addWidget(browse)
        setup_layout.addWidget(QLabel("CONNECTION"))
        self.connection_mode = QComboBox()
        self.connection_mode.addItem("Wireless Wi-Fi (ESP32)", "wireless")
        self.connection_mode.addItem("Wired Serial / Simulator", "serial")
        self.connection_mode.currentIndexChanged.connect(self.update_connection_page)
        setup_layout.addWidget(self.connection_mode)

        self.connection_stack = QStackedWidget()
        wireless_page = QWidget()
        wireless_layout = QHBoxLayout(wireless_page)
        wireless_layout.setContentsMargins(0, 0, 0, 0)
        wireless_layout.setSpacing(6)
        self.wireless_combo = QComboBox()
        self.wireless_combo.setEditable(True)
        self.wireless_combo.setMinimumWidth(170)
        self.wireless_combo.setPlaceholderText("ESP32 IP or discovered device")
        wireless_layout.addWidget(self.wireless_combo, 1)
        discover = QPushButton("Discover")
        discover.setStyleSheet(themed_button_style("muted"))
        discover.clicked.connect(self.discover_wireless_devices)
        wireless_layout.addWidget(discover)
        self.access_key_input = QLineEdit(DEFAULT_ACCESS_KEY)
        self.access_key_input.setPlaceholderText("ESP32 access key")
        self.access_key_input.setEchoMode(QLineEdit.Password)
        self.access_key_input.setMinimumWidth(130)
        wireless_layout.addWidget(self.access_key_input)
        self.connection_stack.addWidget(wireless_page)

        serial_page = QWidget()
        serial_layout = QHBoxLayout(serial_page)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(6)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(180)
        serial_layout.addWidget(self.port_combo, 1)
        refresh = QPushButton("Refresh")
        refresh.setStyleSheet(themed_button_style("muted"))
        refresh.clicked.connect(self.refresh_ports)
        serial_layout.addWidget(refresh)
        self.connection_stack.addWidget(serial_page)
        setup_layout.addWidget(self.connection_stack, 1)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setStyleSheet(themed_button_style("success"))
        self.connect_button.clicked.connect(self.toggle_connection)
        setup_layout.addWidget(self.connect_button)
        layout.addWidget(setup)

        game_row = QHBoxLayout()
        self.canvas = FruitCatcherCanvas()
        self.canvas.direction_pressed.connect(self.move_from_keyboard)
        game_row.addWidget(self.canvas, 1)
        side = QFrame()
        side.setMinimumWidth(230)
        side.setStyleSheet("QFrame { background: #111F35; border: 1px solid #29415F; border-radius: 10px; }")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(10)
        side_title = QLabel("NEURAL LINK")
        side_title.setStyleSheet("font-size: 14px; font-weight: 800; letter-spacing: 1px; color: #C084FC;")
        side_layout.addWidget(side_title)
        self.connection_label = QLabel("DEVICE: OFFLINE")
        self.connection_label.setStyleSheet(themed_label_style("muted"))
        side_layout.addWidget(self.connection_label)
        self.prediction_label = QLabel("GESTURE: --")
        self.prediction_label.setWordWrap(True)
        self.prediction_label.setStyleSheet("font-size: 16px; font-weight: 800; color: #67E8F9;")
        side_layout.addWidget(self.prediction_label)
        self.confidence_label = QLabel("CONFIDENCE: --")
        self.confidence_label.setStyleSheet(themed_label_style("muted"))
        side_layout.addWidget(self.confidence_label)
        side_layout.addWidget(QLabel("MIN CONFIDENCE"))
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(10, 99)
        self.confidence_spin.setValue(60)
        self.confidence_spin.setSuffix(" %")
        side_layout.addWidget(self.confidence_spin)
        side_layout.addSpacing(8)
        self.start_button = QPushButton("START GAME")
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet(themed_button_style("accent"))
        self.start_button.clicked.connect(self.toggle_game)
        side_layout.addWidget(self.start_button)
        reset = QPushButton("Reset Score")
        reset.setStyleSheet(themed_button_style("muted"))
        reset.clicked.connect(self.canvas.reset_game)
        side_layout.addWidget(reset)
        side_layout.addStretch(1)
        guide = QLabel("Gesture mapping:\n• labels containing LEFT move left\n• labels containing RIGHT move right\n\nTip: use the simulator port\nsocket://127.0.0.1:7000\nfor setup testing.")
        guide.setWordWrap(True)
        guide.setStyleSheet("font-size: 11px; color: #94A3B8;")
        side_layout.addWidget(guide)
        game_row.addWidget(side)
        layout.addLayout(game_row, 1)

    def update_connection_page(self):
        self.connection_stack.setCurrentIndex(self.connection_mode.currentIndex())

    def refresh_ports(self):
        current = self.port_combo.currentData() or ""
        self.port_combo.clear()
        self.port_combo.addItem("Simulator (local)", "socket://127.0.0.1:7000")
        for port in serial.tools.list_ports.comports():
            self.port_combo.addItem(f"{port.device} — {port.description}", port.device)
        index = self.port_combo.findData(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def discover_wireless_devices(self):
        self.wireless_combo.clear()
        try:
            self.discovered_devices = ControlProtocol.discover()
            for device in self.discovered_devices:
                self.wireless_combo.addItem(device.summary, device)
            if not self.discovered_devices:
                self.connection_label.setText("WIRELESS: NO ESP32 FOUND — ENTER IP")
                self.connection_label.setStyleSheet(themed_label_style("muted"))
            else:
                self.connection_label.setText(f"WIRELESS: {len(self.discovered_devices)} ESP32 DEVICE(S) FOUND")
                self.connection_label.setStyleSheet(themed_label_style("success"))
        except Exception as exc:
            QMessageBox.warning(self, "Wireless Discovery", str(exc))

    def load_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Random Forest Model", TRAINED_MODEL_DIR, "Joblib Files (*.joblib)")
        if not path:
            return
        try:
            artifact = joblib.load(path)
            model = artifact["model"]
            classes = artifact["class_names"]
            self.window_samples = int(artifact.get("window_samples", 100))
            self.stride_samples = int(artifact.get("stride_samples", 25))
            input_channels = artifact.get("input_channels")
            if input_channels is None:
                # Match the compatibility handling in the mouse controller
                # for older model artifacts that predate this metadata.
                feature_count = getattr(model, "n_features_in_", 0)
                input_channels = {70: 4, 156: 8, 231: 11}.get(feature_count, 4)
            self.num_channels = int(input_channels)
            self.data_buffer = np.zeros((self.num_channels, self.window_samples), dtype=np.float32)
            self.baseline = np.zeros(self.num_channels, dtype=np.float32)
            self.inference_worker.load_model(model, classes)
            self.model_loaded = True
            self.model_label.setText(os.path.basename(path))
            self.model_label.setStyleSheet(themed_label_style("success"))
            self.update_ready_state()
        except Exception as exc:
            QMessageBox.critical(self, "Model Error", f"Could not load the model:\n{exc}")

    def toggle_connection(self):
        if self.connected:
            self.disconnect_device()
            return
        if not self.model_loaded:
            QMessageBox.warning(self, "Model Required", "Load an RF model before connecting the device.")
            return
        try:
            if self.connection_mode.currentData() == "wireless":
                selected = self.wireless_combo.currentData()
                if isinstance(selected, DeviceInfo):
                    target_ip = selected.ip
                else:
                    target_ip = self.wireless_combo.currentText().strip().split()[0]
                if not target_ip:
                    QMessageBox.warning(self, "Wireless Device", "Discover an ESP32 or enter its Wi-Fi IP address.")
                    return
                access_key = self.access_key_input.text().strip() or DEFAULT_ACCESS_KEY
                self.worker = WirelessStreamWorker(WIFI_STREAM_PORT)
                self.worker.batch_received.connect(self.on_batch)
                self.worker.error_occurred.connect(lambda message: QMessageBox.warning(self, "Wireless Stream Error", message))
                self.worker.start()
                ControlProtocol.start_stream(target_ip, access_key, get_local_ip_for_target(target_ip), WIFI_STREAM_PORT)
                self.keepalive_worker = KeepaliveWorker(target_ip, access_key)
                self.keepalive_worker.ping_failed.connect(lambda message: print(f"Game keepalive notice: {message}"))
                self.keepalive_worker.start()
                self.current_wireless_device = (target_ip, access_key)
                connection_text = f"ESP32: STREAMING FROM {target_ip}"
            else:
                port = self.port_combo.currentData()
                if not port:
                    return
                self.worker = SerialWorker(port, 921600, self.num_channels, batch_size=self.stride_samples)
                self.worker.batch_received.connect(self.on_batch)
                self.worker.error_occurred.connect(lambda message: QMessageBox.warning(self, "Device Error", message))
                self.worker.start()
                connection_text = "DEVICE: STREAMING"

            self.connected = True
            self.connect_button.setText("Disconnect")
            self.connect_button.setStyleSheet(themed_button_style("danger"))
            self.connection_label.setText(connection_text)
            self.connection_label.setStyleSheet(themed_label_style("success"))
            self.update_ready_state()
        except Exception as exc:
            self.disconnect_device()
            QMessageBox.critical(self, "Connection Error", str(exc))

    def disconnect_device(self):
        self.stop_game()
        if self.keepalive_worker:
            self.keepalive_worker.stop()
            self.keepalive_worker = None
        if self.current_wireless_device:
            target_ip, access_key = self.current_wireless_device
            try:
                ControlProtocol.stop_stream(target_ip, access_key)
            except Exception:
                pass
            self.current_wireless_device = None
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.connected = False
        self.connect_button.setText("Connect")
        self.connect_button.setStyleSheet(themed_button_style("success"))
        self.connection_label.setText("DEVICE: OFFLINE")
        self.connection_label.setStyleSheet(themed_label_style("muted"))
        self.update_ready_state()

    def update_ready_state(self):
        self.start_button.setEnabled(self.model_loaded and self.connected)

    def on_batch(self, batch):
        if self.data_buffer is None:
            return
        if isinstance(batch, dict):
            batch = batch.get("batch")
        if batch is None:
            return
        batch = np.asarray(batch, dtype=np.float32)
        if batch.ndim != 2 or not len(batch):
            return
        if batch.shape[1] < self.num_channels:
            batch = np.pad(batch, ((0, 0), (0, self.num_channels - batch.shape[1])))
        batch = batch[:, :self.num_channels]
        self.baseline *= 0.95
        self.baseline += 0.05 * np.mean(batch, axis=0, dtype=np.float32)
        incoming = (batch - self.baseline).T
        count = min(incoming.shape[1], self.window_samples)
        self.data_buffer[:, :-count] = self.data_buffer[:, count:]
        self.data_buffer[:, -count:] = incoming[:, -count:]
        self.sample_count += count
        if self.sample_count >= self.stride_samples:
            self.sample_count = 0
            self.inference_worker.submit_window(self.data_buffer.copy())

    def on_prediction(self, label, confidence):
        confidence_pct = confidence * 100
        self.prediction_label.setText(f"GESTURE: {label.upper()}")
        self.confidence_label.setText(f"CONFIDENCE: {confidence_pct:.1f}%")
        label_lower = label.lower()
        if confidence_pct >= self.confidence_spin.value() and "left" in label_lower:
            self.current_direction = "left"
        elif confidence_pct >= self.confidence_spin.value() and "right" in label_lower:
            self.current_direction = "right"
        else:
            self.current_direction = ""

    def move_from_keyboard(self, direction):
        if self.running:
            self.move_basket(direction, 0.055)

    def move_basket(self, direction, amount):
        delta = -amount if direction == "left" else amount
        self.canvas.basket_x = min(0.95, max(0.05, self.canvas.basket_x + delta))

    def toggle_game(self):
        if self.running:
            self.stop_game()
        else:
            self.canvas.reset_game()
            self.running = True
            self.canvas.running = True
            self.last_tick = time.monotonic()
            self.last_spawn = self.last_tick
            self.start_button.setText("STOP GAME")
            self.start_button.setStyleSheet(themed_button_style("danger"))
            self.canvas.setFocus()
            self.game_timer.start()

    def stop_game(self):
        self.running = False
        self.canvas.running = False
        self.game_timer.stop()
        if hasattr(self, "start_button"):
            self.start_button.setText("START GAME")
            self.start_button.setStyleSheet(themed_button_style("accent"))

    def game_tick(self):
        now = time.monotonic()
        elapsed = min(0.05, max(0.001, now - self.last_tick))
        self.last_tick = now
        if self.current_direction:
            self.move_basket(self.current_direction, elapsed * 0.72)
        if now - self.last_spawn > 0.72:
            self.canvas.fruits.append({"x": random.uniform(0.25, 0.93), "y": 0.10, "kind": random.randrange(3)})
            self.last_spawn = now
        caught_y = 0.79
        survivors = []
        for fruit in self.canvas.fruits:
            fruit["y"] += elapsed * 0.24
            if fruit["y"] >= caught_y:
                if abs(fruit["x"] - self.canvas.basket_x) <= 0.09:
                    self.canvas.score += 1
                else:
                    self.canvas.missed += 1
            else:
                survivors.append(fruit)
        self.canvas.fruits = survivors
        self.canvas.update()

    def closeEvent(self, event):
        self.disconnect_device()
        self.inference_worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_dark_theme(app, font_size=15)
    window = FruitCatcherGame()
    window.show()
    sys.exit(app.exec_())
