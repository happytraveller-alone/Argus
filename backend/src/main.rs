use anyhow::Result;
use tokio::net::TcpListener;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use backend_rust::{app::build_router, bootstrap, config::AppConfig, state::AppState};

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
    let app = build_router(state);
    let listener = TcpListener::bind(config.bind_addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
