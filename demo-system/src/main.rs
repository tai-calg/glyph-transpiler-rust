use glyph_system_demo::controller::Controller;
use glyph_system_demo::generated::Input;

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

    println!("state    = {:?}", outcome.cycle.system);
    println!("receipt  = {:?}", outcome.cycle.receipt);
    println!("monitors = {:?}", outcome.monitors);
}
