use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

/// 使用操作系统密码学随机源生成实例凭据，无额外运行时依赖。
pub(crate) fn fill_random(bytes: &mut [u8]) -> std::io::Result<()> {
    #[cfg(windows)]
    {
        #[link(name = "bcrypt")]
        extern "system" {
            fn BCryptGenRandom(algorithm: *mut std::ffi::c_void, buffer: *mut u8, length: u32, flags: u32) -> i32;
        }
        let status = unsafe { BCryptGenRandom(std::ptr::null_mut(), bytes.as_mut_ptr(), bytes.len() as u32, 2) };
        if status < 0 { return Err(std::io::Error::other(format!("BCryptGenRandom failed: {status}"))); }
    }
    #[cfg(not(windows))]
    {
        use std::io::Read;
        std::fs::File::open("/dev/urandom")?.read_exact(bytes)?;
    }
    Ok(())
}

/// 用有限超时探测健康接口并核对实例身份。
pub(crate) async fn check_ready(port: u16, token: &str, instance_id: &str) -> bool {
    let result = tokio::time::timeout(Duration::from_millis(500), async {
        let mut stream = tokio::net::TcpStream::connect(("127.0.0.1", port)).await.ok()?;
        let request = format!("GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n");
        stream.write_all(request.as_bytes()).await.ok()?;
        let mut response = Vec::new();
        stream.take(16384).read_to_end(&mut response).await.ok()?;
        let response = String::from_utf8(response).ok()?;
        let (headers, body) = response.split_once("\r\n\r\n")?;
        if !headers.starts_with("HTTP/1.1 200") { return None; }
        let body: serde_json::Value = serde_json::from_str(body).ok()?;
        Some(body["instance_id"].as_str() == Some(instance_id) && body["status"] == "ok")
    }).await;
    matches!(result, Ok(Some(true)))
}

#[cfg(test)]
mod readiness_tests {
    use super::*;
    use tokio::time::sleep;

    async fn health_server(identity: &str, delay: Duration) -> u16 {
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let identity = identity.to_string();
        tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = [0; 4096];
            let size = stream.read(&mut request).await.unwrap();
            assert!(String::from_utf8_lossy(&request[..size]).contains("Authorization: Bearer test-token"));
            sleep(delay).await;
            let body = format!(r#"{{"status":"ok","instance_id":"{identity}"}}"#);
            let response = format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
            let _ = stream.write_all(response.as_bytes()).await;
        });
        port
    }

    #[tokio::test]
    async fn accepts_only_matching_instance() {
        let port = health_server("expected", Duration::from_millis(20)).await;
        assert!(check_ready(port, "test-token", "expected").await);
        let port = health_server("another-instance", Duration::ZERO).await;
        assert!(!check_ready(port, "test-token", "expected").await);
    }

    #[tokio::test]
    async fn health_probe_has_bounded_timeout() {
        let port = health_server("expected", Duration::from_secs(2)).await;
        let started = std::time::Instant::now();
        assert!(!check_ready(port, "test-token", "expected").await);
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn session_randomness_is_not_reused() {
        let mut first = [0; 48];
        let mut second = [0; 48];
        fill_random(&mut first).unwrap();
        fill_random(&mut second).unwrap();
        assert_ne!(first, second);
        assert_ne!(first, [0; 48]);
    }
}

