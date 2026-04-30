use anyhow::Result;
use backend_rust::{
    runtime::{bootstrap, finding_payload, runner},
    scan::scope_filters,
};
use std::{env, path::Path, process};

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| {
        eprintln!("Usage: backend-runtime-startup <dev|prod|runner|scan-scope|finding-payload>");
        process::exit(1);
    });

    match command.as_str() {
        "dev" | "prod" => bootstrap::run(&command)?,
        "runner" => handle_runner(args)?,
        "scan-scope" => handle_scan_scope(args)?,
        "finding-payload" => handle_finding_payload(args)?,
        _ => {
            eprintln!(
                "Usage: backend-runtime-startup <dev|prod|runner|scan-scope|finding-payload>"
            );
            process::exit(1);
        }
    }

    Ok(())
}

fn handle_finding_payload(mut args: impl Iterator<Item = String>) -> Result<()> {
    let operation = args.next().unwrap_or_else(|| {
        eprintln!("Usage: backend-runtime-startup finding-payload <normalize> --request <path>");
        process::exit(1);
    });
    let operation =
        finding_payload::FindingPayloadOperation::from_cli(&operation).unwrap_or_else(|_| {
            eprintln!(
                "Usage: backend-runtime-startup finding-payload <normalize> --request <path>"
            );
            process::exit(1);
        });

    let flag = args.next().unwrap_or_default();
    let request_path = args.next().unwrap_or_default();
    if flag != "--request" || request_path.is_empty() {
        eprintln!("Usage: backend-runtime-startup finding-payload <normalize> --request <path>");
        process::exit(1);
    }

    println!(
        "{}",
        serde_json::to_string(&finding_payload::execute_from_request_path(
            operation,
            Path::new(&request_path),
        ))?
    );
    Ok(())
}

fn handle_runner(mut args: impl Iterator<Item = String>) -> Result<()> {
    let subcommand = args.next().unwrap_or_else(|| {
        eprintln!("Usage: backend-runtime-startup runner <execute|stop> ...");
        process::exit(1);
    });

    match subcommand.as_str() {
        "execute" => {
            let flag = args.next().unwrap_or_default();
            let spec_path = args.next().unwrap_or_default();
            if flag != "--spec" || spec_path.is_empty() {
                eprintln!("Usage: backend-runtime-startup runner execute --spec <path>");
                process::exit(1);
            }
            let result = runner::execute_spec_file(Path::new(&spec_path))?;
            println!("{}", serde_json::to_string(&result)?);
        }
        "stop" => {
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
            eprintln!("Usage: backend-runtime-startup runner <execute|stop> ...");
            process::exit(1);
        }
    }

    Ok(())
}

fn handle_scan_scope(mut args: impl Iterator<Item = String>) -> Result<()> {
    let operation = args.next().unwrap_or_else(|| {
        eprintln!(
            "Usage: backend-runtime-startup scan-scope <build-patterns|is-ignored|filter-bootstrap-findings> --request <path>"
        );
        process::exit(1);
    });
    let operation = scope_filters::ScopeFilterOperation::from_cli(&operation).unwrap_or_else(|_| {
        eprintln!(
            "Usage: backend-runtime-startup scan-scope <build-patterns|is-ignored|filter-bootstrap-findings> --request <path>"
        );
        process::exit(1);
    });

    let flag = args.next().unwrap_or_default();
    let request_path = args.next().unwrap_or_default();
    if flag != "--request" || request_path.is_empty() {
        eprintln!(
            "Usage: backend-runtime-startup scan-scope <build-patterns|is-ignored|filter-bootstrap-findings> --request <path>"
        );
        process::exit(1);
    }

    println!(
        "{}",
        serde_json::to_string(&scope_filters::execute_from_request_path(
            operation,
            Path::new(&request_path),
        ))?
    );
    Ok(())
}
