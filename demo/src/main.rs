mod generated;
mod host;

fn main() {
    let normal = generated::run(12.0, 25.0, 500);
    let low_voltage = generated::run(9.0, 25.0, 500);
    let capped = generated::run(12.0, 25.0, 5000);

    println!("normal      = {normal:?}");
    println!("low_voltage = {low_voltage:?}");
    println!("capped      = {capped:?}");
}

#[cfg(test)]
mod tests {
    use super::generated::{
        run, AckMonitor, AuthMonitor, BeatMonitor, C, ConvMonitor, E, Receipt, SafeMonitor,
        TemporalVerdict, WaitMonitor,
    };

    #[test]
    fn normal_request_runs() {
        assert_eq!(
            run(12.0, 25.0, 500),
            Ok(Receipt { c: C::Run(500) })
        );
    }

    #[test]
    fn low_voltage_stops() {
        assert_eq!(
            run(9.9, 25.0, 500),
            Ok(Receipt { c: C::Stop })
        );
    }

    #[test]
    fn excessive_speed_is_capped() {
        assert_eq!(
            run(12.0, 25.0, 5000),
            Ok(Receipt { c: C::Run(1000) })
        );
    }

    #[test]
    fn invalid_sensor_is_rejected() {
        assert_eq!(run(f32::NAN, 25.0, 500), Err(E::BadSensor));
    }

    #[test]
    fn empty_trace_remains_pending() {
        assert_eq!(AckMonitor::new().finish(), TemporalVerdict::Pending);
    }

    #[test]
    fn ack_within_deadline_satisfies_closed_trace() {
        let mut monitor = AckMonitor::new();
        assert_eq!(
            monitor.step(0, true, false, true, false, false, false),
            TemporalVerdict::Pending
        );
        assert_eq!(
            monitor.step(4000, false, true, true, false, false, false),
            TemporalVerdict::Pending
        );
        assert_eq!(monitor.finish(), TemporalVerdict::Satisfied);
    }

    #[test]
    fn ack_at_exact_deadline_is_included() {
        let mut monitor = AckMonitor::new();
        monitor.step(0, true, false, true, false, false, false);
        monitor.step(5000, false, true, true, false, false, false);
        assert_eq!(monitor.finish(), TemporalVerdict::Satisfied);
    }

    #[test]
    fn unresolved_ack_at_exact_deadline_is_pending_until_finish() {
        let mut monitor = AckMonitor::new();
        monitor.step(0, true, false, true, false, false, false);
        assert_eq!(
            monitor.step(5000, false, false, true, false, false, false),
            TemporalVerdict::Pending
        );
        assert_eq!(monitor.finish(), TemporalVerdict::Violated);
    }

    #[test]
    fn ack_after_deadline_is_violated() {
        let mut monitor = AckMonitor::new();
        monitor.step(0, true, false, true, false, false, false);
        assert_eq!(
            monitor.step(5001, false, false, true, false, false, false),
            TemporalVerdict::Violated
        );
    }

    #[test]
    fn equal_timestamps_are_allowed() {
        let mut monitor = AckMonitor::new();
        monitor.step(0, true, false, true, false, false, false);
        assert_eq!(
            monitor.step(0, false, false, true, false, false, false),
            TemporalVerdict::Pending
        );
    }

    #[test]
    #[should_panic(expected = "temporal observation time must be monotonic")]
    fn observation_time_cannot_move_backwards() {
        let mut monitor = AckMonitor::new();
        monitor.step(10, false, false, true, false, false, false);
        monitor.step(9, false, false, true, false, false, false);
    }

    #[test]
    fn implication_is_vacuously_true_without_send() {
        let mut monitor = AckMonitor::new();
        monitor.step(0, false, false, true, false, false, false);
        assert_eq!(monitor.finish(), TemporalVerdict::Satisfied);
    }

    #[test]
    fn invariant_violation_is_detected_immediately() {
        let mut monitor = SafeMonitor::new();
        assert_eq!(
            monitor.step(0, false, false, false, false, false, false),
            TemporalVerdict::Violated
        );
    }

    #[test]
    fn untimed_invariant_is_stutter_invariant() {
        let mut single = SafeMonitor::new();
        single.step(0, false, false, true, false, false, false);

        let mut repeated = SafeMonitor::new();
        repeated.step(0, false, false, true, false, false, false);
        repeated.step(0, false, false, true, false, false, false);

        assert_eq!(single.finish(), TemporalVerdict::Satisfied);
        assert_eq!(repeated.finish(), single.finish());
    }

    #[test]
    fn strong_until_requires_target_on_finish() {
        let mut monitor = AuthMonitor::new();
        monitor.step(0, false, false, true, false, false, false);
        assert_eq!(monitor.finish(), TemporalVerdict::Violated);
    }

    #[test]
    fn weak_until_accepts_permanent_hold_on_finish() {
        let mut monitor = WaitMonitor::new();
        monitor.step(0, false, false, true, false, false, false);
        assert_eq!(monitor.finish(), TemporalVerdict::Satisfied);
    }

    #[test]
    fn weak_until_rejects_hold_failure_before_target() {
        let mut monitor = WaitMonitor::new();
        assert_eq!(
            monitor.step(0, false, false, false, false, false, false),
            TemporalVerdict::Violated
        );
    }

    #[test]
    fn until_target_at_initial_point_does_not_require_hold() {
        let mut monitor = AuthMonitor::new();
        assert_eq!(
            monitor.step(0, false, false, false, true, false, false),
            TemporalVerdict::Satisfied
        );
    }

    #[test]
    fn strong_until_satisfies_when_target_arrives() {
        let mut monitor = AuthMonitor::new();
        monitor.step(0, false, false, true, false, false, false);
        assert_eq!(
            monitor.step(100, false, false, false, true, false, false),
            TemporalVerdict::Satisfied
        );
    }

    #[test]
    fn strong_until_rejects_hold_failure_before_target() {
        let mut monitor = AuthMonitor::new();
        assert_eq!(
            monitor.step(0, false, false, false, false, false, false),
            TemporalVerdict::Violated
        );
    }

    #[test]
    fn finite_recurring_property_requires_target_from_final_suffix() {
        let mut monitor = BeatMonitor::new();
        monitor.step(0, false, false, true, false, true, false);
        monitor.step(500, false, false, true, false, false, false);
        assert_eq!(monitor.finish(), TemporalVerdict::Violated);
    }

    #[test]
    fn finite_convergence_accepts_a_stable_final_suffix() {
        let mut monitor = ConvMonitor::new();
        monitor.step(0, false, false, true, false, false, false);
        monitor.step(100, false, false, true, false, false, true);
        assert_eq!(monitor.finish(), TemporalVerdict::Satisfied);
    }
}
