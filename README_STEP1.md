# Reference Motor + FMU Foundation

This stage deliberately stops before the fault-aware controller. The motor model must be validated first; otherwise controller results can hide plant/model errors.

## 1. Install Python dependencies

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Validate the locked WEG reference data

```powershell
python scripts\validate_reference_motor.py
```

Expected: all checks should say `PASS`.

## 3. Check the Modelica model in OMEdit first

Open `models/MotorElectroThermalMechanicalFaultable.mo` in OpenModelica 1.27.x and use `Check -> Check Model`.

The model is intentionally a **reduced-order** electro-thermal-mechanical abstraction. It uses manufacturer data for rated operating points, inertia and temperature-rise calibration, while explicitly treating thermal RC splits, friction and partial-load loss scaling as model assumptions.

## 4. Export FMI 2.0 Co-Simulation FMU

From the project root:

```powershell
python scripts\export_fmu.py --omhome "C:/Program Files/OpenModelica1.27.1-64bit"
```

For a CVODE FMU:

```powershell
python scripts\export_fmu.py --omhome "C:/Program Files/OpenModelica1.27.1-64bit" --cvode
```

OpenModelica supports FMI 2.0 Co-Simulation export with `buildModelFMU(...)`. The default Co-Simulation integrator is Forward Euler; CVODE is also supported when requested. 

## 5. Smoke-test the FMU with a real stepped closed loop

After export, copy the generated `.fmu` path and run:

```powershell
python simulation\fmu_runtime.py --fmu "FULL_PATH_TO_FMU" --stop 180 --step 0.5 --fault-time 60
```

This script applies inputs at every communication step, advances the FMU, reads measurements, and records the faulted trajectory. It contains **no artificial sleep/polling delay**, so later timing metrics can use actual execution measurements.

## 6. Do not tune controllers yet

Do not add the adaptive controller until these conditions are true:

- healthy full-load temperature approaches the expected calibrated operating point;
- rated speed is stable near 1460 rpm;
- rated torque is approximately 36 N·m;
- electrical input and shaft output remain consistent with the 89.7% rated efficiency reference;
- the sensor-bias, cooling-efficiency and unbalance inputs actually change the expected observable channels;
- the FMU can be stepped repeatedly without solver failure.
