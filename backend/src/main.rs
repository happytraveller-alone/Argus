use anyhow::Result;
use tokio::net::TcpListener;
use tokio::sync::watch;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use backend_rust::{
    app::build_router, bootstrap, config::AppConfig,
    runtime::cubesandbox::{wait_for_active_scans_drain, ShutdownGate}, state::AppState,
};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::from_default_env())
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = AppConfig::from_env()?;
    let state = AppState::from_config(config.clone()).await?;
    // Startup/bootstrap happens before we start accepting requests.
    // It should not do heavy migrations, just minimal checks and clear status reporting.
    bootstrap::run(&state).await?;

    let gate = ShutdownGate::new();
    let (shutdown_tx, _shutdown_rx) = watch::channel::<bool>(false);

    // Pass gate directly — build_router mounts a single Extension(ShutdownGate).
    // No secondary .layer() chain needed; single source of truth.
    let app = build_router(state, gate.clone());
    let listener = TcpListener::bind(config.bind_addr).await?;

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal(shutdown_tx, gate))
        .await?;

    tracing::info!("axum graceful shutdown complete");
    Ok(())
}

async fn shutdown_signal(tx: watch::Sender<bool>, gate: ShutdownGate) {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let sigterm = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let sigterm = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => { tracing::info!("received Ctrl+C, initiating graceful shutdown"); }
        _ = sigterm => { tracing::info!("received SIGTERM, initiating graceful shutdown"); }
    }

    gate.set();
    let _ = tx.send(true);

    // Wait for all in-flight scan tasks to finish their cleanup blocks before
    // allowing axum to exit. Without this, detached tokio::spawn scan futures
    // are aborted at their next .await when the runtime drops, meaning
    // best_effort_delete_sandbox never runs and sandboxes leak.
    // Hard timeout: 60 s — remaining orphans are reaped by reconcile / argus-shutdown.sh.
    wait_for_active_scans_drain(tokio::time::Duration::from_secs(60)).await;
}
