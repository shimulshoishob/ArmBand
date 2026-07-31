# Project Workflow Overview

This document explains how the entire ArmBand / BioWave-GUI project works, what each main component is for, why that technology was chosen, what alternatives exist, and how the project can be improved.

---

## 1. What this project is doing

This repository is a complete EMG-based gesture recognition pipeline.

In simple words:

1. Read EMG signals from a device or simulator.
2. Clean and analyze the data in real time.
3. Collect labeled gesture recordings.
4. Convert signals into feature windows.
5. Train a Random Forest classifier.
6. Load that trained model and classify new gestures live.

So the project is not just one script. It is a full system with:

- a GUI desktop app,
- a simulator for development,
- a training pipeline,
- a real-time inference engine,
- a hardware communication layer for ESP32-S3,
- dataset and model artifacts.

---

## 2. High-level system view

The project has four major layers:

### Layer 1 — Device / data source

- The app can connect to:
  - wired COM serial input,
  - TCP simulator input,
  - wireless ESP32-S3 UDP streaming.

This layer provides raw EMG and IMU data.

### Layer 2 — Live processing

- The app shows live plots.
- It computes signal metrics.
- It calibrates baseline thresholds.
- It can collect labeled data for training.

### Layer 3 — Training pipeline

- The stored CSV sessions are converted into sliding windows.
- Features are extracted for each window.
- A Random Forest model is trained.
- Metrics and confusion matrix are saved.

### Layer 4 — Prediction / inference

- The trained model is loaded into the desktop app.
- New windows are converted into features.
- The model outputs a predicted gesture.
- A smoothing logic improves the final displayed class label.

---

## 3. Repository structure and purpose

### Root files

#### README.md

Purpose:

- explains the bigger picture,
- gives setup instructions,
- tells how to run the application.

Why it exists:

- new users need clear onboarding.

Alternative:

- a full docs site or Sphinx documentation,
- better if the project grows and multiple people need more searchable documentation.

### requirements.txt

Purpose:

- lists dependencies required for Python execution.

Used packages:

- `numpy` → numerical array math and FFT handling.
- `PyQt5` → desktop GUI framework.
- `pyqtgraph` → real-time plotting of EMG waveforms.
- `pyserial` → serial communication with hardware or USB devices.
- `joblib` → parallel feature extraction and model serialization.
- `scikit-learn` → Random Forest training and metrics.
- `PyWavelets` → optional wavelet feature support.

Alternatives:

- `PySide6` instead of `PyQt5`
- `matplotlib` for plotting, but it is less suited for continuous live plots
- `xgboost` or `lightgbm` for classification, but the current project already uses Random Forest and keeps the pipeline lightweight

---

## 4. Main folders

### code/

This folder contains the actual application logic.

#### main.py

This is the main desktop application.

It is the core of the whole project because it contains:

- connection dialogs,
- serial and wireless workers,
- calibration logic,
- live plotting,
- data recording,
- training UI,
- model loading,
- real-time gesture classification.

This file is effectively the “brain” of the system.

Why this file is large:

- the app includes multiple workflows in one place,
- it is more convenient for a student project than splitting everything into dozens of small modules.

Alternative:

- split into smaller modules such as:
  - `connection.py`
  - `calibration.py`
  - `recording.py`
  - `training.py`
  - `inference.py`
  - `ui.py`
- this makes the code easier to maintain and test.

### emg_simulator_app.py

Purpose:

- generates synthetic EMG-like data for development and testing.

Why it exists:

- you can test the main app without hardware.
- it helps local debugging for GUI and streaming logic.

How it works:

- it creates channels with a base level plus a periodic EMG signal burst,
- it can stream over TCP or serial,
- it simulates different motion phases such as rest, flex, group activity, and wave patterns.

Alternative:

- use a prerecorded CSV playback tool,
- use a hardware-in-the-loop simulator,
- use the ESP32 hardware directly.

### rf_features.py

Purpose:

- defines the feature extraction contract used for both training and inference.

Why this file is important:

- if training features and inference features are not perfectly aligned, the model will be wrong even if it trains nicely.

This file computes:

- MAV (mean absolute value)
- RMS
- IEMG
- variance
- waveform length
- zero crossings
- slope sign changes
- Willison amplitude
- mean / median / peak frequency
- spectral entropy
- band power in 20–60 Hz, 60–120 Hz, 120–220 Hz
- RMS ratio features
- pairwise channel correlations

Why these features are used:

- EMG signals are not easy to classify directly from raw samples,
- statistical and spectral descriptors capture gesture-specific patterns better than raw values.

Alternative:

- use raw time samples directly with CNNs,
- use STFT or wavelet features,
- use handcrafted features from a smaller subset only.

### train_rf_model_gui.py

Purpose:

- an older or smaller standalone trainer UI.

Why it is here:

- it is useful for older 4-channel CSV workflows.

Alternative:

- remove it and rely only on the integrated trainer inside `main.py`.
- or keep it as a legacy helper.

### app_theme.py

Purpose:

