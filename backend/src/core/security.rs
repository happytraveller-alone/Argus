use std::time::Duration;

use anyhow::{anyhow, Result};
use bcrypt::{hash, verify, DEFAULT_COST};
use jsonwebtoken::{decode, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

use crate::config::AppConfig;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AccessTokenClaims {
    pub exp: usize,
    pub sub: String,
}

pub fn create_access_token(
    subject: impl ToString,
    config: &AppConfig,
    expires_delta: Option<Duration>,
) -> Result<String> {
    let expires = expires_delta.unwrap_or_else(|| {
        Duration::from_secs((config.access_token_expire_minutes.max(1) as u64) * 60)
    });
    let exp = OffsetDateTime::now_utc() + time::Duration::seconds(expires.as_secs() as i64);
    let claims = AccessTokenClaims {
        exp: exp.unix_timestamp() as usize,
        sub: subject.to_string(),
    };
    let algorithm = parse_algorithm(&config.algorithm)?;
    let mut header = Header::new(algorithm);
    header.typ = Some("JWT".to_string());
    encode(
        &header,
        &claims,
        &EncodingKey::from_secret(config.secret_key.as_bytes()),
    )
    .map_err(Into::into)
}

pub fn decode_access_token(token: &str, config: &AppConfig) -> Result<AccessTokenClaims> {
    let algorithm = parse_algorithm(&config.algorithm)?;
    let mut validation = Validation::new(algorithm);
    validation.validate_exp = true;
    let data = decode::<AccessTokenClaims>(
        token,
        &DecodingKey::from_secret(config.secret_key.as_bytes()),
        &validation,
    )?;
    Ok(data.claims)
}

pub fn verify_password(plain_password: &str, hashed_password: &str) -> bool {
    verify(plain_password, hashed_password).unwrap_or(false)
}

pub fn get_password_hash(password: &str) -> Result<String> {
    hash(password, DEFAULT_COST).map_err(Into::into)
}

fn parse_algorithm(value: &str) -> Result<Algorithm> {
    match value.trim().to_ascii_uppercase().as_str() {
        "" | "HS256" => Ok(Algorithm::HS256),
        "HS384" => Ok(Algorithm::HS384),
        "HS512" => Ok(Algorithm::HS512),
        other => Err(anyhow!("unsupported jwt algorithm: {other}")),
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::{create_access_token, decode_access_token, get_password_hash, verify_password};
    use crate::config::AppConfig;

    const PYTHON_GENERATED_JWT: &str =
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE4OTM0NTYwMDAsInN1YiI6ImRlbW8tdXNlciJ9.eepyoq4hV8WE-WCj-_Xl6v0JxPms_XTPgA3iE6nTy3M";
    const PYTHON_BCRYPT_HASH: &str = "$2b$12$Avv3EVtio0wVYVLZqmSypuNZcsjcYI4Xy7xBaCf2utgUmVtRopaca";

    fn test_config() -> AppConfig {
        let mut config = AppConfig::for_tests();
        config.secret_key = "test-secret".to_string();
        config.algorithm = "HS256".to_string();
        config.access_token_expire_minutes = 60;
        config
    }

    #[test]
    fn creates_and_decodes_access_token() {
        let config = test_config();
        let token = create_access_token("demo-user", &config, Some(Duration::from_secs(300)))
            .expect("token should be created");
        let claims = decode_access_token(&token, &config).expect("token should decode");
        assert_eq!(claims.sub, "demo-user");
        assert!(claims.exp > 0);
    }

    #[test]
    fn decodes_python_generated_jwt() {
        let config = test_config();
        let claims =
            decode_access_token(PYTHON_GENERATED_JWT, &config).expect("python token should decode");
        assert_eq!(claims.sub, "demo-user");
        assert_eq!(claims.exp, 1_893_456_000);
    }

    #[test]
    fn password_hash_roundtrip_and_python_hash_compat() {
        let hashed = get_password_hash("secret").expect("hash should succeed");
        assert_ne!(hashed, "secret");
        assert!(verify_password("secret", &hashed));
        assert!(!verify_password("not-secret", &hashed));
        assert!(verify_password("secret", PYTHON_BCRYPT_HASH));
    }
}
