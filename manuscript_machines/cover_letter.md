# Cover letter draft

**Draft for use only after both authors confirm this revised version and approve the Data Availability Statement.**

Dear Editor,

Please consider the manuscript “A Simulation-Based FMU Digital-Twin Workflow for Fault-Informed Thermal Supervisory Control of an Induction Motor” for publication in *Machines*.

The manuscript reports a simulation-based workflow that composes the Modelica Standard Library 18.5 kW squirrel-cage induction-machine benchmark with a lumped thermal model, an FMI 2.0 Co-Simulation interface, Python state estimation and fault diagnosis, 30 s/60 s thermal forecasting, three supervisory policies, and an Asset Administration Shell representation. The evaluation comprises 33 deterministic scenario/controller runs and a separate BaSyx synchronization smoke test.

The paper is framed as an engineering integration and simulation-evaluation study, not as a new diagnostic/control algorithm or a physically validated motor digital twin. The manuscript distinguishes the MSL reference-point check from hardware validation, documents thermal/fault assumptions, reports the controllers’ unequal signal access, and avoids interpreting deterministic scenario averages as statistical generalization. It also makes clear that the AAS measurements are a local smoke test and do not establish industrial deployment or real-time performance.

We consider the subject matter relevant to *Machines* because it brings together induction-machine simulation, thermal estimation, fault-informed supervisory control, FMI-based co-simulation, and AAS data representation. The evaluated source and configuration are now available at a versioned project commit. Raw per-run campaign traces are not included in the public repository; the manuscript directs readers to contact the corresponding author to request access.

The project repository is available at https://github.com/Dilshad-Ahmed1/Industrial-Motor-DT, with the evaluated source revision at https://github.com/Dilshad-Ahmed1/Industrial-Motor-DT/commit/74a5fb3015bb9055cb81499e7676e1479d003104.

The corresponding author is Dilshad Ahmed, Department of Computer Science and Engineering, R.V. College of Engineering, Bengaluru, India (dilshadahmed.cs23@rvce.edu.in). Co-author Sridhar R is an Associate Professor in the Department of Mechanical Engineering at the same institution.

Sincerely,

Dilshad Ahmed  
Corresponding Author  
Department of Computer Science and Engineering  
R.V. College of Engineering (RVCE), Bengaluru, India  
dilshadahmed.cs23@rvce.edu.in
