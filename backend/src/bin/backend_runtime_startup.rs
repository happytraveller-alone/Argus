use anyhow::Result;
use backend_rust::{
    runtime::{bootstrap, code2flow, flow_parser, runner},
    scan::scope_filters,
};
use std::{env, path::Path, process};

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| {
        eprintln!(
            "Usage: backend-runtime-startup <dev|prod|runner|code2flow|flow-parser|scan-scope>"
        );
        process::exit(1);
    });

    match command.as_str() {
        "dev" | "prod" => bootstrap::run(&command)?,
        "runner" => handle_runner(args)?,
        "code2flow" => handle_code2flow(args)?,
        "flow-parser" => handle_flow_parser(args)?,
        "scan-scope" => handle_scan_scope(args)?,
        _ => {
            eprintln!(
                "Usage: backend-runtime-startup <dev|prod|runner|code2flow|flow-parser|scan-scope>"
            );
            process::exit(1);
        }
    }

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

fn handle_code2flow(mut args: impl Iterator<Item = String>) -> Result<()> {
    let flag = args.next().unwrap_or_default();
    let request_path = args.next().unwrap_or_default();
    if flag != "--request" || request_path.is_empty() {
        eprintln!("Usage: backend-runtime-startup code2flow --request <path>");
        process::exit(1);
    }

    println!(
        "{}",
        serde_json::to_string(&code2flow::execute_from_request_path(Path::new(
            &request_path
        )))?
    );
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

fn handle_flow_parser(mut args: impl Iterator<Item = String>) -> Result<()> {
    let operation = args.next().unwrap_or_else(|| {
        eprintln!(
            "Usage: backend-runtime-startup flow-parser <definitions-batch|locate-enclosing-function> --request <path>"
        );
        process::exit(1);
    });
    let operation = flow_parser::FlowParserOperation::from_cli(&operation).unwrap_or_else(|_| {
        eprintln!(
            "Usage: backend-runtime-startup flow-parser <definitions-batch|locate-enclosing-function> --request <path>"
        );
        process::exit(1);
    });

    let flag = args.next().unwrap_or_default();
    let request_path = args.next().unwrap_or_default();
    if flag != "--request" || request_path.is_empty() {
        eprintln!(
            "Usage: backend-runtime-startup flow-parser <definitions-batch|locate-enclosing-function> --request <path>"
        );
        process::exit(1);
    }

    println!(
        "{}",
        serde_json::to_string(&flow_parser::execute_from_request_path(
            operation,
            Path::new(&request_path),
        ))?
    );
    Ok(())
}