- centralizes the dark theme styling of the GUI.

Why it exists:

- consistent UI,
- faster theme changes,
- reusable styling rules.

Alternative:

- hardcode styles inside each widget,
- use a CSS-like style system directly in every window,
- migrate to a modern styling system later.

---

## 5. How the data flows from input to label

Here is the full pipeline in simple steps.

### Step A — Connection

The app receives data through one of three plumbing paths:

- serial wired stream,
- TCP simulator,
- UDP ESP32 wireless stream.

### Step B — Normalize the incoming data

The app converts data into a common internal structure, usually a batch of numeric samples.

This is important because the rest of the app expects a consistent format regardless of hardware source.

### Step C — Plot and analyze live signals

The app calculates current signal metrics from recent samples:

- RMS,
- frequency content,
- correlation,
- baseline drift,
- signal quality indicators.

### Step D — Calibration

Before training or live prediction, the app calibrates rest and flex baseline levels.

This matters because EMG amplitude depends on:

- sensor placement,
- skin contact,
- individual strength,
- noise.

Calibration normalizes those differences.

### Step E — Record labeled sessions

The user collects gesture samples with labels like:

- Left,
- Right,
- fist_close.

The data is stored as a CSV plus a metadata text file in `dataset/`.

### Step F — Build windows

The stored signal is broken into overlapping windows.

This is needed because a single gesture is not just one point; it is a sequence over time.

Why windows:

- classification should be based on short temporal neighborhoods,
- it creates many training examples from one recording.

### Step G — Feature extraction

Each window is converted into a fixed-size vector of engineered features.

This is what the Random Forest actually learns from.

### Step H — Train Random Forest

A Random Forest learns decision rules from those feature vectors.

Why Random Forest here:

- fast enough for live inference,
- works well on tabular engineered features,
- easier to interpret than deep learning,
- good for small to medium EMG datasets.

### Step I — Save model artifact

The trained classifier and metadata are saved under `trained_model/`.

This gives reusable inference artifacts.

### Step J — Real-time prediction

A new incoming window is feature-extracted in the same way as the training windows.

Then the model outputs a predicted gesture label.

A small majority-vote smoothing window may be applied so the UI does not flicker between classes.

---

## 6. Why the project uses these technologies

### PyQt5 + pyqtgraph

Why:

- desktop UI is needed,
- pyqtgraph is better for low-latency real-time waveform plotting than many other plotting tools.

Alternatives:

- Tkinter for simpler GUI,
- Electron for cross-platform desktop but heavier,
- Kivy for mobile-like UI but less conventional for this project.

### NumPy

Why:

- EMG processing is array-heavy,
- FFT, correlation, windowing, and matrix math are all easier and faster in NumPy.

Alternative:

- pure Python loops, but much slower.

### Serial + UDP + TCP workers

Why:

- different input sources need different transport mechanisms,
- separate threads prevent the UI from freezing.

Alternatives:

- single-threaded polling,
- websockets or MQTT for a networked system,
- ROS if the project were larger and more modular.

### Random Forest

Why:

- the project uses engineered features, not raw waveform pixels,
- Random Forest is simple, stable, and good with tabular data,
- inference time is practical for real-time use.

Alternatives:

- SVM
- k-NN
- Gradient Boosting
- CNN / 1D deep learning

### Joblib parallelism

Why:

- feature extraction across many windows is independent,
- parallelism reduces training time for large datasets.

Alternative:

- multiprocessing,
- Dask,
- vectorized batch processing.

---

## 7. The “complex” parts broken down simply

### 7.1 Wireless protocol handling

The wireless firmware uses UDP packets with a `BWIM` header and 5 frames per packet.

Complex part:

- the packet contains both EMG and IMU information,
- the desktop app must parse a binary structure correctly.

Simple breakdown:

- read header,
- confirm magic bytes,
- verify frame size,
- unpack each frame,
- extract EMG channels and IMU orientation values,
- convert them into NumPy rows.

Why this works:

- it is a compact binary protocol for low-latency streaming.

Alternative:

- ASCII JSON or CSV over UDP,
- simpler to debug but more bandwidth-heavy.

### 7.2 Feature extraction contract

The model expects one exact feature shape.

Complex part:

- training and inference must always use the same features.

Simple breakdown:

- a window becomes a matrix of samples,
- a vectorized math path extracts the same descriptors on every channel,
- a fixed ordered vector is returned.

Why it matters:

- otherwise the model learns from one feature space and predicts in another.

Alternative:

- use a trained deep model that learns features directly from raw windows.

### 7.3 Group-aware train/test split

This is one of the most important details in the code.

Complex part:

- overlapping windows from the same recording can leak into both training and test sets,
- this can make accuracy look unrealistically high.

Simple breakdown:

- each segment gets a group ID,
- the split keeps all windows from a source recording on one side of the boundary,
- if that is impossible, it falls back to a stratified split.

Why this is better:

- accuracy becomes more trustworthy.

Alternative:

- random split of all windows, which is easier but less honest.

### 7.4 Real-time inference worker

