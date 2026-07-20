#[path = "../src/generated.rs"]
mod generated;

mod host {
    use super::generated::{C, E, Receipt};

    pub fn exec(c: C) -> Result<Receipt, E> {
        Ok(Receipt { c })
    }
}

use generated::{
    AckMonitor, AckStreamingMonitor, AuthMonitor, AuthStreamingMonitor, BeatMonitor,
    BeatStreamingMonitor, ConvMonitor, ConvStreamingMonitor, SafeMonitor, SafeStreamingMonitor,
    WaitMonitor, WaitStreamingMonitor,
};

fn next_u64(state: &mut u64) -> u64 {
    *state = state
        .wrapping_mul(6_364_136_223_846_793_005)
        .wrapping_add(1_442_695_040_888_963_407);
    *state
}

#[test]
fn streaming_monitors_match_reference_monitors() {
    let mut ack_ref = AckMonitor::new();
    let mut ack_stream = AckStreamingMonitor::new();
    let mut safe_ref = SafeMonitor::new();
    let mut safe_stream = SafeStreamingMonitor::new();
    let mut auth_ref = AuthMonitor::new();
    let mut auth_stream = AuthStreamingMonitor::new();
    let mut wait_ref = WaitMonitor::new();
    let mut wait_stream = WaitStreamingMonitor::new();
    let mut beat_ref = BeatMonitor::new();
    let mut beat_stream = BeatStreamingMonitor::new();
    let mut conv_ref = ConvMonitor::new();
    let mut conv_stream = ConvStreamingMonitor::new();

    let mut random = 0x4d59_5df4_d0f3_3173;
    let mut at_ms = 0_u64;

    for _ in 0..256 {
        at_ms = at_ms.saturating_add(next_u64(&mut random) % 900);
        let send = next_u64(&mut random) & 7 == 0;
        let ack = next_u64(&mut random) & 7 == 0;
        let closed = next_u64(&mut random) & 3 != 0;
        let auth = next_u64(&mut random) & 15 == 0;
        let beat = next_u64(&mut random) & 3 == 0;
        let stable = next_u64(&mut random) & 1 == 0;

        let args = (at_ms, send, ack, closed, auth, beat, stable);

        assert_eq!(
            ack_ref.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6),
            ack_stream.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6)
        );
        assert_eq!(
            safe_ref.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6),
            safe_stream.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6)
        );
        assert_eq!(
            auth_ref.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6),
            auth_stream.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6)
        );
        assert_eq!(
            wait_ref.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6),
            wait_stream.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6)
        );
        assert_eq!(
            beat_ref.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6),
            beat_stream.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6)
        );
        assert_eq!(
            conv_ref.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6),
            conv_stream.step(args.0, args.1, args.2, args.3, args.4, args.5, args.6)
        );
    }

    assert_eq!(ack_ref.finish(), ack_stream.finish());
    assert_eq!(safe_ref.finish(), safe_stream.finish());
    assert_eq!(auth_ref.finish(), auth_stream.finish());
    assert_eq!(wait_ref.finish(), wait_stream.finish());
    assert_eq!(beat_ref.finish(), beat_stream.finish());
    assert_eq!(conv_ref.finish(), conv_stream.finish());
}

#[test]
fn streaming_reset_returns_to_empty_pending_state() {
    let mut monitor = AckStreamingMonitor::new();
    monitor.step(0, true, false, true, false, false, false);
    monitor.reset();
    assert_eq!(monitor.finish(), generated::TemporalVerdict::Pending);
}
