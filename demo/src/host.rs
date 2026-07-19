//! 外部作用の実装。
//! DSLでは `!exec(...)` として境界だけを宣言し、具体的処理はRust側へ置く。

use crate::generated::{C, E, Receipt};

pub fn exec(c: C) -> Result<Receipt, E> {
    // 実機ではここをGPIO、UART、CANなどのドライバ呼出しへ置き換える。
    Ok(Receipt { c })
}
