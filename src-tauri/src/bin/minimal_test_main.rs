//! 最小化测试的可执行入口
//! 
//! 运行方式: cargo run --bin minimal_test_main

fn main() {
    println!("========================================");
    println!("TagHive Minimal Test - Directory Creation");
    println!("========================================\n");
    
    // 使用 eprintln 确保输出立即显示
    eprintln!("Starting minimal tests...\n");
    
    taghive::minimal_test::run_all_tests();
}
