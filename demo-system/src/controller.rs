use crate::generated::{
    cycle as run_cycle, transition, AckDeadlineStreamingMonitor,
    AuthorizationSafeStreamingMonitor, Command, ConvergenceStreamingMonitor, Cycle,
    EmergencySafeStreamingMonitor, Error, FaultSafeStreamingMonitor,
    HeartbeatLiveStreamingMonitor, Input, Mode, System, TemporalVerdict,
};
use crate::host;

pub const VIOLATION_ACK_TIMEOUT: u16 = 1;
pub const VIOLATION_HEARTBEAT_LOSS: u16 = 2;
pub const VIOLATION_UNAUTHORIZED_OPEN: u16 = 3;
pub const VIOLATION_EMERGENCY_OPEN: u16 = 4;
pub const VIOLATION_FAULT_OPEN: u16 = 5;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MonitorSnapshot {
    pub ack_deadline: TemporalVerdict,
    pub heartbeat_live: TemporalVerdict,
    pub authorization_safe: TemporalVerdict,
    pub emergency_safe: TemporalVerdict,
    pub fault_safe: TemporalVerdict,
    pub convergence: TemporalVerdict,
}

impl MonitorSnapshot {
    fn recovery(self) -> Option<(u16, Command)> {
        if self.emergency_safe == TemporalVerdict::Violated {
            return Some((VIOLATION_EMERGENCY_OPEN, Command::EmergencyStop));
        }
        if self.fault_safe == TemporalVerdict::Violated {
            return Some((VIOLATION_FAULT_OPEN, Command::EmergencyStop));
        }
        if self.authorization_safe == TemporalVerdict::Violated {
            return Some((VIOLATION_UNAUTHORIZED_OPEN, Command::EmergencyStop));
        }
        if self.ack_deadline == TemporalVerdict::Violated {
            return Some((VIOLATION_ACK_TIMEOUT, Command::Stop));
        }
        if self.heartbeat_live == TemporalVerdict::Violated {
            return Some((VIOLATION_HEARTBEAT_LOSS, Command::Stop));
        }
        None
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct StepOutcome {
    pub cycle: Cycle,
    pub monitors: MonitorSnapshot,
}

/// Glyph生成ロジックと、時刻・I/O・違反復旧を接続するホスト側制御器。
pub struct Controller {
    state: System,
    ack_deadline: AckDeadlineStreamingMonitor,
    heartbeat_live: HeartbeatLiveStreamingMonitor,
    authorization_safe: AuthorizationSafeStreamingMonitor,
    emergency_safe: EmergencySafeStreamingMonitor,
    fault_safe: FaultSafeStreamingMonitor,
    convergence: ConvergenceStreamingMonitor,
}

impl Controller {
    pub fn new() -> Self {
        Self::with_state(System {
            mode: Mode::Idle,
            sequence: 0,
            last_speed: 0,
            command: Command::Stop,
            closed: true,
            stable: true,
        })
    }

    pub fn with_state(state: System) -> Self {
        Self {
            state,
            ack_deadline: AckDeadlineStreamingMonitor::new(),
            heartbeat_live: HeartbeatLiveStreamingMonitor::new(),
            authorization_safe: AuthorizationSafeStreamingMonitor::new(),
            emergency_safe: EmergencySafeStreamingMonitor::new(),
            fault_safe: FaultSafeStreamingMonitor::new(),
            convergence: ConvergenceStreamingMonitor::new(),
        }
    }

    pub fn state(&self) -> &System {
        &self.state
    }

    /// 1観測点を監視し、違反がなければGlyphの通常cycleを実行する。
    /// 違反時はホスト側で安全側コマンドを選び、違反通知後に作用境界へ反映する。
    pub fn tick(&mut self, at_ms: u64, input: Input) -> Result<StepOutcome, Error> {
        let monitors = self.step_monitors(at_ms, &input);
        let cycle = if let Some((code, command)) = monitors.recovery() {
            host::report_violation(code)?;
            let next = transition(self.state.clone(), command);
            host::write_actuator(next)?
        } else {
            run_cycle(self.state.clone(), input)?
        };
        self.state = cycle.system.clone();
        Ok(StepOutcome { cycle, monitors })
    }

    pub fn finish(&self) -> MonitorSnapshot {
        MonitorSnapshot {
            ack_deadline: self.ack_deadline.finish(),
            heartbeat_live: self.heartbeat_live.finish(),
            authorization_safe: self.authorization_safe.finish(),
            emergency_safe: self.emergency_safe.finish(),
            fault_safe: self.fault_safe.finish(),
            convergence: self.convergence.finish(),
        }
    }

    pub fn reset_monitors(&mut self) {
        self.ack_deadline.reset();
        self.heartbeat_live.reset();
        self.authorization_safe.reset();
        self.emergency_safe.reset();
        self.fault_safe.reset();
        self.convergence.reset();
    }

    fn step_monitors(&mut self, at_ms: u64, input: &Input) -> MonitorSnapshot {
        let args = (
            input.voltage,
            input.temperature,
            input.requested,
            input.authorized,
            input.emergency,
            input.fault,
            input.send,
            input.ack,
            input.heartbeat,
            input.closed,
            input.stable,
        );

        MonitorSnapshot {
            ack_deadline: self.ack_deadline.step(
                at_ms, args.0, args.1, args.2, args.3, args.4, args.5, args.6, args.7,
                args.8, args.9, args.10,
            ),
            heartbeat_live: self.heartbeat_live.step(
                at_ms, args.0, args.1, args.2, args.3, args.4, args.5, args.6, args.7,
                args.8, args.9, args.10,
            ),
            authorization_safe: self.authorization_safe.step(
                at_ms, args.0, args.1, args.2, args.3, args.4, args.5, args.6, args.7,
                args.8, args.9, args.10,
            ),
            emergency_safe: self.emergency_safe.step(
                at_ms, args.0, args.1, args.2, args.3, args.4, args.5, args.6, args.7,
                args.8, args.9, args.10,
            ),
            fault_safe: self.fault_safe.step(
                at_ms, args.0, args.1, args.2, args.3, args.4, args.5, args.6, args.7,
                args.8, args.9, args.10,
            ),
            convergence: self.convergence.step(
                at_ms, args.0, args.1, args.2, args.3, args.4, args.5, args.6, args.7,
                args.8, args.9, args.10,
            ),
        }
    }
}

impl Default for Controller {
    fn default() -> Self {
        Self::new()
    }
}
