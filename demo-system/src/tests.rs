use crate::host;
use crate::{Command, Controller, Error, Input, Mode, TemporalVerdict, ViolationCode};

fn normal_input() -> Input {
    Input {
        voltage: 12.0,
        temperature: 25.0,
        requested: 500,
        authorized: true,
        emergency: false,
        fault: false,
        send: false,
        ack: false,
        heartbeat: true,
        closed: false,
        stable: true,
    }
}

#[test]
fn normal_operation_runs_and_writes_actuator() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let outcome = controller.tick(0, normal_input()).unwrap();

    assert_eq!(outcome.raw_cycle().system.mode, Mode::Running);
    assert_eq!(outcome.raw_cycle().system.last_speed, 500);
    assert_eq!(outcome.raw_cycle().system.command, Command::Run(500));
    assert_eq!(outcome.raw_cycle().receipt.command, Command::Run(500));
    let public_state = outcome.system();
    let public_receipt = outcome.receipt();
    assert_eq!(public_state.mode(), &Mode::Running);
    assert_eq!(public_state.last_speed(), 500);
    assert_eq!(public_state.command(), &Command::Run(500));
    assert_eq!(public_receipt.command(), &Command::Run(500));
    assert_eq!(public_receipt.sequence(), 1);
    assert_eq!(host::take_written_commands(), vec![Command::Run(500)]);
    assert!(host::take_violation_codes().is_empty());
}

#[test]
fn repeated_speed_exercises_payload_value_guard() {
    host::reset_test_state();
    let mut controller = Controller::new();
    controller.tick(0, normal_input()).unwrap();
    let outcome = controller.tick(100, normal_input()).unwrap();

    assert_eq!(outcome.raw_cycle().system.mode, Mode::Running);
    assert_eq!(outcome.raw_cycle().system.last_speed, 500);
    assert_eq!(outcome.raw_cycle().system.sequence, 2);
}

#[test]
fn low_voltage_stops() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.voltage = 9.9;

    let outcome = controller.tick(0, input).unwrap();
    assert_eq!(outcome.raw_cycle().system.mode, Mode::Stopping);
    assert_eq!(outcome.raw_cycle().system.command, Command::Stop);
    assert!(outcome.raw_cycle().system.closed);
    assert!(host::take_violation_codes().is_empty());
}

#[test]
fn high_temperature_stops() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.temperature = 80.1;

    let outcome = controller.tick(0, input).unwrap();
    assert_eq!(outcome.raw_cycle().system.mode, Mode::Stopping);
    assert_eq!(outcome.raw_cycle().system.command, Command::Stop);
    assert!(outcome.raw_cycle().system.closed);
}

#[test]
fn unauthorized_open_state_forces_emergency_stop() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.authorized = false;

    let outcome = controller.tick(0, input).unwrap();
    assert_eq!(
        outcome.monitors().authorization_safe(),
        TemporalVerdict::Violated
    );
    assert_eq!(outcome.raw_cycle().system.mode, Mode::Faulted);
    assert_eq!(outcome.raw_cycle().system.command, Command::EmergencyStop);
    assert!(outcome.raw_cycle().system.closed);
    assert_eq!(
        host::take_violation_codes(),
        vec![ViolationCode::UnauthorizedOpen.wire_code()]
    );
}

#[test]
fn emergency_open_state_forces_emergency_stop() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.emergency = true;

    let outcome = controller.tick(0, input).unwrap();
    assert_eq!(outcome.monitors().emergency_safe(), TemporalVerdict::Violated);
    assert_eq!(outcome.raw_cycle().system.command, Command::EmergencyStop);
    assert!(outcome.raw_cycle().system.closed);
    assert_eq!(
        host::take_violation_codes(),
        vec![ViolationCode::EmergencyOpen.wire_code()]
    );
}

#[test]
fn ack_timeout_stops_after_deadline() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut first = normal_input();
    first.send = true;

    let first_outcome = controller.tick(0, first).unwrap();
    assert_eq!(first_outcome.monitors().ack_deadline(), TemporalVerdict::Pending);

    let outcome = controller.tick(501, normal_input()).unwrap();
    assert_eq!(outcome.monitors().ack_deadline(), TemporalVerdict::Violated);
    assert_eq!(outcome.raw_cycle().system.command, Command::Stop);
    assert!(outcome.raw_cycle().system.closed);
    assert_eq!(
        host::take_violation_codes(),
        vec![ViolationCode::AckTimeout.wire_code()]
    );
}

#[test]
fn heartbeat_loss_stops_after_one_second() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.heartbeat = false;

    controller.tick(0, input.clone()).unwrap();
    let outcome = controller.tick(1001, input).unwrap();
    assert_eq!(outcome.monitors().heartbeat_live(), TemporalVerdict::Violated);
    assert_eq!(outcome.raw_cycle().system.command, Command::Stop);
    assert!(outcome.raw_cycle().system.closed);
    assert_eq!(
        host::take_violation_codes(),
        vec![ViolationCode::HeartbeatLoss.wire_code()]
    );
}

#[test]
fn fault_open_state_forces_closed_fault_mode() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.fault = true;

    let outcome = controller.tick(0, input).unwrap();
    assert_eq!(outcome.monitors().fault_safe(), TemporalVerdict::Violated);
    assert_eq!(outcome.raw_cycle().system.mode, Mode::Faulted);
    assert_eq!(outcome.raw_cycle().system.command, Command::EmergencyStop);
    assert!(outcome.raw_cycle().system.closed);
    assert_eq!(
        host::take_violation_codes(),
        vec![ViolationCode::FaultOpen.wire_code()]
    );
}

#[test]
fn fault_already_closed_uses_normal_stop_path() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.fault = true;
    input.closed = true;

    let outcome = controller.tick(0, input).unwrap();
    assert_eq!(outcome.monitors().fault_safe(), TemporalVerdict::Pending);
    assert_eq!(outcome.raw_cycle().system.mode, Mode::Stopping);
    assert_eq!(outcome.raw_cycle().system.command, Command::Stop);
    assert!(host::take_violation_codes().is_empty());
}

#[test]
fn invalid_sensor_is_rejected_before_actuation() {
    host::reset_test_state();
    let mut controller = Controller::new();
    let mut input = normal_input();
    input.voltage = f32::NAN;

    assert_eq!(controller.tick(0, input), Err(Error::BadSensor));
    assert_eq!(controller.raw_state().mode, Mode::Idle);
    assert!(host::take_written_commands().is_empty());
}

#[test]
fn actuator_error_propagates_without_committing_state() {
    host::reset_test_state();
    host::fail_next_write();
    let mut controller = Controller::new();

    assert_eq!(controller.tick(0, normal_input()), Err(Error::Actuator));
    assert_eq!(controller.raw_state().mode, Mode::Idle);
}

#[test]
fn closed_normal_trace_finishes_satisfied_and_converged() {
    host::reset_test_state();
    let mut controller = Controller::new();
    controller.tick(0, normal_input()).unwrap();
    let final_verdicts = controller.finish();

    assert_eq!(final_verdicts.ack_deadline(), TemporalVerdict::Satisfied);
    assert_eq!(final_verdicts.heartbeat_live(), TemporalVerdict::Satisfied);
    assert_eq!(
        final_verdicts.authorization_safe(),
        TemporalVerdict::Satisfied
    );
    assert_eq!(final_verdicts.emergency_safe(), TemporalVerdict::Satisfied);
    assert_eq!(final_verdicts.fault_safe(), TemporalVerdict::Satisfied);
    assert_eq!(final_verdicts.convergence(), TemporalVerdict::Satisfied);
}
