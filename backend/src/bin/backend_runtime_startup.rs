use anyhow::Result;
use backend_rust::runtime::bootstrap;
use std::{env, process};

fn main() -> Result<()> {
    let mode = env::args().nth(1).unwrap_or_else(|| {
        eprintln!("Usage: backend-runtime-startup <dev|prod>");
        process::exit(1);
    });

    if mode != "dev" && mode != "prod" {
        eprintln!("Mode must be either `dev` or `prod`.");
        process::exit(1);
    }

    bootstrap::run(&mode)?;
    Ok(())
}
