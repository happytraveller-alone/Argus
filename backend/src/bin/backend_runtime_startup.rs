use anyhow::Result;
use backend_rust::runtime::{bootstrap, runner};
use std::{env, path::Path, process};

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| {
        eprintln!(
            "Usage: backend-runtime-startup <dev|prod|runner execute --spec <path>|runner stop --container-id <id>>"
        );
        process::exit(1);
    });

    match command.as_str() {
        "dev" | "prod" => {
            bootstrap::run(&command)?;
        }
        "runner" => match args.next().as_deref() {
            Some("execute") => {
                let flag = args.next().unwrap_or_default();
                let spec_path = args.next().unwrap_or_default();
                if flag != "--spec" || spec_path.is_empty() {
                    eprintln!("Usage: backend-runtime-startup runner execute --spec <path>");
                    process::exit(1);
                }
                let result = runner::execute_spec_file(Path::new(&spec_path))?;
                println!("{}", serde_json::to_string(&result)?);
            }
            Some("stop") => {
                let flag = args.next().unwrap_or_default();
                let container_id = args.next().unwrap_or_default();
                if flag != "--container-id" || container_id.is_empty() {
                    eprintln!("Usage: backend-runtime-startup runner stop --container-id <id>");
                    process::exit(1);
                }
                let payload = serde_json::json!({
                    "stopped": runner::stop_container_sync(&container_id)
                });
                println!("{}", serde_json::to_string(&payload)?);
            }
            _ => {
                eprintln!(
                    "Usage: backend-runtime-startup runner <execute --spec <path>|stop --container-id <id>>"
                );
                process::exit(1);
            }
        },
        _ => {
            eprintln!("Mode must be either `dev`, `prod`, or `runner`.");
            process::exit(1);
        }
    }
    Ok(())
}
