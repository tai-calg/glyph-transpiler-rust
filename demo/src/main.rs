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
        run, AckMonitor, AuthMonitor, C, E, Receipt, SafeMonitor, TemporalVerdict,
        WaitMonitor,
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
    fn ack_after_deadline_is_violated() {
        let mut monitor = AckMonitor::new();
        monitor.step(0, true, false, true, false, false, false);
        assert_eq!(
            monitor.step(5001, false, false, true, false, false, false),
            TemporalVerdict::Violated
        );
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
    fn strong_until_satisfies_when_target_arrives() {
        let mut monitor = AuthMonitor::new();
        monitor.step(0, false, false, true, false, false, false);
        assert_eq!(
            monitor.step(100, false, false, false, true, false, false),
            TemporalVerdict::Satisfied
        );
    }
}
