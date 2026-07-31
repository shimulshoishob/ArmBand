# BioWave Change Log

This file records user-facing and technical changes made to the BioWave codebase.
It is written to explain both **what changed** and **why it changed**, so the
application can be maintained and improved without needing to reconstruct the
reasoning from the source code alone.

## 2026-08-01 — macOS performance, responsive layout, and visual refresh

### 1. Faster macOS mouse control

**Files changed:** `code/mouse.py`, `requirements.txt`, `README.md`

The adaptive mouse controller previously sent every pointer movement through
PyAutoGUI. On macOS, PyAutoGUI includes a small platform-specific pause for
each mouse event. That pause is useful for general automation scripts, but it
makes a real-time EMG-driven cursor feel slow and less responsive.

The controller now uses macOS Quartz events when Quartz is available. Quartz
is the native macOS graphics and input API, so pointer movement and clicks are
sent directly to the operating system instead of passing through PyAutoGUI's
extra timing layer.

Key improvements:

- Mouse movement uses a precise 120 Hz timer instead of a 60 Hz timer.
- Speed is now measured in **pixels per second**, rather than pixels per timer
  tick. This makes cursor speed consistent even if the event loop briefly runs
  slower or faster.
- The default movement speed is now 900 px/sec, which is substantially more
  responsive than the previous effective speed.
- The mouse safety stop remains in place: reaching a display corner disables
  control. The Quartz implementation checks every connected display, not only
  the main monitor.
- Left click, right click, and double click also use native Quartz events on
  macOS. PyAutoGUI remains available as a fallback on non-macOS platforms.
- Incoming EMG baseline calculations were vectorized with NumPy, reducing the
  amount of work performed on the GUI thread for each incoming data batch.

For macOS, `requirements.txt` now includes `pyobjc-framework-Quartz`, and the
README explains that macOS Accessibility permission must be granted to the
terminal or Python application before it can control the pointer.

### 2. macOS-aware rendering and fonts

**Files changed:** `code/main.py`, `code/app_theme.py`

The application now uses `Helvetica Neue` on macOS instead of a generic font.
This gives labels, controls, and dialogs a more natural macOS appearance.

The main startup path also enables high-DPI pixmaps and coalescing of frequent
input events on macOS. These changes help the application look sharp on Retina
displays and leave more of the GUI event loop available for plotting EMG data.

The live plot viewport now uses `MinimalViewportUpdate`. Rather than repainting
the entire high-resolution plot surface for a small trace update, Qt repaints
only the required region when possible. This reduces unnecessary drawing work,
especially on Retina displays.

### 3. Futuristic / cyberpunk visual theme

**Files changed:** `code/app_theme.py`, `code/main.py`

The former blue-and-teal interface was replaced with a darker futuristic visual
system. The new theme uses deep navy surfaces with cyan, teal, and violet neon
accents. It is applied globally, so it affects the main window and the existing
dialogs without changing their underlying workflows.

The refreshed theme includes:

- Layered dark surfaces that make panels easier to distinguish.
- Rounded buttons, inputs, tabs, and panels for a more modern appearance.
- Cyan primary actions, teal success feedback, and pink/red destructive or
  warning feedback.
- Violet scrollbars, neon checkbox/radio indicators, highlighted tables, and
  styled progress bars.
- A dedicated BioWave workstation header in the main window, with a live
  workspace indicator and a real-time EMG subtitle.

No EMG processing, calibration, data recording, or model-training behavior was
removed or changed by this visual redesign.

### 4. Screen-fitting and compact-display support

**Files changed:** `code/main.py`

The main window originally requested a fixed 1380 × 920 size. On smaller
MacBook displays, the row of controls imposed a minimum width of about 1915
pixels. Qt therefore enlarged the main window beyond the display boundary,
which made part of the interface inaccessible until the user manually zoomed
the window from the title bar.

This was corrected in two parts:

