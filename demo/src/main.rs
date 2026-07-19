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
    use super::generated::{run, C, E, Receipt};

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
}
