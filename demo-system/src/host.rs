//! Glyphが宣言した外部作用境界の手書きホスト実装。
//!
//! 実機ではこのモジュールをGPIO/CAN/PWM等のアダプターへ置き換える。

use std::cell::{Cell, RefCell};

use crate::generated::{Command, Cycle, Error, Receipt, System};

thread_local! {
    static WRITTEN_COMMANDS: RefCell<Vec<Command>> = RefCell::new(Vec::new());
    static VIOLATION_CODES: RefCell<Vec<u16>> = RefCell::new(Vec::new());
    static FAIL_NEXT_WRITE: Cell<bool> = const { Cell::new(false) };
}

/// 制御結果を外部アクチュエータへ反映し、反映済み状態と受領情報を返す。
pub fn write_actuator(system: System) -> Result<Cycle, Error> {
    if FAIL_NEXT_WRITE.with(|flag| flag.replace(false)) {
        return Err(Error::Actuator);
    }

    WRITTEN_COMMANDS.with(|commands| commands.borrow_mut().push(system.command.clone()));
    let receipt = Receipt {
        command: system.command.clone(),
        sequence: system.sequence,
    };
    Ok(Cycle { system, receipt })
}

/// 時相制約違反を外部の診断・記録系へ通知する。
pub fn report_violation(code: u16) -> Result<bool, Error> {
    VIOLATION_CODES.with(|codes| codes.borrow_mut().push(code));
    Ok(true)
}

/// テスト用に次回のアクチュエータ書込みだけを失敗させる。
pub fn fail_next_write() {
    FAIL_NEXT_WRITE.with(|flag| flag.set(true));
}

/// 現在のテストスレッドで記録したコマンドを取り出す。
pub fn take_written_commands() -> Vec<Command> {
    WRITTEN_COMMANDS.with(|commands| std::mem::take(&mut *commands.borrow_mut()))
}

/// 現在のテストスレッドで記録した違反コードを取り出す。
pub fn take_violation_codes() -> Vec<u16> {
    VIOLATION_CODES.with(|codes| std::mem::take(&mut *codes.borrow_mut()))
}

/// 現在のテストスレッドのホスト状態を初期化する。
pub fn reset_test_state() {
    WRITTEN_COMMANDS.with(|commands| commands.borrow_mut().clear());
    VIOLATION_CODES.with(|codes| codes.borrow_mut().clear());
    FAIL_NEXT_WRITE.with(|flag| flag.set(false));
}
