# BioWave Change Log

This file records user-facing and technical changes made to the BioWave codebase.
It is written to explain both **what changed** and **why it changed**, so the
application can be maintained and improved without needing to reconstruct the
reasoning from the source code alone.

## 2026-08-15 — Adaptive mouse control for better comparison against trackpad/mouse

**Files changed:** `code/mouse.py`

The EMG cursor controller in `code/mouse.py` was previously constant-speed:
each mapped direction gesture moved the pointer at a fixed pixel rate until the
gesture was released. For an ISO 9241-9 / Fitts' law comparison against a normal
mouse or trackpad this has two predictable weaknesses — coarse overshoot on
large movements, and no way to do slow, precise final positioning. Together
those inflate movement time, produce wandering paths (low path efficiency), and
cause re-entries and reversals. This change adds three controls to close that
gap, each tunable in the **3. Control Settings** tab:

### 1. Adaptive rate control (hold gesture to speed up)

Each time a new direction gesture is held, the cursor starts slow for precise
entry into a target and ramps toward full speed over roughly a quarter second.
Re-engaging a direction restarts the ramp, so the short flicks used for fine
corrections stay slow and gentle while long held movements keep full speed. The
result is a smoother approach curve (fewer overshoots, reversals, and
re-entries) without a distance-based "autopilot" that would make the Fitts
comparison unfair. Disable the `Adaptive Rate` checkbox for constant-speed
control, which is useful for an A/B comparison within the thesis itself.

### 2. Confidence-gear speed scaling (fixed and smoothed)

Cursor speed is now scaled continuously by the smoothed classifier confidence
between a floor of 70% of the set speed (at the confidence threshold) and full
speed (at 100% confidence). The old code only applied a speed factor when the
gesture was already accepted, and it had an inverted fallback that ran at full
speed for low-confidence predictions. The smoothed confidence removes the abrupt
fast/slow snapping as predictions jitter near the threshold, so direction flips
while confidence is low feel less violent.

### 3. Click debounce (hold-to-confirm) and one-click-per-activation

A mapped click gesture no longer fires on the first prediction. The gesture must
be sustained for the `Click Debounce Hold` duration (default 150 ms) before the
click is delivered, and each activation produces exactly one click until the
gesture returns to a non-click action. This suppresses spurious clicks from
classifier flicker, which directly lowers the Fitts error rate.

### 4. Scroll Up / Scroll Down mouse actions

Two new actions (`Scroll Up`, `Scroll Down`) were added to the action mapper so
the armband can scroll documents and web pages, which matters for the qualitative
"everyday tasks" part of the comparison. Scrolling uses native Quartz wheel events
on macOS (line-scroll unit) with a per-second line rate set by the new **Scroll
Speed** control, and falls back to `pyautogui.scroll` elsewhere, matching
PyAutoGUI's sign convention (positive = up). The live status bar now also shows
the current effective cursor speed so the ramp behavior can be watched while
tuning.

**Methodology note:** the ISO 9241-9 panel already supports a `new_emg` test
condition. To report the impact of these changes, record one block with
`Adaptive Rate` **enabled** (new device) and one with it **disabled** (old
device) under the same target layout, then compare block throughput, error rate,
and path efficiency in the exported CSVs.

### 5. Thesis comparison analysis and figures

**Files changed:** `code/compare_devices.py`, `requirements.txt`, `README.md`

Added `code/compare_devices.py`, a standalone analysis script that loads the
exported Fitts/ISO 9241-9 CSVs (trials, `*_block_summary`, `*_regression`) from
any folder, normalises both the current and the older `compare_mouse` log
schema, and renders comparison figures so the `normal_mouse` baseline, the old
constant-speed EMG device, and the improved adaptive-rate EMG device can be
compared visually. Each figure is saved as PNG and PDF into
`comparison_report/`, plus a `comparison_summary.csv` aggregate table and a
printed interpretation:

- throughput per device (with per-trial dots and per-block means),
- Fitts' law MT-vs-ID regression scatter with fitted lines and R²,
- click error / wrong-target / spurious-click rates,
- path efficiency, re-entries, and reversals,
- throughput-by-ID-band to show behaviour at increasing difficulty,
- a combined 2×2 `overview_all_metrics` figure for reuse in the thesis.

`requirements.txt` now includes `matplotlib` and `pandas` for the analysis
script.

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

### 7. ISO 9241-9 / Fitts' Law metrics for adaptive mouse control

**Files changed:** `code/mouse.py`, `README.md`

Added `FittsMetricsCollector`, a self-contained `QObject` that measures the
quality of EMG-driven cursor target acquisition without changing any existing
streaming, classification, movement, or click-control logic. The collector is
only called through lightweight hooks in the existing mouse-motion and click
methods while an ISO trial is active.

