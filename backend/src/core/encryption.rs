use anyhow::{anyhow, Context, Result};
use base64::{engine::general_purpose::URL_SAFE, Engine as _};
use fernet::Fernet;
use serde_json::Value;
use sha2::{Digest, Sha256};

pub const SENSITIVE_LLM_FIELDS: &[&str] = &[
    "llmApiKey",
    "geminiApiKey",
    "openaiApiKey",
    "claudeApiKey",
    "qwenApiKey",
    "deepseekApiKey",
    "zhipuApiKey",
    "moonshotApiKey",
    "baiduApiKey",
    "minimaxApiKey",
    "doubaoApiKey",
];

#[derive(Clone)]
pub struct EncryptionService {
    fernet: Fernet,
}

impl EncryptionService {
    pub fn new(secret_key: &str) -> Result<Self> {
        let mut hasher = Sha256::new();
        hasher.update(secret_key.as_bytes());
        let derived = URL_SAFE.encode(hasher.finalize());
        let fernet = Fernet::new(&derived)
            .ok_or_else(|| anyhow!("failed to initialize fernet with derived key"))?;
        Ok(Self { fernet })
    }

    pub fn encrypt(&self, plaintext: &str) -> String {
        if plaintext.is_empty() {
            return String::new();
        }
        self.fernet.encrypt(plaintext.as_bytes())
    }

    pub fn decrypt(&self, ciphertext: &str) -> String {
        if ciphertext.is_empty() {
            return String::new();
        }
        match self.fernet.decrypt(ciphertext) {
            Ok(bytes) => String::from_utf8(bytes).unwrap_or_else(|_| ciphertext.to_string()),
            Err(_) => ciphertext.to_string(),
        }
    }

    pub fn is_encrypted(&self, value: &str) -> bool {
        if value.is_empty() {
            return false;
        }
        self.fernet.decrypt(value).is_ok()
    }
}

pub fn encrypt_sensitive_fields(payload: &Value, secret_key: &str) -> Result<Value> {
    let service = EncryptionService::new(secret_key)?;
    let mut encrypted = payload.clone();
    let object = encrypted
        .as_object_mut()
        .ok_or_else(|| anyhow!("llm_config payload must be a JSON object"))?;

    for field in SENSITIVE_LLM_FIELDS {
        let Some(value) = object.get_mut(*field) else {
            continue;
        };
        let Some(text) = value.as_str() else {
            continue;
        };
        if text.is_empty() || service.is_encrypted(text) {
            continue;
        }
        *value = Value::String(service.encrypt(text));
    }

    Ok(encrypted)
}

pub fn decrypt_sensitive_string(ciphertext: &str, secret_key: &str) -> Result<String> {
    let service = EncryptionService::new(secret_key)
        .with_context(|| "failed to build encryption service for decrypt")?;
    Ok(service.decrypt(ciphertext))
}

#[cfg(test)]
mod tests {
    use super::{decrypt_sensitive_string, encrypt_sensitive_fields, EncryptionService};
    use serde_json::json;

    const SECRET: &str = "test-secret";
    const PYTHON_FERNET_TOKEN: &str =
        "gAAAAABp2d05IaM39nedGPOfiPuCHMcOAKMDLHGMpncWDXWJ_V8Zl8294Nl36B9ecp9ymK0RTdkgJRdCLZAeXcMhyh_LBvzpHA==";

    #[test]
    fn encryption_roundtrip_matches_python_behavior() {
        let service = EncryptionService::new(SECRET).expect("service should build");
        let ciphertext = service.encrypt("sk-test-openai");
        assert_ne!(ciphertext, "sk-test-openai");
        assert_eq!(service.decrypt(&ciphertext), "sk-test-openai");
        assert!(service.is_encrypted(&ciphertext));
        assert_eq!(service.decrypt("plain-text"), "plain-text");
        assert!(!service.is_encrypted("plain-text"));
    }

    #[test]
    fn decrypts_python_generated_fernet_token() {
        let plaintext =
            decrypt_sensitive_string(PYTHON_FERNET_TOKEN, SECRET).expect("decrypt should work");
        assert_eq!(plaintext, "sk-test-openai");
    }

    #[test]
    fn encrypt_sensitive_fields_only_touches_sensitive_llm_keys() {
        let payload = json!({
            "llmApiKey": "sk-test-openai",
            "llmModel": "gpt-5",
            "openaiApiKey": "sk-provider",
            "llmBaseUrl": "https://api.openai.com/v1"
        });

        let encrypted = encrypt_sensitive_fields(&payload, SECRET).expect("encryption should work");
        assert_ne!(encrypted["llmApiKey"], payload["llmApiKey"]);
        assert_ne!(encrypted["openaiApiKey"], payload["openaiApiKey"]);
        assert_eq!(encrypted["llmModel"], payload["llmModel"]);
        assert_eq!(encrypted["llmBaseUrl"], payload["llmBaseUrl"]);
    }
}