1. The application waits until macOS assigns the window to its actual display,
   then sizes it to 96% of the usable screen width and 90% of its usable height.
   Delaying this one event-loop turn is important for external and secondary
   displays, because their final geometry is not always available during the
   window constructor.
2. The wide rows in the main interface now live in horizontal scroll areas:
   - the instrumentation/control bar;
   - the workflow action row; and
   - the graph plus channel-status workspace.

Instead of allowing a wide row to make the whole application extend off-screen,
the window remains fully visible and only that row can scroll horizontally when
space is limited. On normal-sized monitors, the controls remain visible in the
same layout without needing to scroll.

Dialogs are also clamped to the usable display size before they are centered.
This prevents a large training, analysis, or configuration dialog from opening
partly beyond a smaller display.

### 5. Mouse controller visual alignment

**Files changed:** `code/mouse.py`

The Adaptive Mouse Controller now uses the same global theme as the main
BioWave application. Previously, it had its own older stylesheet, so its
colours, typography, button shapes, and tabs looked different from the main
dashboard.

The controller now has the same deep navy, cyan, violet, and pink cyberpunk
palette as the main application. It also has a matching header identifying it
as the **EMG-driven cursor interface**, and its enable/stop control uses the
shared success and danger button styles. This is a visual-only change: model
loading, device connection, gesture mappings, cursor safety, and pointer
performance continue to behave as before.

### 6. Fruit Catcher EMG training game

**Files changed:** `code/fruit_catcher_game.py`, `README.md`

Added a new standalone application called **Fruit Catcher**. It lets a user
load a trained Random Forest model, connect the streaming EMG device, and use
classified gestures to control a basket catching fruit falling from a tree.

How the game works:

1. Load the same `.joblib` Random Forest model used in the mouse controller.
2. Connect an ESP32 over Wi-Fi, a wired serial device, or select the local
   simulator option.
3. The game receives EMG batches, removes a slowly adapting baseline, collects
   the required model window, and sends it to the existing inference worker.
4. A confident label containing `left` moves the basket left. A confident label
   containing `right` moves it right. The required confidence can be adjusted
   in the game side panel.
5. Fruit falls continuously. A fruit landing over the basket increases the
   score; otherwise it increases the missed count.

The game draws its cyberpunk tree, fruit, grid, and basket directly with Qt's
painting API, so it does not need external image files. For testing without
hardware, it supports the existing local EMG simulator at
`socket://127.0.0.1:7000`. Keyboard controls (`A` / left arrow and `D` / right
arrow) are also included, which makes it possible to test the gameplay before
a model or device is ready.

Run the game with:

```text
python code/fruit_catcher_game.py
```

#### Wireless ESP32 support update

The game originally offered only the wired serial port and local simulator.
It now includes the same **Wireless Wi-Fi (ESP32)** connection mode as
`mouse.py`:

- ESP32 discovery over the project control protocol;
- manual IP entry when discovery cannot find a device;
- an access-key field for the authenticated ESP32 control channel;
- a UDP wireless stream listener for EMG/IMU packets;
- automatic keepalive pings while the game is connected; and
- a stop-stream command when the game disconnects or closes.

Wireless and wired/simulator connections are selected from the new connection
selector in the game setup panel. Both paths feed the same model inference and
basket-control logic, so a user can switch hardware transport without changing
the game or retraining the model.

### Validation completed

The following checks were run after these changes:

- Python syntax compilation for `code/main.py`, `code/mouse.py`, and
  `code/app_theme.py`.
- Headless startup checks for the main application and mouse controller.
- A compact 800 × 600 virtual-screen test confirming that the main window opens
  within the screen bounds (768 × 540) rather than expanding beyond them.
- Headless startup and game-loop checks for Fruit Catcher, including keyboard
  basket movement and animation-timer startup.
- Headless checks confirming that Fruit Catcher switches correctly between its
  wireless ESP32 and wired/simulator connection panels.

## Documentation policy

This change log will be updated whenever future code changes are made in this
workspace. Each entry will identify the relevant files, describe the behavior
that changed, explain the reason for the change, and note any validation that
was performed.
