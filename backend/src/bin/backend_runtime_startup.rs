use anyhow::Result;
use backend_rust::runtime::{bootstrap, code2flow, flow_parser, runner};
use std::{env, process};

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let first = args.next().unwrap_or_else(|| {
        eprintln!("Usage: backend-runtime-startup <dev|prod|runner|code2flow|flow-parser>");
        process::exit(1);
    });

    match first.as_str() {
        "dev" | "prod" => bootstrap::run(&first)?,
        "runner" => handle_runner(args)?,
        "code2flow" => handle_code2flow(args)?,
        "flow-parser" => handle_flow_parser(args)?,
        _ => {
            eprintln!("Usage: backend-runtime-startup <dev|prod|runner|code2flow|flow-parser>");
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
            if flag != "--spec" {
                eprintln!("Usage: backend-runtime-startup runner execute --spec <path>");
                process::exit(1);
            }
            let spec_path = args.next().unwrap_or_else(|| {
                eprintln!("Usage: backend-runtime-startup runner execute --spec <path>");
                process::exit(1);
            });
            let result = runner::execute_from_spec_path(spec_path.as_ref());
            println!("{}", serde_json::to_string(&result)?);
        }
        "stop" => {
            let flag = args.next().unwrap_or_default();
            if flag != "--container-id" {
                eprintln!("Usage: backend-runtime-startup runner stop --container-id <id>");
                process::exit(1);
            }
            let container_id = args.next().unwrap_or_else(|| {
                eprintln!("Usage: backend-runtime-startup runner stop --container-id <id>");
                process::exit(1);
            });
            println!(
                "{}",
                serde_json::to_string(&serde_json::json!({
                    "ok": true,
                    "stopped": runner::stop_container(&container_id),
                    "container_id": container_id,
                }))?
            );
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
    if flag != "--request" {
        eprintln!("Usage: backend-runtime-startup code2flow --request <path>");
        process::exit(1);
    }
    let request_path = args.next().unwrap_or_else(|| {
        eprintln!("Usage: backend-runtime-startup code2flow --request <path>");
        process::exit(1);
    });
    println!(
        "{}",
        serde_json::to_string(&code2flow::execute_from_request_path(request_path.as_ref()))?
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
    if flag != "--request" {
        eprintln!(
            "Usage: backend-runtime-startup flow-parser <definitions-batch|locate-enclosing-function> --request <path>"
        );
        process::exit(1);
    }
    let request_path = args.next().unwrap_or_else(|| {
        eprintln!(
            "Usage: backend-runtime-startup flow-parser <definitions-batch|locate-enclosing-function> --request <path>"
        );
        process::exit(1);
    });
    println!(
        "{}",
        serde_json::to_string(&flow_parser::execute_from_request_path(
            operation,
            request_path.as_ref(),
        ))?
    );
    Ok(())
}
