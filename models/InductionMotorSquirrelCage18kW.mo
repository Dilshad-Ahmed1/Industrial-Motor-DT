within ;
package MotorDigitalTwin
  model InductionMotorSquirrelCage18kW
    "MSL squirrel-cage induction motor with a nominal validation load"

    import Modelica.Constants.pi;
    import Modelica.Units.SI;
    import Modelica.Electrical.Machines.Thermal.Constants;
    import Modelica.Electrical.Machines.Utilities.ParameterRecords
      .IM_SquirrelCageData;

    parameter SI.Power P_nominal_W = 18500
      "Reference shaft output from the MSL 18.5 kW motor example";
    parameter SI.Voltage V_line_nominal_V = 400
      "Reference line-to-line voltage";
    parameter SI.Current I_line_nominal_A = 32.85
      "Reference nominal stator current";
    parameter Real pf_nominal = 0.898
      "Reference nominal power factor";
    parameter SI.Frequency f_nominal_Hz = 50
      "Reference nominal frequency";
    parameter Real n_nominal_rpm = 1462.5
      "Reference nominal speed";
    parameter Integer pole_pairs = 2
      "MSL benchmark parameter; four poles";
    parameter SI.Temperature T_ambient = 293.15
      "Assumed ambient temperature: 20 degC";
    parameter SI.Temperature T_motor_start = 363.15
      "MSL benchmark operating temperature: 90 degC";
    parameter SI.HeatCapacity C_motor = 50000
      "Explicit lumped thermal-capacitance assumption";

    final parameter SI.AngularVelocity omega_nominal =
      2*pi*n_nominal_rpm/60;
    final parameter SI.AngularVelocity omega_synchronous =
      2*pi*f_nominal_Hz/pole_pairs;
    final parameter SI.Torque T_shaft_nominal =
      P_nominal_W/omega_nominal;
    final parameter SI.Power P_input_nominal =
      sqrt(3)*V_line_nominal_V*I_line_nominal_A*pf_nominal;
    final parameter SI.Power P_loss_nominal =
      P_input_nominal - P_nominal_W;
    final parameter SI.ThermalConductance G_motor_ambient =
      P_loss_nominal/(T_motor_start - T_ambient)
      "Derived from the nominal loss and the stated ambient assumption";

    parameter IM_SquirrelCageData machineData(
        statorCoreParameters(PRef=410, VRef=387.9),
        Jr=0.12,
        Rs=0.56,
        alpha20s=Constants.alpha20Copper,
        Lssigma=1.52/(2*pi*f_nominal_Hz),
        frictionParameters(PRef=180, wRef=omega_nominal),
        strayLoadParameters(
          PRef=0.005*P_input_nominal,
          IRef=I_line_nominal_A/sqrt(3),
          wRef=omega_nominal),
        Lm=66.4/(2*pi*f_nominal_Hz),
        Lrsigma=2.31/(2*pi*f_nominal_Hz),
        Rr=0.42,
        alpha20r=Constants.alpha20Aluminium)
      "Parameterization copied from MSL 4.1.0 IMC_withLosses reference case";

    Modelica.Electrical.Machines.BasicMachines.InductionMachines.IM_SquirrelCage
      motor(
        p=pole_pairs,
        fsNominal=f_nominal_Hz,
        Rs=machineData.Rs,
        TsRef=machineData.TsRef,
        alpha20s=machineData.alpha20s,
        Lszero=machineData.Lszero,
        Lssigma=machineData.Lssigma,
        Jr=machineData.Jr,
        Js=machineData.Js,
        frictionParameters=machineData.frictionParameters,
        statorCoreParameters=machineData.statorCoreParameters,
        strayLoadParameters=machineData.strayLoadParameters,
        Lm=machineData.Lm,
        Lrsigma=machineData.Lrsigma,
        Rr=machineData.Rr,
        TrRef=machineData.TrRef,
        alpha20r=machineData.alpha20r,
        TsOperational=T_motor_start,
        TrOperational=T_motor_start,
        useThermalPort=true,
        phiMechanical(fixed=true),
        wMechanical(fixed=true, start=omega_synchronous))
      "Three-phase MSL induction machine, star-connected supply and delta windings";

    Modelica.Electrical.Machines.Utilities.TerminalBox terminalBox(
      terminalConnection="D");
    Modelica.Electrical.Machines.Sensors.CurrentQuasiRMSSensor currentSensor;
    Modelica.Electrical.Machines.Sensors.ElectricalPowerSensor
      electricalPowerSensor;
    Modelica.Electrical.Machines.Sensors.VoltageQuasiRMSSensor voltageSensor;
    Modelica.Electrical.Polyphase.Sources.SineVoltage supply(
      final m=3,
      f=fill(f_nominal_Hz, 3),
      V=fill(sqrt(2/3)*V_line_nominal_V, 3));
    Modelica.Electrical.Polyphase.Basic.Star neutral(final m=3);
    Modelica.Electrical.Analog.Basic.Ground ground;

    Modelica.Mechanics.Rotational.Sensors.PowerSensor shaftPowerSensor;
    Modelica.Mechanics.Rotational.Components.Inertia loadInertia(
      J=machineData.Jr);
    Modelica.Mechanics.Rotational.Sources.Torque loadTorque(useSupport=false);
    Modelica.Blocks.Sources.Ramp loadTorqueRamp(
      height=-T_shaft_nominal,
      offset=0,
      startTime=0.2,
      duration=1.0);

    Modelica.Thermal.HeatTransfer.Components.HeatCapacitor motorThermalMass(
      C=C_motor,
      T(start=T_motor_start, fixed=true));
    Modelica.Thermal.HeatTransfer.Components.ThermalConductor
      motorToAmbient(G=G_motor_ambient);
    Modelica.Thermal.HeatTransfer.Sources.FixedTemperature ambient(
      T=T_ambient);

    output SI.Voltage line_voltage_rms_V =
      sqrt(3)*voltageSensor.V;
    output SI.Current line_current_rms_A = currentSensor.I;
    output SI.Frequency supply_frequency_Hz = f_nominal_Hz;
    output SI.AngularVelocity speed_rad_s = motor.wMechanical;
    output Real speed_rpm = motor.wMechanical*60/(2*pi);
    output Real synchronous_speed_rpm = 60*f_nominal_Hz/pole_pairs;
    output Real slip_fraction =
      (synchronous_speed_rpm - speed_rpm)/synchronous_speed_rpm;
    output SI.Torque torque_electromagnetic_Nm = motor.tauElectrical;
    output SI.Torque torque_shaft_Nm = motor.tauShaft;
    output SI.Power electrical_input_power_W = electricalPowerSensor.P;
    output SI.Power electrical_reactive_power_var = electricalPowerSensor.Q;
    output SI.Power mechanical_output_power_W = shaftPowerSensor.power;
    output Real power_factor =
      if noEvent(abs(electricalPowerSensor.P) > Modelica.Constants.small)
      then electricalPowerSensor.P
        /sqrt(electricalPowerSensor.P^2 + electricalPowerSensor.Q^2)
      else 0;
    output Real efficiency =
      if noEvent(abs(electricalPowerSensor.P) > Modelica.Constants.small)
      then shaftPowerSensor.power/electricalPowerSensor.P
      else 0;
    output SI.Power motor_losses_W = motor.powerBalance.lossPowerTotal;
    output SI.Power stator_copper_losses_W =
      motor.powerBalance.lossPowerStatorWinding;
    output SI.Power stator_core_losses_W =
      motor.powerBalance.lossPowerStatorCore;
    output SI.Power rotor_copper_losses_W =
      motor.powerBalance.lossPowerRotorWinding;
    output SI.Power rotor_core_losses_W =
      motor.powerBalance.lossPowerRotorCore;
    output SI.Power stray_load_losses_W =
      motor.powerBalance.lossPowerStrayLoad;
    output SI.Power friction_losses_W =
      motor.powerBalance.lossPowerFriction;
    output SI.Temperature motor_lumped_temperature_K =
      motorThermalMass.T;

  initial equation
    motor.i_0_s = 0;
    der(motor.idq_sr) = zeros(2);
    der(motor.idq_rr) = zeros(2);

  equation
    connect(supply.plug_p, currentSensor.plug_p);
    connect(currentSensor.plug_n, electricalPowerSensor.plug_p);
    connect(electricalPowerSensor.plug_ni, terminalBox.plugSupply);
    connect(electricalPowerSensor.plug_nv, neutral.plug_p);
    connect(supply.plug_n, neutral.plug_p);
    connect(neutral.pin_n, ground.p);
    connect(terminalBox.plug_sp, motor.plug_sp);
    connect(terminalBox.plug_sn, motor.plug_sn);

    connect(voltageSensor.plug_p, supply.plug_p);
    connect(voltageSensor.plug_n, supply.plug_n);

    connect(motor.flange, shaftPowerSensor.flange_a);
    connect(shaftPowerSensor.flange_b, loadInertia.flange_a);
    connect(loadInertia.flange_b, loadTorque.flange);
    connect(loadTorqueRamp.y, loadTorque.tau);

    for phase in 1:3 loop
      connect(
        motor.thermalPort.heatPortStatorWinding[phase],
        motorThermalMass.port);
    end for;
    connect(motor.thermalPort.heatPortStatorCore, motorThermalMass.port);
    connect(motor.thermalPort.heatPortRotorWinding, motorThermalMass.port);
    connect(motor.thermalPort.heatPortRotorCore, motorThermalMass.port);
    connect(motor.thermalPort.heatPortStrayLoad, motorThermalMass.port);
    connect(motor.thermalPort.heatPortFriction, motorThermalMass.port);
    connect(motorThermalMass.port, motorToAmbient.port_a);
    connect(motorToAmbient.port_b, ambient.port);

    annotation (
      experiment(
        StartTime=0,
        StopTime=8,
        Interval=0.001,
        Tolerance=1e-6));
  end InductionMotorSquirrelCage18kW;
end MotorDigitalTwin;
