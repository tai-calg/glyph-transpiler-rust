use crate::generated::{
    cycle as run_cycle, transition, AckDeadlineStreamingMonitor,
    AuthorizationSafeStreamingMonitor, Command, ConvergenceStreamingMonitor, Cycle,
    EmergencySafeStreamingMonitor, Error, FaultSafeStreamingMonitor,
    HeartbeatLiveStreamingMonitor, Input, Mode, System, TemporalVerdict,
};
use crate::host;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ViolationCode {
    AckTimeout,
    HeartbeatLoss,
    UnauthorizedOpen,
    EmergencyOpen,
    FaultOpen,
}

impl ViolationCode {
    pub(crate) const fn wire_code(self) -> u16 {
        match self {
            Self::AckTimeout => 1,
            Self::HeartbeatLoss => 2,
            Self::UnauthorizedOpen => 3,
            Self::EmergencyOpen => 4,
            Self::FaultOpen => 5,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SystemSnapshot {
    mode: Mode,
    sequence: u16,
    last_speed: u16,
    command: Command,
    closed: bool,
    stable: bool,
}

impl SystemSnapshot {
    fn from_system(system: &System) -> Self {
        Self {
            mode: system.mode.clone(),
            sequence: system.sequence,
            last_speed: system.last_speed,
            command: system.command.clone(),
            closed: system.closed,
            stable: system.stable,
        }
    }

    pub const fn mode(&self) -> &Mode {
        &self.mode
    }

    pub const fn sequence(&self) -> u16 {
        self.sequence
    }

    pub const fn last_speed(&self) -> u16 {
        self.last_speed
    }

    pub const fn command(&self) -> &Command {
        &self.command
    }

    pub const fn closed(&self) -> bool {
        self.closed
    }

    pub const fn stable(&self) -> bool {
        self.stable
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReceiptSnapshot {
    command: Command,
    sequence: u16,
}

impl ReceiptSnapshot {
    fn from_cycle(cycle: &Cycle) -> Self {
        Self {
            command: cycle.receipt.command.clone(),
            sequence: cycle.receipt.sequence,
        }
    }

    pub const fn command(&self) -> &Command {
        &self.command
    }

    pub const fn sequence(&self) -> u16 {
        self.sequence
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MonitorSnapshot {
    ack_deadline: TemporalVerdict,
    heartbeat_live: TemporalVerdict,
    authorization_safe: TemporalVerdict,
    emergency_safe: TemporalVerdict,
    fault_safe: TemporalVerdict,
    convergence: TemporalVerdict,
}

impl MonitorSnapshot {
    pub const fn ack_deadline(&self) -> TemporalVerdict {
        self.ack_deadline
    }

    pub const fn heartbeat_live(&self) -> TemporalVerdict {
        self.heartbeat_live
    }

    pub const fn authorization_safe(&self) -> TemporalVerdict {
        self.authorization_safe
    }

    pub const fn emergency_safe(&self) -> TemporalVerdict {
        self.emergency_safe
    }

    pub const fn fault_safe(&self) -> TemporalVerdict {
        self.fault_safe
    }

    pub const fn convergence(&self) -> TemporalVerdict {
        self.convergence
    }

    fn recovery(&self) -> Option<(ViolationCode, Command)> {
        if self.emergency_safe == TemporalVerdict::Violated {
            return Some((ViolationCode::EmergencyOpen, Command::EmergencyStop));
        }
        if self.fault_safe == TemporalVerdict::Violated {
            return Some((ViolationCode::FaultOpen, Command::EmergencyStop));
        }
        if self.authorization_safe == TemporalVerdict::Violated {
            return Some((ViolationCode::UnauthorizedOpen, Command::EmergencyStop));
        }
        if self.ack_deadline == TemporalVerdict::Violated {
            return Some((ViolationCode::AckTimeout, Command::Stop));
        }
        if self.heartbeat_live == TemporalVerdict::Violated {
            return Some((ViolationCode::HeartbeatLoss, Command::Stop));
        }
        None
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct StepOutcome {
    cycle: Cycle,
    monitors: MonitorSnapshot,
}

impl StepOutcome {
    pub fn system(&self) -> SystemSnapshot {
        SystemSnapshot::from_system(&self.cycle.system)
    }

    pub fn receipt(&self) -> ReceiptSnapshot {
        ReceiptSnapshot::from_cycle(&self.cycle)
    }

    pub const fn monitors(&self) -> &MonitorSnapshot {
        &self.monitors
    }

    pub(crate) const fn raw_cycle(&self) -> &Cycle {
        &self.cycle
    }
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

    pub(crate) fn with_state(state: System) -> Self {
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

    pub fn state(&self) -> SystemSnapshot {
        SystemSnapshot::from_system(&self.state)
    }

    pub(crate) const fn raw_state(&self) -> &System {
        &self.state
    }

    /// 1観測点を監視し、違反がなければGlyphの通常cycleを実行する。
    /// 違反時はホスト側で安全側コマンドを選び、違反通知後に作用境界へ反映する。
    pub fn tick(&mut self, at_ms: u64, input: Input) -> Result<StepOutcome, Error> {
        let monitors = self.step_monitors(at_ms, &input);
        let cycle = if let Some((code, command)) = monitors.recovery() {
            host::report_violation(code.wire_code())?;
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
