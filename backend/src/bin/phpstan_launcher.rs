use std::{env, os::unix::process::CommandExt, process::Command};

fn main() {
    let mut cmd = Command::new("php");
    cmd.arg("/opt/phpstan/phpstan");
    for arg in env::args_os().skip(1) {
        cmd.arg(arg);
    }
    let err = cmd.exec();
    eprintln!("failed to exec php /opt/phpstan/phpstan: {err}");
    std::process::exit(127);
}