This part runs in a background thread.

Why:

- the GUI should never block waiting for inference.

Simple breakdown:

- the app submits a new window,
- the worker extracts features,
- the model predicts,
- the result is emitted back to the UI.

Alternative:

- perform inference directly in the UI thread,
- not recommended because the UI would lag.

---

## 8. What each folder/file really contributes

### dataset/

Purpose:

- stores raw labeled recordings.

Each recording bundle usually has:

- a CSV with signal values,
- metadata with recording context.

Why it matters:

- models can only be as good as the data used to train them.

### trained_model/

Purpose:

- stores trained model artifacts and evaluation outputs.

Typical contents:

- `rf_realtime_model.joblib`
- `training_setup.json`
- `training_results.json`
- `training_summary.txt`
- `classification_report.txt`
- `confusion_matrix.csv`

Why it matters:

- model reproducibility,
- later reuse without retraining,
- better evaluation and documentation.

---

## 9. Why the model is saved as `.joblib`

`joblib` is used to serialize the trained artifact.

Why not just `.pkl`:

- `joblib` is efficient for NumPy-heavy objects,
- it is standard in sklearn workflows.

Alternative:

- `pickle`
- ONNX export
- a dedicated model registry or MLflow artifact store

For this project, `.joblib` is simple and practical.

---

## 10. Practical workflow of how a user would use the project

### Development / testing flow

1. Run `emg_simulator_app.py`.
2. Open `main.py`.
3. Connect using TCP `socket://127.0.0.1:7000`.
4. Watch the live signal.
5. Calibrate channels.
6. Record labeled gestures.
7. Train RF model.
8. Load the model.
9. Use real-time prediction.

### Hardware flow

1. Flash ESP32-S3 firmware.
2. Provision Wi-Fi over USB.
3. Discover the device on the local network.
4. Connect in wireless mode.
5. Live-stream EMG + IMU data.
6. Collect recordings.
7. Train and infer in the same app.

---

## 11. What is good about the current design

### Strengths

- The app is end-to-end.
- It supports both simulation and real hardware.
- It stores training artifacts in a reproducible way.
- It uses a clear feature contract between training and inference.
- It separates UI, processing, and model training into major responsibilities.

---

## 12. What can be improved

### 12.1 Code organization

The biggest improvement would be modularization.

Right now, `main.py` is doing too much.

Better structure:

- connection handling in one module,
- UI window logic in another,
- training logic in another,
- feature extraction in one shared module,
- model inference in another.

### 12.2 Better model strategy

A Random Forest is acceptable, but the project could improve by trying:

- Gradient Boosting,
- Extra Trees,
- SVM,
- MLP,
- lightweight 1D CNN if enough data is available.

For EMG, deep models become better when the dataset gets larger and more standardized.

### 12.3 Data quality management

The project would improve with:

- better quality checks before training,
- missing-label detection,
- outlier rejection,
- channel normalization,
- per-subject calibration.

### 12.4 More robust software design

Potential improvements:

- unit tests for feature extraction,
- test coverage for window generation,
- CI/CD pipeline,
- clearer logging,
- typed configuration objects,
- standardized configuration files instead of many UI defaults.

### 12.5 Better real-time pipeline

Potential upgrades:

- asynchronous scoring pipeline,
- queue-based buffer management,
- adaptive window timing,
- smoother session persistence,
- better drift correction for EMG baseline.

---

## 13. What the project is doing conceptually

At a deeper level, the project is building a small machine learning system for biosignal recognition.

It is a classic pattern:

1. collect signals,
2. engineer features,
3. train classifier,
4. infer on new streams.

This is a very common and practical ML pipeline for biomedical or sensor-based classification problems.

---

## 14. One-sentence summary per file

- `main.py` → the main desktop application and central workflow orchestrator.
- `emg_simulator_app.py` → synthetic signal generator for development and testing.
- `rf_features.py` → shared signal-to-feature conversion logic.
- `train_rf_model_gui.py` → standalone trainer UI for older workflow.
- `app_theme.py` → centralized visual theme and styling.
- `dataset/` → labeled raw EMG recording bundles.
- `trained_model/` → saved model runs and evaluation artifacts.

---

## 15. Simplified mental model

Think of the project like this:

- hardware or simulator = sensor input
- `main.py` = control room
- `rf_features.py` = feature translator
- Random Forest = decision engine
- `trained_model/` = saved knowledge

The app is therefore a complete closed-loop system:

signal → window → feature vector → model → gesture label

---

## 16. Final conclusion

This project is a well-structured EMG gesture recognition prototype. The design is strong in that it combines:

- live hardware streaming,
- a desktop control application,
- data collection,
- handcrafted feature engineering,
- Random Forest training,
- real-time classification.

Its main limitation is maintainability: the project’s core logic is concentrated in a very large file, and the architecture would benefit from decomposition.

The current solution is good for a thesis project, lab prototype, or research workflow. It is practical, understandable, and functional. The next level of quality would come from clearer modularization, stronger data validation, more automated testing, and exploration of alternative classifiers.
