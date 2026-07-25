use glyph_system_demo::{Controller, Input};

fn main() {
    let mut controller = Controller::new();
    let outcome = controller
        .tick(
            0,
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
            },
        )
        .expect("normal controller cycle must succeed");

    println!("state    = {:?}", outcome.system());
    println!("receipt  = {:?}", outcome.receipt());
    println!("monitors = {:?}", outcome.monitors());
}
