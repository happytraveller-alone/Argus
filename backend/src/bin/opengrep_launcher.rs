use std::{env, os::unix::process::CommandExt, process::Command};

const PROXY_KEYS: &[&str] = &[
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
];

fn main() {
    for key in PROXY_KEYS {
        env::remove_var(key);
    }

    env::set_var("NO_PROXY", "*");
    env::set_var("no_proxy", "*");

    let err = Command::new("/usr/local/bin/opengrep.real")
        .args(env::args_os().skip(1))
        .exec();
    eprintln!("failed to exec /usr/local/bin/opengrep.real: {err}");
    std::process::exit(127);
}