Each trial records the cursor start position, target centre and diameter,
movement time (MT), distance (D), nominal width (W), effective width (We),
effective index of difficulty (IDe), and throughput (TP). It also measures
path efficiency, time to first movement, target re-entries, X/Y directional
reversals, and whether the generated click was correct or an error.

Metrics are collected at the existing 120 Hz mouse-control cadence. Cursor
positions are used to calculate travelled path length and an effective-width
estimate. The implementation uses safe fallbacks when a trial has very few
samples so We, path length, and all derived values remain valid.

Trials are grouped into blocks of 20 by default. At block completion, the app
calculates mean and standard-deviation throughput, error rate, mean path
efficiency, mean re-entry count, and mean reversal count. The Fitts panel
shows the latest completed block summary.

The new collapsible **Fitts Metrics (ISO 9241-9)** panel in the mouse
controller lets a user select the CSV location, start a trial by entering a
target's X/Y location and width, inspect trial/block status, and manually save
the log. Completed trials are also automatically written to the CSV, with a
flush after every row, so the current session is retained even if the app later
stops unexpectedly. CSV floats are rounded to four decimal places.

### 8. Mouse controller readability and comparison labels

**Files changed:** `code/mouse.py`, `README.md`

The mouse controller window is now wider by default (820 px), with a larger
minimum size, 16 px standard labels/fields, taller text inputs and spin boxes,
larger group titles, buttons with a minimum readable height, and a clearer
32 px live-prediction label. The header subtitle and safety message were also
increased. This makes connection controls, model mappings, confidence/speed
settings, and Fitts controls legible without relying on tiny UI text.

The Fitts panel now includes a **Test System** selector: `normal_mouse`,
`old_emg`, and `new_emg`. The selected value is stored on each new trial so
multiple conditions can be exported to one CSV and compared later. The README
documents a fair comparison protocol: use the same target schedule and
settings, then compare block throughput, error rate, and path efficiency.

The controller also runs a one-time post-show sizing pass, allowing the larger
readable layout to adapt to the display where macOS finally places the window.

### 9. Fullscreen mouse-controller layout and clearer Fitts guidance

**Files changed:** `code/mouse.py`, `README.md`

The mouse controller now opens maximized. This gives the app enough room to
show the EMG connection/mapping controls and the ISO metrics interface at the
same time, rather than forcing the user to open a compressed section in a
narrow vertical layout.

The Fitts metrics group was moved from the bottom of the window to a dedicated
right-hand panel. It is no longer collapsed by default, has a fixed readable
width, and begins with a plain-language four-step guide: choose the system,
start a trial, move/click the target, and let the app save the result. This
keeps the explanation, test-system selector, CSV controls, status, and action
buttons visible without reducing the size of the main controller controls.

### 10. Visual Fitts target and physical-mouse baseline support

**Files changed:** `code/mouse.py`, `README.md`

Added a full-screen visual target overlay for the Fitts test workflow. Selecting
**Start Visual Target** now places a glowing circular target at a usable random
location on the active display, away from the initial cursor position. The
overlay explains the task, shows crosshairs around the target, and closes after
the trial completes. `Esc` cancels an incomplete trial without writing a row.

The overlay samples normal physical pointer motion and captures physical mouse
clicks, in addition to the existing EMG-generated click hook. This means the
same guided target test can now be used to collect `normal_mouse`, `old_emg`,
and `new_emg` conditions in a single CSV, using the Test System selector. The
README was corrected to reflect that an external physical-click harness is no
longer required for the normal-mouse baseline.

### 11. Automated multi-target Fitts blocks

**Files changed:** `code/mouse.py`, `README.md`

Added **Start Full Test (20 Targets)** to the right-hand Fitts panel. It starts
a clean metrics block and presents targets one at a time, automatically moving
to the next after each click. The default block contains a balanced shuffled
mix of four target diameters: 40, 60, 80, and 120 pixels. Target locations are
also generated away from the current cursor position, so each trial requires a
meaningful movement.

After the twentieth target, the collector completes the block and reports the
combined mean throughput and standard deviation, error rate, path efficiency,
re-entry count, and reversal count. This provides one comparable result for
each system condition rather than requiring manual calculations from individual
targets. The sequence automatically respects a different configured block size
if that value is changed in code.

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
- Fitts collector unit-style checks covering correct and incorrect clicks,
  first-movement timing, completed-block summary generation, CSV columns and
  export, plus a headless mouse-controller UI check for the new panel.
- Headless visual-target checks confirming that an overlay opens, activates an
  ISO trial, and cancels safely without persisting an incomplete row.
- Automated multi-target checks confirming target-by-target advancement and a
  combined block summary after the final target.

## Documentation policy

This change log will be updated whenever future code changes are made in this
workspace. Each entry will identify the relevant files, describe the behavior
that changed, explain the reason for the change, and note any validation that
was performed.
